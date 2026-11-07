"""SRT helpers: build cues from known segment timing, parse/format SRT."""
import re
from dataclasses import dataclass
from typing import Iterable, List

from .providers.base import TranscriptSegment

_CJK = re.compile(r"[\u3000-\u30ff\u3400-\u9fff\uac00-\ud7af\uff00-\uffef]")


@dataclass
class Cue:
    start: float
    end: float
    text: str
    speaker: str = ""


def format_timestamp(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def parse_timestamp(value: str) -> float:
    h, m, rest = value.strip().replace(".", ",").split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def to_srt(cues: Iterable[Cue]) -> str:
    blocks = []
    for n, cue in enumerate((c for c in cues if c.text.strip()), 1):
        blocks.append("%d\n%s --> %s\n%s\n" % (n, format_timestamp(cue.start),
                                               format_timestamp(cue.end), cue.text.strip()))
    return "\n".join(blocks)


def parse_srt(text: str) -> List[TranscriptSegment]:
    out = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if "-->" in line:
                start, end = line.split("-->")
                out.append(TranscriptSegment(parse_timestamp(start), parse_timestamp(end.split()[0]),
                                             "\n".join(lines[i + 1:]).strip()))
                break
    return out


def _weight(text: str) -> float:
    cjk = len(_CJK.findall(text))
    return cjk * 2.0 + (len(text) - cjk) + 1.0


_NO_LINE_START = "，。！？；：、）》」』,.!?;:)"
_SENT_END = re.compile(r"(?<=[.!?。！？…])\s*")
_CLAUSE = re.compile(r"(?<=[,;:，；：、])\s*")


def _join(a: str, b: str) -> str:
    if not a:
        return b
    return a + ("" if _CJK.match(a[-1]) or _CJK.match(b[:1] or " ") else " ") + b


def wrap(text: str, width: int) -> str:
    """Wrap to at most two balanced lines of ~width (CJK characters count double)."""
    if _weight(text) - 1 <= width:
        return text
    if _CJK.search(text) and " " not in text.strip():
        mid = len(text) // 2
        best = None
        for i in range(1, len(text)):  # prefer a break right after punctuation near the middle
            if text[i - 1] in _NO_LINE_START and text[i] not in _NO_LINE_START:
                if best is None or abs(i - mid) < abs(best - mid):
                    best = i
        cut = best if best is not None and abs(best - mid) <= len(text) // 4 else mid
        while cut < len(text) and text[cut] in _NO_LINE_START:
            cut += 1
        return text[:cut] + "\n" + text[cut:]
    words = text.split()
    best_i, best_diff = 1, None
    for i in range(1, len(words)):
        diff = abs(len(" ".join(words[:i])) - len(" ".join(words[i:])))
        if best_diff is None or diff < best_diff:
            best_i, best_diff = i, diff
    return " ".join(words[:best_i]) + "\n" + " ".join(words[best_i:])


def _greedy(pieces: List[str], max_chars: int) -> List[str]:
    out: List[str] = []
    current = ""
    for piece in pieces:
        candidate = _join(current, piece)
        if current and _weight(candidate) - 1 > max_chars:
            out.append(current)
            current = piece
        else:
            current = candidate
    if current:
        out.append(current)
    return out


def _hard_split(text: str, max_chars: int) -> List[str]:
    out = []
    while _weight(text) - 1 > max_chars:
        step = max_chars // 2 if _CJK.search(text) else max_chars
        cut = text.rfind(" ", 0, step)
        cut = cut if cut > step // 3 else step
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    return out + ([text] if text else [])


def chunk_text(text: str, max_chars: int = 84) -> List[str]:
    """Split one segment's text into subtitle-sized cues: sentences first, then
    clauses, then words."""
    units: List[str] = []
    for sentence in (p.strip() for p in _SENT_END.split(text) if p.strip()):
        if _weight(sentence) - 1 <= max_chars:
            units.append(sentence)
            continue
        for clause in _greedy([c.strip() for c in _CLAUSE.split(sentence) if c.strip()], max_chars):
            units.extend(_hard_split(clause, max_chars))
    return [c for c in _greedy(units, max_chars) if c]


def cues_from_timing(items: Iterable[tuple], max_chars: int = 84, line_width: int = 42) -> List[Cue]:
    """``items`` = (start, end, text) per voiced segment; time is shared by character weight."""
    cues: List[Cue] = []
    for start, end, text in items:
        parts = chunk_text(text, max_chars)
        total = sum(_weight(p) for p in parts) or 1.0
        t = start
        for part in parts:
            length = (end - start) * _weight(part) / total
            cues.append(Cue(t, t + length, wrap(part, line_width)))
            t += length
    return cues


def cues_from_transcript(segments: Iterable[TranscriptSegment], line_width: int = 42) -> List[Cue]:
    return [Cue(s.start, s.end, wrap(s.text, line_width)) for s in segments if s.text]


def cues_from_segments(results: Iterable, max_chars: int = 84, line_width: int = 42) -> List[Cue]:
    """Cues for rendered segments (objects with ``start``, ``end``, ``text`` and ``meta``).

    When the engine reported sentence timings (``meta["sentences"]``, seconds relative
    to the clip) they are used directly, so captions follow the actual speech;
    otherwise the segment's time is shared by character weight."""
    cues: List[Cue] = []
    for res in results:
        sentences = [s for s in (getattr(res, "meta", None) or {}).get("sentences") or []
                     if str(s.get("text", "")).strip() and float(s.get("end", 0)) > float(s.get("start", 0))]
        if not sentences:
            for cue in cues_from_timing([(res.start, res.end, res.text)], max_chars, line_width):
                cue.speaker = getattr(res, "speaker", "")
                cues.append(cue)
            continue
        for i, sent in enumerate(sentences):
            start = res.start + float(sent["start"])
            if i + 1 < len(sentences):  # hold the caption until the next sentence starts
                end = res.start + float(sentences[i + 1]["start"])
            else:
                end = min(res.end, res.start + float(sent["end"]) + 0.4)
            if end - start < 0.2:
                end = start + 0.2
            for cue in cues_from_timing([(start, end, str(sent["text"]).strip())], max_chars, line_width):
                cue.speaker = getattr(res, "speaker", "")
                cues.append(cue)
    for a, b in zip(cues, cues[1:]):  # never overlap: one caption on screen at a time
        if a.end > b.start:
            a.end = max(a.start + 0.1, b.start)
    return cues
