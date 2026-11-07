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
Python 3.9 or newer and, for MP3 output and videos, [ffmpeg](https://ffmpeg.org) with libass. The core uses only the standard library. Optional extras: `[edge]` for the free voice engine (`edge-tts`) and `[yaml]` for `voices.yaml`. Run `voiceover doctor` to check everything at once.

## Voiceover and text to speech

### How do I add AI voiceover to a YouTube video?
1. Write your narration in a Markdown or text file.
2. Run `voiceover script script.md --voices voices.json -o out/`.
3. Put `out/voiceover.mp3` on your video editor's timeline.
4. Upload `out/voiceover.srt` in YouTube Studio under *Subtitles*.
For a video with no editing, add `![](image.jpg)` lines above the paragraphs and run `voiceover video --script script.md --music ambient -o video.mp4`.

### How do I turn a single sentence into speech?
Run `voiceover say "Your sentence" -o line.mp3`. A voice is picked from the language of the text; choose one with `--voice`, e.g. `--voice en-GB-SoniaNeural` (list them with `voiceover voices --provider edge --filter en-GB`) or a Miragea actor id from `voiceover voices`.

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
Yes, with the Miragea engine (`MIRAGEA_API_KEY`). Upload a short, clean recording of your voice to a URL the API server can reach and run `voiceover say "Text" --voice https://example.com/me.wav --ref-text "exact words in the recording"`. In a script, put the same `reference_audio_url` and `reference_text` in `voices.json`. You can also save the voice in your Miragea account and use its actor id.

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
By default (`--subtitles timing`) cues come from the sentence boundaries the engine reports while speaking (edge) or from the measured duration of each segment, with the text taken from your script, so there are no recognition errors and no extra API call. Cues never overlap. With `--subtitles recognize` (Miragea), the finished track is sent to the subtitle recognition endpoint for timing that follows the actual speech.

### What subtitle format is produced?
SRT, which YouTube, most video editors and players accept. Cues are split at sentence and clause boundaries and wrapped to at most two lines, with CJK-aware line breaking.

### Can subtitles be burned into the video?
Yes, and it is the default for `voiceover video`: captions are burned in with a style preset (`--style tiktok|clean|bold|minimal|box`; the animated styles highlight each word as it is spoken) and an `.srt` is written next to the MP4 as well. This needs ffmpeg with libass. Use `--subtitles sidecar` for the `.srt` only. Chinese, Japanese and Korean captions need a CJK font installed (for example `fonts-noto-cjk`); `voiceover doctor` checks for one.

## Faceless videos

### How do I make a faceless YouTube video?
Write `![](broll/shot1.jpg)` (an image or a video clip) above each paragraph of the script and run `voiceover video --script script.md --music ambient -o video.mp4`. Each picture is shown exactly while its paragraph is spoken, with Ken Burns motion, slide / zoom / fade transitions, a light film grade, an animated hook card from the script's first heading and word-by-word captions. `--images folder/` still works for paragraphs without their own picture. Rendering is done by ffmpeg; no Python video library is needed. See `examples/demo.en.md`.

### How is each image timed?
B-roll written in the script follows its paragraph; several images in one paragraph share its time, and video clips are trimmed or looped. With only `--images`, each image follows one segment when the counts match, otherwise the audio length is divided evenly.

### What if I have no images at all?
Parts without a picture get an animated gradient with the paragraph's key phrase in large kinetic type (the first `**bold**` phrase, or the strongest words of its first sentence), so a plain script still gives a watchable video.

### How do the word-by-word captions work?
The edge engine reports when each word is spoken, and captions highlight words in that rhythm: `tiktok` pops the spoken word in yellow, `bold` reveals huge words one by one, `clean` softly highlights a calm two-line caption. For engines without word timings the timing is estimated from sentence or paragraph length. Words in `**bold**` and numbers get a keyword colour.

### How do I add background music?
`--music ambient` (or `pulse`) adds a track that is synthesized by this project's own code at render time, so there is nothing to license. `--music song.mp3` uses your file, looped. The music is levelled, faded in and out and ducked under the voice automatically; adjust with `--music-volume 0-1` or turn ducking off with `--no-duck`.

### Can I make vertical videos for Shorts, Reels or TikTok?
Yes: add `--vertical` (= `--size 1080x1920`). Captions switch to the `tiktok` style, get larger and stay above the area the apps cover with their buttons. `--fit cover` crops images to fill the frame; `--fit contain` places them on a blurred background.

### Can I turn off the motion, transitions or effects?
Yes: `--motion none` keeps images still, `--transition 0` or `--transition-style cut` uses hard cuts, `--grade none` removes vignette and grain, and `--no-progress-bar` and `--no-hook` remove the progress line and hook card.

## Engines, API and security

### Which TTS engines are supported?
Built in: `edge` (free Microsoft Edge neural voices through `edge-tts`, the default when no Miragea key is set), `miragea` (voice cloning, expressive models, subtitle recognition; the default when `MIRAGEA_API_KEY` is set), `openai` (`OPENAI_API_KEY`) and `dummy` (offline, for tests and dry runs). Choose with `--provider` or `VOICEOVER_PROVIDER`. Any other engine can be added by implementing the small `VoiceProvider` interface and registering it under the `ai_voiceover_studio.providers` entry point.

### Is the edge engine really free? What are the limits?
It uses Microsoft's online read-aloud voices through the community `edge-tts` package, with no account or key. It needs an internet connection, does not support voice cloning, and its use is subject to Microsoft's terms. For cloning or expressive control use Miragea.

### edge-tts fails behind my proxy
Some HTTPS proxy URLs (for example ones with special characters in the user name) cannot be used by the underlying HTTP library. Set `VOICEOVER_EDGE_PROXY` to a usable proxy URL, or unset `HTTPS_PROXY` for the command. `voiceover doctor --online` tests a real synthesis.

### How do I get a Miragea API key?
Create one at https://miragea.ai/workspace/api and set it with `export MIRAGEA_API_KEY=...`. For a self-hosted deployment, also set `MIRAGEA_BASE_URL` (including `/v1`).

### Can I try it without an API key?
Yes. The default `edge` engine needs no key or account. `--dry-run` works fully offline: it writes silent audio with realistic durations, so you can check parsing, subtitles and video layout.

### What does `voiceover doctor` check?
Python version, ffmpeg and its libass/xfade filters, which engines are installed, whether `MIRAGEA_API_KEY` / `OPENAI_API_KEY` are set (values are never shown), which engine is the default, and whether a CJK caption font is installed. `--online` also synthesizes one short line with the edge engine. Each problem comes with the command that fixes it.

### Is my API key safe?
Keys are read only from environment variables (`MIRAGEA_API_KEY`, `OPENAI_API_KEY`), sent only in the `Authorization` header to the API host, never printed, logged or written to `manifest.json`, and not sent when downloading result files. Redirects are not followed for authenticated requests.

### What happens if the network drops or a job takes long?
Create requests carry an idempotency key, so retrying returns the original job instead of creating a duplicate. Tasks are polled until they finish; if the wait times out, the task id is reported and `voiceover task <id> --wait -o file.mp3` resumes it.

### What do the error codes mean?
`401` the key was rejected; `403` the account has no API access; `409` an idempotency key was reused with different input; `413` the upload is too large; `429` quota exhausted or rate limited. The CLI prints a one-line hint for each. Exit codes: `0` success, `1` task failed, `2` usage or API error.

### Can an AI coding agent use it?
Yes. The repository includes `skills/ai-voiceover/SKILL.md` for Claude Code, Codex, Cursor and similar agents, and every command supports `--json` output.
