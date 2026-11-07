<div align="center">

[English](README.md) · [简体中文](README.zh-CN.md) · **日本語** · [Español](README.es.md)

# AI Voiceover Studio — YouTube・顔出しなし動画のための AI ナレーション、音声合成（TTS）、ボイスクローン

**AI Voiceover Studio は、Markdown の台本をコマンド一つで AI ナレーション、SRT 字幕、字幕付きの顔出しなし（faceless）動画に変えるオープンソースの Python CLI／ライブラリです。無料のニューラル音声ですぐに動き（アカウント・API キー不要）、Miragea を使えばボイスクローンや表現力豊かな声も利用できます。**

[![Tests](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

<table>
<tr>
<td align="center"><img src="docs/assets/demo.gif" alt="examples/demo.en.md から作った 16:9 の顔出しなし動画：シネマティックな B ロール、Ken Burns、フックカード、単語ごとの字幕" width="560"></td>
<td align="center"><img src="docs/assets/demo-short-zh.gif" alt="examples/demo.zh.md から作った 9:16 の中国語ショート" width="200"></td>
</tr>
<tr>
<td align="center"><sub>16:9 YouTube · <a href="docs/assets/demo.mp4">音声付き動画（MP4、34 秒）</a></sub></td>
<td align="center"><sub>9:16 ショート · <a href="docs/assets/demo-short-zh.mp4">MP4、23 秒</a></sub></td>
</tr>
</table>

<sub>それぞれコマンド 1 回の無編集出力：無料の Edge 音声、自動生成 BGM（声の下で自動ダッキング）、B ロールは <a href="examples/broll">examples/broll</a> · <a href="docs/assets/sample-voiceover.mp3">ナレーションのみ（MP3）</a> · <a href="docs/assets/sample-voiceover.srt">字幕（SRT）</a></sub>

</div>

## クイックスタート（3 行）

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio && cd ai-voiceover-studio
pip install -e ".[edge]"
voiceover video --script examples/demo.en.md --style tiktok --music ambient -o out/video.mp4
```

これだけです。`out/video.mp4`（1080p：段落ごとの B ロールと Ken Burns・トランジション、アニメーションするフック、単語ごとにハイライトされる字幕、声に合わせて自動で下がる BGM）、`out/video.srt`、`out/video_voiceover/` のナレーション音声ができます。必要なのは Python 3.9+ と [ffmpeg](https://ffmpeg.org) で、`voiceover doctor` が確認します。

```bash
voiceover script examples/script.md -o out/      # 音声のみ：out/voiceover.mp3 + .srt + manifest.json
voiceover say "チャンネルへようこそ！" -o hello.mp3
voiceover doctor                                 # ffmpeg・エンジン・キー・フォントを確認
```

声の設定ファイルは不要です。台本の話者ごとに、台本の言語に合った別々の声が自動で割り当てられます。

## 機能

| | 内容 |
| --- | --- |
| 🆓 **登録不要** | 既定エンジンは無料の Microsoft Edge ニューラル音声（`edge-tts`）。322 音声・75 言語、アカウントもキーも不要 |
| 🎭 **複数話者の台本** | `[NARRATOR]:` `[ALEX]:` と書くだけで話者ごとに別の声。`voices.json` で指定も可能 |
| 🎞️ **顔出しなし動画** | 段落ごとの B ロール（台本に `![](clip.mp4)`）→ Ken Burns、スライド／ズーム／フェードのトランジション、シネマ風グレード、フックカード付き MP4 |
| 🔤 **アニメーション字幕** | TikTok / CapCut 風の単語ごとのハイライト（実際の単語タイミング）、ポップイン、キーワード色（台本の `**太字**`）、9:16 / 16:9 のセーフエリア |
| 🎵 **BGM とダッキング** | 内蔵の自動生成アンビエント曲（ライセンス不要）または手持ちの曲。話している間は自動で音量を下げる |
| ✨ **画像なしでも見栄えよく** | B ロールのない段落はアニメーショングラデーション＋キーフレーズの大きなキネティックタイポ |
| 💬 **正確な字幕** | エンジンの文境界から SRT を生成、または完成音声を音声認識。CJK の改行に対応 |
| 🎨 **字幕スタイル** | `tiktok`（縦型の既定）・`clean`（横長の既定）・`bold`・`minimal`・`box`、横長／縦長に自動対応 |
| 🧬 **ボイスクローン** | Miragea エンジンで、参照音声の URL（と書き起こし）を声として使用 |
| ♻️ **安全な再実行** | セグメントキャッシュと決定的な冪等キーで、変更のない行は再生成しない |
| 🔌 **差し替え可能なエンジン** | `edge`・`miragea`・`openai`・オフライン `dummy`、または `VoiceProvider` で独自エンジン |
| 🩺 **`voiceover doctor`** | ffmpeg（libass）、エンジン、API キー、CJK フォントを確認し、修正方法を表示 |
| 🪶 **軽量なコア** | 標準ライブラリのみ。エンジンは任意の extra、動画は ffmpeg で直接レンダリング |

## 音声エンジン

| エンジン | 設定 | 向いている用途 |
| --- | --- | --- |
| `edge`（キー未設定時の既定） | `pip install -e ".[edge]"`、登録・キー不要 | お試し、下書き、多言語 |
| `miragea`（`MIRAGEA_API_KEY` 設定時の既定） | `export MIRAGEA_API_KEY=...`（[キーを作成](https://miragea.ai/workspace/api)） | 参照音声によるボイスクローン、感情タグ付きの表現力豊かなモデル、字幕認識 |
| `openai` | `export OPENAI_API_KEY=...` | OpenAI の声（`alloy`、`nova`、`onyx` など） |
| `dummy` | なし（`--dry-run`） | オフラインのテストと CI |

`--provider 名前` または `VOICEOVER_PROVIDER` で選択します。`voiceover voices --provider edge --filter ja-JP` で Edge の声（例 `ja-JP-NanamiNeural`）を一覧できます。キーは環境変数からのみ読み込まれ、表示・保存はされません。Edge の音声は Microsoft のオンライン読み上げサービス（コミュニティパッケージ `edge-tts` 経由）で、インターネット接続が必要です。

## 複数話者の台本（対話・吹き替え）

```markdown
[NARRATOR]: 晴れた日の空は青い。でも太陽の光は白い。青はどこから来るのでしょう？
[ALEX](tags=curious): 太陽の光って白いの？
[pause 0.8]
[NARRATOR](speed=1.05): 波長の短い青い光ほど、大気中で強く散乱されるのです。
```

`[名前]:` で話者を指定、タグのない行は直前の話者を継続、空行で新しいセグメント、`[pause 1.5]` で無音を挿入します。声の設定がなければ話者ごとに別の声が自動で割り当てられます。自分で選ぶ場合は `voices.json` に書きます（[例](examples/voices.example.json)）。

```bash
voiceover script script.md --voices voices.json -o out/
```

## 参照音声によるボイスクローン

ボイスクローンには Miragea エンジン（`MIRAGEA_API_KEY`）を使います。

```bash
voiceover say "テキストから生成した私自身の声です。" \
  --voice https://example.com/my-voice.wav --ref-text "my-voice.wav で実際に話した内容。" \
  --lang ja -o cloned.mp3
```

ご自身の声、または使用許可を得た声のみをクローンしてください。

## 字幕（SRT）

`--subtitles timing`（既定、台本の文字をそのまま使用し追加の API 呼び出しなし）、`recognize`（完成音声を音声認識）、`none` から選べます。日本語・中国語・韓国語の改行にも対応しています。

## 台本から顔出しなし YouTube 動画とショートを作る

B ロールは台本に直接書きます。Markdown の画像行がその下の段落の画像／動画クリップになり、`**太字**` は字幕でハイライトされます。

```bash
voiceover video --script examples/demo.en.md --style tiktok --music ambient -o video.mp4   # 16:9 YouTube
voiceover video --script examples/demo.zh.md --vertical --music ambient -o short.mp4       # 9:16 ショート / リール / TikTok
voiceover video --script notes.md -o explainer.mp4                                         # 画像なし：キネティックタイポ
```

主なオプション：`--style tiktok|clean|bold|minimal|box`（縦型は `tiktok`、横長は `clean` が既定）、`--music ambient|pulse|ファイル`（`ambient`・`pulse` はレンダリング時に本プロジェクトのコードで合成、ライセンス不要）、`--music-volume 0-1`（既定 0.5）、`--no-duck`、`--hook テキスト` / `--no-hook`（既定は台本の最初の `#` 見出し）、`--vertical`、`--transition-style mix|fade|slide|zoom|cut`、`--grade cinematic|none`、`--images フォルダ`（`![](...)` のない段落用）、`--font`（日本語字幕には CJK フォントが必要。`voiceover doctor` で確認）。動画は ffmpeg 1 回の呼び出しで描画され、Python の動画ライブラリは不要です。

## 対応言語

- **edge**：75 言語（`voiceover voices --provider edge`）。日・英・中・韓・西・仏・独・伊・葡・露は台本の文字または `--lang` から声を自動選択。
- **miragea**：中国語、英語、日本語、韓国語、ドイツ語、フランス語、ロシア語、ポルトガル語、スペイン語、イタリア語（ボイスクローン対応）。

## よくある質問

詳しくは [docs/FAQ.md](docs/FAQ.md)（英語）をご覧ください。

**YouTube 動画に AI ナレーションを付けるには？** 台本を Markdown で書き、`voiceover script` を実行して、`voiceover.mp3` を編集ソフトに配置し、`voiceover.srt` を字幕としてアップロードします。

**自分の声をクローンできますか？** はい。API から取得できる URL に録音を置き、`--voice` と `--ref-text` を指定します。

**API キーなしで使えますか？** はい。既定の `edge` エンジンは無料でアカウント不要、`--dry-run` は完全にオフラインです。Miragea のキーがあればボイスクローンや表現力豊かな声も使えます。

## アーキテクチャ・比較・ロードマップ

詳細は英語版の [Architecture](README.md#architecture)、[How it compares](README.md#how-it-compares)、[Roadmap](README.md#roadmap) を参照してください。

## コントリビュート

Issue・PR を歓迎します。[CONTRIBUTING.md](CONTRIBUTING.md) を参照し、`pip install -e ".[dev,edge]" && pytest`（オフライン）でテストしてください。

## ライセンス

[MIT](LICENSE) © 2026 Miragea contributors
