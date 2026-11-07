"""Draw the six example slides in examples/slides/ (needs Pillow).

    python examples/make_slides.py [--size 1920x1080] [--out examples/slides]

The slides are simple vector-style illustrations for the "Why the sky is blue"
example script. The lower third is kept calm so captions stay readable.
"""
import argparse
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_CANDIDATES = ("Inter.ttf", "Inter-Bold.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf")


def font(size, weight=b"Bold"):
    for name in FONT_CANDIDATES:
        for folder in (Path.home() / ".fonts", Path("/usr/share/fonts/truetype/dejavu"),
                       Path("/Library/Fonts"), Path("C:/Windows/Fonts")):
            path = folder / name
            if path.is_file():
                f = ImageFont.truetype(str(path), size)
                try:
                    f.set_variation_by_name(weight)
                except Exception:
                    pass
                return f
    return ImageFont.load_default()


def gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        t = y / (h - 1)
        t = t * t * (3 - 2 * t)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = c
    return img


def glow(img, center, radius, colour, strength=0.55):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    for i in range(24, 0, -1):
        r = radius * (1 + i * 0.12)
        a = int(255 * strength * (1 - i / 24) ** 2 / 3)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=colour + (a,))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(radius * 0.25)))


def cloud(d, x, y, s, fill=(255, 255, 255, 235)):
    for dx, dy, r in ((0, 0, 1.0), (0.9, -0.35, 1.2), (1.9, 0, 0.95), (0.95, 0.2, 1.0)):
        rr = r * s
        d.ellipse((x + dx * s - rr, y + dy * s - rr, x + dx * s + rr, y + dy * s + rr), fill=fill)


def heading(img, text, sub=None, y=0.12, colour=(255, 255, 255)):
    w, h = img.size
    d = ImageDraw.Draw(img)
    f = font(int(h * 0.075))
    tw = d.textlength(text, font=f)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text(((w - tw) / 2, h * y + 4), text, font=f, fill=(0, 0, 0, 90))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)))
    d.text(((w - tw) / 2, h * y), text, font=f, fill=colour)
    if sub:
        fs = font(int(h * 0.032), b"Medium")
        sw = d.textlength(sub, font=fs)
        d.text(((w - sw) / 2, h * y + h * 0.1), sub, font=fs, fill=colour + (210,))


def molecules(d, w, h, n, rng, area, colour=(255, 255, 255, 150)):
    x0, y0, x1, y1 = area
    pts = []
    for _ in range(n):
        x, y = rng.uniform(x0, x1) * w, rng.uniform(y0, y1) * h
        r = rng.uniform(4, 9) * h / 1080
        d.ellipse((x - r, y - r, x + r, y + r), fill=colour)
        pts.append((x, y))
    return pts


def slide1(size):
    w, h = size
    img = gradient(size, (38, 104, 214), (140, 196, 245)).convert("RGBA")
    glow(img, (w * 0.78, h * 0.3), h * 0.09, (255, 236, 170), 0.9)
    d = ImageDraw.Draw(img)
    r = h * 0.08
    d.ellipse((w * 0.78 - r, h * 0.3 - r, w * 0.78 + r, h * 0.3 + r), fill=(255, 244, 214))
    cloud(d, w * 0.12, h * 0.42, h * 0.06)
    cloud(d, w * 0.55, h * 0.55, h * 0.045, (255, 255, 255, 200))
    heading(img, "Why is the sky blue?", "a 60-second explainer", y=0.1)
    return img


def slide2(size):
    w, h = size
    img = gradient(size, (20, 24, 48), (52, 64, 120)).convert("RGBA")
    d = ImageDraw.Draw(img)
    for i, (cx, col, label) in enumerate(((0.33, (255, 214, 102), "what we expect"),
                                          (0.67, (255, 255, 255), "what it really is"))):
        glow(img, (w * cx, h * 0.45), h * 0.11, col, 0.8)
        d = ImageDraw.Draw(img)
        r = h * 0.11
        d.ellipse((w * cx - r, h * 0.45 - r, w * cx + r, h * 0.45 + r), fill=col)
        f = font(int(h * 0.034), b"Medium")
        tw = d.textlength(label, font=f)
        d.text((w * cx - tw / 2, h * 0.62), label, font=f, fill=(225, 230, 255))
    heading(img, "Sunlight is white", y=0.09)
    return img


SPECTRUM = [(148, 0, 211), (75, 0, 130), (0, 90, 255), (0, 200, 120), (255, 230, 0), (255, 127, 0), (240, 30, 30)]


def slide3(size):
    w, h = size
    img = gradient(size, (14, 18, 38), (30, 36, 72)).convert("RGBA")
    d = ImageDraw.Draw(img)
    # white beam into a prism, fanning out into the spectrum
    px, py = w * 0.36, h * 0.47
    d.line((0, h * 0.40, px, py), fill=(255, 255, 255), width=int(h * 0.012))
    tri = [(px - h * 0.11, py + h * 0.1), (px + h * 0.11, py + h * 0.1), (px, py - h * 0.13)]
    for i, c in enumerate(SPECTRUM):
        y_end = h * (0.30 + i * 0.045)
        d.polygon([(px + h * 0.02, py), (w, y_end - h * 0.02), (w, y_end + h * 0.02)], fill=c + (205,))
    d.polygon(tri, fill=(210, 230, 255, 120), outline=(255, 255, 255))
    heading(img, "Every colour of the rainbow", y=0.08)
    return img


def slide4(size):
    w, h = size
    rng = random.Random(4)
    img = gradient(size, (16, 44, 120), (54, 120, 220)).convert("RGBA")
    d = ImageDraw.Draw(img)
    pts = molecules(d, w, h, 26, rng, (0.08, 0.28, 0.92, 0.68))
    # red ray passes straight through
    d.line((0, h * 0.62, w, h * 0.5), fill=(255, 90, 80, 220), width=int(h * 0.008))
    # blue rays bounce between molecules
    path = [(0, h * 0.35)] + sorted(rng.sample(pts, 9), key=lambda p: p[0])
    for a, b in zip(path, path[1:]):
        d.line((a, b), fill=(130, 200, 255, 255), width=int(h * 0.007))
    for x, y in path[1:]:
        r = h * 0.012
        d.ellipse((x - r, y - r, x + r, y + r), fill=(180, 225, 255))
    heading(img, "Blue light scatters most", y=0.08)
    return img


def slide5(size):
    w, h = size
    img = gradient(size, (54, 40, 110), (255, 122, 69)).convert("RGBA")
    glow(img, (w * 0.5, h * 0.78), h * 0.12, (255, 170, 90), 1.0)
    d = ImageDraw.Draw(img)
    r = h * 0.12
    d.ellipse((w * 0.5 - r, h * 0.78 - r, w * 0.5 + r, h * 0.78 + r), fill=(255, 196, 120))
    d.rectangle((0, h * 0.8, w, h), fill=(40, 22, 52))
    heading(img, "Sunsets: reds and oranges", y=0.1)
    return img


def slide6(size):
    w, h = size
    img = gradient(size, (12, 14, 30), (34, 30, 74)).convert("RGBA")
    rng = random.Random(6)
    d = ImageDraw.Draw(img)
    for _ in range(140):
        x, y, r = rng.uniform(0, w), rng.uniform(0, h * 0.7), rng.uniform(0.8, 2.4)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rng.randint(90, 220)))
    # play button
    cx, cy, r = w / 2, h * 0.42, h * 0.1
    d.rounded_rectangle((cx - r * 1.45, cy - r, cx + r * 1.45, cy + r), radius=int(r * 0.45), fill=(235, 52, 64))
    d.polygon([(cx - r * 0.35, cy - r * 0.45), (cx - r * 0.35, cy + r * 0.45), (cx + r * 0.5, cy)],
              fill=(255, 255, 255))
    heading(img, "One-minute science", y=0.1)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--out", default=str(Path(__file__).parent / "slides"))
    args = ap.parse_args()
    size = tuple(int(v) for v in args.size.split("x"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for n, fn in enumerate((slide1, slide2, slide3, slide4, slide5, slide6), 1):
        fn(size).convert("RGB").save(out / ("%02d.jpg" % n), quality=88, optimize=True, progressive=True)
        print(out / ("%02d.jpg" % n))


if __name__ == "__main__":
    main()
