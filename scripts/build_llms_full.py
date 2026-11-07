"""Regenerate llms-full.txt: the project's docs concatenated into one plain file for LLMs.

Run from the repository root:  python scripts/build_llms_full.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = "https://raw.githubusercontent.com/yanghhu/ai-voiceover-studio/main/"
FILES = [
    "README.md",
    "docs/FAQ.md",
    "docs/use-cases/faceless-youtube.md",
    "docs/use-cases/shorts-reels-tiktok.md",
    "docs/use-cases/explainer-and-recap-narration.md",
    "docs/use-cases/multilingual-dubbing.md",
    "docs/use-cases/podcast-and-audiobook-snippets.md",
    "skills/ai-voiceover/SKILL.md",
    "CHANGELOG.md",
]


def main() -> None:
    parts = [(ROOT / "llms.txt").read_text(encoding="utf-8").split("\n## ")[0].rstrip(),
             "\nThis file concatenates the project's documentation. Each part starts with its source URL.\n"]
    for name in FILES:
        text = (ROOT / name).read_text(encoding="utf-8").strip()
        parts.append("\n\n" + "=" * 80 + "\nSource: " + RAW + name + "\n" + "=" * 80 + "\n\n" + text + "\n")
    (ROOT / "llms-full.txt").write_text("".join(parts), encoding="utf-8")
    print("wrote llms-full.txt")


if __name__ == "__main__":
    main()
