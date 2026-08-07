#!/usr/bin/env python3
import argparse
import sys
import os
from pathlib import Path

from subtitle import get_subtitle_tracks, print_tracks, extract_srt, find_track_by_lang, is_image_subtitle
from translate import translate_srt
from transcribe import transcribe
from output import build_output_path, write_srt
from srt_utils import parse_srt_blocks, build_srt
from filter import filter_blocks


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".m4v", ".avi", ".mov", ".webm", ".ts", ".wmv"}

EPILOG = """動作:
  字幕トラックあり
    言語コード省略  → 字幕トラック一覧を表示して終了
    言語コード指定  → 指定言語の字幕をそのまま SRT として出力
    --translate 付き → 指定言語の字幕を翻訳して SRT として出力（既定は英語、--translate=ja で日本語）
    --transcribe 付き → 字幕トラックを無視して Whisper で音声認識

  字幕トラックなし
    言語コード省略  → Whisper で音声認識し、検出した言語で SRT を出力（翻訳なし）
    言語コード指定  → その言語を指定してWhisperで音声認識(自動検出はスキップ)。
                     無音区間等での言語誤検出対策として、音声言語が分かっている
                     場合は指定を推奨

出力ファイル:
  {動画ファイルと同じフォルダ}/{ベース名}.{言語コード}.srt

例:
  transcription.py "movie.mkv"
  transcription.py "movie.mkv" fr
  transcription.py "movie.mkv" fr --translate
  transcription.py "movie.mkv" fr --translate=ja
  transcription.py "movie.mkv" --transcribe
  transcription.py "season1/" en --translate=ja
  transcription.py "ep1.mkv" "ep2.mkv" en
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcription.py",
        description="動画ファイルからオフラインで SRT 字幕ファイルを生成する",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "inputs", nargs="+", metavar="<動画ファイル|フォルダ|言語コード>",
        help="動画ファイル・フォルダ（複数指定可）。2〜3文字の英字は字幕トラックの言語コードとして解釈",
    )
    parser.add_argument(
        "--translate", nargs="?", const="en", default=None, metavar="言語",
        help="字幕を指定言語に翻訳して出力（省略時 en。--translate=ja / --translate ja）",
    )
    parser.add_argument(
        "--transcribe", action="store_true",
        help="字幕トラックを無視して Whisper で音声認識を強制実行",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="既存の SRT ファイルを確認せずに上書きする",
    )
    return parser


def confirm_overwrite(path: str, force: bool) -> bool:
    """出力先が既存の場合に上書き確認する。上書きしてよければ True"""
    if force or not os.path.exists(path):
        return True
    answer = input(f"出力先が既に存在します: {path}\n上書きしますか? [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def collect_videos(paths: list[str]) -> list[str]:
    """ファイル・フォルダの指定から動画ファイル一覧を組み立てる"""
    videos = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            videos.append(str(path))
        elif path.is_dir():
            found = sorted(
                str(f) for f in path.rglob("*")
                if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
            )
            if not found:
                print(f"警告: フォルダに動画ファイルが見つかりません: {p}")
            videos.extend(found)
        else:
            print(f"エラー: ファイルが見つかりません: {p}")
            sys.exit(1)
    return videos


def process_video(video_path: str, lang_code: str | None,
                  translate_target: str | None, force_transcribe: bool,
                  force_overwrite: bool = False) -> bool:
    """1本の動画を処理する。成功なら True"""
    # 字幕トラックを確認
    print("字幕トラックを確認中...", end="", flush=True)
    try:
        tracks = get_subtitle_tracks(video_path)
    except RuntimeError as e:
        print(f"\nエラー: {e}")
        return False
    print(" 完了")

    if tracks and not force_transcribe:
        # 字幕ありの動画
        if lang_code is None:
            # 言語コード未指定 → トラック一覧を表示するのみ
            print_tracks(tracks)
            print("\n言語コードを指定して再実行してください。")
            print(f"  例: transcription.py \"{video_path}\" en")
            return True

        # 指定言語のトラックを検索
        track = find_track_by_lang(tracks, lang_code)
        if track is None:
            print(f"エラー: 言語 '{lang_code}' の字幕トラックが見つかりません。")
            print_tracks(tracks)
            return False

        if is_image_subtitle(track):
            print(f"エラー: トラック [{track['index']}] ({track['lang']}) は画像字幕（{track['codec']}）のため、テキストとして抽出できません。")
            print("音声認識で字幕を生成する場合は --transcribe を指定してください。")
            print(f"  例: transcription.py \"{video_path}\" --transcribe")
            return False

        print(f"字幕トラック [{track['index']}] ({track['lang']}) を抽出中 ", end="", flush=True)
        try:
            srt_text = extract_srt(video_path, track["index"])
        except RuntimeError as e:
            print(f"\nエラー: {e}")
            return False
        print("*")

        # フィルター適用
        blocks = parse_srt_blocks(srt_text)
        blocks = filter_blocks(blocks)
        srt_text = build_srt(blocks)

        if translate_target:
            # --translate 指定時のみ翻訳（既定 en、--translate=ja などで指定）
            try:
                srt_text = translate_srt(srt_text, src_lang=track["lang"], target_lang=translate_target)
            except RuntimeError as e:
                print(f"\nエラー: {e}")
                return False
            output_path = build_output_path(video_path, translate_target)
        else:
            output_path = build_output_path(video_path, lang_code)

        if not confirm_overwrite(output_path, force_overwrite):
            print("スキップしました。")
            return True
        write_srt(output_path, srt_text)

    else:
        # 字幕なし、または --transcribe 指定 → Whisper で音声認識
        if force_transcribe and tracks:
            print("--transcribe 指定。字幕トラックを無視して Whisper で音声認識を行います。")
        else:
            print("字幕トラックなし。Whisper で音声認識を行います。")
        try:
            srt_text, detected_lang = transcribe(video_path, language=lang_code)
        except RuntimeError as e:
            print(f"\nエラー: {e}")
            return False

        # フィルター適用
        blocks = parse_srt_blocks(srt_text)
        blocks = filter_blocks(blocks)
        srt_text = build_srt(blocks)

        print(f"\n検出言語: {detected_lang}")
        # 言語コードを明示指定していた場合はそれをファイル名に使う
        # (誤検出時も出力先が呼び出し側の期待通りになるようにするため)
        output_path = build_output_path(video_path, lang_code or detected_lang)
        if not confirm_overwrite(output_path, force_overwrite):
            print("スキップしました。")
            return True
        write_srt(output_path, srt_text)

    return True


def main():
    parser = build_parser()
    ns = parser.parse_args()

    translate_target = ns.translate.lower() if ns.translate else None
    force_transcribe = ns.transcribe

    # 位置引数の解釈:
    #   存在するファイル・フォルダ → 入力
    #   それ以外の 2〜3 文字の引数 → 言語コード
    input_paths = []
    lang_code = None
    for a in ns.inputs:
        if os.path.exists(a):
            input_paths.append(a)
        elif lang_code is None and 2 <= len(a) <= 3 and a.isalpha():
            lang_code = a.lower()
        else:
            print(f"エラー: ファイルが見つかりません: {a}")
            sys.exit(1)

    if not input_paths:
        print("エラー: 入力ファイルまたはフォルダを指定してください。")
        sys.exit(1)

    videos = collect_videos(input_paths)
    if not videos:
        print("エラー: 処理対象の動画ファイルがありません。")
        sys.exit(1)

    if len(videos) == 1:
        ok = process_video(videos[0], lang_code, translate_target, force_transcribe, ns.force)
        sys.exit(0 if ok else 1)

    # 一括処理
    print(f"一括処理: {len(videos)} 本の動画を処理します。\n")
    failed = []
    for i, v in enumerate(videos, 1):
        print(f"=== [{i}/{len(videos)}] {v}")
        if not process_video(v, lang_code, translate_target, force_transcribe, ns.force):
            failed.append(v)
        print()

    print(f"完了: {len(videos) - len(failed)}/{len(videos)} 本成功")
    if failed:
        print("失敗したファイル:")
        for v in failed:
            print(f"  {v}")
        sys.exit(1)


if __name__ == "__main__":
    main()
