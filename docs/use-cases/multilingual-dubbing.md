# Multilingual dubbing: one video, several languages

**Short answer:** write (or translate) one script per language with the same speaker tags and image lines, then run [AI Voiceover Studio](../../README.md) once per script. Voices are picked automatically for each language — detected from the text for English, Chinese, Japanese, Korean and Russian, or set with `--lang` (for example `--lang es` gives Álvaro and Elvira) — so the same video comes out dubbed in every language with matching captions.

## Run it

The repository ships the same two-voice explainer in English, Chinese and Spanish:

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio && cd ai-voiceover-studio
pip install -e ".[edge]"
voiceover script examples/script.md    -o out/en/
voiceover script examples/script.zh.md -o out/zh/
voiceover script examples/script.es.md -o out/es/ --lang es
```

`--lang` is needed for Latin-script languages other than English (Spanish, French, German, Italian, Portuguese), because the text alone does not tell them apart reliably. Each folder gets `voiceover.mp3` and `voiceover.srt` in that language. For finished videos with burned-in captions, use `voiceover video` the same way:

```bash
voiceover video --script examples/script.es.md --lang es --images examples/broll/en -o out/es.mp4
```

## Tips

- Keep the same paragraph order and `![](...)` lines in every language, so the pictures stay in sync.
- Choose voices per language with a voices file (`"NARRATOR": {"actor_id": "es-MX-JorgeNeural"}`); list them with `voiceover voices --provider edge --filter es-`.
- The free edge engine covers 70+ languages and locales. To keep the *same* voice across languages, use a cloned voice with the Miragea engine (`reference_audio_url` in `voices.json`).
- Translation is up to you (or your translation tool); automatic translate-and-dub is on the roadmap.

Related: [Shorts / Reels / TikTok](shorts-reels-tiktok.md) · [FAQ](../FAQ.md)
