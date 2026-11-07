---
name: ai-voiceover
description: Turn a written script into an AI voiceover (text to speech, multi-speaker, voice cloning) with SRT subtitles and optionally a faceless slideshow video, using the `voiceover` CLI from ai-voiceover-studio. Use when the user asks to voice, narrate, dub or add a voiceover/subtitles to a script or video.
---

# AI Voiceover

Use the `voiceover` CLI (package `ai-voiceover-studio`, Python 3.9+) to generate narration.

## Setup check

1. `voiceover --version` — if missing: `pip install -e <repo>` or `pip install ai-voiceover-studio`
   (add `[video]` for videos, `[yaml]` for voices.yaml).
2. Real voices need `MIRAGEA_API_KEY` in the environment (created at https://miragea.ai/workspace/api).
   Never ask the user to paste the key into chat, never echo it, never write it to files.
   If it is not set, do a `--dry-run` first and tell the user how to set the key.
3. MP3 output needs `ffmpeg`; without it use `--name voiceover.wav` / `-o file.wav`.

## Workflow: voice a script

1. **Prepare the script** (Markdown or TXT). One speaker tag per line or paragraph:
   ```
   [NARRATOR]: Opening line.
   Untagged lines continue the current speaker.

   [ALEX](tags=excited, speed=1.1): A different character.
   [pause 1]
   ```
   Headings, HTML comments, code blocks and tables are ignored.
2. **Pick voices.** `voiceover voices --json` lists account voices (`voice_id` = actor id).
   Match by name; if two voices share a name, ask the user which one. A voice can also be a
   public reference-audio URL (voice cloning) plus its exact transcript as `reference_text`.
   Only clone voices the user owns or has permission to use.
3. **Write `voices.json`** mapping every speaker (upper-case keys) to a voice:
   ```json
   {"default": {"actor_id": "123"}, "ALEX": {"reference_audio_url": "https://...", "reference_text": "..."}}
   ```
4. **Dry run** (offline, validates speakers and timing):
   `voiceover script script.md --voices voices.json -o out/ --dry-run --json`
5. **Generate**: `voiceover script script.md --voices voices.json -o out/ --json`
   Outputs `out/voiceover.mp3`, `out/voiceover.srt`, `out/manifest.json`, `out/segments/`.
6. Report the saved paths and duration. Do not claim success unless the command exited 0.

## Other commands

- One line: `voiceover say "text" --voice <actor_id|https://ref.wav> [--ref-text "..."] [--lang en] -o line.mp3`
- Faceless video: `voiceover video --images slides/ --script script.md --voices voices.json -o video.mp4 [--subtitles burn|sidecar|none] [--size 1080x1920]`
  One image per segment gives exact slide timing; otherwise slides share time evenly.
- Subtitles from speech recognition instead of timing: add `--subtitles recognize` (one extra API call).
- Resume a task after a wait timeout: `voiceover task <task_id> --wait -o out.mp3`.

## Rules

- Re-running the same command is safe: unchanged segments come from cache and remote
  requests reuse idempotency keys. Use `--fresh` only when the user wants a new take.
- On a wait timeout, keep the reported `task_id` and resume with `voiceover task`; do not resubmit.
- Exit codes: 0 ok, 1 provider task failed, 2 usage/config/API error. With `--json`, errors are
  `{"error": {"code", "message", "http_status", "retryable"}, "task_id"?}`.
- 401: key rejected → user checks `MIRAGEA_API_KEY`. 403: account lacks API access.
  429: quota/rate limit → wait or top up, do not loop. 400: fix text/voice/speed/tags.
- Supported languages (Miragea): Chinese, English, Japanese, Korean, German, French, Russian,
  Portuguese, Spanish, Italian.
