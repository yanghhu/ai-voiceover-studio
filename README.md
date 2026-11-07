<div align="center">

**English** · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Español](README.es.md)

# AI Voiceover Studio — text to speech & voice cloning for YouTube and faceless videos

**AI Voiceover Studio is an open-source Python CLI and library that turns a written script into a finished AI voiceover — multi-speaker narration, voice cloning, SRT subtitles and a simple faceless video — in one command.**

[![Tests](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Dependencies: none](https://img.shields.io/badge/core%20deps-zero-brightgreen.svg)](pyproject.toml)
[![Agent skill](https://img.shields.io/badge/agent%20skill-Claude%20Code%20%7C%20Codex%20%7C%20Cursor-purple.svg)](skills/ai-voiceover/SKILL.md)

</div>

```bash
voiceover script video-script.md --voices voices.json -o out/
# -> out/voiceover.mp3  out/voiceover.srt  out/manifest.json
```

## Demo

<!-- DEMO PLACEHOLDER: replace with docs/assets/demo.gif (terminal run + resulting video, ~15 s, < 5 MB)
<p align="center"><img src="docs/assets/demo.gif" alt="AI voiceover generated from a Markdown script, with subtitles" width="720"></p>
-->

> 🎬 *Demo GIF coming soon.* Until then, try the offline dry run below — it renders the full pipeline (timing, subtitles, video) with silent audio and needs no API key.

## Table of contents

- [Why this exists](#why-this-exists)
- [Features](#features-ai-voiceover-text-to-speech-and-subtitles)
- [Quickstart](#quickstart-text-to-speech-in-60-seconds)
- [Multi-character scripts (dialogue & dubbing)](#multi-character-scripts-dialogue-and-dubbing)
- [Voice cloning from a reference clip](#voice-cloning-from-a-reference-clip)
- [Subtitles (SRT)](#subtitles-srt-for-youtube)
- [Faceless YouTube video](#faceless-youtube-video-from-images-and-a-script)
- [Use it from Python](#use-it-from-python)
- [Use it from an AI coding agent](#use-it-from-an-ai-coding-agent)
- [Architecture](#architecture)
- [Supported languages](#supported-languages)
- [How it compares](#how-it-compares)
- [FAQ](#faq)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

## Why this exists

Most voiceover workflows for YouTube explainers, tutorials and faceless channels look the same: write a script, paste it paragraph by paragraph into a TTS tool, download a pile of clips, line them up in an editor, then transcribe it all again to get captions. AI Voiceover Studio does that whole loop from a plain Markdown file, reproducibly, so a script edit means re-running one command — and only the lines you changed are generated again.

## Features: AI voiceover, text to speech and subtitles

| | What you get |
| --- | --- |
| 🗣️ **Text to speech** | `voiceover say "..."` — one line to an MP3/WAV, with speed and style/emotion tags |
| 🎭 **Multi-speaker scripts** | `[NARRATOR]:` / `[ALEX]:` lines in Markdown or TXT, each speaker mapped to its own voice |
| 🧬 **Voice cloning** | use a reference audio URL (plus its transcript) instead of a stock voice |
| 💬 **Subtitles** | SRT generated from exact segment timing, or from speech recognition on the final mix |
| 🎞️ **Faceless video** | images + script → MP4 slideshow with voiceover and sidecar or burned-in captions |
| ♻️ **Re-run safely** | per-line cache and deterministic idempotency keys: unchanged lines are never generated twice |
| 🔌 **Pluggable engines** | small `VoiceProvider` interface; [Miragea](https://miragea.ai) is the built-in remote engine, a silent `dummy` engine works offline |
| 🤖 **Agent-ready** | ships an agent skill and a `--json` mode for Claude Code, Codex, Cursor and scripts |
| 🪶 **Tiny footprint** | Python 3.9+ standard library only; `moviepy` and `PyYAML` are optional extras, `ffmpeg` is used when present |

## Quickstart: text to speech in 60 seconds

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio.git
cd ai-voiceover-studio
pip install -e .                # add [video] for faceless videos, [yaml] for voices.yaml

# 1) Offline dry run — no key, no network, silent audio with realistic timing
voiceover script examples/script.md --dry-run -o out/

# 2) Real voices
export MIRAGEA_API_KEY=...      # create one at https://miragea.ai/workspace/api
voiceover voices                # list the voices in your account (actor ids)
voiceover say "Welcome back to the channel!" --voice <actor_id> -o hello.mp3
```

`MIRAGEA_BASE_URL` (default `https://miragea.ai/v1`) points the client at a self-hosted deployment. The key is read from the environment, sent only in the `Authorization` header to the API host, and never printed, logged or written to `manifest.json`.

> MP3/M4A output and non-WAV conversions use [ffmpeg](https://ffmpeg.org) when it is installed. Without ffmpeg, choose `.wav` output (`--name voiceover.wav`).

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

Map speakers to voices in `voices.json` (see [examples/voices.example.json](examples/voices.example.json)):

```json
{
  "default":  { "actor_id": "YOUR_ACTOR_ID" },
  "NARRATOR": { "actor_id": "YOUR_ACTOR_ID", "model": "standard" },
  "ALEX":     { "reference_audio_url": "https://example.com/alex.wav",
                "reference_text": "The exact words spoken in alex.wav." }
}
```

```bash
voiceover script examples/script.md --voices voices.json -o out/ --gap 0.4
```

Output:

| File | Contents |
| --- | --- |
| `out/voiceover.mp3` | the full track (`--name voiceover.wav` for WAV) |
| `out/voiceover.srt` | subtitles aligned to the track |
| `out/segments/*.wav` | one clip per segment — also the cache for the next run |
| `out/manifest.json` | speakers, text, start/end times, task ids and idempotency keys per segment |

Edit one line and run again: only that line is regenerated. Use `--fresh` when you want a new take of everything.

## Voice cloning from a reference clip

```bash
voiceover say "This is my own voice, generated from text." \
  --voice https://example.com/my-voice.wav \
  --ref-text "The exact words I said in my-voice.wav." \
  --lang en -o cloned.mp3
```

A `--voice` value that starts with `http(s)://` is treated as reference audio; anything else is an actor id. The URL must be reachable by the API server. Providing the exact transcript (`--ref-text`) gives the engine the most accurate reference; without it, the engine recognizes the reference speech itself. Only clone voices you own or have explicit permission to use.

## Subtitles (SRT) for YouTube

| Mode | How | When to use |
| --- | --- | --- |
| `--subtitles timing` *(default)* | Cues from the known duration of each segment, text taken verbatim from the script | Your script is the source of truth — no extra API call, no recognition errors |
| `--subtitles recognize` | Uploads the final mix to the engine's subtitle recognition endpoint | You want word-level timing that follows the actual speech |
| `--subtitles none` | No SRT | Audio-only projects |

Cues are split at sentence and clause boundaries and wrapped to two lines (CJK-aware). Upload the `.srt` to YouTube Studio → *Subtitles*, or burn it into the video (next section).

## Faceless YouTube video from images and a script

```bash
pip install -e ".[video]"
voiceover video --images examples/slides/ --script examples/script.md \
  --voices voices.json -o video.mp4 --subtitles burn          # or: sidecar | none
voiceover video ... --size 1080x1920 -o short.mp4              # vertical, for Shorts / Reels / TikTok
```

Images are used in file-name order. If the number of images equals the number of script segments, each image stays on screen exactly while its segment is spoken; otherwise the track is divided evenly. `--fit cover` crops to fill the frame; `--fit contain` letterboxes onto a blurred copy of the image. Burned-in captions need an ffmpeg build with libass (standard in most distributions).

## Use it from Python

```python
from voiceover_studio import Studio

studio = Studio()                                   # default engine: miragea (reads MIRAGEA_API_KEY)
studio.say("Hello!", voice="ACTOR_ID", output="hello.mp3", speed=1.1)

result = studio.render_script("script.md", "out/", voices="voices.json", subtitles="timing")
print(result.audio_path, result.srt_path, round(result.duration, 1))
for seg in result.segments:
    print(seg.start, seg.end, seg.speaker, seg.text)

Studio("dummy").render_script("script.md", "dry/")  # offline, for tests and CI
```

Errors are typed: `ConfigError` (bad input), `ProviderError` (HTTP/API error with `.status`, `.code`, `.retryable`, `.task_id`, `.hint`), `TaskFailed` (the job finished as failed).

## Use it from an AI coding agent

[`skills/ai-voiceover/SKILL.md`](skills/ai-voiceover/SKILL.md) is a drop-in skill for Claude Code, Codex, Cursor and similar agents. Copy the folder into your agent's skills directory (for example `~/.claude/skills/` or `.cursor/skills/`), or point the agent at it, then ask: *"Voice `script.md` with the voices in `voices.json` and give me subtitles."* Every command supports `--json` and stable exit codes (`0` ok, `1` task failed, `2` usage/API error).

## Architecture

```
script.md ──► script.py ──► [Segment(speaker, text, options, pause)]
                                  │   voices.json ─► config.py (speaker → Voice)
                                  ▼
                            studio.py ── cache hit? ──► segments/NNN_speaker_hash.wav
                                  │ no
                                  ▼
                     providers/base.py  VoiceProvider.synthesize()
                     ├─ providers/miragea.py  POST /audio/generations → poll /tasks/{id} → download
                     ├─ providers/dummy.py    offline silence with estimated duration
                     └─ your provider         (entry point "ai_voiceover_studio.providers")
                                  ▼
                       audio.py  decode → concat with gaps → export (wav / ffmpeg)
                                  ▼
                    subtitles.py  timing cues  or  provider.transcribe() → SRT
                                  ▼
                        video.py  (optional, moviepy) images + track + captions → MP4
```

Reliability details for remote engines:

- **Asynchronous tasks.** Jobs are created, then polled using the server's `poll_after_seconds`; a wait timeout reports the task id so you can resume with `voiceover task <id> --wait` instead of submitting again.
- **Idempotency.** Every create request carries an `Idempotency-Key` derived from the exact request content. Retrying after a network error or re-running the script returns the original task rather than creating a duplicate.
- **Retries** happen only for errors the API marks `retryable` (and network failures), always with the same key.
- **Clear errors** for 401 (key rejected), 403 (account has no API access), 409 (key reused with different input), 413 (upload too large) and 429 (quota or rate limit), each with a one-line hint.

### Adding a voice engine

```python
from voiceover_studio.providers.base import VoiceProvider, SynthesisResult

class MyProvider(VoiceProvider):
    name = "myengine"
    max_text_length = 2000

    def synthesize(self, text, voice, *, audio_format="wav", cache_key=None):
        audio = call_my_engine(text, voice.actor_id, speed=voice.speed or 1.0)
        return SynthesisResult(audio=audio, format="wav")
```

Register it in your package's `pyproject.toml` and use `voiceover --provider myengine ...`:

```toml
[project.entry-points."ai_voiceover_studio.providers"]
myengine = "my_package.provider:MyProvider"
```

`list_voices()` and `transcribe()` are optional; without `transcribe()`, subtitles fall back to timing.

## Supported languages

The built-in Miragea engine supports voiceover in **Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish and Italian**. Subtitle wrapping handles both space-separated and CJK text. `--lang` is a language hint for reference audio (for example `zh`, `en`, `ja`). Other engines support whatever their provider supports.

## How it compares

A neutral look at common ways to produce a voiceover:

| | Recording yourself | Web TTS editor | Calling a TTS API directly | **AI Voiceover Studio** |
| --- | --- | --- | --- | --- |
| Multi-speaker script in one file | manual | usually per-clip | you write the code | ✅ built in |
| Re-generate only changed lines | re-record | manual | you write the code | ✅ cache + idempotency |
| Subtitles | separate step | varies | separate step | ✅ SRT included |
| Faceless video output | editor | varies | no | ✅ optional |
| Scriptable / CI / AI agents | no | no | yes | ✅ CLI, `--json`, Python API |
| Swap engines | — | no | rewrite | ✅ provider interface |
| Natural human performance | ✅ best | depends on engine | depends on engine | depends on engine |

If you need a full timeline editor, music mixing or lip-sync, use a video editor alongside this tool — it intentionally does one job: script in, voiceover (and captions) out.

## FAQ

More answers in [docs/FAQ.md](docs/FAQ.md).

**How do I add AI voiceover to a YouTube video?**
Write your narration in a Markdown file, run `voiceover script script.md --voices voices.json -o out/`, then drop `out/voiceover.mp3` onto your editor's timeline and upload `out/voiceover.srt` as YouTube subtitles. For a faceless video with no editing at all, use `voiceover video --images slides/ --script script.md -o video.mp4`.

**Can I clone my own voice?**
Yes. Host a short, clean recording of your voice at a URL the API can reach, then pass it as `--voice https://.../me.wav` with its exact transcript as `--ref-text`. You can also save it as a voice in your Miragea account and use its actor id. Only clone voices you have the right to use.

**Which languages are supported?**
With the built-in Miragea engine: Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish and Italian.

**Can different characters have different voices?**
Yes — tag lines with `[NAME]:` and map each name to a voice in `voices.json`. Unmapped speakers use `default` or `--default-voice`; a missing voice is reported before anything is generated.

**Do I need an API key to try it?**
No. `--dry-run` uses an offline engine that produces silent audio with realistic timing, so you can check script parsing, subtitles and video layout first.

**Will re-running a script generate everything again?**
No. Each segment is cached by its text and voice settings, and remote requests use deterministic idempotency keys. Pass `--fresh` for a brand-new take.

**Is my API key safe?**
It is read from `MIRAGEA_API_KEY`, sent only to the API host, never printed or saved, and result downloads are fetched without it.

## Roadmap

- [ ] Demo GIF and sample videos
- [ ] Inline images in the script (`![](slide.png)`) to drive slide timing
- [ ] Background music bed with automatic ducking
- [ ] Ken Burns pan/zoom and simple transitions for slides
- [ ] Subtitle styling presets (Shorts, documentary, karaoke)
- [ ] Translate-and-dub: script → other languages → voiceover
- [ ] Parallel segment generation with a concurrency limit
- [ ] Optional synchronous engine mode for very short lines
- [ ] More community providers via the entry-point interface

Ideas and votes welcome in [Issues](https://github.com/yanghhu/ai-voiceover-studio/issues).

## Contributing

Contributions are welcome — bug reports, docs, new providers and features alike. See [CONTRIBUTING.md](CONTRIBUTING.md). In short:

```bash
pip install -e ".[dev,video,yaml]"
pytest                      # fully offline, no API key needed
```

Keep the core dependency-free, add tests with mocked HTTP for anything that talks to a network, and never commit keys or generated media.

## License

[MIT](LICENSE) © 2026 Miragea contributors. Generated voices are subject to the terms of the engine you use; respect the rights of the people whose voices you clone.
