"""音声認識ディスパッチャ・各エンジンのテスト。

モデルの実ロードは一切行わない（すべてモック）。
"""
from unittest.mock import patch

from parakeet_mlx.alignment import AlignedSentence, AlignedToken

import asr_parakeet
import asr_whisper
import config
import transcribe as dispatcher
from asr_parakeet import _sentences_to_segments


# --- 1. Whisper 経路: 移設で挙動が壊れていないことの保証 --------------------

FAKE_WHISPER_RESULT = {
    "language": "en",
    "segments": [
        {"text": " Hello world", "start": 0.0, "end": 2.0},
        {"text": "", "start": 2.0, "end": 3.0},  # 空文字は除外される
        {"text": " Zero duration", "start": 3.0, "end": 3.0},  # end<=start は除外される
        {"text": " Third line", "start": 4.0, "end": 6.0},
    ],
}


def test_whisper_transcribe_builds_srt():
    with patch("mlx_whisper.transcribe", return_value=FAKE_WHISPER_RESULT) as mock_transcribe:
        srt_text, lang = asr_whisper.transcribe("dummy.mp4", language="en")

    assert lang == "en"
    assert "Hello world" in srt_text
    assert "Third line" in srt_text
    assert "Zero duration" not in srt_text
    assert srt_text.count("-->") == 2

    mock_transcribe.assert_called_once()
    _, kwargs = mock_transcribe.call_args
    assert kwargs["language"] == "en"
    assert kwargs["word_timestamps"] is True
    assert kwargs["no_speech_threshold"] == 0.6
    assert kwargs["condition_on_previous_text"] is False
    assert kwargs["hallucination_silence_threshold"] == 2.0


# --- 2. Parakeet: 末尾句読点の遅延補正 --------------------------------------

def test_trailing_punctuation_delay_is_trimmed():
    """実測されたバグの再現: 末尾の '.' だけが17秒以上遅れて出力される場合、
    セグメント終端は実発話の終わり(直前の実トークンの終端)に切り詰められる"""
    tokens = [
        AlignedToken(id=1, text="It's", start=125.0, duration=1.0),    # end=126.0
        AlignedToken(id=2, text=" about", start=126.0, duration=1.0),  # end=127.0
        AlignedToken(id=3, text=" time", start=127.0, duration=3.28),  # end=130.28
        AlignedToken(id=4, text=".", start=147.88, duration=0.32),     # end=148.20 (17.6秒後)
    ]
    sentence = AlignedSentence(text="It's about time.", tokens=tokens)

    segments = _sentences_to_segments([sentence])

    assert len(segments) == 1
    assert segments[0]["start"] == 125.0
    assert segments[0]["end"] == 130.28
    assert segments[0]["text"] == "It's about time."


def test_trailing_punctuation_within_threshold_is_kept():
    """句読点の遅延が閾値(PUNCT_GAP_MAX=1.0秒)以内なら通常通り末尾トークンの終端を使う"""
    tokens = [
        AlignedToken(id=1, text="Hello", start=0.0, duration=1.0),   # end=1.0
        AlignedToken(id=2, text=".", start=1.2, duration=0.1),       # end=1.3 (0.2秒後)
    ]
    sentence = AlignedSentence(text="Hello.", tokens=tokens)

    segments = _sentences_to_segments([sentence])

    assert len(segments) == 1
    assert segments[0]["end"] == 1.3


# --- 3. Parakeet: トークン間ギャップでのセグメント分割 -----------------------

def test_large_token_gap_splits_segment():
    """隣接トークン間のギャップが TOKEN_GAP_MAX(2.0秒)を超える箇所でセグメントを分割する"""
    tokens = [
        AlignedToken(id=1, text="Hello", start=0.0, duration=1.0),    # end=1.0
        AlignedToken(id=2, text=" world.", start=1.0, duration=1.0),  # end=2.0
        AlignedToken(id=3, text="Goodbye", start=10.0, duration=1.0), # gap=8.0秒 > 閾値
        AlignedToken(id=4, text=" now.", start=11.0, duration=1.0),   # end=12.0
    ]
    sentence = AlignedSentence(text="Hello world.Goodbye now.", tokens=tokens)

    segments = _sentences_to_segments([sentence])

    assert len(segments) == 2
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 2.0
    assert segments[0]["text"] == "Hello world."
    assert segments[1]["start"] == 10.0
    assert segments[1]["end"] == 12.0
    assert segments[1]["text"] == "Goodbye now."


# --- 3.5 Parakeet: 最大表示時間による分割 -----------------------------------

def _contiguous_tokens(count: int, duration: float, start: float = 0.0) -> list:
    """隙間なく連続する疑似トークン列を作る（連続発話の再現）"""
    return [
        AlignedToken(id=i, text=f" w{i}", start=start + i * duration, duration=duration)
        for i in range(count)
    ]


def test_long_continuous_sentence_is_split_by_duration():
    """実測されたケースの再現: 息継ぎのない長い一文（24秒）がそのまま1セグメントに
    ならず、MAX_SEGMENT_DURATION 以下の複数セグメントに分割される"""
    tokens = _contiguous_tokens(40, 0.5)  # 0.0〜20.0秒、ギャップは全て0
    sentence = AlignedSentence(text="long", tokens=tokens)

    segments = _sentences_to_segments([sentence])

    assert len(segments) > 1
    for seg in segments:
        assert seg["end"] - seg["start"] <= asr_parakeet.MAX_SEGMENT_DURATION
    # 全体の範囲は保たれる
    assert segments[0]["start"] == 0.0
    assert segments[-1]["end"] == 20.0


def test_duration_split_prefers_largest_gap():
    """分割点は中央付近で最もギャップ（息継ぎ）が大きい位置が選ばれる"""
    tokens = _contiguous_tokens(6, 0.8)  # 0.0〜4.8秒
    # 5.3秒から後半を開始（0.5秒のギャップ。TOKEN_GAP_MAX=2.0 未満なのでギャップ分割はされない）
    tokens += [
        AlignedToken(id=100 + i, text=f" x{i}", start=5.3 + i * 0.8, duration=0.8)
        for i in range(6)
    ]
    sentence = AlignedSentence(text="gap", tokens=tokens)

    segments = _sentences_to_segments([sentence])

    assert len(segments) == 2
    assert segments[0]["end"] == 4.8
    assert segments[1]["start"] == 5.3


def test_single_token_longer_than_max_is_not_split():
    """トークンが1個しかない場合は分割しようがないのでそのまま出す（無限再帰の防止）"""
    tokens = [AlignedToken(id=1, text="Hmm", start=0.0, duration=10.0)]
    sentence = AlignedSentence(text="Hmm", tokens=tokens)

    segments = _sentences_to_segments([sentence])

    assert len(segments) == 1
    assert segments[0]["end"] - segments[0]["start"] == 10.0


def test_short_sentence_is_not_split():
    """MAX_SEGMENT_DURATION 以下のセグメントは分割されない"""
    tokens = _contiguous_tokens(6, 0.5)  # 3.0秒
    sentence = AlignedSentence(text="short", tokens=tokens)

    segments = _sentences_to_segments([sentence])

    assert len(segments) == 1


def test_trailing_punctuation_attaches_to_last_segment_after_split():
    """分割が起きた場合でも、分離した末尾句読点は最終セグメントのテキストに残り、
    終端時刻は引き伸ばされない"""
    tokens = _contiguous_tokens(40, 0.5)  # 0.0〜20.0秒
    tokens.append(AlignedToken(id=999, text=".", start=40.0, duration=0.2))  # 20秒後に遅延
    sentence = AlignedSentence(text="long.", tokens=tokens)

    segments = _sentences_to_segments([sentence])

    assert len(segments) > 1
    assert segments[-1]["text"].endswith(".")
    assert segments[-1]["end"] == 20.0  # 遅延した句読点に引きずられない


# --- 4. エンジン振り分け ------------------------------------------------

def _force_engine(monkeypatch, engine):
    """asr_engine 設定値を既定に関わらず強制する(既定値変更の影響を受けないテスト用)"""
    def fake_get(section, key):
        if section == "models" and key == "asr_engine":
            return engine
        return config._DEFAULTS[section][key]

    monkeypatch.setattr(config, "get", fake_get)


def test_dispatch_uses_parakeet_for_supported_language(monkeypatch, capsys):
    _force_engine(monkeypatch, "parakeet")

    with patch.object(asr_parakeet, "transcribe", return_value=("srt", "fr")) as mock_p, \
         patch.object(asr_whisper, "transcribe") as mock_w:
        result = dispatcher.transcribe("dummy.mp4", language="fr")

    assert result == ("srt", "fr")
    mock_p.assert_called_once_with("dummy.mp4", language="fr")
    mock_w.assert_not_called()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[transcription] asr_engine=parakeet" in captured.err


def test_dispatch_uses_whisper_for_unsupported_language(monkeypatch, capsys):
    """asr_engine="parakeet" 設定時、Parakeet 非対応言語は Whisper にフォールバックする"""
    _force_engine(monkeypatch, "parakeet")

    with patch.object(asr_parakeet, "transcribe") as mock_p, \
         patch.object(asr_whisper, "transcribe", return_value=("srt", "ja")) as mock_w:
        result = dispatcher.transcribe("dummy.mp4", language="ja")

    assert result == ("srt", "ja")
    mock_w.assert_called_once_with("dummy.mp4", language="ja")
    mock_p.assert_not_called()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[transcription] asr_engine=whisper" in captured.err


def test_dispatch_uses_whisper_when_language_unspecified(monkeypatch, capsys):
    """asr_engine="parakeet" 設定時も、言語未指定なら Whisper を使う
    (Parakeet に言語自動検出機能が無いため)"""
    _force_engine(monkeypatch, "parakeet")

    with patch.object(asr_parakeet, "transcribe") as mock_p, \
         patch.object(asr_whisper, "transcribe", return_value=("srt", "en")) as mock_w:
        result = dispatcher.transcribe("dummy.mp4", language=None)

    assert result == ("srt", "en")
    mock_w.assert_called_once_with("dummy.mp4", language=None)
    mock_p.assert_not_called()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[transcription] asr_engine=whisper" in captured.err


def test_dispatch_forced_whisper_engine_ignores_supported_language(monkeypatch, capsys):
    """asr_engine="whisper" のときは Parakeet 対応言語を指定しても常に Whisper を使う"""
    _force_engine(monkeypatch, "whisper")

    with patch.object(asr_parakeet, "transcribe") as mock_p, \
         patch.object(asr_whisper, "transcribe", return_value=("srt", "fr")) as mock_w:
        result = dispatcher.transcribe("dummy.mp4", language="fr")

    assert result == ("srt", "fr")
    mock_w.assert_called_once_with("dummy.mp4", language="fr")
    mock_p.assert_not_called()

    captured = capsys.readouterr()
    assert captured.out == ""
    # asr_engine="whisper" 設定時は Parakeet 対応言語でもフォールバックではなく
    # 常時 whisper。実際に呼ばれたのが whisper であることが出力に反映される。
    assert "[transcription] asr_engine=whisper" in captured.err


# --- 4.5 エンジン振り分け: 標準エラー出力フォーマットの厳密検証 -------------

def test_dispatch_logs_exact_stderr_format_for_parakeet(monkeypatch, capsys):
    """呼び出し元(st)がパースする固定フォーマットの行そのものを厳密検証する。
    標準出力には一切書き込まれないこと(既存の出力パース互換のため)も確認する。"""
    _force_engine(monkeypatch, "parakeet")

    with patch.object(asr_parakeet, "transcribe", return_value=("srt", "en")), \
         patch.object(asr_whisper, "transcribe"):
        dispatcher.transcribe("dummy.mp4", language="en")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "[transcription] asr_engine=parakeet\n"


def test_dispatch_logs_exact_stderr_format_for_whisper_fallback(capsys):
    """非対応言語(ja)指定時、asr_engine 設定は "parakeet" のままでも実際に
    使われたのは whisper であることが出力に反映される(フォールバック後の実値)。"""
    with patch.object(asr_parakeet, "transcribe"), \
         patch.object(asr_whisper, "transcribe", return_value=("srt", "ja")):
        dispatcher.transcribe("dummy.mp4", language="ja")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "[transcription] asr_engine=whisper\n"


# --- 5. 戻り値契約: いずれの経路でも (str, str) が返る ----------------------

def test_return_type_contract_whisper_path():
    with patch.object(asr_whisper, "transcribe", return_value=("srt text", "ja")):
        result = dispatcher.transcribe("dummy.mp4", language="ja")

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], str)


def test_return_type_contract_parakeet_path(monkeypatch):
    _force_engine(monkeypatch, "parakeet")

    with patch.object(asr_parakeet, "transcribe", return_value=("srt text", "fr")):
        result = dispatcher.transcribe("dummy.mp4", language="fr")

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], str)
