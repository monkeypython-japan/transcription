---
status: accepted
date: 2026-06
tags:
  - project/whisperai
modified: 2026-08-10
---

# 0001. openai-whisper から mlx-whisper への移行

## 状況

初期実装では `openai-whisper`（PyTorch ベース）を音声認識に使用していた。Apple Silicon 上では GPU（Metal）を活用できず、認識速度が実用上ボトルネックになっていた。また、無音区間でのハルシネーション（存在しない発話の生成、「I'm sorry.」の繰り返しなど）が目立った。

## 決定

音声認識モデルを `mlx-community/whisper-large-v3-mlx`（Apple MLX 最適化版）に置き換える。

- `no_speech_threshold=0.6` でハルシネーション抑制
- `condition_on_previous_text=False` で前セグメントへの過度な依存を防止
- `word_timestamps=True` を有効化し、単語単位のタイムスタンプでセグメント終端を精確化（30 秒チャンク境界へのスナップ防止）

## 理由

- M シリーズ GPU をフル活用でき、大幅な高速化が見込める
- MLX 版は Apple Silicon 向けにチューニングされており、同精度でのオフライン実行に適する

## 影響

- `requirements.txt` から `openai-whisper` を除去し `mlx-whisper` に置換
- macOS（Apple Silicon）以外での動作は非対象になる
