import re

from progress import tick

import config
from asr_whisper import _segments_to_srt

PARAKEET_MODEL = config.get("models", "parakeet")

# 末尾句読点トークンの遅延許容(秒)。これを超える遅延がある場合、
# セグメント終端の計算からそのトークンを除外する
PUNCT_GAP_MAX = 1.0

# トークン間ギャップでセグメントを分割する閾値(秒)
TOKEN_GAP_MAX = 2.0

# 1セグメントの最大表示時間(秒)。これを超える場合は息継ぎ位置で分割する。
# Parakeet は長い連続した一文をそのまま1セグメントとして出力するため
# (実測: ナレーションで24秒のセグメント)、字幕として成立する長さに割る
MAX_SEGMENT_DURATION = 7.0

# 分割点を探す範囲。セグメント全体の先頭/末尾からこの割合を除いた中央部分から
# 分割点を選ぶ(極端に短い断片ができるのを防ぐ)
SPLIT_SEARCH_MARGIN = 0.25

# 句読点のみで構成されるトークンの判定用正規表現
_PUNCT_ONLY_RE = re.compile(r"^[\s\.,!?;:、。！？…‥·・]+$")

# プロセス内でモデルを1回だけロードしてキャッシュする
# (parakeet-mlx issue #34: 反復ロード時の Metal メモリ蓄積を避けるため)
_model = None


def _get_model():
    global _model
    if _model is None:
        from parakeet_mlx import from_pretrained

        print(f"Parakeet モデルを読み込み中: {PARAKEET_MODEL}")
        _model = from_pretrained(PARAKEET_MODEL)
    return _model


def _is_punct_only(text: str) -> bool:
    """トークンのテキストが句読点のみで構成されるか判定する"""
    return bool(text) and bool(_PUNCT_ONLY_RE.match(text))


def _split_by_gap(tokens: list) -> list[list]:
    """隣接トークン間のギャップが TOKEN_GAP_MAX を超える箇所でトークン列を分割する"""
    groups = [[]]
    for i, tok in enumerate(tokens):
        if i > 0 and tok.start - tokens[i - 1].end > TOKEN_GAP_MAX:
            groups.append([])
        groups[-1].append(tok)
    return [g for g in groups if g]


def _split_by_duration(tokens: list) -> list[list]:
    """継続時間が MAX_SEGMENT_DURATION を超えるトークン列を再帰的に2分割する

    分割点はセグメント中央部(先頭・末尾から SPLIT_SEARCH_MARGIN を除いた範囲)の
    うち、トークン間ギャップが最も大きい位置(息継ぎ)を選ぶ。ギャップが同じ場合は
    中央に最も近い位置を選ぶ。連続発話ではギャップがほぼ 0 のため、範囲を中央に
    限定しないと 1 トークンだけの断片が量産されてしまう。
    """
    if len(tokens) < 2:
        return [tokens]

    start = tokens[0].start
    end = tokens[-1].end
    if end - start <= MAX_SEGMENT_DURATION:
        return [tokens]

    span = end - start
    lo = start + span * SPLIT_SEARCH_MARGIN
    hi = end - span * SPLIT_SEARCH_MARGIN
    mid = (start + end) / 2

    best_key = None
    best_i = None
    for i in range(1, len(tokens)):
        boundary = tokens[i].start
        if not (lo <= boundary <= hi):
            continue
        # ギャップの大きさを優先し、同じなら中央に近い方を選ぶ
        key = (tokens[i].start - tokens[i - 1].end, -abs(boundary - mid))
        if best_key is None or key > best_key:
            best_key = key
            best_i = i

    if best_i is None:
        # 中央部に境界が無い場合は、中央に最も近い境界で分割する
        best_i = min(range(1, len(tokens)), key=lambda i: abs(tokens[i].start - mid))

    return _split_by_duration(tokens[:best_i]) + _split_by_duration(tokens[best_i:])


def _split_trailing_punctuation(tokens: list) -> tuple[list, list]:
    """末尾の句読点のみのトークン列を分離する

    parakeet-mlx は文末の句読点トークンで sentence を区切る仕様のため、句読点は
    常に sentence の末尾に来る。その句読点が直前の実トークン終端から
    PUNCT_GAP_MAX を超えて遅延している場合、(コアトークン, 遅延した句読点トークン)
    に分離する。遅延が無ければ分離せず (tokens, []) を返す。
    """
    i = len(tokens) - 1
    while i >= 0 and _is_punct_only(tokens[i].text):
        i -= 1

    if i < 0 or i == len(tokens) - 1:
        # 全トークンが句読点、または末尾に句読点トークンが無い場合は分離しない
        return tokens, []

    gap = tokens[i + 1].start - tokens[i].end
    if gap > PUNCT_GAP_MAX:
        return tokens[: i + 1], tokens[i + 1 :]
    return tokens, []


def _sentences_to_segments(sentences: list) -> list[dict]:
    """Parakeet の AlignedSentence 一覧を、補正済みの {text, start, end} セグメント列に変換する

    1. 末尾の句読点トークンが大きく遅延している場合は分離し、終端時刻の計算から除外する
       (parakeet-mlx の AlignedSentence.end は tokens[-1].end から算出される仕様のため、
       句読点トークンだけが大きく遅れて出力されるとセグメント終端が不当に引き伸ばされる)
    2. 分離した句読点はテキストとしては末尾セグメントに残す(内容は失わない)
    3. 残りのトークン列は、隣接トークン間のギャップが TOKEN_GAP_MAX を超える箇所で
       セグメントを分割する(保険。句読点なしで長時間の無音を挟む場合に対応)
    4. さらに MAX_SEGMENT_DURATION を超えるセグメントを息継ぎ位置で再帰的に分割する
       (長い連続した一文が1枚の字幕として長時間表示され続けるのを防ぐ)
    """
    segments = []
    for sentence in sentences:
        core_tokens, tail_tokens = _split_trailing_punctuation(sentence.tokens)
        groups = [
            group
            for gap_group in _split_by_gap(core_tokens)
            for group in _split_by_duration(gap_group)
        ]
        tail_text = "".join(t.text for t in tail_tokens)

        for idx, group in enumerate(groups):
            text = "".join(t.text for t in group)
            if idx == len(groups) - 1:
                text += tail_text
            start = group[0].start
            end = group[-1].end
            segments.append({"text": text.strip(), "start": start, "end": end})
    return segments


def transcribe(video_path: str, language: str | None = None) -> tuple[str, str]:
    """parakeet-mlx で音声認識を行い (SRT テキスト, 言語コード) を返す。

    Parakeet に言語自動検出機能は無いため、language は呼び出し側から渡された
    値をそのまま返す(呼び出し元で対応言語であることを確認済みの前提)。
    """
    import mlx.core as mx

    model = _get_model()

    print("音声認識中（Apple GPU 使用、Parakeet）", end="", flush=True)
    # chunk_duration 未指定(既定 None)だと長尺動画で OOM するため必ず指定する
    result = model.transcribe(video_path, chunk_duration=120.0, overlap_duration=15.0)
    tick()

    segments = _sentences_to_segments(result.sentences)
    srt_text = _segments_to_srt(segments)

    # 複数ファイル処理時の Metal メモリ蓄積対策(parakeet-mlx issue #34)
    mx.clear_cache()

    return srt_text, language
