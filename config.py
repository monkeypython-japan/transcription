import tomllib
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "config.toml"

# config.toml が無い・キーが無い場合のデフォルト値
_DEFAULTS = {
    "models": {
        "whisper": "mlx-community/whisper-large-v3-mlx",
        # 音声認識エンジンの選択("parakeet" | "whisper")
        "asr_engine": "parakeet",
        "parakeet": "mlx-community/parakeet-tdt-0.6b-v3",
        # Parakeet が対応する言語(ISO 639-1)。日本語・中国語・韓国語は非対応
        "parakeet_languages": [
            "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr", "hr", "hu", "it",
            "lt", "lv", "mt", "nl", "pl", "pt", "ro", "ru", "sk", "sl", "sv", "uk",
        ],
        "translation_multilingual": "Helsinki-NLP/opus-mt-mul-en",
        "translation_nllb": "facebook/nllb-200-distilled-600M",
        # 英語への翻訳で言語別モデルを優先する言語（ISO 639-1）
        "marian_source_langs": [
            "fr", "de", "es", "it", "nl", "pt", "ru", "pl", "sv", "da",
            "fi", "hu", "cs", "tr", "ar", "vi", "zh", "ja", "ko",
        ],
    },
    "filter": {
        "credit_patterns": [
            r"sous-titrage",
            r"subtitl(e|ing|ed) by",
            r"sync(ed|hronized)? (by|and corrected)",
            r"translated by",
            r"ripped by",
            r"encoded by",
            r"www\.",
            r"opensubtitles",
            r"subscene",
            r"addic7ed",
            r"©",
            r"transcript\s+\w",
        ],
    },
}


def _load() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    return {}


_config = _load()


def get(section: str, key: str):
    """config.toml の値を返す。無ければデフォルト値"""
    try:
        return _config[section][key]
    except KeyError:
        return _DEFAULTS[section][key]
