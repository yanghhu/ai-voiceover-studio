"""AI review & polish: the model watches the rendered video and improves it.

Like a human editor, the vision model looks at frames of the rendered preview, scores how
professional the result is and reports concrete issues; the polish loop then applies the
fixes it can (color grading, restyled overlay cards, clips swapped for better-matching
catalog entries), re-renders and reviews again — until the score is good or the rounds
run out.
"""
from __future__ import annotations

import base64
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .errors import ConfigError

REVIEW_SYSTEM = (
    "You are a strict video post-production supervisor. You see numbered frames of a "
    "narrated video and its script. Judge how professional the result looks. Respond with "
    "ONLY a JSON object, no markdown fences:\n"
    '{{"score": <0-10 overall professionalism>, '
    '"issues": [{{"frame": <1-based frame number>, '
    '"label": "<dark|flat|blurry|cluttered|unreadable|mismatch|watermark>", '
    '"detail": "short concrete description"}}]}}\n'
    "Labels: dark = too dark, flat = washed-out colors, blurry = soft/low-res footage, "
    "cluttered = busy frame that hides the subject, unreadable = overlay text hard to read, "
    "mismatch = the picture does not fit the narration of its shot, watermark = visible "
    "stock watermark. Report only real, visible issues; an empty issues list means the "
    "frames look professional."
)

COLOR_LABELS = ("dark", "flat")
SCRIPT_LABELS = ("unreadable", "mismatch", "cluttered")

MEDIA_RE = re.compile(r"^!\[\]\(([^)]+)\)(\{overlay\})?\s*$")


def extract_frames(video: Path, dest_dir: Path, n: int = 6) -> List[Path]:
    """Sample n frames evenly from the video (needs ffmpeg + ffprobe)."""
    from .audio import _ffmpeg
    from .clips import probe_duration
    duration = probe_duration(Path(video))
    if duration <= 0:
        raise ConfigError("Cannot read the video duration (ffprobe): is ffmpeg installed?")
    dest_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    interval = duration / (n + 1)
    for i in range(1, n + 1):
        out = dest_dir / ("frame_%02d.jpg" % i)
        try:
            _ffmpeg(["-ss", "%.2f" % (interval * i), "-i", str(video),
                     "-frames:v", "1", "-q:v", "3", str(out)])
        except ConfigError:
            continue
        if out.is_file():
            frames.append(out)
    if not frames:
        raise ConfigError("No frame could be extracted from the video.")
    return frames


def review_video(client: Any, model: str, video: Path, script: str, *,
                 n_frames: int = 6, frames: Optional[Sequence[Path]] = None
                 ) -> Dict[str, Any]:
    """Vision review of the rendered video: {score, issues:[{frame, label, detail}]}."""
    from .ai_video import _parse_json_object
    if frames is None:
        frames = extract_frames(Path(video), Path(video).parent / "review_frames", n_frames)
    if not frames:
        raise ConfigError("No frames to review.")
    content: List[Dict[str, Any]] = [{"type": "text", "text": "Script of the video:\n%s"
                                      % (script or "(no script)")[:3000]}]
    for i, frame in enumerate(frames, 1):
        encoded = base64.b64encode(Path(frame).read_bytes()).decode("ascii")
        content.append({"type": "text", "text": "Frame %d:" % i})
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64," + encoded}})
    answer = client.chat(model, [{"role": "system", "content": REVIEW_SYSTEM},
                                 {"role": "user", "content": content}], max_tokens=800)
    report = _parse_json_object(answer)
    issues = []
    for item in report.get("issues") or []:
        if not isinstance(item, dict):
            continue
        try:
            frame = int(item.get("frame", 0))
        except (TypeError, ValueError):
            continue
        label = str(item.get("label", "")).strip().lower()
        if label:
            issues.append({"frame": frame, "label": label,
                           "detail": str(item.get("detail", ""))[:160]})
    try:
        score = float(report.get("score", 0))
    except (TypeError, ValueError):
        score = 0.0
    return {"score": score, "issues": issues}


def parse_script_blocks(script: str) -> List[Dict[str, Any]]:
    """Script -> blocks [{media, overlay, text}]; media lines start with ![](path)."""
    blocks: List[Dict[str, Any]] = []
    for line in (script or "").splitlines():
        stripped = line.strip()
        match = MEDIA_RE.match(stripped)
        if match:
            blocks.append({"media": match.group(1), "overlay": bool(match.group(2)),
                           "text": ""})
        elif stripped.startswith("#") or not stripped:
            continue
        else:
            for block in reversed(blocks):
                if block["media"] and not block["overlay"]:
                    block["text"] = (block["text"] + " " + stripped).strip()
                    break
            else:
                blocks.append({"media": None, "overlay": False, "text": stripped})
    return blocks


def _block_shot(blocks: List[Dict[str, Any]], frame: int, n_frames: int) -> int:
    """Approximate the shot a sampled frame belongs to (equal-duration assumption)."""
    shots = [b for b in blocks if b["media"] and not b["overlay"]]
    if not shots:
        return 0
    index = min(len(shots) - 1, (frame - 1) * len(shots) // max(1, n_frames))
    return blocks.index(shots[index]) + 1


def swap_shot_media(script: str, shot: int, catalog: List[Dict[str, Any]]
                    ) -> Tuple[str, Optional[str]]:
    """Replace the clip of shot N with the best-matching unused catalog entry."""
    blocks = parse_script_blocks(script)
    media_blocks = [b for b in blocks if b["media"] and not b["overlay"]]
    if shot < 1 or shot > len(media_blocks):
        return script, None
    block = media_blocks[shot - 1]
    used = {b["media"] for b in blocks if b["media"]}
    words = {w for w in re.findall(r"[a-zà-ù']{4,}", block["text"].lower())}
    best, best_hits = None, 0
    for entry in catalog:
        path = entry.get("clip_path")
        if not path or path in used or not Path(path).is_file():
            continue
        haystack = " ".join(entry.get("tags") or []) + " " + entry.get("description", "")
        hits = sum(1 for w in words if w in haystack.lower())
        if hits > best_hits:
            best, best_hits = entry, hits
    if best is None:
        return script, None
    lines = script.splitlines()
    needle = "![](%s)" % block["media"]
    for i, line in enumerate(lines):
        if line.strip().startswith(needle):
            lines[i] = line.replace(block["media"], best["clip_path"])
            break
    return "\n".join(lines), best.get("description", "")[:120]


def restyle_shot_card(script: str, shot: int, plan_item: Dict[str, Any], workdir: Path,
                      style: str) -> Tuple[str, Optional[str]]:
    """Re-draw the overlay card of shot N (1-based over the video clips) in a new style."""
    from .overlays import render_card
    blocks = parse_script_blocks(script)
    media_blocks = [(i, b) for i, b in enumerate(blocks) if b["media"] and not b["overlay"]]
    if shot < 1 or shot > len(media_blocks):
        return script, None
    index = media_blocks[shot - 1][0]
    card = next((b for b in blocks[index + 1:] if b["media"] and b["overlay"]), None)
    if card is None:
        return script, None
    path = render_card(plan_item, workdir / ("card_shot_%02d" % shot), style=style)
    lines = script.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("![](%s)" % card["media"]):
            lines[i] = line.replace(card["media"], str(path))
            break
    return "\n".join(lines), str(path)


def apply_color_fix(video: Path, workdir: Path, labels: Sequence[str]) -> Path:
    """Post-process the video with an ffmpeg eq filter (dark/flat fixes)."""
    from .audio import _ffmpeg
    labels = set(labels)
    brightness = 0.06 if "dark" in labels else 0.0
    contrast = 0.10 if "flat" in labels else 0.0
    saturation = 1.25 if "flat" in labels else 1.0
    workdir.mkdir(parents=True, exist_ok=True)
    out = workdir / ("polished_%02d.mp4" % (len(list(workdir.glob("polished_*.mp4"))) + 1))
    args = ["-i", str(video), "-vf", "eq=brightness=%.2f:contrast=%.2f:saturation=%.2f"
            % (brightness, contrast, saturation), "-c:a", "copy", str(out)]
    _ffmpeg(args)
    return out


def polish_video(client: Any, model: str, video: Path, script: str, workdir: Path, *,
                 max_rounds: int = 2, overlay_plan: Optional[List[Dict[str, Any]]] = None,
                 card_style: str = "Scuro", catalog: Optional[List[Dict[str, Any]]] = None,
                 rerender: Optional[Callable[[str], str]] = None,
                 progress: Optional[Callable[[str], None]] = None,
                 n_frames: int = 6) -> Dict[str, Any]:
    """Review -> fix -> re-render loop. Returns {score, rounds, fixes, video, script}."""
    def say(message: str) -> None:
        if progress:
            progress(message)

    video = Path(video)
    script = script or ""
    plan_by_scene: Dict[int, Dict[str, Any]] = {}
    for item in overlay_plan or []:
        try:
            plan_by_scene[int(item.get("scene", 0))] = item
        except (TypeError, ValueError):
            continue
    fixes: List[str] = []
    score = None
    rounds = 0
    for round_no in range(1, max(1, max_rounds) + 1):
        rounds = round_no
        say("Rounds %d: the model watches the video..." % round_no)
        report = review_video(client, model, video, script, n_frames=n_frames)
        score = report["score"]
        issues = report["issues"]
        say("Score **%.0f/10**, %d issue(s) detected." % (score, len(issues)))
        if score >= 8 or not issues:
            break
        color = [i["label"] for i in issues if i["label"] in COLOR_LABELS]
        script_issues = [i for i in issues if i["label"] in SCRIPT_LABELS]
        changed = False
        if color:
            video = apply_color_fix(video, workdir, color)
            fixes.append("color correction (%s)" % ", ".join(sorted(set(color))))
            say("Color correction applied: %s." % ", ".join(sorted(set(color))))
            changed = True
        for issue in script_issues:
            shot = _block_shot(parse_script_blocks(script), issue["frame"], n_frames)
            if not shot:
                continue
            if issue["label"] == "unreadable" and shot in plan_by_scene:
                contrast = "Chiaro" if card_style in ("", "Scuro", "Blu notte") else "Scuro"
                script, path = restyle_shot_card(script, shot, plan_by_scene[shot], workdir,
                                                 contrast)
                if path:
                    fixes.append("overlay card of shot %d redrawn (%s)" % (shot, contrast))
                    say("Overlay card of shot %d redrawn for readability." % shot)
                    changed = True
            elif issue["label"] in ("mismatch", "cluttered") and catalog:
                script, description = swap_shot_media(script, shot, catalog)
                if description is not None:
                    fixes.append("clip of shot %d replaced (%s...)" % (shot, description[:60]))
                    say("Clip of shot %d replaced with a better-matching one." % shot)
                    changed = True
        if not changed:
            say("No automatic fix available for these issues.")
            break
        if rerender is not None:
            video = Path(rerender(script))
            say("Preview re-rendered.")
    return {"score": score, "rounds": rounds, "fixes": fixes,
            "video": str(video), "script": script}
