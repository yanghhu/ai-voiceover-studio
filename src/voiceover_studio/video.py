"""Faceless video: a slideshow of images timed to the voiceover, with subtitles.

Requires the optional extra: ``pip install 'ai-voiceover-studio[video]'`` (moviepy).
Burned-in subtitles additionally need an ffmpeg build with libass (most have it).
"""
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, List, Optional, Tuple

from .audio import ffmpeg_path
from .errors import ConfigError
from .studio import RenderResult, Studio

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def _moviepy():
    try:
        import moviepy  # noqa: F401
    except ImportError:
        raise ConfigError("Video export needs moviepy: pip install 'ai-voiceover-studio[video]'") from None
    try:  # moviepy >= 2
        from moviepy import AudioFileClip, ImageClip, concatenate_videoclips
        v2 = True
    except ImportError:  # moviepy 1.x
        from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips  # type: ignore
        v2 = False
    return AudioFileClip, ImageClip, concatenate_videoclips, v2


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


def _frame(path: Path, size: Tuple[int, int], fit: str):
    from PIL import Image, ImageFilter  # moviepy depends on Pillow
    import numpy as np

    w, h = size
    img = Image.open(path).convert("RGB")
    if fit == "cover":
        scale = max(w / img.width, h / img.height)
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
        left, top = (img.width - w) // 2, (img.height - h) // 2
        return np.array(img.crop((left, top, left + w, top + h)))
    # contain: fit inside a blurred, enlarged copy of itself (no black bars)
    bg_scale = max(w / img.width, h / img.height)
    bg = img.resize((max(1, round(img.width * bg_scale)), max(1, round(img.height * bg_scale))))
    bg = bg.crop(((bg.width - w) // 2, (bg.height - h) // 2, (bg.width - w) // 2 + w,
                  (bg.height - h) // 2 + h)).filter(ImageFilter.GaussianBlur(24))
    scale = min(w / img.width, h / img.height)
    fg = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    bg.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    return np.array(bg)


def _burn(video: Path, srt: Path, output: Path) -> None:
    exe = ffmpeg_path()
    if not exe:
        raise ConfigError("Burning subtitles needs ffmpeg; use --subtitles sidecar instead.")
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "subs.srt"  # avoid escaping issues in the filter path
        shutil.copy(srt, local)
        style = "FontSize=18,Outline=2,Shadow=0,MarginV=40"
        proc = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video.resolve()),
                               "-vf", "subtitles=subs.srt:force_style='%s'" % style,
                               "-c:a", "copy", str(output.resolve())],
                              cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise ConfigError("ffmpeg could not burn subtitles (needs libass): "
                              + proc.stderr.decode("utf-8", "replace")[-400:])


def render_video(studio: Studio, images: Any, script: Any, output: Any, *, voices: Any = None,
                 default_voice: Optional[str] = None, size: Tuple[int, int] = (1920, 1080),
                 fps: int = 30, subtitles: str = "sidecar", fit: str = "cover",
                 subtitle_source: str = "timing", **render_kwargs: Any) -> dict:
    """Render script -> voiceover -> slideshow MP4. ``subtitles``: sidecar | burn | none."""
    if subtitles not in ("sidecar", "burn", "none"):
        raise ConfigError("subtitles must be sidecar, burn or none")
    AudioFileClip, ImageClip, concatenate_videoclips, v2 = _moviepy()
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    pictures = list_images(Path(images))
    workdir = out.parent / (out.stem + "_voiceover")
    render = studio.render_script(script, workdir, voices=voices, default_voice=default_voice,
                                  output_name="voiceover.wav",
                                  subtitles="none" if subtitles == "none" else subtitle_source,
                                  **render_kwargs)
    durations = plan_slides(len(pictures), render)
    clips = []
    for pic, seconds in zip(pictures, durations):
        clip = ImageClip(_frame(pic, size, fit))
        clips.append(clip.with_duration(seconds) if v2 else clip.set_duration(seconds))
    track = AudioFileClip(render.audio_path)
    video = concatenate_videoclips(clips, method="chain")
    video = video.with_audio(track) if v2 else video.set_audio(track)
    target = out if subtitles != "burn" else out.with_name(out.stem + ".raw" + out.suffix)
    kwargs = dict(fps=fps, codec="libx264", audio_codec="aac", logger=None)
    video.write_videofile(str(target), **kwargs)
    track.close()
    video.close()
    srt_out = None
    if render.srt_path and subtitles == "burn":
        _burn(target, Path(render.srt_path), out)
        target.unlink()
    if render.srt_path and subtitles in ("sidecar", "burn"):
        srt_out = str(out.with_suffix(".srt"))
        shutil.copy(render.srt_path, srt_out)
    return {"video": str(out), "subtitles": srt_out, "audio": render.audio_path,
            "duration": round(render.duration, 3), "images": len(pictures),
            "manifest": render.manifest_path}
