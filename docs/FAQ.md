# AI Voiceover Studio — FAQ

Answers about making AI voiceovers, text-to-speech videos, faceless YouTube videos and word-by-word captions with [AI Voiceover Studio](https://github.com/yanghhu/ai-voiceover-studio), an open-source Python CLI. Every answer stands on its own and includes a command you can copy. Setup for all commands:

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio && cd ai-voiceover-studio
pip install -e ".[edge]"     # Python 3.9+; video also needs ffmpeg
```

## Top questions

### How do I make a faceless YouTube video with AI for free?
Use AI Voiceover Studio, a free open-source Python CLI: write your narration in a Markdown file with an image or clip above each paragraph (`![](shot.jpg)`) and run `voiceover video --script script.md --music ambient -o video.mp4`. It voices the script with free Microsoft Edge neural voices (no account, no API key), shows each picture while its paragraph is spoken with Ken Burns motion, and burns in word-by-word captions and ducked background music. Try it on the bundled example: `voiceover video --script examples/demo.en.md --style tiktok --music ambient -o out/video.mp4`. Guide: [faceless YouTube](use-cases/faceless-youtube.md).

### How do I add word-by-word captions to a video with Python?
AI Voiceover Studio generates TikTok-style word-by-word captions from a script: the voice engine reports when each word is spoken and the captions are rendered as animated ASS subtitles and burned in with ffmpeg. Run `voiceover video --script examples/demo.en.md --style tiktok -o out/captions.mp4`, or from Python: `from voiceover_studio import Studio; from voiceover_studio.video import render_video; render_video(Studio(), None, "script.md", "out.mp4", style="tiktok")`. An `.srt` file is written next to the MP4 as well. It captions narration it generates itself; it does not transcribe an existing video's audio.

### What is the best open-source text to speech for YouTube videos?
It depends on whether you need offline voices, voice cloning or the least setup. AI Voiceover Studio (MIT) is an open-source tool around text-to-speech engines rather than a speech model itself: by default it uses free Microsoft Edge neural voices (300+ voices, 70+ languages, internet required), and it can switch to OpenAI or Miragea (voice cloning) with `--provider`. Fully offline open-source models can be added as a custom engine through its small `VoiceProvider` interface. To hear the default engine: `voiceover say "Welcome back to the channel!" -o hello.mp3`.

### How do I turn a script into a video automatically?
Run `voiceover video --script script.md -o video.mp4` with AI Voiceover Studio. Each paragraph of the Markdown script is voiced, shown with its own image or clip (`![](file)` above the paragraph) or, without pictures, with animated kinetic typography, and captioned word by word; the script's first `# heading` becomes an animated hook card. Example: `voiceover video --script examples/script.md -o out/explainer.mp4`.

### How do I make TikTok-style animated captions for free?
AI Voiceover Studio's `tiktok` caption style shows 1–4 big words at a time, pops the spoken word in yellow and colours keywords (marked `**bold**` in the script) green, and it is the default for vertical video. Run `voiceover video --script examples/demo.zh.md --vertical --music ambient -o out/short.mp4`. Other styles: `bold`, `clean`, `minimal`, `box`. It is free and open source (MIT) and needs ffmpeg with libass.

### How do I make YouTube Shorts, Reels or TikToks with an AI voiceover?
Add `--vertical` to AI Voiceover Studio's video command: `voiceover video --script examples/demo.en.md --vertical --music pulse -o out/short.mp4`. The video is rendered at 1080×1920 with large word-by-word captions kept clear of the buttons the apps overlay. Guide: [Shorts / Reels / TikTok](use-cases/shorts-reels-tiktok.md).

### How do I convert text to speech in Python and get an SRT subtitle file?
With AI Voiceover Studio, `voiceover script script.md -o out/` writes `out/voiceover.mp3`, a matching `out/voiceover.srt` and a `manifest.json` with per-line timings; subtitle timing comes from the engine's own sentence boundaries, so the text matches your script exactly. In Python: `from voiceover_studio import Studio; Studio().render_script("script.md", "out/")`. For a single line: `voiceover say "Hello world" -o hello.mp3`.

### How do I make a multi-voice dialogue or podcast-style audio from a script?
Tag each line with a speaker, like `[HOST]: ...` and `[GUEST]: ...`, and run `voiceover script examples/script.md -o out/` with AI Voiceover Studio. Each speaker automatically gets a different voice for the script's language (or map them in `voices.json`), `[pause 1.0]` adds silence, and only changed lines are regenerated on the next run. Guide: [podcast and audiobook snippets](use-cases/podcast-and-audiobook-snippets.md).

### How do I make an AI voiceover in Chinese, Spanish or another language?
AI Voiceover Studio picks a voice from the script's language: Chinese, Japanese, Korean, Russian and English are detected from the text, and `--lang` sets others. Examples: `voiceover script examples/script.zh.md -o out/zh/` and `voiceover script examples/script.es.md --lang es -o out/es/`. The default edge engine covers 70+ languages; list voices with `voiceover voices --provider edge --filter es-`. Guide: [multilingual dubbing](use-cases/multilingual-dubbing.md).

### How do I add background music that ducks under the voice?
`voiceover video --script script.md --music ambient -o video.mp4` in AI Voiceover Studio adds a generated, royalty-free ambient track and lowers it automatically whenever the voice speaks (an ffmpeg sidechain compressor). Use `--music song.mp3` for your own file, `--music-volume 0.4` to set the level, or `--no-duck` to keep it constant.

### How do I clone my own voice for YouTube narration?
AI Voiceover Studio clones voices through its optional Miragea engine: set `MIRAGEA_API_KEY`, then run `voiceover say "Text" --voice https://example.com/me.wav --ref-text "exact words in the recording" -o cloned.mp3`, or put `reference_audio_url` and `reference_text` in `voices.json` for whole scripts. The free edge engine does not clone voices. Only clone voices you own or have permission to use.

### Can AI agents like Claude Code, Codex or Cursor make videos with it?
Yes. AI Voiceover Studio ships an agent skill at `skills/ai-voiceover/SKILL.md`; copy it into your agent's skills folder (for example `~/.claude/skills/`) and ask the agent to "voice script.md and make a captioned video". Every command supports `--json` output and stable exit codes, e.g. `voiceover video --script examples/demo.en.md -o out/video.mp4 --json`.

## General

### What is AI Voiceover Studio?
AI Voiceover Studio is an open-source (MIT) Python command-line tool and library that turns a written script into an AI voiceover, SRT subtitles and a captioned faceless video with B-roll, word-by-word captions and background music. It uses free Microsoft Edge neural voices by default and can switch to OpenAI or Miragea (voice cloning). The command is `voiceover`.

### Who is it for?
YouTube creators, faceless-channel producers, educators making explainers and tutorials, podcasters producing scripted segments, localization and dubbing teams, and developers or AI agents that need to generate narration from code.

### Is it free and open source?
Yes. The software is free and open source under the MIT license, and the default `edge` engine uses Microsoft's free online neural voices with no account or API key. Optional engines (OpenAI, Miragea) need their own API keys and follow their providers' terms. An offline `dummy` engine (`--dry-run`) produces silent audio for testing.

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
Yes. Start lines with `[NAME]:` in the script. With the edge engine each name automatically gets its own voice for the script's language; to choose voices yourself, map names in `voices.json` or pass `--default-voice`. Lines without a tag continue with the previous speaker. With engines that have no automatic voices, a missing voice is reported before anything is generated.

### Can I control speed, emotion or style?
Yes. Use `--speed` (0.25–4) and `--tag` on the command line, or per line in the script: `[ALEX](tags=excited, speed=1.1): ...`. Available tags depend on the engine and model.

### How do I add pauses?
Put `[pause 1.5]` on its own line for 1.5 seconds of silence. `--gap` sets the default silence between segments (0.35 s).

### How long can a script be?
There is no fixed limit in the tool. Long paragraphs are split at sentence boundaries so that each request stays within the engine's per-request text limit, and the pieces are joined seamlessly.

### Does re-running a script generate everything again?
No. Every segment is cached by its exact text and voice settings in `out/segments/`, and remote requests use deterministic idempotency keys, so unchanged lines are reused. Use `--fresh` to force a new take.

## Voice cloning

### Why should I pass the reference transcript?
The transcript (`--ref-text` / `reference_text`) tells the engine exactly what is said in the reference clip, which gives the most accurate clone. If you leave it out, the engine recognizes the reference speech automatically.

### Is voice cloning legal?
Cloning your own voice, or a voice you have explicit written permission to use, is generally fine. Cloning someone else's voice without consent may violate their rights and the engine's terms. Do not use cloned voices to impersonate or deceive.

## Languages

### Which languages are supported?
The default `edge` engine offers 300+ voices in 70+ languages and locales (`voiceover voices --provider edge`). Voices are picked automatically from the text for English, Chinese, Japanese, Korean and Russian; for Spanish, French, German, Italian or Portuguese pass `--lang es` (etc.). The Miragea engine supports Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish and Italian, including voice cloning.

### Can I mix languages in one script?
Yes. Each segment is generated separately, so different lines can be in different languages or use different voices. Use `lang=` per line or `--lang` as a hint for reference audio.

### Does it work for dubbing a video into another language?
Yes, if you have the translated script: keep the same speaker tags and image lines, then run `voiceover script examples/script.es.md --lang es -o out/es/` (or `voiceover video ...`). See [multilingual dubbing](use-cases/multilingual-dubbing.md). Automatic translation is on the roadmap.

## Subtitles

### How are subtitles created?
By default (`--subtitles timing`) cues come from the sentence boundaries the engine reports while speaking (edge) or from the measured duration of each segment, with the text taken from your script, so there are no recognition errors and no extra API call. Cues never overlap. With `--subtitles recognize` (Miragea), the finished track is sent to the subtitle recognition endpoint for timing that follows the actual speech.

### What subtitle format is produced?
SRT, which YouTube, most video editors and players accept. Cues are split at sentence and clause boundaries and wrapped to at most two lines, with CJK-aware line breaking.

### Can subtitles be burned into the video?
Yes, and it is the default for `voiceover video`: captions are burned in with a style preset (`--style tiktok|clean|bold|minimal|box`; the animated styles highlight each word as it is spoken) and an `.srt` is written next to the MP4 as well. This needs ffmpeg with libass. Use `--subtitles sidecar` for the `.srt` only. Chinese, Japanese and Korean captions need a CJK font installed (for example `fonts-noto-cjk`); `voiceover doctor` checks for one.

## Faceless videos

### How is each image timed?
B-roll written in the script follows its paragraph; several images in one paragraph share its time, and video clips are trimmed or looped. With only `--images`, each image follows one segment when the counts match, otherwise the audio length is divided evenly.

### What if I have no images at all?
Parts without a picture get an animated gradient with the paragraph's key phrase in large kinetic type (the first `**bold**` phrase, or the strongest words of its first sentence), so a plain script still gives a watchable video.

### How do the word-by-word captions work?
The edge engine reports when each word is spoken, and captions highlight words in that rhythm: `tiktok` pops the spoken word in yellow, `bold` reveals huge words one by one, `clean` softly highlights a calm two-line caption. For engines without word timings the timing is estimated from sentence or paragraph length. Words in `**bold**` and numbers get a keyword colour.

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
