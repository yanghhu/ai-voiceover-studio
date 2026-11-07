"""Faceless video: images timed to the voiceover, with motion and styled captions.

Everything is rendered by a single ffmpeg call (no Python video dependency):

* slow Ken Burns zoom/pan on every image (``motion="kenburns"``, or ``"none"``)
* soft cross-fades between images (``transition`` seconds)
* styled, burned-in captions via libass (see :mod:`voiceover_studio.captions`)
* an optional title card taken from the script's first ``# heading``
* an optional thin progress bar

Without ``--images`` a slow animated gradient is used as the background, so a
script alone is enough to get a video.
"""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from .audio import ffmpeg_path
from .captions import line_layout, to_ass
from .errors import ConfigError
from .studio import RenderResult, Studio
from .subtitles import cues_from_segments, parse_srt, Cue

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
#: Background palettes used when no images are given (two colours each).
PALETTES = (("0x1b2a6b", "0x3a7bd5"), ("0x2b1055", "0x7597de"), ("0x0f2027", "0x2c5364"),
            ("0x42275a", "0x734b6d"))


def list_images(folder: Path) -> List[Path]:
    if not folder.is_dir():
        raise ConfigError("Images folder not found: %s" % folder)
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not images:
        raise ConfigError("No images (%s) in %s" % (", ".join(IMAGE_EXTS), folder))
    return images


def plan_slides(n_images: int, render: RenderResult) -> List[float]:
    """Seconds per image. One image per voiced segment if the counts match,
    otherwise the track is split evenly."""
    total = render.duration
    segs = render.segments
    if n_images == len(segs) and n_images > 0:
        starts = [0.0] + [s.start for s in segs[1:]]
        ends = starts[1:] + [total]
        return [max(0.1, e - s) for s, e in zip(starts, ends)]
    return [total / n_images] * n_images


def script_title(script: Any) -> Optional[str]:
    """First Markdown ``# heading`` of the script, if any."""
    try:
        for line in Path(script).read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*#\s+(.+?)\s*#*\s*$", line)
            if m:
                return m.group(1)
    except OSError:
        return None
    return None


def _even(n: float) -> int:
    return max(2, int(round(n / 2.0)) * 2)


def _slide_chain(idx: int, label: str, size: Tuple[int, int], fps: int, seconds: float,
                 fit: str, motion: str, zoom: float) -> str:
    """Filter chain for one input image -> ``[label]`` of exactly ``seconds``."""
    w, h = size
    frames = max(1, int(round(seconds * fps)))
    # Work on a slightly larger canvas so the zoom never shows an edge.
    cw, ch = _even(w * (1 + zoom)), _even(h * (1 + zoom))
    if fit == "contain":
        base = ("[%d:v]split=2[bg%d][fg%d];"
                "[bg%d]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,gblur=sigma=40,"
                "eq=brightness=-0.08[bgs%d];"
                "[fg%d]scale=%d:%d:force_original_aspect_ratio=decrease[fgs%d];"
                "[bgs%d][fgs%d]overlay=(W-w)/2:(H-h)/2,setsar=1" % (
                    idx, idx, idx, idx, cw, ch, cw, ch, idx, idx, cw, ch, idx, idx, idx))
    else:
        base = "[%d:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1" % (
            idx, cw, ch, cw, ch)
    # Decode and scale the still once, then repeat that frame (much faster than
    # re-decoding a looped image for every output frame).
    base += ",loop=loop=%d:size=1:start=0,setpts=N/(%d*TB)" % (frames + 1, fps)
    if motion == "kenburns":
        # Alternate zoom-in / zoom-out and pan direction per slide; ease in-out.
        p = "(0.5-0.5*cos(PI*min(n/%d,1)))" % frames
        grow = p if idx % 2 == 0 else "(1-%s)" % p
        # scale up from the output size to the canvas size, then crop the output size
        sw = "trunc((%d+%d*%s)/2)*2" % (w, cw - w, grow)
        sh = "trunc((%d+%d*%s)/2)*2" % (h, ch - h, grow)
        drift = 1 if idx % 4 in (0, 3) else -1
        x = "(iw-%d)/2+%d*(%s-0.5)*(iw-%d)/4" % (w, drift, p, w)
        y = "(ih-%d)/2" % h
        moving = ",scale=w='%s':h='%s':eval=frame:flags=bicubic,crop=%d:%d:x='%s':y='%s'" % (
            sw, sh, w, h, x, y)
    else:
        moving = ",scale=%d:%d,crop=%d:%d" % (w, h, w, h)
    return "%s%s,trim=end_frame=%d,setpts=N/(%d*TB),fps=%d,format=yuv420p[%s]" % (
        base, moving, frames, fps, fps, label)


def build_command(exe: str, pictures: Sequence[Optional[Path]], durations: Sequence[float], audio: str,
                  output: str, *, size: Tuple[int, int], fps: int, fit: str = "cover",
                  motion: str = "kenburns", transition: float = 0.5, ass_path: Optional[str] = None,
                  fonts_dir: Optional[str] = None, progress_bar: bool = False,
                  total: Optional[float] = None, zoom: float = 0.09,
                  preset: str = "veryfast") -> List[str]:
    """ffmpeg argument list for the whole video (exposed for tests)."""
    w, h = size
    n = len(durations)
    fade = max(0.0, min(transition, min(durations) / 3.0)) if n > 1 else 0.0
    args = [exe, "-hide_banner", "-loglevel", "error", "-y"]
    for i, (pic, seconds) in enumerate(zip(pictures, durations)):
        length = seconds + (fade if i < n - 1 else 0.0) + 0.1
        if pic is None:
            c0, c1 = PALETTES[i % len(PALETTES)]
            args += ["-f", "lavfi", "-t", "%.3f" % length, "-i",
                     "gradients=s=%dx%d:c0=%s:c1=%s:x0=0:y0=0:x1=%d:y1=%d:speed=0.008:rate=%d" % (
                         _even(w * (1 + zoom)), _even(h * (1 + zoom)), c0, c1, w, h, fps)]
        else:
            args += ["-i", str(pic)]
    args += ["-i", str(audio)]
    parts = []
    for i, seconds in enumerate(durations):
        length = seconds + (fade if i < n - 1 else 0.0)
        parts.append(_slide_chain(i, "s%d" % i, size, fps, length, fit, motion, zoom))
    last = "s0"
    offset = 0.0
    for i in range(1, n):
        offset += durations[i - 1]
        out = "x%d" % i
        if fade > 0:
            parts.append("[%s][s%d]xfade=transition=fade:duration=%.3f:offset=%.3f[%s]" % (
                last, i, fade, offset, out))
        else:
            parts.append("[%s][s%d]concat=n=2:v=1:a=0[%s]" % (last, i, out))
        last = out
    if progress_bar and total:
        bar_h = max(4, int(h * 0.006))
        parts.append("color=c=white@0.85:s=%dx%d:r=%d[bar]" % (w, bar_h, fps))
        parts.append("[%s][bar]overlay=x='-W+W*t/%.3f':y=H-h:shortest=1[pb]" % (last, max(total, 0.1)))
        last = "pb"
    if ass_path:
        sub = "ass=%s" % ass_path
        if fonts_dir:
            sub += ":fontsdir=%s" % fonts_dir
        parts.append("[%s]%s[v]" % (last, sub))
        last = "v"
    args += ["-filter_complex", ";".join(parts), "-map", "[%s]" % last, "-map", "%d:a" % n,
             "-c:v", "libx264", "-preset", preset, "-crf", "21", "-pix_fmt", "yuv420p",
             "-r", str(fps), "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
             "-shortest", str(output)]
    return args


def render_video(studio: Studio, images: Any, script: Any, output: Any, *, voices: Any = None,
                 default_voice: Optional[str] = None, size: Tuple[int, int] = (1920, 1080),
                 fps: int = 30, subtitles: str = "burn", fit: str = "cover",
                 subtitle_source: str = "timing", style: str = "clean", motion: str = "kenburns",
                 transition: float = 0.5, title: Any = "auto", speaker_labels: bool = False,
                 progress_bar: bool = True, font: Optional[str] = None,
                 **render_kwargs: Any) -> dict:
    """Render script -> voiceover -> MP4. ``subtitles``: burn (default) | sidecar | none.

    ``title``: ``"auto"`` shows the script's first heading only on the generated background
    (images usually carry their own titles), ``True`` always shows it, a string sets it,
    ``False`` hides it.
    ``font``: a font family name, or a path to a .ttf/.otf file.
    """
    if subtitles not in ("sidecar", "burn", "none"):
        raise ConfigError("subtitles must be sidecar, burn or none")
    if motion not in ("kenburns", "none"):
        raise ConfigError("motion must be kenburns or none")
    exe = ffmpeg_path()
    if not exe:
        raise ConfigError("Video export needs ffmpeg (https://ffmpeg.org). Run `voiceover doctor`.")
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    pictures: List[Optional[Path]] = list_images(Path(images)) if images else []
    workdir = out.parent / (out.stem + "_voiceover")
    render = studio.render_script(script, workdir, voices=voices, default_voice=default_voice,
                                  output_name="voiceover.wav",
                                  subtitles="none" if subtitles == "none" else subtitle_source,
                                  **render_kwargs)
    if not pictures:
        count = max(1, min(len(render.segments), 8))
        pictures = [None] * count
    durations = plan_slides(len(pictures), render)

    if title == "auto":
        title = images is None or images == ""
    heading = script_title(script) if title is True else (title or None)
    fonts_dir = None
    font_name = font
    if font and Path(font).is_file():
        fonts_dir = str(Path(font).resolve().parent)
        font_name = _font_family(Path(font)) or Path(font).stem
    with tempfile.TemporaryDirectory() as tmp:
        ass_path = None
        if subtitles == "burn" or heading:
            cues: List[Cue] = []
            if subtitles == "burn" and render.srt_path:
                if render.subtitle_source == "timing":
                    max_chars, width = line_layout(size, style)
                    cues = cues_from_segments(render.segments, max_chars=max_chars, line_width=width)
                else:
                    cues = [Cue(s.start, s.end, s.text) for s in
                            parse_srt(Path(render.srt_path).read_text(encoding="utf-8"))]
            ass_file = Path(tmp) / "captions.ass"
            ass_file.write_text(to_ass(cues, size, style=style, font=font_name,
                                       speaker_labels=speaker_labels, title=heading), encoding="utf-8")
            ass_path = "captions.ass"  # relative: avoids filter-path escaping on every OS
        cmd = build_command(exe, [p.resolve() if p else None for p in pictures], durations,
                            str(Path(render.audio_path).resolve()), str(out.resolve()), size=size,
                            fps=fps, fit=fit, motion=motion, transition=transition, ass_path=ass_path,
                            fonts_dir=fonts_dir, progress_bar=progress_bar, total=render.duration)
        proc = subprocess.run(cmd, cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise ConfigError("ffmpeg could not render the video: "
                              + proc.stderr.decode("utf-8", "replace").strip()[-800:])
    srt_out = None
    if render.srt_path and subtitles in ("sidecar", "burn"):
        srt_out = str(out.with_suffix(".srt"))
        shutil.copy(render.srt_path, srt_out)
    info = {"video": str(out), "subtitles": srt_out, "audio": render.audio_path,
            "duration": round(render.duration, 3), "images": len(pictures),
            "manifest": render.manifest_path, "style": style, "motion": motion}
    (workdir / "video.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


def _font_family(path: Path) -> Optional[str]:
    """Family name of a font file via fc-scan (when fontconfig tools are installed)."""
    exe = shutil.which("fc-scan")
    if not exe:
        return None
    proc = subprocess.run([exe, "--format", "%{family[0]}", str(path)], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL)
    name = proc.stdout.decode("utf-8", "replace").strip()
    return name or None
