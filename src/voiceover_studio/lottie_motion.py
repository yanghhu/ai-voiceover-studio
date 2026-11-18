"""Motion design (Lottie): the AI writes the animation, python-lottie renders it.

Instead of asking an image model to redraw the same scene N times (which always drifts),
here the **text** LLM writes a professional vector animation directly in the industry
Lottie (Bodymovin) JSON format — shapes, lines, icons, keyframed motion — and
`python-lottie <https://github.com/tehttae/python-lottie>`_ (pure Python, no AI inside)
validates it and renders the seamless-looping GIF (and a live HTML preview via the
lottie-web player).

The loop cannot drift by construction: every keyframe returns to its starting value, so
the animation is deterministic and infinitely repeatable.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .errors import ConfigError

LOTTIE_FRAMERATE = 30

LOTTIE_SYSTEM = """You are a professional motion designer. The user describes an animation \
for an explainer video. Write it as a **Lottie (Bodymovin) JSON animation** that loops \
**seamlessly** (the last keyframe's value must equal the first's, so the cycle never jumps).

Strict format rules (Bodymovin v5.7):
- One single JSON object only: {"v":"5.7.4","fr":%(fr)d,"ip":0,"op":%(op)d,"w":%(w)d,"h":%(h)d,"nm":"name","layers":[...]}.
- Only **shape layers**: {"ty":4,"ind":N,"ip":0,"op":%(op)d,"ks":{...}}. NO text layers, NO \
image layers, NO expressions, NO effects, NO masks, NO easing objects (omit "o"/"i" inside \
keyframes: linear interpolation).
- Shapes: {"ty":"el" ellipse,"ty":"rc" rect,"ty":"sr" star/polygon,"ty":"sh" bezier path} with \
{"ty":"fl" fill (c as 0-1 float [r,g,b,1]),"ty":"st" stroke, "ty":"tr" transform} inside \
{"ty":"gr"} groups.
- Keyframed properties use {"a":1,"k":[{"t":0,"s":[...]},{"t":..,"s":[...]}]}. Position values \
are pixel pairs [x,y]; scale is a percentage pair [sx,sy] (100 = original); opacity 0-100.
- Use "ty":"tm" (trim path) with keyframed "s"/"e" for line-drawing animations, and \
rotation/"r" keyframes for sway: for swaying plants, anchor rotation at the bottom (treat it \
like a stalk pivoting on its base) and make rotation go -a -> +a -> -a across the cycle.
- Keep it bold and readable at video size: big shapes, few colors, strong silhouettes. The \
animation must look professional, like the infographic animations in a high-end explainer, \
NOT a shaky wiggle.

Answer ONLY with the JSON object."""

CARTOON_TAIL = """The animation is for a **cartoon character** drawn purely with shapes. \
Build the character as groups of simple shapes (head, torso, arms, legs) and animate it \
with the classic cartoon principles:
- Rotate limbs from their joints: each limb group's transform anchor sits at the \
shoulder/hip; keyframe the rotation so it goes -a -> +a -> -a across the cycle. A walk \
cycle: right leg and left arm in phase, the opposite ones in antiphase, plus the whole \
body bobbing up-down once per step.
- Add life inside the same cycle: a blink (the eye shapes squash to ~10%% height for \
2-3 frames), squash-and-stretch on the landing (scale 108x92 -> 92x108 -> 100x100), a \
subtle head tilt.
- Everything must return EXACTLY to its t=0 value at t=%(op)d (feet at the same contact \
point) so the character can walk in place forever: one full stride per cycle. If the user \
asks to move across the scene, move the whole character layer's position linearly and \
ask how far, or keep the walk in place.
- Flat colors, bold outlines, strong silhouette readable at video size. No text layers.

Answer ONLY with the JSON object."""


CARTOON_SYSTEM = LOTTIE_SYSTEM[:LOTTIE_SYSTEM.index("- Keep it bold")] + CARTOON_TAIL

def _lottie():
    try:
        from lottie.importers import importers
        from lottie.exporters import exporters
    except ImportError:
        raise ConfigError("python-lottie is required for the Motion design mode: "
                          "pip install lottie (rendering to GIF also needs 'cairosvg' and "
                          "the system libcairo, e.g. 'apt install libcairo2').") from None
    return importers, exporters


def generate_lottie(client: Any, model: str, prompt: str, out_path: Path, *,
                    width: int = 960, height: int = 540, n_frames: int = 60,
                    kind: str = "infographic", extra: str = "") -> Dict[str, Any]:
    """Scene description -> validated Lottie JSON written to ``out_path`` (.json).

    The text LLM writes the whole animation; this only normalizes the timeline (frame rate,
    size, loop length) so the loop is seamless no matter what the model produced, and checks
    that python-lottie can actually parse it."""
    from .ai_video import _parse_json_object
    if not (prompt or "").strip():
        raise ValueError("Describe the animation (scene, style and what moves).")
    system = CARTOON_SYSTEM if str(kind).lower().startswith("cartoon") else LOTTIE_SYSTEM
    user = "%s\n\nAnimation description: %s" % (((extra or "").strip() + " to follow."), prompt.strip()) \
        if (extra or "").strip() else prompt.strip()
    content = client.chat(model, [
        {"role": "system", "content": system % {"fr": LOTTIE_FRAMERATE,
                                                "op": int(n_frames), "w": width,
                                                "h": height}},
        {"role": "user", "content": user}])
    data = _parse_json_object(content)
    # normalize the timeline: deterministic loop, exact size, exact frame count
    data["fr"] = LOTTIE_FRAMERATE
    data["ip"] = 0
    data["op"] = int(n_frames)
    data["w"] = width
    data["h"] = height
    if not isinstance(data.get("layers"), list) or not data["layers"]:
        raise ConfigError("The Lottie JSON returned by the model has no layers.")
    out_path = Path(out_path)
    if out_path.suffix != ".json":
        out_path = Path(str(out_path) + ".json")  # the JSON writer always adds the extension
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data), encoding="utf-8")
    _validate_lottie(out_path)
    return data


def _validate_lottie(path: Path) -> Any:
    """Parse the file with python-lottie: an invalid animation dies here, loudly."""
    importers, _ = _lottie()
    with open(path, "r", encoding="utf-8") as fh:
        animation = importers.get("lottie").process(fh)
    if not animation.layers:
        raise ConfigError("The Lottie animation is empty (no layers).")
    return animation


def lottie_convert(animation: Any, fmt: str, dest: Path) -> bool:
    """Export a loaded Lottie animation to ``fmt`` ("gif" or "html") at ``dest``."""
    importers, exporters = _lottie()
    exporter = exporters.get(fmt)
    if exporter is None:
        raise ConfigError("The '%s' exporter of python-lottie needs cairosvg (and the system "
                          "libcairo, e.g. 'apt install libcairo2' / Colab cell 1 installs "
                          "it) to rasterize frames." % fmt)
    exporter.process(animation, str(dest))
    return dest.is_file()


def lottie_to_gif(json_path: Path, dest_base: Path, *, loop_seconds: Optional[float] = None,
                  with_html: bool = True) -> Tuple[Optional[Path], Optional[Path]]:
    """Render the .json Lottie animation into a seamless-looping GIF (+ HTML preview).

    ``loop_seconds`` rescales the frame rate so the whole cycle takes exactly that time.
    Returns ``(gif_path, html_path)``; either may be ``None`` if that export is not asked
    for or the renderer is unavailable (error raised for the GIF, never for the HTML)."""
    animation = _validate_lottie(json_path)
    if loop_seconds:
        span = max(1.0, float(animation.out_point) - float(animation.in_point))
        animation.frame_rate = max(1, round(span / float(loop_seconds)))
    dest_base = Path(dest_base)
    dest_base.parent.mkdir(parents=True, exist_ok=True)
    gif_path: Optional[Path] = Path(str(dest_base) + ".gif")
    _loop_forever = _gif_loop_forever
    try:
        lottie_convert(animation, "gif", gif_path)
        _loop_forever(gif_path)
    except ConfigError:
        gif_path = None  # renderer missing locally: the HTML preview still works
    html_path: Optional[Path] = Path(str(dest_base) + ".html")
    if with_html:
        lottie_convert(animation, "html", html_path)
    else:
        html_path = None
    return gif_path, html_path


def _gif_loop_forever(gif_path: Path) -> None:
    """Re-encode the lottie GIF so it loops forever (loop=0) if it does not already."""
    from PIL import Image
    with Image.open(gif_path) as im:
        if im.info.get("loop") == 0:
            return
        frames = []
        try:
            while True:
                frames.append(im.copy())
                im.seek(im.tell() + 1)
        except EOFError:
            pass
        durations = []
        for _ in frames:
            durations.append(im.info.get("duration", 100))
    frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0)
