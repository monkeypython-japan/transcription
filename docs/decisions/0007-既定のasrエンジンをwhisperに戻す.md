---
status: accepted
date: 2026-08-09
tags:
  - project/transcription
---

# 0007. 既定の ASR エンジンを Whisper に戻す

## 状況

[[0006-parakeetのセリフ欠落対策としてbeam探索とoverlap拡大を導入|ADR 0006]] で Parakeet の
セリフ欠落を軽減する対策（Beam 探索・overlap 拡大）を実施したが、同じ実測（`The_Questor_Tapes.mp4`、
90分）で比較すると、対策後の Parakeet でも Whisper 側にのみ存在する4語以上の連続語句
（欠落候補）が28件残った（対策前は42件）。Whisper 側にも無音区間のハルシネーション
（今回の実測で8箇所、`filter.py` で除去される定型句）があるが、欠落候補のタイムスタンプとは
重複しておらず、今回の欠落ギャップを相殺する要因にはならないことを確認済み。

ユーザーより「精度を優先する」との明確な判断があったため、既定のハイブリッド振り分け
（[[0005-音声認識エンジンをparakeetへ切り替える|ADR 0005]]）における既定エンジンを見直す。

## 決定

`config.py` の `_DEFAULTS["models"]["asr_engine"]` と `config.toml` の `asr_engine` を
`"parakeet"` から `"whisper"` に変更する。これにより、明示的に `asr_engine = "parakeet"` を
設定しない限り、常に Whisper 経路が使われる（[[0005-音声認識エンジンをparakeetへ切り替える|ADR 0005]]
で定義したハイブリッド振り分けの `asr_engine = "whisper"` 分岐がそのまま適用される）。

Parakeet 経路の実装（[[0006-parakeetのセリフ欠落対策としてbeam探索とoverlap拡大を導入|ADR 0006]]
の対策含む）はそのまま残し、`asr_engine = "parakeet"` を明示指定すれば高速・低ハルシネーション
路線として引き続き利用できる。

## 却下案

- **Parakeet の欠落を完全に解消してから既定を維持する**: [[0006-parakeetのセリフ欠落対策としてbeam探索とoverlap拡大を導入|ADR 0006]]
  で判明した通り、残る欠落の一部は parakeet-mlx 本体のチャンク結合ロジックに起因し、
  自プロジェクト側の対策だけでは完全解消の見込みが立たない。精度優先の方針が明確なため、
  完全解消を待たず既定を切り替えることにした

## 影響

- 既定動作が変わる: 何も設定しない場合、`--transcribe` 等での音声認識は常に Whisper が使われる
  （Parakeet 対応言語であっても Parakeet には回されない）
- 処理時間: 既定経路が Whisper になるため、平均的な処理時間は増加する（実測: 90分動画で
  Parakeet(対策後) 493秒 → Whisper 1226秒、約2.5倍）
- 無音区間のハルシネーションのリスクは既定経路で再び顕在化するが、`filter.py` による
  除去は従来通り適用される
- 日本語・中国語・韓国語等はいずれの設定でも従来通り Whisper が使われるため、この変更による
  挙動差は無い
- `config.toml` を明示的に `asr_engine = "parakeet"` にすれば、[[0005-音声認識エンジンをparakeetへ切り替える|ADR 0005]]
  時点の高速・低ハルシネーション構成にいつでも戻せる
