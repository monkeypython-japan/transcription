---
status: investigating
tags:
  - project/transcription
date: 2026-08-09
---

# Parakeet 経路の音声認識で、Whisper と比べてセリフの欠落が多い

## 症状

`/Users/mamoru/Temp/The_Questor_Tapes.mp4`（英語音声、字幕トラック無し、`--transcribe`
相当で音声認識、既定の Parakeet 経路）を聞き取らせたところ、本編中のセリフが
かなりの数欠落した。同じファイルを Whisper 経路（`asr_engine = "whisper"`）で
処理すると欠落はより少ない。

## 調査方針

1. 同一動画ファイルを Parakeet / Whisper の両エンジンでそれぞれ書き起こし、SRT を出力する
2. 2つの SRT を突き合わせ、Whisper 側にのみ存在するブロック（＝Parakeet 側の欠落候補）を洗い出す
3. 欠落箇所の傾向（無音区間直後か、早口・重複音声か、chunk 境界付近か等）を分析する
4. 傾向を踏まえて Parakeet 側の改善策を検討する（`chunk_duration`/`overlap_duration` の調整、
   モデル側パラメータ、後段のギャップ検出等）

## 原因

（調査中）

## 対処

（調査中）
