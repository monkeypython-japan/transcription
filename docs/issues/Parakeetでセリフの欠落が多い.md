---
status: resolved
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

- チャンク境界の結合ロジック（parakeet-mlx `alignment.py`）が、オーバーラップ区間の
  トークン一致に失敗すると時刻の中間点で単純に切り捨てるフォールバックへ入り、
  そのフォールバックがセリフを丸ごと欠落させることがある
- Greedy 探索（既定）自体が、チャンク分割の有無に関係なく節をまるごと読み飛ばす
  ことがある（Beam 探索では回復した実例あり）

詳細な調査手順・実測値は [[../decisions/0006-parakeetのセリフ欠落対策としてbeam探索とoverlap拡大を導入|ADR 0006]] を参照。

## 対処

`asr_parakeet.py` で decoding を Beam(beam_size=5) に変更し、overlap_duration を
15秒→30秒に拡大した。同一ファイルでの検証で欠落候補が42件→28件（大欠落はほぼ解消）
に減少（処理時間は156秒→493秒、Whisperの1226秒よりは高速）。

## 備考

チャンク境界の結合バグ自体（parakeet-mlx 側の実装）は解消しておらず、今回の対処は
軽減策。残存する欠落候補（28件、大半は数語程度）がある点に留意。
