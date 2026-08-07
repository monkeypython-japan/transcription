from progress import tick

import config

MLX_MODEL = config.get("models", "whisper")


def _segments_to_srt(segments: list) -> str:
    """Whisper セグメントを SRT テキストに変換"""
    def fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    idx = 0
    for seg in segments:
        text = seg["text"].strip()
        if not text or seg["end"] <= seg["start"]:
            continue
        idx += 1
        start = fmt_time(seg["start"])
        end = fmt_time(seg["end"])
        lines.append(f"{idx}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def transcribe(video_path: str, language: str | None = None) -> tuple[str, str]:
    """mlx-whisper で音声認識を行い (SRT テキスト, 言語コード) を返す。

    language を指定すると自動言語検出をスキップしてその言語でデコードする。
    無音区間等でのハルシネーションにより言語が誤検出される実例
    (無音中の空耳クレジット行につられ、実際は英語音声の動画がロシア語と
    誤判定された等)があるため、呼び出し側で音声言語が分かっている場合は
    指定を推奨する。
    """
    import mlx_whisper

    print("音声認識中（Apple GPU 使用）", end="", flush=True)
    result = mlx_whisper.transcribe(
        video_path,
        path_or_hf_repo=MLX_MODEL,
        verbose=False,
        word_timestamps=True,
        language=language,
        # 無音区間のハルシネーション抑制
        no_speech_threshold=0.6,
        condition_on_previous_text=False,
        initial_prompt="",
        # 2秒以上の無音区間はデコード自体をスキップする(word_timestamps前提)
        hallucination_silence_threshold=2.0,
    )
    tick()

    lang = result.get("language", "en")
    srt_text = _segments_to_srt(result["segments"])
    return srt_text, lang
