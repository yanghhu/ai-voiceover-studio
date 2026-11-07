<div align="center">

**English** · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Español](README.es.md)

# AI Voiceover Studio — text to speech, subtitles & faceless videos from a script

**AI Voiceover Studio is an open-source Python CLI and library that turns a Markdown script into a finished AI voiceover — multi-speaker narration, SRT subtitles and a captioned faceless video — in one command. It works out of the box with free neural voices (no account, no API key), and plugs into Miragea for voice cloning and expressive voices.**

[![Tests](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Core deps: none](https://img.shields.io/badge/core%20deps-zero-brightgreen.svg)](pyproject.toml)
[![Agent skill](https://img.shields.io/badge/agent%20skill-Claude%20Code%20%7C%20Codex%20%7C%20Cursor-purple.svg)](skills/ai-voiceover/SKILL.md)

<img src="docs/assets/demo.gif" alt="Terminal command followed by the generated faceless video: Ken Burns slides, two AI voices and burned-in captions" width="720">

<sub>Real output, unedited: [full video with sound (MP4, 40 s)](docs/assets/demo.mp4) · [voiceover only (MP3)](docs/assets/sample-voiceover.mp3) · [subtitles (SRT)](docs/assets/sample-voiceover.srt) · [vertical Chinese Short (MP4)](docs/assets/demo-short-zh.mp4)</sub>

</div>

## Quickstart

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio && cd ai-voiceover-studio
pip install -e ".[edge]"
voiceover video --images examples/slides --script examples/script.md -o out/video.mp4
```

That is the whole setup. You get `out/video.mp4` (1080p, two voices, Ken Burns motion, captions burned in), `out/video.srt`, and the voiceover track in `out/video_voiceover/`. It needs Python 3.9+ and [ffmpeg](https://ffmpeg.org); `voiceover doctor` checks both.

```bash
voiceover script examples/script.md -o out/          # audio only: out/voiceover.mp3 + .srt + manifest.json
voiceover say "Welcome back to the channel!" -o hello.mp3
voiceover doctor                                      # ffmpeg, engines, keys, fonts
```

No voices file is needed: every speaker in the script automatically gets its own voice, chosen from the script's language.

## Table of contents

- [Why this exists](#why-this-exists)
- [Features](#features)
- [Voice engines](#voice-engines)
- [Multi-character scripts](#multi-character-scripts-dialogue-and-dubbing)
- [Voice cloning](#voice-cloning-from-a-reference-clip)
- [Subtitles (SRT)](#subtitles-srt-for-youtube)
- [Faceless video](#faceless-youtube-video-from-images-and-a-script)
- [Use it from Python](#use-it-from-python)
- [Use it from an AI coding agent](#use-it-from-an-ai-coding-agent)
- [Architecture](#architecture)
- [Supported languages](#supported-languages)
- [How it compares](#how-it-compares)
- [FAQ](#faq)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

## Why this exists

Most voiceover workflows for YouTube explainers, tutorials and faceless channels look the same: write a script, paste it paragraph by paragraph into a TTS tool, download a pile of clips, line them up in an editor, then transcribe everything again to get captions. AI Voiceover Studio does that whole loop from a plain Markdown file, reproducibly, so a script edit means re-running one command — and only the lines you changed are generated again.

## Features

| | What you get |
| --- | --- |
| 🆓 **Works without signup** | free Microsoft Edge neural voices via `edge-tts` are the default engine — 300+ voices, 70+ languages |
| 🎭 **Multi-speaker scripts** | `[NARRATOR]:` / `[ALEX]:` lines in Markdown or TXT; each speaker gets its own voice automatically, or map them in `voices.json` |
| 🎞️ **Faceless video** | images (or just a script) → MP4 with slow Ken Burns zoom, cross-fades, a progress bar and styled burned-in captions |
| 💬 **Accurate subtitles** | SRT timed from the engine's own sentence boundaries, or speech recognition on the final mix; CJK-aware line wrapping |
| 🎨 **Caption styles** | `clean`, `box`, `bold` (Shorts/Reels) and `minimal`; speaker labels; sizes adapt to 16:9 and 9:16 |
| 🧬 **Voice cloning** | with the Miragea engine: a reference audio URL (plus its transcript) instead of a stock voice |
| ♻️ **Re-run safely** | per-line cache and deterministic idempotency keys: unchanged lines are never generated twice |
| 🔌 **Pluggable engines** | `edge`, `miragea`, `openai`, offline `dummy`, or your own via a small `VoiceProvider` interface |
| 🩺 **`voiceover doctor`** | checks ffmpeg (libass), engines, API keys and CJK fonts, and tells you the exact fix |
| 🤖 **Agent-ready** | an agent skill plus `--json` output and stable exit codes for Claude Code, Codex, Cursor and scripts |
| 🪶 **Tiny core** | standard library only; engines are optional extras; video is rendered by ffmpeg directly |

## Voice engines

| Engine | Setup | Best for |
| --- | --- | --- |
| `edge` *(default without a key)* | `pip install -e ".[edge]"` — no account, no key | trying it out, drafts, many languages |
| `miragea` *(default when `MIRAGEA_API_KEY` is set)* | `export MIRAGEA_API_KEY=...` ([create a key](https://miragea.ai/workspace/api)) | voice cloning from a reference clip, expressive models with emotion tags, subtitle recognition |
| `openai` | `export OPENAI_API_KEY=...` | OpenAI voices (`alloy`, `nova`, `onyx`, ...) |
| `dummy` | nothing (`--dry-run`) | offline tests and CI: silent audio with realistic timing |

Pick one with `--provider NAME` or `VOICEOVER_PROVIDER=NAME`. List voices with `voiceover voices --provider edge --filter en-GB` (Edge voice ids look like `en-GB-SoniaNeural`) or `voiceover voices` for the actors saved in your Miragea account.

Edge voices come from Microsoft's online read-aloud service through the community `edge-tts` package; they need an internet connection and are subject to Microsoft's terms. If you are behind an HTTPS proxy that edge-tts cannot use, set `VOICEOVER_EDGE_PROXY`.

## Multi-character scripts (dialogue and dubbing)

Write the script the way you would read it:

```markdown
# Why the Sky Is Blue — 60-second explainer

[NARRATOR]: Look up on a clear day and the sky is blue. But sunlight is white.
So where does the blue come from?

[ALEX](tags=curious): Wait — sunlight is white? It looks yellow to me.

[pause 0.8]

[ALEX](speed=1.05): So blue light bounces all over the sky!
```

Rules: a `[NAME]:` tag sets the speaker; untagged lines continue with the current speaker; a blank line starts a new segment; `[pause 1.5]` inserts silence; `(tags=a|b, speed=1.1, model=..., lang=...)` sets per-line options. Headings, HTML comments, code blocks and tables are skipped, and Markdown emphasis and links are read as plain text. Long paragraphs are split at sentence boundaries to stay within the engine's per-request text limit.

Without a voices file each speaker gets a distinct voice for the script's language (for example Andrew and Ava for English, Yunxi and Xiaoxiao for Chinese). To choose voices yourself, map speakers in `voices.json` (see [examples/voices.example.json](examples/voices.example.json)):

```json
{
  "NARRATOR": { "actor_id": "en-GB-RyanNeural" },
  "ALEX":     { "actor_id": "en-US-AvaNeural", "speed": 1.05 }
}
```

With Miragea, `actor_id` is an actor from `voiceover voices`, or use `reference_audio_url` + `reference_text` to clone a voice:

```json
{
  "NARRATOR": { "actor_id": "YOUR_ACTOR_ID", "model": "standard" },
  "ALEX":     { "reference_audio_url": "https://example.com/alex.wav",
                "reference_text": "The exact words spoken in alex.wav." }
}
```

```bash
voiceover script examples/script.md --voices voices.json -o out/ --gap 0.4
```

| File | Contents |
| --- | --- |
| `out/voiceover.mp3` | the full track (`--name voiceover.wav` for WAV) |
| `out/voiceover.srt` | subtitles aligned to the track |
| `out/segments/*.wav` | one clip per segment — also the cache for the next run |
| `out/manifest.json` | speakers, voices, text, start/end times and sentence timings per segment |

Edit one line and run again: only that line is regenerated. Use `--fresh` for a new take of everything.

## Voice cloning from a reference clip

Voice cloning uses the Miragea engine:

```bash
export MIRAGEA_API_KEY=...
voiceover say "This is my own voice, generated from text." \
  --voice https://example.com/my-voice.wav \
  --ref-text "The exact words I said in my-voice.wav." \
  --lang en -o cloned.mp3
```

A `--voice` value that starts with `http(s)://` is treated as reference audio; anything else is a voice id. The URL must be reachable by the API server. Providing the exact transcript (`--ref-text`) gives the engine the most accurate reference. Only clone voices you own or have explicit permission to use.

## Subtitles (SRT) for YouTube

| Mode | How | When to use |
| --- | --- | --- |
| `--subtitles timing` *(default)* | Cues from the engine's sentence boundaries (edge) or from each segment's duration, text taken from the script | Your script is the source of truth — no extra call, no recognition errors |
| `--subtitles recognize` | Uploads the final mix to the engine's subtitle recognition (Miragea) | You want timing that follows the actual speech of any engine's audio |
| `--subtitles none` | No SRT | Audio-only projects |

Cues are split at sentence and clause boundaries, never overlap, and are wrapped to two balanced lines (CJK-aware). Upload the `.srt` to YouTube Studio → *Subtitles*, or burn it into the video (next section).

## Faceless YouTube video from images and a script

```bash
voiceover video --images examples/slides --script examples/script.md -o video.mp4
voiceover video --script examples/script.zh.md -o short.mp4 --size 1080x1920 --style bold   # vertical Short, no images needed
voiceover video --images slides/ --script script.md -o video.mp4 --style box --speaker-labels
```

| Option | Default | What it does |
| --- | --- | --- |
| `--images DIR` | animated-gradient background | images used in file-name order; if their count equals the number of segments, each image is shown exactly while its segment is spoken |
| `--subtitles burn\|sidecar\|none` | `burn` | burn styled captions in (an `.srt` is written too), sidecar only, or none |
| `--style clean\|box\|bold\|minimal` | `clean` | caption look; `bold` is large centred text for Shorts / Reels / TikTok |
| `--motion kenburns\|none` | `kenburns` | slow eased zoom and pan, alternating direction per image |
| `--transition SEC` | `0.5` | cross-fade between images (`0` = hard cut) |
| `--size WxH` | `1920x1080` | e.g. `1080x1920` for vertical video |
| `--fit cover\|contain` | `cover` | crop to fill, or fit onto a blurred copy of the image |
| `--title TEXT` / `--no-title` | script's first `#` heading, when no images are given | title card at the start |
| `--speaker-labels` | off | small speaker name above each caption |
| `--font NAME\|FILE` | Inter, falling back to system fonts | caption font; for Chinese/Japanese make sure a CJK font is installed (`voiceover doctor` checks) |
| `--no-progress-bar` | bar on | thin progress line at the bottom |

Video is rendered by one ffmpeg call (libass captions, `xfade` transitions), so there is no Python video dependency. The example slides were drawn with [`examples/make_slides.py`](examples/make_slides.py).

## Use it from Python

```python
from voiceover_studio import Studio

studio = Studio()                                    # edge, or miragea when MIRAGEA_API_KEY is set
studio.say("Hello!", None, "hello.mp3")              # voice picked from the text's language
studio.say("Hello!", "en-GB-SoniaNeural", "sonia.mp3", speed=1.1)

result = studio.render_script("script.md", "out/")   # one voice per speaker, automatically
print(result.audio_path, result.srt_path, round(result.duration, 1))
for seg in result.segments:
    print(seg.start, seg.end, seg.speaker, seg.voice, seg.text)

from voiceover_studio.video import render_video
render_video(studio, "slides/", "script.md", "video.mp4", style="box", speaker_labels=True)

Studio("dummy").render_script("script.md", "dry/")   # offline, for tests and CI
```

Errors are typed: `ConfigError` (bad input), `ProviderError` (HTTP/API error with `.status`, `.code`, `.retryable`, `.task_id`, `.hint`), `TaskFailed` (the job finished as failed), `NotSupported` (the engine lacks a capability, e.g. cloning on edge).

## Use it from an AI coding agent

[`skills/ai-voiceover/SKILL.md`](skills/ai-voiceover/SKILL.md) is a drop-in skill for Claude Code, Codex, Cursor and similar agents. Copy the folder into your agent's skills directory (for example `~/.claude/skills/` or `.cursor/skills/`), or point the agent at it, then ask: *"Voice `script.md` and make a captioned video from the images in `slides/`."* Every command supports `--json` and stable exit codes (`0` ok, `1` task failed, `2` usage/API error).

## Architecture

```
script.md ──► script.py ──► [Segment(speaker, text, options, pause)]
                                  │   voices.json ─► config.py (speaker → Voice), else provider.auto_voice()
                                  ▼
                            studio.py ── cache hit? ──► segments/NNN_speaker_hash.wav (+ .timing.json)
                                  │ no
                                  ▼
                     providers/base.py  VoiceProvider.synthesize()
                     ├─ providers/edge.py     edge-tts stream → audio + sentence boundaries
                     ├─ providers/miragea.py  POST /audio/generations → poll /tasks/{id} → download
                     ├─ providers/openai.py   POST /audio/speech
                     ├─ providers/dummy.py    offline silence with estimated duration
                     └─ your provider         (entry point "ai_voiceover_studio.providers")
                                  ▼
                       audio.py  decode → concat with gaps → export (wav / ffmpeg)
                                  ▼
                    subtitles.py  sentence/segment timing  or  provider.transcribe() → SRT
                                  ▼
             captions.py + video.py  ASS styles → one ffmpeg graph: Ken Burns, xfade, captions → MP4
```

Reliability details for remote engines:

- **Asynchronous tasks (Miragea).** Jobs are created, then polled using the server's `poll_after_seconds`; a wait timeout reports the task id so you can resume with `voiceover task <id> --wait` instead of submitting again.
- **Idempotency.** Every create request carries an `Idempotency-Key` derived from the exact request content. Retrying after a network error or re-running the script returns the original task rather than creating a duplicate.
- **Retries** happen only for errors the API marks `retryable` (and network failures), always with the same key.
- **Clear errors** for 401 (key rejected), 403 (no API access), 409 (key reused with different input), 413 (upload too large) and 429 (quota or rate limit), each with a one-line hint. Keys are never printed or written to `manifest.json`.

### Adding a voice engine

```python
from voiceover_studio.providers.base import VoiceProvider, SynthesisResult, Voice

class MyProvider(VoiceProvider):
    name = "myengine"
    max_text_length = 2000
    supports_auto_voices = True

    def synthesize(self, text, voice, *, audio_format="wav", cache_key=None):
        audio = call_my_engine(text, voice.actor_id, speed=voice.speed or 1.0)
        return SynthesisResult(audio=audio, format="wav")

    def auto_voice(self, n, language):          # optional: voice for the n-th speaker
        return Voice(actor_id=["voice-a", "voice-b"][n % 2])
```

Register it in your package's `pyproject.toml` and use `voiceover --provider myengine ...`:

```toml
[project.entry-points."ai_voiceover_studio.providers"]
myengine = "my_package.provider:MyProvider"
```

`list_voices()` and `transcribe()` are optional; return `meta={"sentences": [...]}` from `synthesize()` to get sentence-accurate subtitles.

## Supported languages

- **edge**: 70+ languages and locales (`voiceover voices --provider edge`); automatic voices for English, Chinese, Japanese, Korean, Spanish, French, German, Italian, Portuguese and Russian, picked from the script's text or `--lang`.
- **miragea**: Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish and Italian, including voice cloning.
- Subtitle wrapping handles both space-separated and CJK text.

## How it compares

A neutral look at common ways to produce a voiceover:

| | Recording yourself | Web TTS editor | Calling a TTS API directly | **AI Voiceover Studio** |
| --- | --- | --- | --- | --- |
| Multi-speaker script in one file | manual | usually per-clip | you write the code | ✅ built in |
| Re-generate only changed lines | re-record | manual | you write the code | ✅ cache + idempotency |
| Subtitles | separate step | varies | separate step | ✅ SRT included |
| Captioned faceless video | editor | varies | no | ✅ one command |
| Scriptable / CI / AI agents | no | no | yes | ✅ CLI, `--json`, Python API |
| Swap engines | — | no | rewrite | ✅ provider interface |
| Natural human performance | ✅ best | depends on engine | depends on engine | depends on engine |

If you need a full timeline editor, music mixing or lip-sync, use a video editor alongside this tool — it intentionally does one job well: script in, voiceover, captions and a clean video out.

## FAQ

More answers in [docs/FAQ.md](docs/FAQ.md).

**Do I need an API key?**
No. The default `edge` engine uses free online neural voices with no account. `--dry-run` works fully offline with silent audio. A Miragea key adds voice cloning and expressive voices; an OpenAI key adds OpenAI voices.

**How do I add AI voiceover to a YouTube video?**
Write your narration in a Markdown file, run `voiceover script script.md -o out/`, then drop `out/voiceover.mp3` onto your editor's timeline and upload `out/voiceover.srt` as YouTube subtitles. For a captioned video with no editing at all, run `voiceover video --images slides/ --script script.md -o video.mp4`.

**Can I make vertical Shorts / Reels?**
Yes: `--size 1080x1920 --style bold`. Caption size and line length adapt to the frame.

**Can I clone my own voice?**
Yes, with the Miragea engine: pass a URL of a short, clean recording as `--voice https://.../me.wav` and its exact transcript as `--ref-text`. Only clone voices you have the right to use.

**Can different characters have different voices?**
Yes — tag lines with `[NAME]:`. Each name gets its own voice automatically, or map names to voices in `voices.json`.

**Will re-running a script generate everything again?**
No. Each segment is cached by its text and voice settings, and remote requests use deterministic idempotency keys. Pass `--fresh` for a brand-new take.

**Something doesn't work — where do I start?**
Run `voiceover doctor` (add `--online` to synthesize one test line). It checks Python, ffmpeg with libass, installed engines, keys and CJK fonts, and prints the fix for each problem.

## Roadmap

- [x] Demo GIF and sample videos
- [x] Free default engine (edge) and OpenAI engine
- [x] Ken Burns motion, cross-fades and caption style presets
- [x] `voiceover doctor`
- [ ] Inline images in the script (`![](slide.png)`) to drive slide timing
- [ ] Background music bed with automatic ducking
- [ ] Word-by-word (karaoke) caption highlighting
- [ ] Translate-and-dub: script → other languages → voiceover
- [ ] Parallel segment generation with a concurrency limit
- [ ] Publish to PyPI

Ideas and votes welcome in [Issues](https://github.com/yanghhu/ai-voiceover-studio/issues).

## Contributing

Contributions are welcome — bug reports, docs, new providers and features alike. See [CONTRIBUTING.md](CONTRIBUTING.md). In short:

```bash
pip install -e ".[dev,edge,yaml]"
pytest                      # fully offline: engines and HTTP are mocked, no key needed
```

Keep the core dependency-free, add tests with mocked network calls, and never commit keys or generated media (except the curated demo files in `docs/assets/`).

## License

[MIT](LICENSE) © 2026 Miragea contributors. Generated voices are subject to the terms of the engine you use; respect the rights of the people whose voices you clone.
