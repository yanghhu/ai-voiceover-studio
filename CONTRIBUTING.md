# Contributing to AI Voiceover Studio

Thanks for helping! Bug reports, docs fixes, new voice providers and features are all welcome.

## Development setup

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio.git
cd ai-voiceover-studio
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,video,yaml]"
pytest
voiceover script examples/script.md --dry-run -o out/
```

The test-suite runs fully offline. Never call a paid endpoint from tests: use the
`FakeTransport` in `tests/conftest.py` or the `dummy` provider.

## Guidelines

- **Keep the core dependency-free.** The package must work with the Python 3.9+ standard
  library alone. Heavy dependencies belong behind an optional extra.
- **Tests for every change.** Anything that talks to a network gets mocked HTTP tests.
- **Secrets stay secret.** Never print, log or persist API keys; never commit keys,
  `voices.json` with private URLs, or generated media.
- **Small, focused PRs** with a line in `CHANGELOG.md` under *Unreleased*.
- Style: readable code over clever code; type hints on public functions.

## Adding a provider

1. Subclass `voiceover_studio.providers.base.VoiceProvider` and implement `synthesize()`
   (optionally `list_voices()` and `transcribe()`).
2. Publish it as its own package and register the entry point
   `ai_voiceover_studio.providers`, or open a PR if it is broadly useful and dependency-free.
3. Add tests that run without network access.

## Reporting bugs

Include the command you ran (with `--json -v` if possible), the `manifest.json` if relevant,
your OS and Python version. Remove API keys and private URLs first.

## Voice ethics

Only clone voices you own or have explicit permission to use. PRs that facilitate
impersonation without consent will not be accepted.
