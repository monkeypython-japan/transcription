# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 言語

- 会話は全て日本語で行う。
- 会話の引き継ぎサマリー（コンテキスト圧縮時の要約）も日本語で行う。

## 開発ルール

- **すべての変更はブランチを作成してから行う。main への直接コミットは禁止。**
- 曖昧な点はユーザーに質問する。
- ブランチ上で変更を実施したら、ユーザーがテストを行う。
- テスト完了後、Claude がコミットして main へマージする。
- マージに先立ち、ブランチの変更内容に仕様の変更（挙動・数値・UI・AIロジック）が含まれる場合は `transcription-spec.md` に反映してから main へマージする。
- origin へのプッシュに先立ち、変更内容を `README.md` に反映してからプッシュする。

## 統括プロジェクト（video-translation）へエスカレーションする条件

本プロジェクトは映像翻訳システムのサブプロジェクトで、`subtitle-translation` が
出力 SRT を `<ROOT>/<name>/source.en.srt` として消費する。その**契約の正本**は
`video-translation/docs/spec/contracts.md`（言語は常に `en` を明示指定する等）。

**次の4つに当たるときだけ統括に上げる。当たらない限り、規模が大きくても自分で進めてよい**（統括 ADR-0009）。

1. **出力 SRT の命名・形式・言語指定の扱いを変えたくなった**（共有ファイル契約に触れる）
2. **他プロジェクト（subtitle-translation / japanese-dubbing）の作業が必要になった**
3. **前提・方針が変わった**（プロジェクト横断で効くもの）
4. **ユーザーの判断が要る**

**回答は相談ノートの末尾に「統括の回答・発注」として追記される。** エスカレーション後にセッションを再開したら、**作業を始める前にまずそこを読む**（契約は統括が先に更新しているので `video-translation/docs/spec/contracts.md` の該当節も見る）。同じ相談を二度上げない。

## プロジェクト概要

オフライン動画字幕生成 CLI ツール。動画ファイルを受け取り、SRT ファイルを出力する。
仕様（アーキテクチャ・動作・技術スタック）の正本は [`transcription-spec.md`](transcription-spec.md) を参照。

## 開発コマンド

```bash
# 仮想環境のセットアップ（初回のみ）
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 仮想環境の有効化（ターミナルを開き直した場合）
source .venv/bin/activate

# 実行例（字幕トラック一覧表示 / 字幕なし動画の音声認識）
python transcription.py "<動画ファイル>"

# 実行例（字幕トラックをそのまま抽出）
python transcription.py "<動画ファイル>" fr

# 実行例（字幕トラックを英語に翻訳して出力）
python transcription.py "<動画ファイル>" fr --translate
```

> パスに日本語やスペースが含まれる場合はダブルクォートで囲む。
