# Make YouTube Shorts, Instagram Reels and TikToks with word-by-word captions

**Short answer:** add `--vertical` to the `voiceover video` command of [AI Voiceover Studio](../../README.md). The video is rendered at 1080×1920, captions switch to the TikTok-style word-by-word preset (1–4 big words, the spoken word pops in yellow, keywords in green), and they stay above the area the apps cover with buttons.

## Run it

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio && cd ai-voiceover-studio
pip install -e ".[edge]"
voiceover video --script examples/demo.zh.md --vertical --music ambient -o out/short.mp4
```

This is the command that produced the [9:16 Chinese demo](../assets/demo-short-zh.mp4). For an English Short from the same kind of script:

```bash
voiceover video --script examples/demo.en.md --vertical --music pulse -o out/short-en.mp4
```

Chinese, Japanese and Korean captions need a CJK font (for example `fonts-noto-cjk`); `voiceover doctor` checks for one, and `--font NotoSansSC-Bold.otf` picks a specific file.

## Tips for short-form

- Keep it under 60 seconds: roughly 130–160 English words or 250–300 Chinese characters.
- Put the hook in the `# heading`; it is shown as an animated card for the first 2.2 s (`--hook-seconds` to change).
- Mark one or two keywords per paragraph with `**bold**` so they light up in the captions.
- `--fit contain` keeps landscape images whole on a blurred background instead of cropping them.
- `--style bold` reveals huge words one by one; `--style clean` gives calmer two-line captions.

Related: [Faceless YouTube](faceless-youtube.md) · [Multilingual dubbing](multilingual-dubbing.md) · [FAQ](../FAQ.md)
