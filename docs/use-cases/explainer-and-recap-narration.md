# Narrate explainers, tutorials and movie recaps with AI voiceover

**Short answer:** [AI Voiceover Studio](../../README.md) voices your script paragraph by paragraph and shows each image, slide or video clip exactly while its paragraph is spoken. Put a folder of slides or clips next to a narration script and one command gives you a narrated, captioned MP4 plus the separate voiceover track and SRT for your editor.

## Run it

Narrate a folder of images or clips, used in file-name order, one per paragraph:

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio && cd ai-voiceover-studio
pip install -e ".[edge]"
voiceover video --script examples/script.md --images examples/broll/en --style clean -o out/explainer.mp4
```

`examples/script.md` is a two-voice science explainer (`[NARRATOR]` and `[ALEX]`); each speaker gets a different voice automatically.

## Movie and series recaps

Cut your scenes into short clips (`01.mp4`, `02.mp4`, …) and reference them in the script, one per paragraph:

```markdown
# The ending, explained

![](clips/01.mp4)
In the final scene, the detective finally realises the letters were never from her sister.

![](clips/02.mp4)
That changes **everything** we saw in the first episode.
```

```bash
voiceover video --script recap.md --style clean --transition-style cut --grade none -o recap.mp4
```

Clips are trimmed or looped to the length of their paragraph. Use only footage you have the right to use, and check the platform's rules on commentary and fair use.

## Audio only, for your own editor

```bash
voiceover script examples/script.md -o out/narration/
```

Gives `out/narration/voiceover.mp3`, `voiceover.srt` and a `manifest.json` with the start and end time of every paragraph, so you can line up cuts in Premiere, DaVinci Resolve or CapCut.

Related: [Faceless YouTube](faceless-youtube.md) · [Podcast and audiobook snippets](podcast-and-audiobook-snippets.md) · [FAQ](../FAQ.md)
