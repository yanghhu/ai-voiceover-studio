---
name: ai-voiceover
description: Turn a written script into an AI voiceover (text to speech, multi-speaker, voice cloning) with SRT subtitles and optionally a captioned faceless video, using the `voiceover` CLI from ai-voiceover-studio. Works with free voices and no API key. Use when the user asks to voice, narrate, dub or add a voiceover/subtitles to a script or video.
---

# AI Voiceover

Use the `voiceover` CLI (package `ai-voiceover-studio`, Python 3.9+) to generate narration.

## Setup check

1. `voiceover --version` — if missing: `pip install -e "<repo>[edge]"`
   (`[edge]` = free voices, `[yaml]` = voices.yaml).
2. Run `voiceover doctor --json` and fix any `fail` it reports (it never prints keys).
3. Engines: without keys the free `edge` engine is used (internet needed, no account).
   `MIRAGEA_API_KEY` switches the default to Miragea (voice cloning, expressive models);
   `OPENAI_API_KEY` enables `--provider openai`. Never ask the user to paste a key into chat,
   never echo it, never write it to files.
4. MP3 output and video need `ffmpeg` (with libass for burned captions).

## Workflow: voice a script

1. **Prepare the script** (Markdown or TXT). One speaker tag per line or paragraph:
   ```
   [NARRATOR]: Opening line.
   Untagged lines continue the current speaker.

   [ALEX](tags=excited, speed=1.1): A different character.
   [pause 1]
   ```
   Headings, HTML comments, code blocks and tables are ignored.
2. **Voices (optional).** Without a voices file every speaker gets its own voice automatically,
   chosen from the script's language. To choose: `voiceover voices --json` (add
   `--provider edge --filter en-GB` for Edge voices such as `en-GB-SoniaNeural`; for Miragea
   `voice_id` = actor id). If two voices share a name, ask the user which one. With Miragea a
   voice can also be a public reference-audio URL plus its exact transcript (`reference_text`).
   Only clone voices the user owns or has permission to use.
3. **Write `voices.json`** if the user picked voices (upper-case keys):
   ```json
   {"NARRATOR": {"actor_id": "en-US-AndrewNeural"}, "ALEX": {"actor_id": "en-US-AvaNeural", "speed": 1.05}}
   ```
4. **Dry run** (offline, validates speakers and timing):
   `voiceover script script.md -o out/ --dry-run --json`
5. **Generate**: `voiceover script script.md [--voices voices.json] -o out/ --json`
   Outputs `out/voiceover.mp3`, `out/voiceover.srt`, `out/manifest.json`, `out/segments/`.
6. Report the saved paths and duration. Do not claim success unless the command exited 0.

## Other commands

- One line: `voiceover say "text" [--voice <voice id|https://ref.wav>] [--ref-text "..."] [--lang en] -o line.mp3`
- Faceless video: `voiceover video --script script.md -o video.mp4 [--vertical] [--style tiktok|clean|bold|minimal|box] [--music ambient|pulse|file] [--images dir/] [--font file.ttf] [--subtitles burn|sidecar|none]`
  Put `![](path/to/image-or-clip)` above a paragraph to show it while that paragraph is spoken
  (paths relative to the script); `**bold**` words are highlighted. Word-by-word captions are burned in
  by default; the first `# heading` becomes a hook card (`--hook`, `--no-hook`). Paragraphs without a
  picture get kinetic typography. `--music ambient` adds generated, royalty-free music ducked under
  the voice. For Shorts / Reels / TikTok use `--vertical`. For CJK captions pass a CJK `--font`.
- Subtitles from speech recognition instead of timing (Miragea): add `--subtitles recognize` (one extra API call).
- Resume a task after a wait timeout: `voiceover task <task_id> --wait -o out.mp3`.

## Rules

- Re-running the same command is safe: unchanged segments come from cache and remote
  requests reuse idempotency keys. Use `--fresh` only when the user wants a new take.
- On a wait timeout, keep the reported `task_id` and resume with `voiceover task`; do not resubmit.
- Exit codes: 0 ok, 1 provider task failed, 2 usage/config/API error. With `--json`, errors are
  `{"error": {"code", "message", "http_status", "retryable"}, "task_id"?}`.
- 401: key rejected → user checks the key variable. 403: account lacks API access.
  429: quota/rate limit → wait, do not loop. 400: fix text/voice/speed/tags.
- `proxy_unsupported` (edge): set `VOICEOVER_EDGE_PROXY` or unset `HTTPS_PROXY` for the command.
- Languages: edge covers 75 languages; Miragea covers Chinese, English, Japanese, Korean, German,
  French, Russian, Portuguese, Spanish, Italian (with voice cloning).
