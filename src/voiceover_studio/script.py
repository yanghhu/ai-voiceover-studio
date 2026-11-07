"""Script parsing: Markdown / plain text -> speaker segments.

Format (all optional)::

    # Title lines and other Markdown headings are ignored
    [NARRATOR]: Every line can name its speaker.
    Lines without a tag continue with the current speaker.

    [ALEX]: Hi! **Markdown** emphasis and [links](https://x.y) are stripped.
    [pause 1.5]
    [ALEX](tags=excited, speed=1.1): Per-line options in parentheses.

A blank line ends a paragraph; each paragraph becomes one segment (long ones are
split at sentence boundaries to respect the provider's text limit).
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_SPEAKER = "NARRATOR"

_TAG = re.compile(r"^\s*(?:[-*]\s+)?\[(?P<name>[^\]\n]{1,40})\]\s*(?:\((?P<opts>[^)]*)\))?\s*:\s*(?P<text>.*)$")
_PAUSE = re.compile(r"^\s*\[(?:pause|break)\s*(?P<sec>\d+(?:\.\d+)?)?\s*s?\]\s*$", re.I)
_SENTENCE = re.compile(r"(?<=[.!?。！？…])\s+|(?<=[。！？])")


@dataclass
class Segment:
    speaker: str
    text: str
    pause_after: float = 0.0
    options: Dict[str, Any] = field(default_factory=dict)
    index: int = 0


def clean_markdown(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)              # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)          # links
    text = re.sub(r"`([^`]*)`", r"\1", text)                       # inline code
    text = re.sub(r"(\*\*|__|\*|_|~~)(?=\S)(.+?)(?<=\S)\1", r"\2", text)  # emphasis
    text = re.sub(r"^\s*(?:>|[-*+]\s|\d+\.\s)\s*", "", text)        # quotes / bullets
    return re.sub(r"\s+", " ", text).strip()


def _parse_options(raw: Optional[str]) -> Dict[str, Any]:
    opts: Dict[str, Any] = {}
    if not raw:
        return opts
    for part in re.split(r";|,(?=\s*\w+\s*=)", raw):
        if "=" not in part:
            continue
        key, value = (s.strip() for s in part.split("=", 1))
        key = key.lower()
        if key == "speed":
            try:
                opts["speed"] = float(value)
            except ValueError:
                continue
        elif key in ("tag", "tags"):
            opts["tags"] = [t.strip() for t in re.split(r"[|,]", value) if t.strip()]
        elif key in ("model", "language", "lang"):
            opts["language" if key == "lang" else key] = value
    return opts


def split_text(text: str, max_chars: int) -> List[str]:
    """Split at sentence ends (then commas, then hard) so each chunk <= max_chars."""
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]
    chunks: List[str] = []
    current = ""
    pieces = [p for p in _SENTENCE.split(text) if p and p.strip()]
    for piece in pieces:
        piece = piece.strip()
        while len(piece) > max_chars:
            cut = max(piece.rfind(", ", 0, max_chars), piece.rfind("，", 0, max_chars),
                      piece.rfind(" ", 0, max_chars))
            cut = cut + 1 if cut > max_chars // 3 else max_chars
            head, piece = piece[:cut].strip(), piece[cut:].strip()
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        joiner = "" if (current and _is_cjk(current[-1])) else " "
        candidate = (current + joiner + piece).strip() if current else piece
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks


def _is_cjk(ch: str) -> bool:
    return bool(re.match(r"[\u3000-\u30ff\u3400-\u9fff\uac00-\ud7af\uff00-\uffef]", ch))


def parse_script(source: str, *, default_speaker: str = DEFAULT_SPEAKER,
                 max_chars: int = 0) -> List[Segment]:
    """Parse script text (not a path) into segments."""
    segments: List[Segment] = []
    speaker = default_speaker
    options: Dict[str, Any] = {}
    buffer: List[str] = []
    in_fence = False
    in_comment = False

    def flush() -> None:
        nonlocal buffer
        text = clean_markdown(" ".join(buffer))
        buffer = []
        if not text:
            return
        for chunk in split_text(text, max_chars):
            segments.append(Segment(speaker, chunk, options=dict(options)))

    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if in_comment or stripped.startswith("<!--"):
            in_comment = "-->" not in stripped
            continue
        if not stripped:
            flush()
            continue
        if stripped.startswith("#") or re.fullmatch(r"[-*_=]{3,}", stripped) \
                or (stripped.startswith("|") and stripped.endswith("|")):
            flush()
            continue
        pause = _PAUSE.match(stripped)
        if pause:
            flush()
            seconds = float(pause.group("sec") or 1.0)
            if segments:
                segments[-1].pause_after += seconds
            else:
                segments.append(Segment(speaker, "", pause_after=seconds))
            continue
        tag = _TAG.match(line)
        if tag and not tag.group("name").lower().startswith(("pause", "break")):
            flush()
            speaker = tag.group("name").strip().upper()
            options = _parse_options(tag.group("opts"))
            line = tag.group("text")
        buffer.append(line)
    flush()
    for i, seg in enumerate(segments):
        seg.index = i
    return segments


def speakers(segments: List[Segment]) -> List[str]:
    seen: List[str] = []
    for seg in segments:
        if seg.text and seg.speaker not in seen:
            seen.append(seg.speaker)
    return seen
