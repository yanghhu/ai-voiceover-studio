# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-07

### Added
- `voiceover say`: text to speech for a single line, with actor ids or a reference-audio URL (voice cloning).
- `voiceover script`: multi-speaker Markdown/TXT scripts (`[SPEAKER]:` tags, `[pause N]`, per-line
  `tags`/`speed`/`model`/`lang`), speaker → voice mapping via `voices.json` / `voices.yaml`,
  concatenation with configurable gaps, `manifest.json`, and a per-segment cache.
- SRT subtitles from segment timing (default) or provider speech recognition (`--subtitles recognize`).
- `voiceover video`: faceless slideshow video (moviepy) with sidecar or burned-in subtitles,
  landscape or vertical sizes.
- `voiceover voices` (account voice list, pagination) and `voiceover task` (resume/inspect a task).
- Provider interface (`VoiceProvider`) with entry-point discovery; built-in `miragea` provider
  (async tasks, polling, deterministic idempotency keys, retry on retryable errors, clear
  401/403/409/413/429 messages) and offline `dummy` provider.
- Agent skill `skills/ai-voiceover/SKILL.md`, `--json` output and stable exit codes.
- Offline test-suite with mocked HTTP.
