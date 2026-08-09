---
status: accepted
date: 2026-08-09
tags:
  - project/transcription
---

# 0006. Parakeet のセリフ欠落対策として Beam 探索と overlap 拡大を導入する

## 状況

`The_Questor_Tapes.mp4`（英語音声、約90分、字幕トラック無し）を既定の Parakeet 経路
（`chunk_duration=120.0`, `overlap_duration=15.0`, decoding は既定の Greedy）で
書き起こしたところ、同じファイルを Whisper 経路で書き起こした結果と比べて
セリフの欠落がかなりの数あった（[[../issues/Parakeetでセリフの欠落が多い|issue]]）。

## 調査

1. 同一ファイルを Parakeet（既定設定）・Whisper の両エンジンで書き起こし、SRT 化
2. 両者の全文をトークン単位で `difflib.SequenceMatcher` により突き合わせ、
   Whisper 側にのみ存在する4語以上の連続語句（＝Parakeet の欠落候補）を抽出
   → **42件**検出。うち複数件は20〜56語（1〜2文まるごと）の欠落
3. 欠落候補のうち代表的な3箇所（36:12 / 51:57 / 1:17:49 付近）の音声を
   ffmpeg で90秒程度切り出し、チャンク分割なし（`chunk_duration` 未指定、
   90秒 < 120秒のため単一チャンクとして処理される）で単体デコードして比較
   - **36:12・51:57 付近**: 単体デコードでは Greedy・Beam のどちらでも欠落箇所の
     セリフが正しく認識された。→ 全編処理（チャンク分割あり）でのみ欠落する
     ことから、**チャンク境界の結合処理**が原因と判明
   - **1:17:49 付近**: 単体デコード（チャンク分割なし）でも **Greedy は
     「Don't ask me any questions. In exactly ten minutes and twelve seconds,
     a hydrogen bomb is probably going to go off up there.」を丸ごと欠落**させたが、
     **Beam（beam_size=5）は正しく認識**した。→ チャンク分割と無関係に
     **Greedy 探索自体がセリフを欠落させる**ことがあると判明

## 原因

欠落には性質の異なる2つの原因が組み合わさっている。

1. **チャンク境界の結合バグ（parakeet-mlx 側の実装）**: `model.transcribe()` の
   長尺動画チャンク分割処理は、隣接チャンクのオーバーラップ区間でトークン列の
   一致（`merge_longest_contiguous` → 失敗時 `merge_longest_common_subsequence`）を
   探し、一致が見つからない場合は両チャンクの時刻の中間点で単純に切り捨てる
   フォールバックに入る（`alignment.py`）。このフォールバックは、オーバーラップ
   区間の認識結果が2チャンク間で大きく食い違う場合に、セリフがどちらの
   チャンクの採用範囲にも入らない「死角」に落ちて丸ごと消えることがある
2. **Greedy 探索固有の欠落（TDT モデル一般の性質）**: チャンク分割の有無に関係なく、
   Greedy（既定）はある種の連続した節をまるごと読み飛ばすことがある。Beam 探索は
   複数の仮説を保持したまま先に進むため、Greedy が一本道で外した箇所を拾える

いずれも [[0005-音声認識エンジンをparakeetへ切り替える|ADR 0005]] で Parakeet 採用時に
未検証だった長尺動画（同ADRの実測は3分クリップ中心）・全編通しでの挙動。

## 対処

`asr_parakeet.py` の `model.transcribe()` 呼び出しを変更:

- `decoding_config=DecodingConfig(decoding=Beam(beam_size=5))` を指定（既定の Greedy から変更）
- `overlap_duration` を 15.0 → 30.0 に拡大（境界のオーバーラップ区間を広げ、
  トークン列一致によるチャンク結合が成功しやすくし、フォールバックの発生
  そのものを減らす）

### 効果検証（`The_Questor_Tapes.mp4` 全編、Whisper比の欠落候補数で比較）

| 設定 | 欠落候補（4語以上） | 処理時間 |
|---|---:|---:|
| 既定（Greedy, overlap=15秒） | 42件（うち20〜56語の大欠落 約10件） | 156秒 |
| 変更後（Beam size=5, overlap=30秒） | 28件（20語以上の大欠落は1件のみ） | 493秒 |

欠落候補は33%減少し、特に実害の大きい大欠落（1〜2文まるごと）はほぼ解消された。
処理時間は約3.2倍に伸びたが、同ファイルの Whisper 経路（1226秒）と比べると
依然として約2.5倍高速であり、[[0005-音声認識エンジンをparakeetへ切り替える|ADR 0005]]
で Parakeet を選定した「無音区間ハルシネーションが起きにくく高速」という
利点は維持される。

## 却下案

- **チャンク分割を無効化する（`chunk_duration` 未指定）**: 長尺動画で OOM するため
  不可（[[0005-音声認識エンジンをparakeetへ切り替える|ADR 0005]] で既知）
- **parakeet-mlx の `alignment.py`（結合ロジック）を直接パッチ/フォーク**: サードパーティ
  依存の内部実装であり、保守負荷とアップストリーム追従コストが見合わないため見送り。
  overlap 拡大によるフォールバック発生率の低減で当面は許容範囲とする
- **`chunk_duration` を伸ばしてチャンク数自体を減らす**: 境界の発生回数は減らせるが、
  OOM リスクとのトレードオフが不明であり、今回は overlap 拡大のみで有意な改善が
  確認できたため見送り（将来的な追加検証の余地はある）

## 影響

- `asr_parakeet.py` の `model.transcribe()` 呼び出しのみ変更。公開契約
  `transcribe(video_path, language=None) -> (srt_text, lang)` は変更なし
- Parakeet 経路の処理時間が既定設定比で約3.2倍に増加する（それでも Whisper より高速）
- 上記検証の通り、チャンク境界の結合バグ自体は解消しておらず、残存する欠落候補
  （28件、大半は数語程度の短い欠落）がある。完全な解消ではなく軽減策である点に留意
