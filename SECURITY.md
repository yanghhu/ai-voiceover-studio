# Security Policy

## Supported versions

Security fixes are made on the latest release on the `main` branch.

| Version | Supported |
| --- | --- |
| 0.3.x | ✅ |
| < 0.3 | ❌ |

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report them privately through GitHub:
[Security → Report a vulnerability](https://github.com/yanghhu/ai-voiceover-studio/security/advisories/new).
Include the version (`voiceover --version`), the command or code that triggers the problem, and what
you expected to happen. Remove API keys and private URLs from anything you send.

You can expect an acknowledgement within a few days. Once the issue is confirmed, a fix and an
advisory are published, and you are credited unless you prefer otherwise.

## What is in scope

- Leaks of API keys (`MIRAGEA_API_KEY`, `OPENAI_API_KEY`) through output, logs, `manifest.json`,
  cache files or requests to hosts other than the configured API host
- Path traversal or arbitrary file writes from script content, `voices.json` or B-roll paths
- Command injection through file names, fonts or other values passed to ffmpeg
- Unsafe handling of downloaded audio or redirects

Problems in third-party engines (Microsoft Edge voices, OpenAI, Miragea) or in ffmpeg itself should
be reported to those projects.

## How keys are handled

Keys are read only from environment variables, sent only in the `Authorization` header to the API
host, never printed or written to disk, and not sent when downloading result files. Authenticated
requests do not follow redirects.
