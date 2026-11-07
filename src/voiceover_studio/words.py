"""Word-level timing for animated (karaoke) captions.

Engines that report word boundaries (edge) give exact times. For every other
engine the time of a sentence, or of the whole segment, is shared between its
words by a simple reading-length weight, which is close enough for captions
that highlight one word at a time.

Times here are absolute seconds in the final voiceover track.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\uf900-\ufaff]")
_TOKEN = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\uf900-\ufaff]|[^\s\u3040-\u30ff\u3400-\u9fff"
                    r"\uac00-\ud7af\uf900-\ufaff\u3000-\u303f\uff00-\uffef]+")
SENTENCE_END = ".!?。！？…"
#: CJK particles that read badly at the start of a caption page
NO_PAGE_START = "的了吗呢吧啊着过地得们"
CLAUSE_END = ",;:，；：、—–"
_PUNCT = SENTENCE_END + CLAUSE_END + "\"'“”‘’()（）《》「」『』[]【】-"
_STOP = {"a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "for", "by", "with", "is", "are",
         "was", "were", "be", "been", "it", "its", "this", "that", "as", "so", "than", "then", "from", "into",
         "you", "your", "we", "our", "they", "their", "he", "she", "his", "her", "i", "me", "my", "do", "does",
         "did", "not", "no", "yes", "just", "only", "about", "what", "where", "when", "who", "how", "why",
         "there", "here", "even", "still", "already", "while", "before", "after", "more", "most", "very"}


@dataclass
class Word:
    start: float
    end: float
    text: str
    tail: str = ""          # punctuation that followed the word in the script
    key: bool = False       # highlighted keyword (**bold** in the script, or a number)

    @property
    def cjk(self) -> bool:
        return bool(CJK.search(self.text))


@dataclass
class Page:
    """Words shown together on screen."""
    words: List[Word] = field(default_factory=list)
    start: float = 0.0
    end: float = 0.0

    @property
    def text(self) -> str:
        return join_words([w.text for w in self.words])


def join_words(parts: Sequence[str]) -> str:
    """Join caption words: no space between two CJK words, one space otherwise."""
    out = ""
    for part in parts:
        if out and not (CJK.search(out[-1]) and CJK.search(part[:1] or " ")):
            out += " "
        out += part
    return out


def weight(text: str) -> float:
    """Rough reading length: CJK characters ~ syllables, Latin ~ letters / 3."""
    cjk = len(CJK.findall(text))
    other = len(re.sub(r"\s", "", text)) - cjk
    return cjk * 1.0 + other / 3.0 + 0.4


def tokenize(text: str) -> List[str]:
    """Split text into caption words: Latin words by spaces, CJK into short runs (2 characters,
    keeping a run of 3 together rather than leaving one character alone)."""
    tokens: List[str] = []
    run = ""
    for tok in _TOKEN.findall(text):
        if CJK.fullmatch(tok):
            run += tok
            continue
        if run:
            tokens.extend(_cjk_runs(run))
            run = ""
        tok = tok.strip(_PUNCT)
        if tok:
            tokens.append(tok)
    if run:
        tokens.extend(_cjk_runs(run))
    return tokens


def _cjk_runs(run: str) -> List[str]:
    out = []
    i = 0
    while i < len(run):
        size = 3 if len(run) - i == 3 else 2
        out.append(run[i:i + size])
        i += size
    return out


def _clean(word: str) -> str:
    return word.strip().strip(_PUNCT).strip()


def align(text: str, words: List[Word]) -> List[Word]:
    """Attach the punctuation that follows each word in ``text`` (``tail``), in place."""
    pos = 0
    for i, word in enumerate(words):
        found = text.find(word.text, pos) if word.text else -1
        if found < 0:
            found = text.lower().find(word.text.lower(), pos)
        if found < 0:
            continue
        pos = found + len(word.text)
        nxt = len(text)
        if i + 1 < len(words) and words[i + 1].text:
            j = text.find(words[i + 1].text, pos)
            nxt = j if j >= 0 else nxt
        tail = "".join(ch for ch in text[pos:nxt] if ch in SENTENCE_END + CLAUSE_END + "?!？！")
        word.tail = tail
    return words


def sentences_from_words(text: str, words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group engine word boundaries (relative ``start``/``end``/``text``) into sentences
    using the punctuation of ``text``. Returns the same shape as engine sentence boundaries."""
    items = [Word(float(w.get("start", 0)), float(w.get("end", 0)), _clean(str(w.get("text", ""))))
             for w in words if _clean(str(w.get("text", "")))]
    if not items:
        return []
    align(text, items)
    out: List[Dict[str, Any]] = []
    current: List[Word] = []
    for word in items:
        current.append(word)
        if any(ch in SENTENCE_END for ch in word.tail):
            out.append(_sentence(current))
            current = []
    if current:
        out.append(_sentence(current))
    return out


def _sentence(words: List[Word]) -> Dict[str, Any]:
    text = join_words([w.text + w.tail for w in words])
    return {"start": round(words[0].start, 3), "end": round(words[-1].end, 3), "text": text}


def estimate(start: float, end: float, text: str) -> List[Word]:
    """Spread ``text`` over ``[start, end]`` by reading weight (pauses after punctuation)."""
    tokens = tokenize(text)
    if not tokens:
        return []
    words = align(text, [Word(0, 0, t) for t in tokens])
    weights = [weight(w.text) + (0.9 if any(c in SENTENCE_END for c in w.tail) else
                                 0.45 if w.tail else 0.0) for w in words]
    total = sum(weights) or 1.0
    t = start
    for w, wt in zip(words, weights):
        span = (end - start) * wt / total
        w.start = t
        speak = weight(w.text) / wt if wt else 1.0
        w.end = t + span * speak
        t += span
    return words


def _mark_keys(words: List[Word], emphasis: Iterable[str]) -> None:
    phrases = [e.strip() for e in emphasis if e and e.strip()]
    lowered = [p.lower() for p in phrases]
    key_tokens = set()
    for p in lowered:
        key_tokens.update(_clean(t) for t in p.split())
    for w in words:
        lw = w.text.lower()
        if any(ch.isdigit() for ch in w.text):
            w.key = True
        elif w.cjk:
            w.key = any(lw in p for p in lowered)
        elif lw in key_tokens and lw not in _STOP:
            w.key = True


def segment_words(segment: Any) -> List[Word]:
    """Absolute word timings for one rendered segment (``SegmentResult``-like object)."""
    meta = getattr(segment, "meta", None) or {}
    base = float(segment.start)
    raw = [w for w in meta.get("words") or [] if _clean(str(w.get("text", "")))]
    words: List[Word] = []
    if raw:
        for w in raw:
            text = _clean(str(w["text"]))
            s, e = base + float(w.get("start", 0)), base + float(w.get("end", 0))
            if CJK.search(text) and len(text) > 4:  # long CJK token: split so it can wrap
                words.extend(estimate(s, e, text))
            else:
                words.append(Word(s, max(e, s + 0.05), text))
        align(segment.text, words)
    else:
        sentences = [s for s in meta.get("sentences") or []
                     if str(s.get("text", "")).strip() and float(s.get("end", 0)) > float(s.get("start", 0))]
        if sentences:
            for s in sentences:
                words.extend(estimate(base + float(s["start"]), base + float(s["end"]), str(s["text"])))
        else:
            words = estimate(base, float(segment.end), segment.text)
    for a, b in zip(words, words[1:]):
        if a.end > b.start:
            a.end = b.start
    _mark_keys(words, getattr(segment, "emphasis", None) or [])
    return words


def paginate(words: List[Word], *, max_weight: float, max_words: int, lines: int = 1,
             gap: float = 0.45, hold: float = 0.6) -> List[Page]:
    """Group words into on-screen pages: a page ends at a sentence end, at a pause, when it
    would not fit (``max_weight`` per line x ``lines``), or after ``max_words``. A comma ends a
    page that is already more than half full."""
    pages: List[Page] = []
    current: List[Word] = []
    budget = max_weight * lines

    def size(ws: List[Word]) -> float:
        return sum(len(w.text) * (2 if w.cjk else 1) + (0 if w.cjk else 1) for w in ws)

    for i, word in enumerate(words):
        ends_sentence = any(ch in SENTENCE_END + "?!？！" for ch in word.tail)
        # a short last word of a sentence may overflow a little rather than sit alone
        slack = 4 if (word.tail and size([word]) <= 4) else 0
        if word.cjk and word.text[0] in NO_PAGE_START:
            slack = max(slack, 2 * len(word.text))
        particle = word.cjk and word.text[0] in NO_PAGE_START
        if current and (size(current + [word]) > budget + slack
                        or (len(current) >= max_words and not particle)
                        or word.start - current[-1].end > gap):
            pages.append(Page(current))
            current = []
        current.append(word)
        # CJK captions break at every comma; Latin ones once the page is half full
        ends_clause = bool(word.tail) and (word.cjk or size(current) >= budget * 0.5)
        if ends_sentence or ends_clause:
            pages.append(Page(current))
            current = []
    if current:
        pages.append(Page(current))
    for i, page in enumerate(pages):
        page.start = page.words[0].start
        page.end = page.words[-1].end + 0.25
        if i + 1 < len(pages):
            nxt = pages[i + 1].words[0].start
            page.end = nxt if nxt - page.words[-1].end < hold else min(page.end, nxt)
    return pages


def key_phrase(segment: Any, max_words: int = 4) -> str:
    """Short phrase for big kinetic text: the first **bold** phrase, else the strongest words
    of the first sentence."""
    emphasis = [e for e in getattr(segment, "emphasis", None) or [] if e.strip()]
    if emphasis:
        return emphasis[0].strip()
    text = str(segment.text).strip()
    first = re.split(r"(?<=[.!?。！？])\s*", text)[0] or text
    if CJK.search(first):
        first = re.split(r"[，,；;：:。！？]", first)[0]
        return first[:10]
    words = [w.strip(_PUNCT) for w in first.split() if w.strip(_PUNCT)]
    if len(words) <= max_words:
        return " ".join(words)
    strong = [(i, w) for i, w in enumerate(words) if w.lower() not in _STOP]
    best = sorted(strong, key=lambda iw: (-len(iw[1]), iw[0]))[:max_words]
    return " ".join(w for _, w in sorted(best))
