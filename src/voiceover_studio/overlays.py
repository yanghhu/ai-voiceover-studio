"""Transparent infographic cards drawn locally: text, icons and accent lines.

The presentation style of the web studio overlays these cards on the video shots
(``![](card.png){overlay}`` in the script). They are rendered with Pillow from the
overlay plan designed by the model (title, bullet points, icon concepts) — no AI
image generation involved, so they are precise, fast and free.
"""
from __future__ import annotations

import glob
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .errors import ConfigError

CARD_STYLES: Dict[str, Dict[str, Tuple[int, int, int, int]]] = {
    "Scuro": {"bg": (13, 20, 36, 180), "text": (255, 255, 255, 255),
              "accent": (96, 190, 255, 255)},
    "Chiaro": {"bg": (255, 255, 255, 200), "text": (24, 28, 40, 255),
               "accent": (31, 90, 200, 255)},
    "Blu notte": {"bg": (8, 14, 48, 185), "text": (230, 240, 255, 255),
                  "accent": (120, 160, 255, 255)},
    "Carta": {"bg": (247, 240, 222, 210), "text": (60, 45, 30, 255),
              "accent": (150, 90, 40, 255)},
}

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
)


def _font_file() -> Optional[str]:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    for root in ("/usr/share/fonts", "/Library/Fonts", "C:/Windows/Fonts"):
        hits = sorted(glob.glob(root + "/**/*Bold*.ttf", recursive=True))
        if hits:
            return hits[0]
    return None


def _font(size: int) -> Any:
    from PIL import ImageFont
    path = _font_file()
    try:
        return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
    except OSError:
        return ImageFont.load_default(size)


def _wrap(draw: Any, text: str, font: Any, max_width: int) -> List[str]:
    words = (text or "").split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _draw_icon(draw: Any, kind: str, x: float, y: float, size: float, color: Tuple[int, int, int, int]) -> None:
    """Small vector glyph for a bullet: check, arrow, star, alert or a plain dot."""
    key = (kind or "").lower()
    w = 2.0
    if "check" in key or "spunta" in key or "ok" in key or "visto" in key:
        draw.line([(x + size * 0.10, y + size * 0.55), (x + size * 0.40, y + size * 0.85),
                   (x + size * 0.92, y + size * 0.15)], fill=color, width=int(max(2, size * 0.14)))
    elif "arrow" in key or "freccia" in key:
        mid = y + size * 0.5
        draw.line([(x, mid), (x + size * 0.75, mid)], fill=color,
                  width=int(max(2, size * 0.12)))
        head = size * 0.42
        draw.polygon([(x + size, mid), (x + size - head, mid - head * 0.6),
                      (x + size - head, mid + head * 0.6)], fill=color)
    elif "star" in key or "stella" in key:
        cx, cy, outer, inner = x + size / 2, y + size / 2, size * 0.48, size * 0.20
        points = []
        for i in range(10):
            radius = outer if i % 2 == 0 else inner
            angle = -math.pi / 2 + i * math.pi / 5
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        draw.polygon(points, fill=color)
    elif "alert" in key or "attenzione" in key or "!" in key:
        draw.polygon([(x + size / 2, y), (x + size, y + size), (x, y + size)],
                     outline=color, width=int(max(2, size * 0.10)))
        draw.line([(x + size / 2, y + size * 0.35), (x + size / 2, y + size * 0.62)],
                  fill=color, width=int(max(2, size * 0.10)))
        draw.ellipse([x + size / 2 - size * 0.05, y + size * 0.72,
                      x + size / 2 + size * 0.05, y + size * 0.82], fill=color)
    else:
        r = size * 0.22
        cx, cy = x + size / 2, y + size / 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


def render_card(item: Dict[str, Any], dest_base: Any, style: str = "Scuro",
                width: int = 1600, height: int = 900) -> Path:
    """Overlay plan item ({title, bullets, icons}) -> transparent PNG card.

    The card is drawn on a transparent canvas: the renderer composites it over the
    shot's clip, so the video keeps playing underneath."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise ConfigError("The overlay cards need Pillow: pip install Pillow") from None
    cfg = CARD_STYLES.get(style or "", CARD_STYLES["Scuro"])
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = int(width * 0.05)
    box = [margin, margin, width - margin, height - margin]
    draw.rounded_rectangle(box, radius=int(width * 0.025), fill=cfg["bg"])
    pad = int(width * 0.04)
    x, y = box[0] + pad, box[1] + pad
    maxw = box[2] - pad - x
    title_font = _font(int(height * 0.082))
    body_font = _font(int(height * 0.050))
    chip_font = _font(int(height * 0.040))
    for line in _wrap(draw, str(item.get("title", "")).strip(), title_font, maxw)[:3]:
        draw.text((x, y), line, font=title_font, fill=cfg["text"])
        y += int(title_font.size * 1.22)
    y += int(height * 0.018)
    draw.rectangle([x, y, x + int(maxw * 0.20), y + max(4, int(height * 0.007))],
                   fill=cfg["accent"])
    y += int(height * 0.050)
    icon_size = int(height * 0.055)
    gap = int(width * 0.015)
    for bullet in (item.get("bullets") or [])[:5]:
        text = str(bullet).strip()
        if not text:
            continue
        _draw_icon(draw, "dot", x, y, icon_size, cfg["accent"])
        lines = _wrap(draw, text, body_font, maxw - icon_size - gap)[:2]
        for i, line in enumerate(lines):
            draw.text((x + icon_size + gap, y - int(body_font.size * 0.12) + i * int(body_font.size * 1.25)),
                      line, font=body_font, fill=cfg["text"])
        y += max(icon_size, int(body_font.size * 1.25) * len(lines)) + int(height * 0.022)
        if y > box[3] - pad - chip_font.size * 2:
            break
    icons = [str(i).strip() for i in (item.get("icons") or []) if str(i).strip()]
    if icons and y < box[3] - pad - chip_font.size * 2:
        cx = x
        chip_h = int(chip_font.size * 1.7)
        for icon in icons[:4]:
            label = icon[:24]
            chip_w = int(draw.textlength(label, font=chip_font)) + int(chip_font.size * 1.6)
            if cx + chip_w > box[2] - pad:
                break
            draw.rounded_rectangle([cx, y, cx + chip_w, y + chip_h],
                                   radius=chip_h // 2, outline=cfg["accent"],
                                   width=max(2, int(height * 0.004)))
            _draw_icon(draw, icon, cx + int(chip_font.size * 0.35),
                       y + (chip_h - chip_font.size * 0.9) / 2, chip_font.size * 0.9,
                       cfg["accent"])
            draw.text((cx + int(chip_font.size * 1.15), y + int(chip_font.size * 0.35)),
                      label, font=chip_font, fill=cfg["text"])
            cx += chip_w + gap
    dest = Path(str(dest_base) + ".png")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest
