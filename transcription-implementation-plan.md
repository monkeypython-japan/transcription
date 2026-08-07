# transcription 実装プラン

## フェーズ 1: プロジェクト基盤

- [ ] git リポジトリ初期化
- [ ] `.gitignore` 作成（Python 用）
- [ ] `requirements.txt` 作成
  - `openai-whisper`
  - `ffmpeg-python`

## フェーズ 2: コア機能実装

### 2-1. CLI エントリポイント (`transcription.py`)
- [ ] コマンドライン引数のパース（動画ファイル、オプションの言語コード）
- [ ] ファイル存在チェック

### 2-2. 字幕トラック検出 (`subtitle.py`)
- [ ] ffprobe で字幕ストリームの一覧を取得
- [ ] 言語コード付きでトラック一覧を表示する関数
- [ ] 指定言語の字幕トラックを抽出して SRT 形式で返す関数

### 2-3. 字幕翻訳 (`translate.py`)
- [ ] 抽出した字幕テキストを英語に翻訳する関数
- [ ] 使用ライブラリ: Helsinki-NLP/opus-mt（オフライン）または Whisper の translate タスク
- [ ] SRT のタイムコードを保持したまま本文のみ翻訳

### 2-4. Whisper 音声認識 (`transcribe.py`)
- [ ] モデルのキャッシュ確認・初回ダウンロード（`~/Library/Application Support/transcription/`）
- [ ] 動画から音声を抽出（ffmpeg）
- [ ] Whisper large モデルで文字起こし（言語自動検出）
- [ ] 認識結果を SRT 形式に変換

### 2-5. 進捗表示 (`progress.py`)
- [ ] 処理ステップごとに `*` を追記表示するユーティリティ

### 2-6. SRT 出力 (`output.py`)
- [ ] 出力ファイルパスの生成（`{basename}.{lang}.srt`）
- [ ] SRT ファイルの書き出し

## フェーズ 3: 統合・動作確認

- [ ] 各ケースの動作確認
  - 字幕あり・言語コードなし（トラック一覧表示）
  - 字幕あり・言語コードあり（翻訳して SRT 出力）
  - 字幕なし（Whisper 自動検出・SRT 出力）
- [ ] エラーハンドリング（不正ファイル、存在しない言語コード等）

## モジュール構成（予定）

```
transcription/
├── transcription.py   # エントリポイント
├── subtitle.py        # 字幕トラック検出・抽出
├── translate.py       # 字幕翻訳
├── transcribe.py      # Whisper 音声認識
├── progress.py        # 進捗表示
├── output.py          # SRT ファイル出力
└── requirements.txt
```

## 実装順序

1. フェーズ 1（基盤）
2. 2-1 → 2-5 → 2-2 → 2-6（CLI・進捗・字幕検出・出力の骨格）
3. 2-4（Whisper 音声認識）
4. 2-3（字幕翻訳）
5. フェーズ 3（統合テスト）
