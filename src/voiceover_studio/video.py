"""Faceless video: B-roll timed to the voiceover, with motion, music and animated captions.

Everything is rendered by a single ffmpeg call (no Python video dependency):

* B-roll per script segment: put ``![](clip.mp4)`` or ``![](photo.jpg)`` in the script
  (or pass ``--images folder``). Stills get a slow Ken Burns move (zoom in, zoom out
  or pan, alternating), clips are trimmed or looped to fit.
* transitions between shots: a tasteful mix of slide / zoom / fade (``--transition-style``)
* a light cinematic grade: contrast, vignette and film grain (``--grade``)
* word-by-word animated captions via libass (see :mod:`voiceover_studio.captions`)
* an animated hook card in the first seconds (the script's ``# heading`` or ``--hook``)
* background music ducked under the voice: a built-in generated ambient bed or your file
* parts without any picture get an animated gradient with large kinetic typography of
  the segment's key phrase instead of an empty background
"""
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from . import music as musiclib
from .audio import ffmpeg_path
from .captions import animated_ass, build_pages, default_style, get_style, line_layout, to_ass
from .errors import ConfigError
from .studio import RenderResult, Studio
from .subtitles import Cue, cues_from_segments, parse_srt
from .words import Word, estimate, key_phrase, segment_words

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".mkv", ".m4v", ".gif")
#: Transition sets for ``--transition-style``; ``mix`` cycles through its list.
TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "mix": ("smoothleft", "zoomin", "fade", "smoothup"),
    "fade": ("fade",),
    "slide": ("smoothleft", "smoothright"),
    "zoom": ("zoomin",),
    "cut": (),
}
#: Animated backgrounds for parts without a picture (three deep colours each).
PALETTES = (("0x0b1026", "0x3b1d6e", "0x0e6b8c"), ("0x1a0b2e", "0x7a1f5c", "0x1f3a8a"),
            ("0x04211f", "0x0f5e63", "0x2b2f77"), ("0x26070f", "0x8a2c1d", "0x3a1360"),
            ("0x0a1a33", "0x1e5bb8", "0x5a1e8c"))
GRADES = ("cinematic", "none")
SUPERSAMPLE = 1.5  # Ken Burns works on a 1.5x canvas so sub-pixel motion stays smooth


@dataclass
class Shot:
    """One visual: ``kind`` is image, video or kinetic (generated background + key phrase)."""
    duration: float
    kind: str = "kinetic"
    source: Optional[Path] = None
    phrase: str = ""
    start: float = 0.0


def list_images(folder: Path) -> List[Path]:
    if not folder.is_dir():
        raise ConfigError("Images folder not found: %s" % folder)
    media = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS + VIDEO_EXTS)
    if not media:
        raise ConfigError("No images or clips (%s) in %s" % (", ".join(IMAGE_EXTS + VIDEO_EXTS), folder))
    return media


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


def _kind(path: Path) -> str:
    return "video" if path.suffix.lower() in VIDEO_EXTS else "image"


def plan_shots(render: RenderResult, *, media: Sequence[Path] = (), script_dir: Optional[Path] = None,
               max_kinetic_shot: float = 8.0) -> List[Shot]:
    """Decide what is on screen when.

    * Segments that name B-roll in the script (``![](file)``) show it; several files in one
      segment share its time.
    * Other segments take the next file from ``media`` (``--images``) when given.
    * Anything left gets an animated background with the segment's key phrase.
    * Without script B-roll, ``media`` keeps the classic behaviour: one file per segment when
      the counts match, otherwise the files share the whole track evenly.
    """
    segs = render.segments
    total = render.duration
    has_broll = any(getattr(s, "visuals", None) for s in segs)
    if not has_broll and media:
        return [Shot(d, _kind(p), p) for p, d in zip(media, plan_slides(len(media), render))]
    starts = [0.0] + [s.start for s in segs[1:]]
    ends = starts[1:] + [total]
    queue = list(media)
    shots: List[Shot] = []
    for seg, start, end in zip(segs, starts, ends):
        span = max(0.1, end - start)
        files: List[Path] = []
        for ref in getattr(seg, "visuals", None) or []:
            path = Path(ref)
            if not path.is_absolute() and script_dir is not None:
                path = script_dir / path
            if not path.is_file():
                raise ConfigError("B-roll file not found: %s (paths are relative to the script)" % path)
            files.append(path)
        if not files and queue:
            files = [queue.pop(0)]
        if files:
            shots.extend(Shot(span / len(files), _kind(f), f) for f in files)
            continue
        pieces = max(1, int(span // max_kinetic_shot) + (1 if span % max_kinetic_shot > 1.0 else 0))
        sentences = [x for x in re.split(r"(?<=[.!?。！？])\s*", str(seg.text)) if x.strip()] or [seg.text]
        pieces = min(pieces, len(sentences)) if len(sentences) > 1 else pieces
        for i in range(pieces):
            # each piece shows the key phrase of its own share of the sentences
            part = sentences[i * len(sentences) // pieces:(i + 1) * len(sentences) // pieces]
            sub = SimpleNamespace(text=" ".join(part) or seg.text,
                                  emphasis=[e for e in (getattr(seg, "emphasis", None) or [])
                                            if e in " ".join(part)] if pieces > 1 else
                                  getattr(seg, "emphasis", None) or [])
            shots.append(Shot(span / pieces, "kinetic", None, key_phrase(sub)))
    t = 0.0
    for shot in shots:
        shot.start = t
        t += shot.duration
    return shots


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


def _moves(zoom: float) -> Tuple[Tuple[float, float, float, float, float, float], ...]:
    """Ken Burns moves, cycled per still: (zoom start, zoom end, x start, x end, y start, y end);
    x / y are the crop position as a fraction of the free space (0.5 = centred)."""
    z = 1.0 + zoom
    return ((1.0, z, 0.5, 0.5, 0.45, 0.5),         # push in
            (z, z, 0.0, 1.0, 0.5, 0.5),            # pan left -> right
            (z, 1.0, 0.5, 0.5, 0.5, 0.45),         # pull out
            (z, z + zoom * 0.3, 1.0, 0.0, 0.6, 0.4))  # pan right -> left, slight rise


def _still_chain(idx: int, label: str, size: Tuple[int, int], fps: int, seconds: float, fit: str,
                 motion: str, zoom: float, move: int) -> str:
    w, h = size
    frames = max(1, int(round(seconds * fps)))
    cw, ch = _even(w * SUPERSAMPLE), _even(h * SUPERSAMPLE)
    if fit == "contain":
        base = ("[%d:v]split=2[bg%d][fg%d];"
                "[bg%d]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,gblur=sigma=40,"
                "eq=brightness=-0.08[bgs%d];"
                "[fg%d]scale=%d:%d:force_original_aspect_ratio=decrease[fgs%d];"
                "[bgs%d][fgs%d]overlay=(W-w)/2:(H-h)/2,setsar=1" % (
                    idx, idx, idx, idx, cw, ch, cw, ch, idx, idx, cw, ch, idx, idx, idx))
    else:
        base = "[%d:v]scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,crop=%d:%d,setsar=1" % (
            idx, cw, ch, cw, ch)
    if motion == "kenburns":
        z0, z1, x0, x1, y0, y1 = _moves(zoom)[move % 4]
        p = "(on/%d)" % max(1, frames - 1)
        z = "%.4f+%.4f*%s" % (z0, z1 - z0, p)
        x = "(iw-iw/zoom)*(%.3f+%.3f*%s)" % (x0, x1 - x0, p)
        y = "(ih-ih/zoom)*(%.3f+%.3f*%s)" % (y0, y1 - y0, p)
        body = ",zoompan=z='%s':x='%s':y='%s':d=%d:s=%dx%d:fps=%d" % (z, x, y, frames, w, h, fps)
    else:
        body = ",scale=%d:%d,loop=loop=%d:size=1:start=0" % (w, h, frames + 1)
    return "%s%s,trim=end_frame=%d,setpts=N/(%d*TB),fps=%d,format=yuv420p[%s]" % (
        base, body, frames, fps, fps, label)


def _clip_chain(idx: int, label: str, size: Tuple[int, int], fps: int, seconds: float) -> str:
    w, h = size
    frames = max(1, int(round(seconds * fps)))
    return ("[%d:v]fps=%d,scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,"
            "trim=end_frame=%d,setpts=N/(%d*TB),fps=%d,format=yuv420p[%s]" % (
                idx, fps, w, h, w, h, frames, fps, fps, label))


def _kinetic_input(i: int, size: Tuple[int, int], fps: int, seconds: float, radial: bool) -> List[str]:
    w, h = size
    c0, c1, c2 = PALETTES[i % len(PALETTES)]
    src = "gradients=s=%dx%d:c0=%s:c1=%s:c2=%s:n=3:speed=0.012:rate=%d:d=%.3f" % (
        w, h, c0, c1, c2, fps, seconds + 0.1)
    return ["-f", "lavfi", "-i", src]


@lru_cache(maxsize=4)
def ffmpeg_caps(exe: str) -> Tuple[FrozenSet[str], bool, bool]:
    """``(xfade transitions, has gradients, gradients has type)`` of the installed ffmpeg."""
    def helptext(name: str) -> str:
        try:
            proc = subprocess.run([exe, "-hide_banner", "-h", "filter=" + name], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=20)
            return proc.stdout.decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError):
            return ""
    xf = helptext("xfade")
    names = frozenset(m for m in re.findall(r"^\s+(\w+)\s+-?\d+\s+\.\.FV", xf, re.M))
    grad = helptext("gradients")
    return names, "gradients AVOptions" in grad, bool(re.search(r"^\s+type\s", grad, re.M))


def build_command(exe: str, shots: Sequence[Shot], audio: str, output: str, *, size: Tuple[int, int],
                  fps: int, fit: str = "cover", motion: str = "kenburns", transition: float = 0.5,
                  transition_style: str = "mix", ass_path: Optional[str] = None,
                  fonts_dir: Optional[str] = None, progress_bar: bool = False,
                  total: Optional[float] = None, zoom: float = 0.12, grade: str = "cinematic",
                  music: Optional[str] = None, music_builtin: bool = False, music_volume: float = 0.5,
                  duck: bool = True, preset: str = "veryfast", crf: int = 20,
                  caps: Optional[Tuple[FrozenSet[str], bool, bool]] = None) -> List[str]:
    """ffmpeg argument list for the whole video (exposed for tests).

    ``caps`` is :func:`ffmpeg_caps` of the target ffmpeg; ``None`` assumes a recent ffmpeg."""
    w, h = size
    n = len(shots)
    if n == 0:
        raise ConfigError("Nothing to show")
    durations = [s.duration for s in shots]
    total = total or sum(durations)
    names, has_gradients, gradient_type = caps if caps else (frozenset(), True, True)
    style = TRANSITIONS.get(transition_style)
    if style is None:
        raise ConfigError("transition style must be one of: %s" % ", ".join(TRANSITIONS))
    if names:
        style = tuple(t for t in style if t in names) or (("fade",) if style else ())
    fade = max(0.0, min(transition, min(durations) / 3.0)) if (n > 1 and style) else 0.0
    args = [exe, "-hide_banner", "-loglevel", "error", "-y"]
    parts = []
    still = 0
    for i, shot in enumerate(shots):
        length = shot.duration + (fade if i < n - 1 else 0.0)
        label = "s%d" % i
        if shot.kind == "kinetic" or shot.source is None:
            if has_gradients:
                args += _kinetic_input(i, size, fps, length, gradient_type)
            else:
                c0 = PALETTES[i % len(PALETTES)][1]
                args += ["-f", "lavfi", "-i", "color=c=%s:s=%dx%d:r=%d:d=%.3f" % (c0, w, h, fps, length + 0.1)]
            parts.append("[%d:v]format=yuv420p,trim=end_frame=%d,setpts=N/(%d*TB),fps=%d[%s]" % (
                i, max(1, int(round(length * fps))), fps, fps, label))
        elif shot.kind == "video":
            args += ["-stream_loop", "-1", "-t", "%.3f" % (length + 0.2), "-i", str(shot.source)]
            parts.append(_clip_chain(i, label, size, fps, length))
        else:
            args += ["-i", str(shot.source)]
            parts.append(_still_chain(i, label, size, fps, length, fit, motion, zoom, still))
            still += 1
    voice_idx = n
    args += ["-i", str(audio)]
    music_idx = None
    if music:
        music_idx = n + 1
        args += musiclib.builtin_input(music, total) if music_builtin else musiclib.file_input(music)
    last = "s0"
    offset = 0.0
    for i in range(1, n):
        offset += durations[i - 1]
        out = "x%d" % i
        if fade > 0:
            parts.append("[%s][s%d]xfade=transition=%s:duration=%.3f:offset=%.3f[%s]" % (
                last, i, style[(i - 1) % len(style)], fade, offset, out))
        else:
            parts.append("[%s][s%d]concat=n=2:v=1:a=0[%s]" % (last, i, out))
        last = out
    if grade == "cinematic":
        parts.append("[%s]eq=contrast=1.06:saturation=1.08,vignette=angle=PI/5,"
                     "noise=alls=5:allf=t,format=yuv420p[graded]" % last)
        last = "graded"
    elif grade != "none":
        raise ConfigError("grade must be one of: %s" % ", ".join(GRADES))
    if progress_bar:
        bar_h = max(4, int(h * 0.005))
        parts.append("color=c=0xFFD700@0.9:s=%dx%d:r=%d[bar]" % (w, bar_h, fps))
        parts.append("[%s][bar]overlay=x='-W+W*t/%.3f':y=H-h:shortest=1[pb]" % (last, max(total, 0.1)))
        last = "pb"
    if ass_path:
        sub = "ass=%s" % ass_path
        if fonts_dir:
            sub += ":fontsdir=%s" % fonts_dir
        parts.append("[%s]%s[v]" % (last, sub))
        last = "v"
    audio_map = "%d:a" % voice_idx
    if music_idx is not None:
        parts.append(musiclib.mix_filter("%d:a" % voice_idx, "%d:a" % music_idx, "aout", duration=total,
                                         volume=music_volume, builtin=music_builtin, duck=duck))
        audio_map = "[aout]"
    args += ["-filter_complex", ";".join(parts), "-map", "[%s]" % last, "-map", audio_map,
             "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
             "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
             "-t", "%.3f" % total, str(output)]
    return args


def caption_words(render: RenderResult) -> List[Word]:
    """Word timings for the whole track: engine word boundaries where available, else
    estimated from sentence or segment timing (or from recognised subtitles)."""
    if render.subtitle_source == "recognize" and render.srt_path:
        words: List[Word] = []
        for cue in parse_srt(Path(render.srt_path).read_text(encoding="utf-8")):
            words.extend(estimate(cue.start, cue.end, cue.text))
        return words
    out: List[Word] = []
    for seg in render.segments:
        out.extend(segment_words(seg))
    return out


def render_video(studio: Studio, images: Any, script: Any, output: Any, *, voices: Any = None,
                 default_voice: Optional[str] = None, size: Tuple[int, int] = (1920, 1080),
                 fps: int = 30, subtitles: str = "burn", fit: str = "cover",
                 subtitle_source: str = "timing", style: str = "auto", motion: str = "kenburns",
                 transition: float = 0.5, transition_style: str = "mix", title: Any = "auto",
                 hook_seconds: float = 2.2, speaker_labels: bool = False, progress_bar: bool = True,
                 font: Optional[str] = None, music: Optional[str] = None, music_volume: float = 0.5,
                 duck: bool = True, grade: str = "cinematic", **render_kwargs: Any) -> dict:
    """Render script -> voiceover -> MP4. ``subtitles``: burn (default) | sidecar | none.

    ``style``: caption style, ``auto`` = tiktok for vertical, clean for landscape.
    ``title``: the hook card. ``"auto"`` uses the script's first ``# heading`` when there is
    one, a string sets the text, ``False`` turns it off.
    ``music``: ``ambient`` / ``pulse`` (built in, generated) or a path to an audio file.
    ``font``: a font family name, or a path to a .ttf/.otf file.
    """
    if subtitles not in ("sidecar", "burn", "none"):
        raise ConfigError("subtitles must be sidecar, burn or none")
    if motion not in ("kenburns", "none"):
        raise ConfigError("motion must be kenburns or none")
    if grade not in GRADES:
        raise ConfigError("grade must be one of: %s" % ", ".join(GRADES))
    if transition_style not in TRANSITIONS:
        raise ConfigError("transition style must be one of: %s" % ", ".join(TRANSITIONS))
    style = default_style(size) if style in (None, "", "auto") else style
    st = get_style(style)
    music_src, music_builtin = musiclib.parse_music(music)
    if music_src and not music_builtin and not Path(music_src).is_file():
        raise ConfigError("Music file not found: %s (or use --music ambient)" % music_src)
    exe = ffmpeg_path()
    if not exe:
        raise ConfigError("Video export needs ffmpeg (https://ffmpeg.org). Run `voiceover doctor`.")
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    media: List[Path] = list_images(Path(images)) if images else []
    workdir = out.parent / (out.stem + "_voiceover")
    render = studio.render_script(script, workdir, voices=voices, default_voice=default_voice,
                                  output_name="voiceover.wav",
                                  subtitles="none" if subtitles == "none" else subtitle_source,
                                  **render_kwargs)
    shots = plan_shots(render, media=[p.resolve() for p in media], script_dir=Path(script).resolve().parent)

    if title is True or title == "auto":
        heading = script_title(script)
    else:
        heading = title or None
    fonts_dir = None
    font_name = font
    if font and Path(font).is_file():
        fonts_dir = str(Path(font).resolve().parent)
        font_name = _font_family(Path(font)) or Path(font).stem
    kinetic = [(s.start + 0.1, s.start + s.duration - 0.1, s.phrase) for s in shots
               if s.kind == "kinetic" and s.phrase]
    with tempfile.TemporaryDirectory() as tmp:
        ass_path = None
        if subtitles == "burn" or heading or kinetic:
            pages = []
            cues: List[Cue] = []
            if subtitles == "burn" and render.srt_path:
                if st.mode == "static":
                    if render.subtitle_source == "timing":
                        max_chars, width = line_layout(size, style)
                        cues = cues_from_segments(render.segments, max_chars=max_chars, line_width=width)
                    else:
                        cues = [Cue(s.start, s.end, s.text) for s in
                                parse_srt(Path(render.srt_path).read_text(encoding="utf-8"))]
                else:
                    pages = build_pages(caption_words(render), size, style)
            if st.mode == "static" and speaker_labels:
                doc = to_ass(cues, size, style=style, font=font_name, speaker_labels=True, title=heading)
            else:
                doc = animated_ass(pages, size, style=style, font=font_name, hook=heading,
                                   hook_seconds=hook_seconds, kinetic=kinetic, static_cues=cues)
            (Path(tmp) / "captions.ass").write_text(doc, encoding="utf-8")
            ass_path = "captions.ass"  # relative: avoids filter-path escaping on every OS
        # Encode next to the temporary files, then move: some network / FUSE file systems
        # cannot rewrite the file in place for +faststart.
        tmp_out = Path(tmp) / ("render" + (out.suffix or ".mp4"))
        cmd = build_command(exe, shots, str(Path(render.audio_path).resolve()), str(tmp_out),
                            size=size, fps=fps, fit=fit, motion=motion, transition=transition,
                            transition_style=transition_style, ass_path=ass_path, fonts_dir=fonts_dir,
                            progress_bar=progress_bar, total=render.duration, grade=grade,
                            music=music_src if music_builtin else (str(Path(music_src).resolve())
                                                                   if music_src else None),
                            music_builtin=music_builtin, music_volume=music_volume, duck=duck,
                            caps=ffmpeg_caps(exe))
        proc = subprocess.run(cmd, cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise ConfigError("ffmpeg could not render the video: "
                              + proc.stderr.decode("utf-8", "replace").strip()[-2500:])
        shutil.move(str(tmp_out), str(out))
    srt_out = None
    if render.srt_path and subtitles in ("sidecar", "burn"):
        srt_out = str(out.with_suffix(".srt"))
        shutil.copy(render.srt_path, srt_out)
    info = {"video": str(out), "subtitles": srt_out, "audio": render.audio_path,
            "duration": round(render.duration, 3), "images": sum(1 for s in shots if s.kind != "kinetic"),
            "shots": len(shots), "manifest": render.manifest_path, "style": style, "motion": motion,
            "music": music_src or None}
    (workdir / "video.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


def _font_family(path: Path) -> Optional[str]:
    """Name libass will match for a font file passed with ``--font``.

    libass matches fonts loaded from ``fontsdir`` by their legacy family name (name ID 1,
    e.g. "Montserrat ExtraBold" for a single-weight file), which is read straight from the
    font's ``name`` table; the file name is the fallback."""
    try:
        name = font_family_name(path.read_bytes())
    except OSError:
        name = None
    return name or path.stem.replace("-", " ").replace("_", " ") or None


def font_family_name(data: bytes) -> Optional[str]:
    """Legacy family name (name ID 1) of a TrueType / OpenType font, preferring English."""
    import struct
    try:
        if data[:4] == b"ttcf":  # collection: first font
            data_offset = struct.unpack(">I", data[12:16])[0]
        else:
            data_offset = 0
        num_tables = struct.unpack(">H", data[data_offset + 4:data_offset + 6])[0]
        for i in range(num_tables):
            rec = data_offset + 12 + 16 * i
            tag, _, offset, _ = struct.unpack(">4sIII", data[rec:rec + 16])
            if tag != b"name":
                continue
            _, count, strings = struct.unpack(">HHH", data[offset:offset + 6])
            best = None
            for j in range(count):
                r = offset + 6 + 12 * j
                platform, encoding, language, name_id, length, str_off = struct.unpack(
                    ">HHHHHH", data[r:r + 12])
                if name_id != 1:
                    continue
                raw = data[offset + strings + str_off: offset + strings + str_off + length]
                if platform in (0, 3):
                    text = raw.decode("utf-16-be", "replace")
                elif platform == 1:
                    text = raw.decode("latin-1", "replace")
                else:
                    continue
                rank = 0 if (platform == 3 and language == 0x409) else 1
                if text.strip() and (best is None or rank < best[0]):
                    best = (rank, text.strip())
            return best[1] if best else None
    except (struct.error, IndexError):
        return None
    return None
