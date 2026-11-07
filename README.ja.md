<div align="center">

[English](README.md) · [简体中文](README.zh-CN.md) · **日本語** · [Español](README.es.md)

# AI Voiceover Studio — YouTube・顔出しなし動画のための AI ナレーション、音声合成（TTS）、ボイスクローン

**AI Voiceover Studio は、書いた台本をコマンド一つで完成した AI ナレーションに変えるオープンソースの Python CLI／ライブラリです。複数話者のナレーション、ボイスクローン、SRT 字幕、シンプルな顔出しなし（faceless）動画まで作れます。**

[![Tests](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

```bash
voiceover script video-script.md --voices voices.json -o out/
# -> out/voiceover.mp3  out/voiceover.srt  out/manifest.json
```

## デモ

<!-- デモのプレースホルダー: docs/assets/demo.gif に差し替え -->

> 🎬 *デモ GIF は準備中です。* 下のオフライン実行（`--dry-run`）なら API キーなしで、無音の音声を使ってパイプライン全体（タイミング、字幕、動画）を確認できます。

## 機能：AI ナレーション・音声合成・字幕

| | 内容 |
| --- | --- |
| 🗣️ **音声合成（TTS）** | `voiceover say "..."` で一文を MP3/WAV に。速度とスタイル／感情タグを指定可能 |
| 🎭 **複数話者の台本** | Markdown/TXT に `[NARRATOR]:` `[ALEX]:` と書き、話者ごとに別の声を割り当て |
| 🧬 **ボイスクローン** | 参照音声の URL（と書き起こし）を声として使用 |
| 💬 **字幕** | セグメントの長さから正確な SRT を生成、または完成音声を音声認識 |
| 🎞️ **顔出しなし動画** | 画像＋台本 → ナレーションと字幕付きのスライドショー MP4 |
| ♻️ **安全な再実行** | セグメントキャッシュと決定的な冪等キーで、変更のない行は再生成しない |
| 🔌 **差し替え可能なエンジン** | `VoiceProvider` インターフェース。組み込みのリモートエンジンは [Miragea](https://miragea.ai)、オフライン用 `dummy` もあり |
| 🪶 **軽量** | Python 3.9+ 標準ライブラリのみ。`moviepy`・`PyYAML` は任意、`ffmpeg` があれば利用 |

## クイックスタート

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio.git
cd ai-voiceover-studio
pip install -e .

voiceover script examples/script.md --dry-run -o out/      # オフライン、キー不要

export MIRAGEA_API_KEY=...      # https://miragea.ai/workspace/api で作成
voiceover voices                # アカウントの声（actor id）一覧
voiceover say "チャンネルへようこそ！" --voice <actor_id> -o hello.mp3
```

キーは環境変数からのみ読み込まれ、API ホストへの `Authorization` ヘッダーにのみ使われます。表示・ログ出力・保存はされません。MP3 出力には [ffmpeg](https://ffmpeg.org) が必要です（なければ `.wav` を指定）。

## 複数話者の台本（対話・吹き替え）

```markdown
[NARRATOR]: 晴れた日の空は青い。でも太陽の光は白い。青はどこから来るのでしょう？
[ALEX](tags=curious): 太陽の光って白いの？
[pause 0.8]
[NARRATOR](speed=1.05): 波長の短い青い光ほど、大気中で強く散乱されるのです。
```

`[名前]:` で話者を指定、タグのない行は直前の話者を継続、空行で新しいセグメント、`[pause 1.5]` で無音を挿入します。話者と声の対応は `voices.json` に書きます（[例](examples/voices.example.json)）。

```bash
voiceover script script.md --voices voices.json -o out/
```

## 参照音声によるボイスクローン

```bash
voiceover say "テキストから生成した私自身の声です。" \
  --voice https://example.com/my-voice.wav --ref-text "my-voice.wav で実際に話した内容。" \
  --lang ja -o cloned.mp3
```

ご自身の声、または使用許可を得た声のみをクローンしてください。

## 字幕（SRT）

`--subtitles timing`（既定、台本の文字をそのまま使用し追加の API 呼び出しなし）、`recognize`（完成音声を音声認識）、`none` から選べます。日本語・中国語・韓国語の改行にも対応しています。

## 画像と台本から顔出しなし YouTube 動画を作る

```bash
pip install -e ".[video]"
voiceover video --images examples/slides/ --script examples/script.md -o video.mp4 --subtitles burn
voiceover video ... --size 1080x1920 -o short.mp4     # 縦型（ショート動画向け）
```

## 対応言語

組み込みの Miragea エンジン：**中国語、英語、日本語、韓国語、ドイツ語、フランス語、ロシア語、ポルトガル語、スペイン語、イタリア語**。

## よくある質問

詳しくは [docs/FAQ.md](docs/FAQ.md)（英語）をご覧ください。

**YouTube 動画に AI ナレーションを付けるには？** 台本を Markdown で書き、`voiceover script` を実行して、`voiceover.mp3` を編集ソフトに配置し、`voiceover.srt` を字幕としてアップロードします。

**自分の声をクローンできますか？** はい。API から取得できる URL に録音を置き、`--voice` と `--ref-text` を指定します。

**API キーなしで試せますか？** はい、`--dry-run` は完全にオフラインで動作します。

## アーキテクチャ・比較・ロードマップ

詳細は英語版の [Architecture](README.md#architecture)、[How it compares](README.md#how-it-compares)、[Roadmap](README.md#roadmap) を参照してください。

## コントリビュート

Issue・PR を歓迎します。[CONTRIBUTING.md](CONTRIBUTING.md) を参照し、`pip install -e ".[dev]" && pytest`（オフライン）でテストしてください。

## ライセンス

[MIT](LICENSE) © 2026 Miragea contributors
