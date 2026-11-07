# Podcast intros, trailers and audiobook samples with multi-voice text to speech

**Short answer:** [AI Voiceover Studio](../../README.md) turns a tagged script into one mixed audio file with a different voice per character, controlled pauses and an SRT transcript. That makes it a quick way to produce podcast intros and outros, episode trailers, ad reads and audiobook sample chapters from text.

## Run it

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio && cd ai-voiceover-studio
pip install -e ".[edge]"
voiceover script examples/script.md --voices examples/voices.edge.json --gap 0.5 -o out/podcast/
```

Output: `out/podcast/voiceover.mp3`, `voiceover.srt` (a timed transcript), one clip per line in `segments/` and `manifest.json`. Use `--name episode-intro.wav` for uncompressed audio.

## Script format

```markdown
[HOST]: Welcome back to the show. Today: why the sky is blue.

[GUEST](tags=curious, speed=1.05): I always thought sunlight was yellow!

[pause 1.0]

[HOST]: Let's find out.
```

- Each `[NAME]:` gets its own voice automatically, or map names to voices in `voices.json`.
- `[pause 1.0]` inserts silence; `--gap` sets the default gap between lines.
- For audiobook narration, a slightly slower pace often sounds better: `--speed 0.95`.
- Re-running only regenerates lines you changed, so long chapters are cheap to revise.

## A single line

```bash
voiceover say "Thanks for listening — see you next week." -o outro.mp3
```

Use only voices you have the right to use; cloning (Miragea engine) requires the speaker's permission.

Related: [Explainer narration](explainer-and-recap-narration.md) · [FAQ](../FAQ.md)
