#!/usr/bin/env python3
"""共有ファイル契約に触れうる編集を検知して注意する(統括 video-translation の ADR-0009)。

PostToolUse(Edit|Write|MultiEdit) フックから呼ばれる。標準入力にフック入力 JSON。
リポジトリ内の *.py / *.sh を編集し、その中身が共有ファイル名に言及していたら、
統括へのエスカレーションが要るかどうかを1度だけ問い直す。

- LLM を呼ばない決定論的なチェックで、トークンは消費しない
- NAS 上の実データ(<ROOT>/<name>/*)の書き込みは対象外。夜間ジョブや通常の
  パイプライン実行で毎回鳴らないようにするため、対象はリポジトリ内の実装だけ
- 同じセッションでは1回しか鳴らさない(注意喚起であって関門ではない)

終了コード 2 = 標準エラーの内容が Claude へのフィードバックになる。編集自体は
既に完了しており、取り消しはしない。
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

# 契約の正本: video-translation/docs/spec/contracts.md
CONTRACT_FILES = (
    "source.en.srt",
    "translated.jp.srt",
    "diarization.json",
    "translation-speakers.json",
    "speaker-cast.json",
    "speakers.json",
    "jpdub-voices.json",
    "characters.md",
)
ESCALATE = "/Users/mamoru/projects/Claude/Projects/video-translation/bin/escalate.sh"


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    path = (data.get("tool_input") or {}).get("file_path") or ""
    if not path:
        return 0

    repo = pathlib.Path(__file__).resolve().parents[2]

    # ★リポジトリ外の判定は「文字列だけ」で行い、ファイルシステムに触らない。
    #   Path.resolve() や is_file() を先に呼ぶと、NAS(SMB)上のパスを渡された
    #   ときにマウントの応答待ちでフックごとハングし、セッションが止まる。
    #   実データは <ROOT>/<name>/ すなわちリポジトリ外にあるので、ここで確実に落とす。
    target = pathlib.Path(os.path.abspath(path))  # abspath は字句解析のみ(I/Oしない)
    if not str(target).startswith(str(repo) + os.sep):
        return 0
    if target.suffix not in (".py", ".sh"):  # 実装だけを見る(ドキュメントは鳴らさない)
        return 0
    if not target.is_file():  # ここから先はローカルのリポジトリ内だけ
        return 0

    try:
        text = target.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0

    hit = [name for name in CONTRACT_FILES if name in text]
    if not hit:
        return 0

    marker = pathlib.Path(tempfile.gettempdir()) / f"contract-guard-{data.get('session_id', 'none')}"
    if marker.exists():  # 同じセッションでは1回だけ
        return 0
    marker.touch()

    print(
        f"⚠ 共有ファイル契約に関係する実装を編集しました({target.name} が {', '.join(hit)} に言及)。\n"
        f"  スキーマ(フィールド・意味・命名)を変えるなら、統括にエスカレーションしてください:\n"
        f"    {ESCALATE} \"<1行の要約>\"\n"
        f"  値が増えるだけ・読み書きの実装が変わるだけなら該当しません。そのまま進めてください。\n"
        f"  判断基準は CLAUDE.md「統括へエスカレーションする条件」/ 契約の正本は\n"
        f"  video-translation/docs/spec/contracts.md(ADR-0009)。",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
