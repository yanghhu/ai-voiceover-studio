# Make a faceless YouTube video with AI from a script

**Short answer:** with [AI Voiceover Studio](../../README.md) you write the narration in a Markdown file, put an image or clip above each paragraph, and run one command. You get a 1080p MP4 with an AI voiceover, B-roll with Ken Burns motion, word-by-word captions, an animated hook card and background music — using free neural voices, with no account or API key.

## Run it

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio && cd ai-voiceover-studio
pip install -e ".[edge]"
voiceover video --script examples/demo.en.md --style tiktok --music ambient -o out/faceless.mp4
```

Output: `out/faceless.mp4` (1920×1080), `out/faceless.srt` (upload it to YouTube Studio → *Subtitles*), and the voiceover track in `out/faceless_voiceover/`. Needs Python 3.9+ and ffmpeg; run `voiceover doctor` if anything is missing. This is the command that produced the [16:9 demo](../assets/demo.mp4).

## Write your own script

```markdown
# Cleopatra vs. the Moon landing

![](broll/en/01-pyramid.jpg)
Cleopatra lived closer to the **Moon landing** than to the building of the Great Pyramid.

![](broll/en/02-build.jpg)
The pyramid at Giza was finished around 2560 BC. Cleopatra was born about **2,500 years** later.
```

- The `# heading` becomes the hook card shown in the first seconds (`--hook "..."` to override, `--no-hook` to remove).
- `![](file)` sets the picture or video clip for the paragraph below it; paths are relative to the script.
- `**bold**` words are highlighted in the captions.
- No pictures yet? Leave the image lines out and each paragraph gets animated kinetic typography instead.

## Useful options

| Goal | Option |
| --- | --- |
| Calm captions instead of big words | `--style clean` |
| Your own music, quieter | `--music song.mp3 --music-volume 0.35` |
| A specific voice | `--default-voice en-GB-RyanNeural` (list: `voiceover voices --provider edge --filter en-`) |
| Use a folder of images in name order | `--images my-broll/` |
| Matching font of the demo | `--font Montserrat-ExtraBold.ttf` |
| Preview offline, no voice service | `--dry-run` |

Related: [Shorts / Reels / TikTok](shorts-reels-tiktok.md) · [FAQ](../FAQ.md)
