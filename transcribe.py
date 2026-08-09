import sys

import config

import asr_parakeet
import asr_whisper


def _log_actual_engine(actual_engine: str) -> None:
    """実際に使用したエンジン名を標準エラー出力に1行出力する。

    呼び出し元(subtitle-translation 等)がサブプロセスの標準エラー出力から
    この行を拾い、ログに実際のエンジン名を反映するためのインターフェース。
    標準出力(SRT本体・進捗表示)には一切影響しない。
    """
    print(f"[transcription] asr_engine={actual_engine}", file=sys.stderr, flush=True)


def transcribe(video_path: str, language: str | None = None) -> tuple[str, str]:
    """音声認識を行い (SRT テキスト, 言語コード) を返す。

    language を指定すると自動言語検出をスキップしてその言語でデコードする。
    無音区間等でのハルシネーションにより言語が誤検出される実例
    (無音中の空耳クレジット行につられ、実際は英語音声の動画がロシア語と
    誤判定された等)があるため、呼び出し側で音声言語が分かっている場合は
    指定を推奨する。

    エンジン振り分け(config.toml の asr_engine で切替):
    - "whisper": 常に mlx-whisper を使用する(旧挙動)
    - "parakeet"(既定): 言語が Parakeet 対応言語(欧州25言語)として指定されて
      いれば parakeet-mlx を使用する。それ以外(日本語・中国語・韓国語等の
      非対応言語を指定、または言語未指定)は mlx-whisper にフォールバックする。
      Parakeet には言語自動検出機能が無いため、言語未指定時に「Parakeet対応
      言語かどうか」を判定する安価な手段が無い。mlx_whisper にも言語判定のみを
      安価に行う公開 API は無い(内部関数 model.detect_language はモデルの
      直接ロードや mel スペクトログラム計算などの非公開の内部処理を必要とし、
      結局 whisper 側の transcribe とほぼ同じコストがかかる)ため、言語未指定
      時は二度手間を避けて Whisper で通常認識しその結果をそのまま返す。

    実際に使用したエンジン名を標準エラー出力に
    `[transcription] asr_engine=parakeet` / `[transcription] asr_engine=whisper`
    の形式で1行出力する(呼び出し元がログに実エンジン名を反映するためのインター
    フェース。フォールバック後の実際の値であり engine 変数の値そのものではない)。
    """
    engine = config.get("models", "asr_engine")

    if engine == "whisper":
        _log_actual_engine("whisper")
        return asr_whisper.transcribe(video_path, language=language)

    # engine == "parakeet"
    if language is not None:
        parakeet_languages = config.get("models", "parakeet_languages")
        if language in parakeet_languages:
            _log_actual_engine("parakeet")
            return asr_parakeet.transcribe(video_path, language=language)
        _log_actual_engine("whisper")
        return asr_whisper.transcribe(video_path, language=language)

    # 言語未指定: Whisper で通常認識し、その結果をそのまま返す
    _log_actual_engine("whisper")
    return asr_whisper.transcribe(video_path, language=None)
