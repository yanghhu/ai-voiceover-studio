# AI Voiceover Studio — FAQ

Clear answers about AI voiceover, text to speech, voice cloning, subtitles and faceless YouTube videos with AI Voiceover Studio. Each answer stands on its own.

## General

### What is AI Voiceover Studio?
AI Voiceover Studio is an open-source (MIT) Python command-line tool and library that turns a written script into an AI voiceover. It handles multi-speaker narration, voice cloning from a reference clip, SRT subtitles and simple faceless slideshow videos. The command is `voiceover`.

### Who is it for?
YouTube creators, faceless-channel producers, educators making explainers and tutorials, podcasters producing scripted segments, localization and dubbing teams, and developers or AI agents that need to generate narration from code.

### Is it free and open source?
The software is free and open source under the MIT license. Generating real voices uses a voice engine; the built-in remote engine is Miragea, which requires an account and API key. An offline `dummy` engine produces silent audio for testing at no cost.

### What does it need to run?
Python 3.9 or newer. The core uses only the standard library. Optional: `ffmpeg` for MP3/M4A output and burned-in captions, `moviepy` for video (`pip install "ai-voiceover-studio[video]"`), and `PyYAML` for `voices.yaml`.

## Voiceover and text to speech

### How do I add AI voiceover to a YouTube video?
1. Write your narration in a Markdown or text file.
2. Run `voiceover script script.md --voices voices.json -o out/`.
3. Put `out/voiceover.mp3` on your video editor's timeline.
4. Upload `out/voiceover.srt` in YouTube Studio under *Subtitles*.
For a video with no editing, run `voiceover video --images slides/ --script script.md -o video.mp4`.

### How do I turn a single sentence into speech?
Run `voiceover say "Your sentence" --voice <actor_id> -o line.mp3`. Get actor ids with `voiceover voices`.

### Can different characters have different voices?
Yes. Start lines with `[NAME]:` in the script and map each name to a voice in `voices.json`. Lines without a tag continue with the previous speaker. Speakers that are not mapped use the `default` entry or `--default-voice`. A missing voice is reported before anything is generated.

### Can I control speed, emotion or style?
Yes. Use `--speed` (0.25–4) and `--tag` on the command line, or per line in the script: `[ALEX](tags=excited, speed=1.1): ...`. Available tags depend on the engine and model.

### How do I add pauses?
Put `[pause 1.5]` on its own line for 1.5 seconds of silence. `--gap` sets the default silence between segments (0.35 s).

### How long can a script be?
There is no fixed limit in the tool. Long paragraphs are split at sentence boundaries so that each request stays within the engine's per-request text limit, and the pieces are joined seamlessly.

### Does re-running a script generate everything again?
No. Every segment is cached by its exact text and voice settings in `out/segments/`, and remote requests use deterministic idempotency keys, so unchanged lines are reused. Use `--fresh` to force a new take.

## Voice cloning

### Can I clone my own voice?
Yes. Upload a short, clean recording of your voice to a URL the API server can reach and run `voiceover say "Text" --voice https://example.com/me.wav --ref-text "exact words in the recording"`. In a script, put the same `reference_audio_url` and `reference_text` in `voices.json`. You can also save the voice in your Miragea account and use its actor id.

### Why should I pass the reference transcript?
The transcript (`--ref-text` / `reference_text`) tells the engine exactly what is said in the reference clip, which gives the most accurate clone. If you leave it out, the engine recognizes the reference speech automatically.

### Is voice cloning legal?
Cloning your own voice, or a voice you have explicit written permission to use, is generally fine. Cloning someone else's voice without consent may violate their rights and the engine's terms. Do not use cloned voices to impersonate or deceive.

## Languages

### Which languages are supported?
With the built-in Miragea engine: Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish and Italian. Other engines support whatever their provider supports.

### Can I mix languages in one script?
Yes. Each segment is generated separately, so different lines can be in different languages or use different voices. Use `lang=` per line or `--lang` as a hint for reference audio.

### Does it work for dubbing a video into another language?
Yes, if you have the translated script: write it with one speaker tag per character, map each character to a voice, and run `voiceover script`. Automatic translation is on the roadmap.

## Subtitles

### How are subtitles created?
By default (`--subtitles timing`) cues are built from the measured duration of each generated segment, with the text taken verbatim from your script, so there are no recognition errors and no extra API call. With `--subtitles recognize`, the finished track is sent to the engine's subtitle recognition endpoint for timing that follows the actual speech.

### What subtitle format is produced?
SRT, which YouTube, most video editors and players accept. Cues are split at sentence and clause boundaries and wrapped to at most two lines, with CJK-aware line breaking.

### Can subtitles be burned into the video?
Yes: `voiceover video ... --subtitles burn`. This needs ffmpeg with libass. `--subtitles sidecar` (default) writes a separate `.srt` next to the MP4.

## Faceless videos

### How do I make a faceless YouTube video?
Install the video extra (`pip install -e ".[video]"`), put your images in a folder, and run `voiceover video --images slides/ --script script.md --voices voices.json -o video.mp4`. Images are shown in file-name order.

### How is each image timed?
If the number of images equals the number of script segments, each image is shown exactly while its segment is spoken. Otherwise the audio length is divided evenly between images.

### Can I make vertical videos for Shorts, Reels or TikTok?
Yes: add `--size 1080x1920`. `--fit cover` crops images to fill the frame; `--fit contain` places them on a blurred background.

## Engines, API and security

### Which TTS engines are supported?
Miragea is the built-in remote engine and the default; `dummy` is an offline engine for tests and dry runs. Any other engine can be added by implementing the small `VoiceProvider` interface and registering it under the `ai_voiceover_studio.providers` entry point.

### How do I get a Miragea API key?
Create one at https://miragea.ai/workspace/api and set it with `export MIRAGEA_API_KEY=...`. For a self-hosted deployment, also set `MIRAGEA_BASE_URL` (including `/v1`).

### Can I try it without an API key?
Yes. Add `--dry-run` to any command. It uses the offline engine, which writes silent audio with realistic durations, so you can check parsing, subtitles and video layout.

### Is my API key safe?
The key is read only from the `MIRAGEA_API_KEY` environment variable, sent only in the `Authorization` header to the API host, never printed, logged or written to `manifest.json`, and not sent when downloading result files. Redirects are not followed for authenticated requests.

### What happens if the network drops or a job takes long?
Create requests carry an idempotency key, so retrying returns the original job instead of creating a duplicate. Tasks are polled until they finish; if the wait times out, the task id is reported and `voiceover task <id> --wait -o file.mp3` resumes it.

### What do the error codes mean?
`401` the key was rejected; `403` the account has no API access; `409` an idempotency key was reused with different input; `413` the upload is too large; `429` quota exhausted or rate limited. The CLI prints a one-line hint for each. Exit codes: `0` success, `1` task failed, `2` usage or API error.

### Can an AI coding agent use it?
Yes. The repository includes `skills/ai-voiceover/SKILL.md` for Claude Code, Codex, Cursor and similar agents, and every command supports `--json` output.
