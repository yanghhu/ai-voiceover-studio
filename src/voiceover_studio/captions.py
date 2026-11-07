"""Styled captions: subtitle cues or word timings -> an ASS file that ffmpeg/libass burns in.

Sizes are derived from the video size, so the same style looks right in
1920x1080, 1280x720 and vertical 1080x1920, and positions keep clear of the
areas that TikTok / Shorts / Reels cover with their own buttons.

Animated styles (word-by-word, from engine word timings or an estimate):

* ``tiktok``  2-4 big words at a time, thick outline, the spoken word pops and turns
  yellow, keywords stay green (default for vertical video)
* ``bold``    huge words in the middle, revealed one by one as they are spoken
* ``clean``   one or two calm lines in the lower third, the spoken word lightly
  highlighted (default for landscape video)

Static styles (one subtitle line at a time):

* ``minimal`` small, thin outline, for screen recordings
* ``box``     white text on a translucent dark box

The same file also carries the optional hook/title card and the large kinetic
key phrases shown when a part of the video has no picture.
"""
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from .errors import ConfigError
from .subtitles import Cue
from .words import CJK, Page, Word, join_words, paginate


@dataclass(frozen=True)
class CaptionStyle:
    name: str
    size: float              # font size as a fraction of the short side
    primary: str             # ASS colour &HAABBGGRR
    outline_colour: str
    back_colour: str
    border_style: int        # 1 outline + shadow, 3 opaque box
    outline: float           # fraction of the short side
    shadow: float            # fraction of the short side
    alignment: int           # numpad layout: 2 bottom centre, 5 middle centre
    margin_v: float          # fraction of height (static styles)
    bold: bool = True
    accent: str = "&H0044CCFF"  # speaker label colour
    uppercase: bool = False
    mode: str = "static"     # static | pop | reveal | line
    active: str = "&H0000D7FF"   # colour of the word being spoken
    key: str = "&H0071F07C"      # colour of keywords
    words_vertical: int = 3      # max words per page (animated styles)
    words_landscape: int = 5
    lines: int = 1
    y_vertical: float = 0.66     # caption baseline as a fraction of the height
    y_landscape: float = 0.86
    pop: int = 118               # start scale (%) of the spoken word (pop mode)


STYLES = {
    "tiktok": CaptionStyle("tiktok", 0.08, "&H00FFFFFF", "&H00000000", "&H96000000", 1,
                           0.0085, 0.0045, 2, 0.0, uppercase=True, mode="pop",
                           words_vertical=3, words_landscape=4, y_vertical=0.66, y_landscape=0.86),
    "bold": CaptionStyle("bold", 0.098, "&H00FFFFFF", "&H00000000", "&H80000000", 1,
                         0.0095, 0.004, 2, 0.0, accent="&H00FFFFFF", uppercase=True, mode="reveal",
                         words_vertical=2, words_landscape=3, y_vertical=0.58, y_landscape=0.62,
                         active="&H0000E5FF"),
    "clean": CaptionStyle("clean", 0.052, "&H00FFFFFF", "&H32000000", "&H8C000000", 1,
                          0.0034, 0.0026, 2, 0.075, accent="&H00FFE3A6", mode="line",
                          active="&H0085E8FF", key="&H00FFFFFF", words_vertical=7,
                          words_landscape=14, lines=2, y_vertical=0.74, y_landscape=0.9),
    "minimal": CaptionStyle("minimal", 0.038, "&H00FFFFFF", "&H40000000", "&H00000000", 1,
                            0.0018, 0.0, 2, 0.050, bold=False),
    "box": CaptionStyle("box", 0.046, "&H00FFFFFF", "&H70141418", "&H70141418", 3,
                        0.0110, 0.0, 2, 0.070, accent="&H0091E3FF"),
}
DEFAULT_FONT = "Inter"


def default_style(size: Tuple[int, int]) -> str:
    """``tiktok`` for vertical video, ``clean`` for landscape."""
    return "tiktok" if size[1] > size[0] else "clean"


def get_style(name: str) -> CaptionStyle:
    try:
        return STYLES[name]
    except KeyError:
        raise ConfigError("Unknown caption style %r. Choose one of: %s" % (name, ", ".join(STYLES))) from None


def font_px(style: CaptionStyle, size: Tuple[int, int]) -> int:
    """Caption font size in pixels; based on the short side so vertical video stays legible.
    Animated styles are a little larger in vertical video, where phones show them full screen."""
    boost = 1.12 if (style.mode != "static" and size[1] > size[0]) else 1.0
    return max(8, int(round(style.size * min(size) * boost)))


def line_layout(size: Tuple[int, int], style: str = "clean") -> Tuple[int, int]:
    """``(max_chars, line_width)`` for subtitle chunking at this video size, in the
    weight units of :mod:`voiceover_studio.subtitles` (a CJK character counts 2)."""
    st = get_style(style)
    usable = size[0] * 0.86
    width = max(12, int(usable / (font_px(st, size) * (0.62 if st.uppercase else 0.52))))
    width = min(width, 42)
    return width * 2, width


def ass_time(seconds: float) -> str:
    cs = int(round(max(0.0, seconds) * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def _escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")
            .replace("\r", "").replace("\n", "\\N"))


def _style_line(name: str, font: str, fs: int, primary: str, outline_colour: str, back: str, bold: bool,
                spacing: float, border_style: int, outline: int, shadow: int, alignment: int,
                margin_h: int, margin_v: int) -> str:
    return "Style: %s,%s,%d,%s,&H000000FF,%s,%s,%d,0,0,0,100,100,%.1f,0,%d,%d,%d,%d,%d,%d,%d,1" % (
        name, font, fs, primary, outline_colour, back, -1 if bold else 0, spacing, border_style, outline,
        shadow, alignment, margin_h, margin_h, margin_v)


def _header(size: Tuple[int, int], styles: Sequence[str]) -> List[str]:
    w, h = size
    return [
        "[Script Info]",
        "; generated by ai-voiceover-studio",
        "ScriptType: v4.00+",
        "PlayResX: %d" % w,
        "PlayResY: %d" % h,
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ] + list(styles) + [
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]


def _scaler(size: Tuple[int, int]):
    short = min(size)
    return lambda frac: max(1, int(round(frac * short)))  # noqa: E731


#: CJK glyphs look smaller than Latin capitals at the same point size; animated CJK
#: captions are scaled up by this factor.
CJK_SCALE = 1.25


def _mostly_cjk(words: Sequence[Word]) -> bool:
    return bool(words) and sum(1 for w in words if w.cjk) * 2 > len(words)


def _caption_style_line(st: CaptionStyle, size: Tuple[int, int], font: str, cjk: bool = False) -> str:
    w, h = size
    px = _scaler(size)
    fs = int(font_px(st, size) * (CJK_SCALE if cjk else 1.0))
    return _style_line("Caption", font, fs, st.primary, st.outline_colour, st.back_colour, st.bold,
                       fs * (0.02 if st.uppercase else 0.012), st.border_style, px(st.outline),
                       px(st.shadow), st.alignment, int(w * 0.07), px(st.margin_v))


def to_ass(cues: Iterable[Cue], size: Tuple[int, int], *, style: str = "clean",
           font: Optional[str] = None, speaker_labels: bool = False,
           title: Optional[str] = None, title_seconds: float = 3.2) -> str:
    """ASS document with one static caption per cue (any style; animated styles are shown
    without animation here, see :func:`animated_ass` for word-by-word captions)."""
    st = get_style(style)
    w, h = size
    font = font or DEFAULT_FONT
    px = _scaler(size)
    fs = font_px(st, size)
    margin_h = int(w * 0.07)
    margin_v = px(st.margin_v) if st.mode == "static" else int(h * (1 - _caption_y(st, size)))
    styles = [
        _style_line("Caption", font, fs, st.primary, st.outline_colour, st.back_colour, st.bold,
                    fs * 0.012, st.border_style, px(st.outline), px(st.shadow), st.alignment,
                    margin_h, margin_v),
        _style_line("Title", font, px(0.072), "&H00FFFFFF", "&H60000000", "&H80000000", True, 0, 1,
                    px(0.004), px(0.003), 8, margin_h, px(0.12)),
    ]
    events: List[str] = []
    if title:
        events.append("Dialogue: 1,%s,%s,Title,,0,0,0,,{\\fad(400,500)}%s" % (
            ass_time(0.15), ass_time(title_seconds), _escape(title.strip())))
    label_size = max(1, int(fs * 0.62))
    for cue in cues:
        text = cue.text.strip()
        if not text:
            continue
        text = _escape(text.upper() if st.uppercase else text)
        if speaker_labels and cue.speaker:
            text = "{\\fs%d\\c%s\\bord%d}%s{\\r}\\N%s" % (
                label_size, st.accent, max(1, px(st.outline) // 2), _escape(cue.speaker.title()), text)
        events.append("Dialogue: 0,%s,%s,Caption,,0,0,0,,{\\fad(120,120)}%s" % (
            ass_time(cue.start), ass_time(cue.end), text))
    return "\n".join(_header(size, styles) + events) + "\n"


# -- animated captions ---------------------------------------------------------------------

def _caption_y(st: CaptionStyle, size: Tuple[int, int]) -> float:
    return st.y_vertical if size[1] > size[0] else st.y_landscape


def _em(text: str, upper: bool) -> float:
    """Approximate rendered width of ``text`` in em (heavy sans fonts)."""
    width = 0.0
    for ch in text:
        if CJK.match(ch):
            width += 1.0
        elif ch == " ":
            width += 0.3
        else:
            width += 0.7 if upper else 0.6
    return width


def page_limits(st: CaptionStyle, size: Tuple[int, int]) -> Tuple[float, int]:
    """``(max_weight, max_words)`` per caption line for :func:`voiceover_studio.words.paginate`."""
    w, h = size
    vertical = h > w
    usable = w * (0.80 if vertical else 0.78)
    char = font_px(st, size) * (0.7 if st.uppercase else 0.6)
    return max(6.0, usable / char), st.words_vertical if vertical else st.words_landscape


def _display(word: Word, st: CaptionStyle) -> str:
    text = word.text.upper() if st.uppercase else word.text
    tail = "".join(ch for ch in word.tail if ch in "?!？！") if st.mode in ("pop", "reveal") else word.tail
    if word.cjk and st.mode in ("pop", "reveal"):
        tail = ""
    return text + tail


def _break_lines(parts: List[str], lines: int, upper: bool) -> List[List[int]]:
    """Indexes of ``parts`` per line, balanced by width."""
    n = len(parts)
    if lines <= 1 or n < 2:
        return [list(range(n))]
    widths = [_em(p, upper) for p in parts]
    total = sum(widths)
    best, best_diff = 1, None
    acc = 0.0
    for i in range(1, n):
        acc += widths[i - 1]
        diff = abs(acc - (total - acc))
        if best_diff is None or diff < best_diff:
            best, best_diff = i, diff
    if total < 14:  # short enough for one line
        return [list(range(n))]
    return [list(range(best)), list(range(best, n))]


def page_events(pages: Sequence[Page], st: CaptionStyle, size: Tuple[int, int], layer: int = 2) -> List[str]:
    """Dialogue lines for word-by-word captions: one event per spoken word of each page."""
    w, h = size
    x, y = w // 2, int(h * _caption_y(st, size))
    rise = max(4, int(min(size) * 0.012))
    events: List[str] = []
    for page in pages:
        parts = [_display(word, st) for word in page.words]
        rows = _break_lines(parts, st.lines, st.uppercase)
        for i, word in enumerate(page.words):
            start = page.start if i == 0 else word.start
            end = page.words[i + 1].start if i + 1 < len(page.words) else page.end
            if end - start < 0.02:
                continue
            pop_ms = int(min(160, max(60, (end - start) * 600)))
            rendered = []
            for j, piece in enumerate(parts):
                txt = _escape(piece)
                wj = page.words[j]
                if j == i:
                    if st.mode == "pop":
                        txt = "{\\c%s\\fscx%d\\fscy%d\\t(0,%d,\\fscx100\\fscy100)}%s{\\r}" % (
                            st.active, st.pop, st.pop, pop_ms, txt)
                    else:
                        txt = "{\\c%s}%s{\\r}" % (st.active, txt)
                elif j > i and st.mode == "reveal":
                    txt = "{\\alpha&HFF&}%s{\\r}" % txt
                elif j > i and st.mode == "line":
                    txt = "{\\1a&H50&}%s{\\r}" % txt
                elif wj.key and st.mode != "line":
                    txt = "{\\c%s}%s{\\r}" % (st.key, txt)
                rendered.append(txt)
            text = "\\N".join(_join_plain([rendered[k] for k in row], [parts[k] for k in row])
                               for row in rows)
            last = i == len(page.words) - 1
            fade = "\\fad(%d,%d)" % (70 if i == 0 else 0, 90 if last else 0) if (i == 0 or last) else ""
            if i == 0:
                lead = "{\\move(%d,%d,%d,%d,0,110)%s}" % (x, y + rise, x, y, fade)
            else:
                lead = "{\\pos(%d,%d)%s}" % (x, y, fade)
            events.append("Dialogue: %d,%s,%s,Caption,,0,0,0,,%s%s" % (
                layer, ass_time(start), ass_time(end), lead, text))
    return events


def _join_plain(rendered: List[str], plain: List[str]) -> str:
    """Join styled words; spaces follow the plain text (none between CJK words)."""
    out = ""
    prev = ""
    for r, p in zip(rendered, plain):
        if out and not (CJK.search(prev[-1:] or " ") and CJK.search(p[:1] or " ")):
            out += " "
        out += r
        prev = p
    return out


def _wrap_phrase(text: str, max_em: float, upper: bool) -> List[str]:
    if CJK.search(text) and " " not in text and any(p in text for p in "，,、：；"):
        # CJK: break at the punctuation first, then wrap each clause on its own
        clauses = [c for c in re.split(r"(?<=[，,、：；])", text) if c]
        out: List[str] = []
        for clause in clauses:
            out.extend(_wrap_phrase(clause.rstrip("，,、：；"), max_em, upper))
        return out
    if CJK.search(text) and " " not in text and _em(text, upper) > max_em:
        # CJK without spaces: split into equal parts so no line ends up with one character
        parts = int(-(-_em(text, upper) // max_em))
        step = -(-len(text) // parts)
        return [text[i:i + step] for i in range(0, len(text), step)]
    tokens = list(text) if (CJK.search(text) and " " not in text) else text.split()
    joiner = "" if (CJK.search(text) and " " not in text) else " "
    lines: List[str] = []
    cur = ""
    for tok in tokens:
        cand = (cur + joiner + tok) if cur else tok
        if cur and _em(cand, upper) > max_em:
            lines.append(cur)
            cur = tok
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def hook_events(text: str, size: Tuple[int, int], *, start: float = 0.0, seconds: float = 2.2,
                uppercase: bool = True, accent: str = "&H0000D7FF") -> List[str]:
    """Animated hook card: the frame dims, the hook text punches in, an accent bar grows."""
    w, h = size
    vertical = h > w
    fs = int(min(size) * (0.12 if vertical else 0.1))
    shown = text.strip().upper() if uppercase else text.strip()
    lines = _wrap_phrase(shown, (w * (0.82 if vertical else 0.7)) / fs, uppercase)
    cx, cy = w // 2, int(h * (0.31 if vertical else 0.44))
    end = start + seconds
    bar_w, bar_h = int(w * (0.22 if vertical else 0.14)), max(6, int(min(size) * 0.011))
    bar_y = cy + int(len(lines) * fs * 0.62) + bar_h * 2
    txt = "\\N".join(_escape(l) for l in lines)
    return [
        "Dialogue: 1,%s,%s,Shade,,0,0,0,,{\\an7\\pos(0,0)\\p1\\fad(0,350)}m 0 0 l %d 0 l %d %d l 0 %d{\\p0}" % (
            ass_time(start), ass_time(end), w, w, h, h),
        "Dialogue: 3,%s,%s,Hook,,0,0,0,,{\\an5\\pos(%d,%d)\\fad(90,320)\\fscx135\\fscy135"
        "\\t(0,260,0.6,\\fscx100\\fscy100)}%s" % (ass_time(start), ass_time(end), cx, cy, txt),
        "Dialogue: 3,%s,%s,Bar,,0,0,0,,{\\an5\\pos(%d,%d)\\p1\\1c%s\\fscx0\\t(180,520,0.5,\\fscx100)"
        "\\fad(0,320)}m 0 0 l %d 0 l %d %d l 0 %d{\\p0}" % (
            ass_time(start), ass_time(end), cx, bar_y, accent, bar_w, bar_w, bar_h, bar_h),
    ]


def kinetic_events(phrase: str, start: float, end: float, size: Tuple[int, int], *,
                   uppercase: bool = True, accent: str = "&H0000D7FF", index: int = 0) -> List[str]:
    """Large kinetic typography for a part of the video without a picture: the key phrase
    builds up word by word, drifts slowly and fades out before the next part."""
    if not phrase.strip() or end - start < 0.4:
        return []
    w, h = size
    vertical = h > w
    fs = int(min(size) * (0.125 if vertical else 0.11))
    shown = phrase.strip().upper() if uppercase else phrase.strip()
    lines = _wrap_phrase(shown, (w * (0.80 if vertical else 0.66)) / fs, uppercase)
    cx, cy = w // 2, int(h * (0.42 if vertical else 0.42))
    drift = int(min(size) * 0.025) * (1 if index % 2 == 0 else -1)
    longest = max((t for l in lines for t in (l.split() or [l])), key=lambda t: _em(t, uppercase))
    out_lines = []
    n = 0
    step = min(0.16, max(0.07, (end - start) * 0.05))
    for line in lines:
        cjk_line = bool(CJK.search(line)) and " " not in line
        tokens = list(line) if cjk_line else line.split()
        pieces = []
        for tok in tokens:
            t0 = int(n * step * 1000)
            colour = "\\c%s" % (accent if (tok == longest or any(c.isdigit() for c in tok))
                                  else "&H00FFFFFF")
            pieces.append("{\\alpha&HFF&\\fscx55\\fscy55%s\\t(%d,%d,0.5,\\alpha&H00&\\fscx100\\fscy100)}%s"
                          % (colour, t0, t0 + 240, _escape(tok)))
            n += 1
        out_lines.append(("" if cjk_line else " ").join(pieces))
    ms = int((end - start) * 1000)
    text = "\\N".join(out_lines)
    return ["Dialogue: 1,%s,%s,Kinetic,,0,0,0,,{\\an5\\move(%d,%d,%d,%d,0,%d)\\fad(0,260)}%s" % (
        ass_time(start), ass_time(end), cx - drift, cy, cx + drift, cy, ms, text)]


def animated_ass(pages: Sequence[Page], size: Tuple[int, int], *, style: str = "tiktok",
                 font: Optional[str] = None, hook: Optional[str] = None, hook_seconds: float = 2.2,
                 kinetic: Sequence[Tuple[float, float, str]] = (), static_cues: Iterable[Cue] = ()) -> str:
    """One ASS document with word-by-word captions (``pages``), or static ``static_cues`` for
    static styles, plus an optional hook card and kinetic key phrases
    (``(start, end, phrase)`` per picture-less part)."""
    st = get_style(style)
    w, h = size
    font = font or DEFAULT_FONT
    px = _scaler(size)
    vertical = h > w
    hook_fs = int(min(size) * (0.12 if vertical else 0.1))
    kin_fs = int(min(size) * (0.125 if vertical else 0.11))
    accent = st.active if st.mode != "static" else "&H0000D7FF"
    styles = [
        _caption_style_line(st, size, font, _mostly_cjk([w for p in pages for w in p.words]))
        if st.mode != "static" else
        _style_line("Caption", font, font_px(st, size), st.primary, st.outline_colour, st.back_colour,
                    st.bold, font_px(st, size) * 0.012, st.border_style, px(st.outline), px(st.shadow),
                    st.alignment, int(w * 0.07), px(st.margin_v)),
        _style_line("Hook", font, hook_fs, "&H00FFFFFF", "&H00000000", "&H90000000", True, hook_fs * 0.02, 1,
                    px(0.009), px(0.006), 5, int(w * 0.06), 0),
        _style_line("Kinetic", font, kin_fs, "&H00FFFFFF", "&H00101010", "&H78000000", True, kin_fs * 0.02, 1,
                    px(0.006), px(0.008), 5, int(w * 0.06), 0),
        _style_line("Shade", font, 10, "&H70000000", "&H00000000", "&H00000000", False, 0, 1, 0, 0, 7, 0, 0),
        _style_line("Bar", font, 10, "&H00FFFFFF", "&H00000000", "&H00000000", False, 0, 1, 0, 0, 5, 0, 0),
    ]
    events: List[str] = []
    hook_end = 0.0
    if hook:
        events += hook_events(hook, size, seconds=hook_seconds, uppercase=st.uppercase or st.mode != "line",
                              accent=accent)
        hook_end = hook_seconds
    for i, (k_start, k_end, phrase) in enumerate(kinetic):
        events += kinetic_events(phrase, max(k_start, hook_end), k_end, size,
                                 uppercase=st.uppercase or st.mode != "line", accent=accent, index=i)
    if st.mode == "static":
        for cue in static_cues:
            text = cue.text.strip()
            if text:
                events.append("Dialogue: 2,%s,%s,Caption,,0,0,0,,{\\fad(120,120)}%s" % (
                    ass_time(cue.start), ass_time(cue.end), _escape(text.upper() if st.uppercase else text)))
    else:
        events += page_events(pages, st, size)
    return "\n".join(_header(size, styles) + events) + "\n"


def build_pages(words: List[Word], size: Tuple[int, int], style: str) -> List[Page]:
    """Split words into caption pages that fit ``style`` at video ``size``."""
    st = get_style(style)
    max_weight, max_words = page_limits(st, size)
    if _mostly_cjk(words):
        max_weight /= CJK_SCALE
    return paginate(words, max_weight=max_weight, max_words=max_words, lines=st.lines, hold=0.9)
