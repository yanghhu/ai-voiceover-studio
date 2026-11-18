"""AI-illustration slides: no stock or YouTube clips, only AI images brought to life.

Pipeline: narration (one paragraph per scene) -> one concrete image prompt per paragraph
(planned by the model, fully editable) -> illustration generated with an OpenRouter image
model -> animated into a looping GIF with a Ken Burns move (Pillow, offline and free) ->
text, frames and symbols drawn as a transparent card and baked over the animation.

For subjects whose movement must be real (swaying ears, crawling worms...),
:func:`animate_loop` instead moves ONE single AI image with cyclic procedural motion
(zero drift between generations) and :func:`build_gif` assembles true multi-frame AI
animations with ping-pong + cross-fades.

The resulting ``.gif`` files are treated as video shots by the render engine (ffmpeg loops
them with ``-stream_loop``), so the final clips never look static and the narration audio,
captions and transitions all keep working unchanged.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .errors import ConfigError

IMAGE_SYSTEM = """You design the illustrations of a narrated video. For every numbered \
paragraph of the narration write ONE image prompt for an AI image model: a rich, concrete \
visual description of the single picture that best illustrates that paragraph (subject, \
setting, composition, colors), written in the same language as the narration so it can be \
used directly.

The image must contain NO words, letters, numbers or captions. Avoid people's faces and \
brands. Answer ONLY with a JSON list of strings, one per paragraph, in the same order."""

# Model output sizes per aspect ratio: small enough to keep the GIFs light, big enough for
# a 1080p render (the engine scales shots up; a slight upscale is invisible after grading).
ASPECT_SIZES: Dict[str, Tuple[int, int]] = {"16:9": (960, 540), "1:1": (900, 900),
                                            "9:16": (540, 960)}

# Motion presets, in the same order as video._moves (Ken Burns loop baked into the GIF).
MOTIONS = ["push-in", "pan", "pull-out", "pan + rise"]

# Cyclic procedural motions over ONE still image (no AI-frame drift, perfect loop).
LOOP_MOTIONS = ["wind", "waves", "breathe", "shimmer"]

GIF_OVERLAY_OPACITY = 0.92  # matches the renderer's OVERLAY_OPACITY


def _paragraphs(narration: str) -> List[str]:
    return [p.strip() for p in (narration or "").split("\n\n")
            if p.strip() and not p.strip().startswith("#")]


def plan_image_prompts(client: Any, model: str, narration: str, prompt: str = "") -> List[str]:
    """Narration (one paragraph per scene) -> one editable image prompt per paragraph."""
    from .ai_video import _parse_json
    paragraphs = _paragraphs(narration)
    if not paragraphs:
        raise ValueError("Write the narration first (step 1).")
    user = ("Context of the video: %s\n\n" % prompt.strip() if (prompt or "").strip() else "") \
        + "\n\n".join("%d. %s" % (i, p) for i, p in enumerate(paragraphs, 1))
    content = client.chat(model, [{"role": "system", "content": IMAGE_SYSTEM},
                                  {"role": "user", "content": user}])
    raw = _parse_json(content)
    if not isinstance(raw, list) or not raw:
        raise ConfigError("The model did not return the illustration prompts.")
    prompts = []
    for item in raw:
        if isinstance(item, dict):
            item = item.get("prompt", "")
        if not isinstance(item, str) or not item.strip():
            continue
        prompts.append(item.strip()[:600])
    # pad so paragraph i always has a prompt (first sentence as a fallback description)
    while len(prompts) < len(paragraphs):
        fallback = re.split(r"(?<=[.!?])\s+", paragraphs[len(prompts)])[0]
        prompts.append(fallback[:200])
    return prompts[:len(paragraphs)]


def animate_still(src: Any, dest_base: Any, *, overlay: Optional[Any] = None,
                  size: Tuple[int, int] = (960, 540), motion: str = "push-in",
                  zoom: float = 0.12, frames: int = 16, loop_seconds: float = 1.8) -> Path:
    """Turn a still image into a looping Ken Burns GIF (optionally under a transparent card).

    The move presets mirror the renderer's Ken Burns table; ``overlay`` is a card PNG drawn
    by :mod:`voiceover_studio.overlays` (text, icons, accent lines) baked at the 42%-width
    spot with the same opacity the render engine uses, so the GIF preview matches the video.
    """
    from .video import _moves
    try:
        from PIL import Image
    except ImportError:
        raise ConfigError("Pillow is required to animate the illustrations: "
                          "pip install Pillow (part of 'ai-voiceover-studio[webui]').") from None
    src, dest = Path(src), Path(str(dest_base) + ".gif")
    with Image.open(src) as still:
        base = still.convert("RGB")
    w, h = size
    max_zoom = 1.0 + zoom * 1.4  # worst-case crop margin across all move presets
    target_w = max(w, int(w * max_zoom + 0.5))
    target_h = max(h, int(h * max_zoom + 0.5))
    scale = max(target_w / base.width, target_h / base.height)
    base = base.resize((max(target_w, round(base.width * scale)),
                        max(target_h, round(base.height * scale))), Image.LANCZOS)
    card = None
    if overlay is not None:
        ow = max(1, round(w * 0.42))
        oh = max(1, round(ow * 900 / 1600))
        card = Image.open(Path(overlay)).convert("RGBA").resize((ow, oh), Image.LANCZOS)
        alpha = card.getchannel("A").point(lambda v: int(v * GIF_OVERLAY_OPACITY))
        card.putalpha(alpha)
    z0, z1, x0, x1, y0, y1 = _moves(zoom)[MOTIONS.index(motion) % len(_moves(zoom))]
    active = []
    for i in range(frames):
        u = i / max(1, frames - 1)
        z = z0 + (z1 - z0) * u
        cw, ch = base.width / z, base.height / z
        left = (base.width - cw) * (x0 + (x1 - x0) * u)
        top = (base.height - ch) * (y0 + (y1 - y0) * u)
        frame = base.crop((int(left), int(top), int(left + cw), int(top + ch))) \
            .resize((w, h), Image.LANCZOS)
        if card is not None:
            frame = _bake_card(frame, card, w, h)
        active.append(frame.convert("P", palette=Image.ADAPTIVE, colors=256))
    per_frame = max(20, int(round(loop_seconds * 1000 / frames)))
    active[0].save(dest, save_all=True, append_images=active[1:], duration=per_frame,
                   loop=0, optimize=False)
    return dest


def generate_stills(client: Any, model: str, prompts: List[str], out_dir: Path, *,
                    style: str = "", extra: str = "", aspect: str = "16:9",
                    progress: Optional[Callable[[str], None]] = None
                    ) -> Tuple[List[Optional[str]], List[str]]:
    """One illustration per prompt via the OpenRouter image model (the paid step).

    Returns ``(stills, errors)``: ``stills[i]`` is the image path or ``None`` when that
    illustration failed; a failed scene never aborts the batch."""
    from .ai_video import generate_illustration
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stills: List[Optional[str]] = []
    errors: List[str] = []
    for i, desc in enumerate(prompts, 1):
        if progress:
            progress("Generating illustration %d/%d with %s: %s"
                     % (i, len(prompts), model, desc[:80]))
        try:
            still = generate_illustration(client, desc, out_dir / ("still_%02d" % i),
                                          model=model, style=style, aspect_ratio=aspect,
                                          extra=extra)
            stills.append(str(still))
        except Exception as exc:
            stills.append(None)
            errors.append("Illustration %d failed: %s" % (i, str(exc)[:200]))
        if progress:
            progress("Illustration %d/%d done (%s)"
                     % (i, len(prompts), "ok" if stills[-1] else "failed"))
    return stills, errors


def animate_slides(stills: List[Optional[str]], out_dir: Path, *, paragraphs: List[str],
                   aspect: str = "16:9", motion: str = "push-in",
                   overlay_plan: Optional[List[Dict[str, Any]]] = None,
                   with_cards: bool = True, card_style: str = "Scuro",
                   progress: Optional[Callable[[str], None]] = None
                   ) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Local, free step: Ken Burns GIFs (with the text/frame/symbol card baked when asked).

    Returns ``(slides, errors)``; ``slides[i]`` is ``{"scene": n, "gif": path}`` when the
    animation succeeded, otherwise nothing is appended and the scene falls back to an
    animated-text shot in the script."""
    from .overlays import render_card
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_scene = {o.get("scene"): o for o in (overlay_plan or []) if isinstance(o, dict)}
    slides: List[Dict[str, Any]] = []
    errors: List[str] = []
    for i, still in enumerate(stills, 1):
        if not still or not Path(still).is_file():
            continue
        if progress:
            progress("Animating illustration %d/%d (%s) into a GIF"
                     % (i, len(stills), motion))
        card: Optional[Path] = None
        if with_cards:
            item = by_scene.get(i) or {"scene": i, "title": paragraphs[i - 1][:80],
                                       "bullets": [], "icons": []}
            card = render_card(item, out_dir / ("card_%02d" % i), style=card_style)
        try:
            gif = animate_still(still, out_dir / ("slide_%02d" % i), overlay=card,
                                size=ASPECT_SIZES.get(aspect, ASPECT_SIZES["16:9"]),
                                motion=motion)
            slides.append({"scene": i, "gif": str(gif), "still": still})
        except Exception as exc:
            errors.append("Animation of scene %d failed: %s" % (i, str(exc)[:200]))
        if progress:
            progress("Scene %d/%d animated" % (i, len(stills)))
    return slides, errors


def build_slide_script(slides: List[Dict[str, Any]], narration: str, title: str = "") -> str:
    """Narration + animated GIFs -> Markdown script (the text stays exactly as written)."""
    paragraphs = _paragraphs(narration)
    if not paragraphs:
        raise ValueError("Write the narration first (step 1).")
    lines: List[str] = []
    if title.strip():
        lines += ["# " + title.strip(), ""]
    gifs = {s["scene"]: s["gif"] for s in slides}
    for i, paragraph in enumerate(paragraphs, 1):
        if gifs.get(i):
            lines += ["![](%s)" % gifs[i], ""]
        lines += [paragraph, ""]
    return "\n".join(lines).strip() + "\n"


MOTION_SYSTEM = """You are designing a **seamlessly looping animated GIF** made of \
AI-generated frames. The user gives you a scene and what moves in it (for example: wheat \
ears swaying in the wind, or worms crawling). Plan how many frames are requested.

For EVERY frame write the prompt for the image model. All the frame prompts must describe \
the **same exact scene**: same camera, same composition, same crop, same colors and \
lighting, same background. The ONLY thing that changes from one frame to the next is the \
**phase of the movement** of the moving element, progressing smoothly through the cycle \
(start position ... middle ... end position). The last frame's movement phase must connect \
back to the first frame's phase (full cycle). Keep each prompt short and identical to the \
previous one except for the movement phrase.

Answer ONLY with a JSON list of strings: exactly one prompt per frame, in cycle order."""


def plan_motion_frames(client: Any, model: str, prompt: str, motion: str,
                       n_frames: int = 4) -> List[str]:
    """Scene + movement -> N frame prompts of the same scene at cyclic motion phases."""
    from .ai_video import _parse_json
    if not (prompt or "").strip():
        raise ValueError("Describe the subject of the animation (step 1).")
    content = client.chat(model, [
        {"role": "system", "content": MOTION_SYSTEM},
        {"role": "user", "content": ("Scene: %s\nMovement: %s\nFrames in the cycle: %d"
                                     % (prompt.strip(), motion.strip() or "gentle sway",
                                        n_frames))}])
    raw = _parse_json(content)
    if not isinstance(raw, list) or not raw:
        raise ConfigError("The model did not return the frame prompts.")
    prompts = [str(item).strip()[:600] for item in raw if str(item).strip()]
    while len(prompts) < n_frames:  # pad by cycling the frames the model did return
        prompts.append(prompts[len(prompts) % max(1, len(prompts))])
    return prompts[:n_frames]


def animate_loop(src: Any, dest_base: Any, *, overlay: Optional[Any] = None,
                 size: Tuple[int, int] = (960, 540), motion: str = "wind",
                 intensity: float = 1.0, frames: int = 14,
                 loop_seconds: float = 1.6) -> Path:
    """Turn ONE still image into a seamlessly looping GIF with procedural motion.

    This is the zero-drift alternative to multi-frame AI animations: the image model
    draws the scene only once, and the movement (wind sway, water ripples, breathing
    zoom...) is applied locally with Pillow as a cyclic, sinusoidal transformation —
    the phase wraps around 2*pi exactly, so the loop returns to its starting frame with
    no discontinuity and the scene can never 'wobble' between AI generations.

    ``motion`` presets: "wind" (top-heavy horizontal sway, for ears/grass/flags),
    "waves" (bottom-heavy sway, for water and reflections), "breathe" (cyclic zoom),
    "shimmer" (very subtle sway, for leaves and light). ``intensity`` scales the
    amplitude (1.0 = default). ``overlay`` is baked like in :func:`animate_still`.
    """
    import math
    try:
        from PIL import Image
    except ImportError:
        raise ConfigError("Pillow is required to animate the illustrations: "
                          "pip install Pillow (part of 'ai-voiceover-studio[webui]').") from None
    src, dest = Path(src), Path(str(dest_base) + ".gif")
    if motion not in LOOP_MOTIONS:
        motion = "wind"
    intensity = max(0.1, float(intensity))
    with Image.open(src) as still:
        base = still.convert("RGB")
    w, h = size
    amp = (max(2, round(w * 0.03 * intensity)) if motion in ("wind", "waves")
           else max(1, round(w * 0.012 * intensity)) if motion == "shimmer" else 0)
    margin = amp  # horizontal room the sway needs on each side (0 for "breathe")
    tw = w + 2 * margin
    scale = max(tw / base.width, h / base.height)
    big = base.resize((max(tw, round(base.width * scale)),
                       max(h, round(base.height * scale))), Image.LANCZOS)
    big = big.crop(((big.width - tw) // 2, (big.height - h) // 2,
                    (big.width - tw) // 2 + tw, (big.height - h) // 2 + h))
    card = None
    if overlay is not None:
        ow = max(1, round(w * 0.42))
        oh = max(1, round(ow * 900 / 1600))
        card = Image.open(Path(overlay)).convert("RGBA").resize((ow, oh), Image.LANCZOS)
        alpha = card.getchannel("A").point(lambda v: int(v * GIF_OVERLAY_OPACITY))
        card.putalpha(alpha)
    active = []
    for i in range(frames):
        phase = 2.0 * math.pi * i / frames  # wraps back exactly: perfect loop by design
        sway = math.sin(phase)
        if motion == "breathe":
            z = 1.0 + 0.05 * intensity * (0.5 - 0.5 * math.cos(phase))
            cw, ch = tw / z, h / z
            left = (tw - cw) / 2.0
            top = (h - ch) / 2.0
            frame = big.crop((int(left), int(top), int(left + cw), int(top + ch))) \
                .resize((w, h), Image.LANCZOS)
        else:
            if motion == "waves":  # water: the bottom of the frame sways the most
                slope, s0 = amp * sway / h, 0.0
            else:  # wind / shimmer: anchored at the bottom, the top sways the most
                slope, s0 = -amp * sway / h, amp * sway
            frame = big.transform((w, h), Image.AFFINE,
                                  (1, slope, s0 - margin, 0, 1, 0),
                                  resample=Image.BILINEAR)
        if card is not None:
            frame = _bake_card(frame, card, w, h)
        active.append(frame.convert("P", palette=Image.ADAPTIVE, colors=256))
    per_frame = max(20, int(round(loop_seconds * 1000 / frames)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    active[0].save(dest, save_all=True, append_images=active[1:], duration=per_frame,
                   loop=0, optimize=False)
    return dest


def _bake_card(frame: "Image.Image", card: "Image.Image",
               w: int, h: int) -> "Image.Image":
    """Bake a transparent card PNG over one frame (same spot as the render engine)."""
    frame_rgba = frame.convert("RGBA")
    frame_rgba.alpha_composite(card, (w - card.width - max(16, round(w * 0.035)),
                                      h - card.height - max(16, round(h * 0.035))))
    return frame_rgba.convert("RGB")


def build_gif(frames: List[Any], dest_base: Any, *, loop_seconds: float = 1.2,
              blend: int = 0, pingpong: bool = True) -> Path:
    """Assemble frame images into a seamlessly looping animated GIF.

    With ``pingpong`` the sequence plays forward then backward (1..N..1), so the loop
    always returns to its exact starting point with no discontinuity. ``blend`` inserts
    that many cross-fade frames between consecutive frames to smooth out any difference
    the image model introduced (ghosting is the trade-off, keep it low)."""
    try:
        from PIL import Image
    except ImportError:
        raise ConfigError("Pillow is required to assemble GIFs: pip install Pillow.") from None
    frames = [Path(f) for f in frames if f and Path(f).is_file()]
    if len(frames) < 2:
        raise ValueError("At least two frame images are needed for an animation "
                         "(generate them in step 2 first).")
    with Image.open(frames[0]) as first:
        size = first.size
    imgs = []
    for f in frames:
        with Image.open(f) as im:
            img = im.convert("RGB")
            if img.size != size:
                img = img.resize(size, Image.LANCZOS)
            imgs.append(img)
    order = list(range(len(imgs)))
    if pingpong:
        order += list(range(len(imgs) - 2, 0, -1))
    if blend > 0:
        blended: List[Image.Image] = []
        for i, img in enumerate(order):
            blended.append(imgs[img])
            nxt = imgs[order[(i + 1) % len(order)]]
            for j in range(1, blend + 1):
                blended.append(Image.blend(imgs[img], nxt, j / (blend + 1)))
        sequence = blended
    else:
        sequence = [imgs[i] for i in order]
    per_frame = max(20, int(round(loop_seconds * 1000 / len(sequence))))
    dest = Path(str(dest_base) + ".gif")
    dest.parent.mkdir(parents=True, exist_ok=True)
    pal = [im.convert("P", palette=Image.ADAPTIVE, colors=256) for im in sequence]
    pal[0].save(dest, save_all=True, append_images=pal[1:], duration=per_frame, loop=0)
    return dest
