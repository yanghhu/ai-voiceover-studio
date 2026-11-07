"""`voiceover doctor`: check the local setup and say exactly what to fix."""
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import __version__
from .audio import ffmpeg_path
from .providers import default_provider_name, edge_installed

Check = Dict[str, Any]
MARK = {"ok": "✔", "warn": "!", "fail": "✘", "info": "·"}


def _check(name: str, status: str, detail: str, fix: Optional[str] = None) -> Check:
    out = {"name": name, "status": status, "detail": detail}
    if fix:
        out["fix"] = fix
    return out


def _ffmpeg_filters(exe: str, runner: Callable[..., Any]) -> str:
    try:
        proc = runner([exe, "-hide_banner", "-filters"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      timeout=20)
        return proc.stdout.decode("utf-8", "replace")
    except Exception:  # pragma: no cover - broken binary
        return ""


def _has_filter(listing: str, name: str) -> bool:
    return any(line.split()[1:2] == [name] for line in listing.splitlines() if line.strip())


def run_checks(*, online: bool = False, environ: Optional[Dict[str, str]] = None,
               which: Callable[[str], Optional[str]] = shutil.which,
               runner: Callable[..., Any] = subprocess.run,
               edge_available: Optional[bool] = None,
               online_test: Optional[Callable[[], float]] = None) -> List[Check]:
    env = os.environ if environ is None else environ
    checks: List[Check] = []
    py = sys.version_info
    checks.append(_check("python", "ok" if py >= (3, 9) else "fail",
                         "Python %d.%d.%d on %s, ai-voiceover-studio %s" % (
                             py[0], py[1], py[2], platform.system() or "?", __version__),
                         None if py >= (3, 9) else "Install Python 3.9 or newer"))

    exe = env.get("FFMPEG_BINARY") or which("ffmpeg") if environ is not None else ffmpeg_path()
    install = {"Darwin": "brew install ffmpeg", "Windows": "winget install ffmpeg"}.get(
        platform.system(), "sudo apt install ffmpeg  (or your package manager)")
    if not exe:
        checks.append(_check("ffmpeg", "fail", "not found: needed for MP3 output and video", install))
    else:
        listing = _ffmpeg_filters(exe, runner)
        missing = [f for f in ("ass", "xfade", "gblur") if not _has_filter(listing, f)]
        if missing:
            checks.append(_check("ffmpeg", "warn", "%s (missing filters: %s; burned captions or transitions "
                                 "will not work)" % (exe, ", ".join(missing)),
                                 "Install an ffmpeg build with libass, e.g. " + install))
        else:
            checks.append(_check("ffmpeg", "ok", "%s (libass captions, cross-fades: yes)" % exe))

    edge = edge_installed() if edge_available is None else edge_available
    checks.append(_check("engine: edge", "ok" if edge else "warn",
                         "edge-tts installed: free neural voices, no key" if edge
                         else "edge-tts not installed (the free default engine)",
                         None if edge else 'pip install "ai-voiceover-studio[edge]"'))
    has_miragea = bool(env.get("MIRAGEA_API_KEY"))
    checks.append(_check("engine: miragea", "ok" if has_miragea else "info",
                         "MIRAGEA_API_KEY is set (value hidden): voice cloning, expressive voices, "
                         "subtitle recognition" if has_miragea
                         else "MIRAGEA_API_KEY not set (optional: voice cloning, expressive voices)",
                         None if has_miragea else "Create a key at https://miragea.ai/workspace/api"))
    has_openai = bool(env.get("OPENAI_API_KEY"))
    checks.append(_check("engine: openai", "ok" if has_openai else "info",
                         "OPENAI_API_KEY is set (value hidden)" if has_openai
                         else "OPENAI_API_KEY not set (optional)"))

    explicit = env.get("VOICEOVER_PROVIDER", "").strip()
    chosen = explicit or ("miragea" if has_miragea else "edge")
    usable = {"edge": edge, "miragea": has_miragea, "openai": has_openai, "dummy": True}.get(chosen, True)
    checks.append(_check("default engine", "ok" if usable else "fail",
                         "%s%s" % (chosen, " (from VOICEOVER_PROVIDER)" if explicit else ""),
                         None if usable else 'pip install "ai-voiceover-studio[edge]" or pass --provider'))

    fc = which("fc-list")
    if fc:
        try:
            proc = runner([fc, ":lang=zh", "family"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            cjk = bool(proc.stdout.strip())
        except Exception:  # pragma: no cover
            cjk = False
        checks.append(_check("CJK caption font", "ok" if cjk else "info",
                             "found" if cjk else "no Chinese/Japanese font found for burned captions",
                             None if cjk else "Install e.g. fonts-noto-cjk, or pass --font path/to/font.ttf"))

    if online:
        if not edge:
            checks.append(_check("online test", "fail", "skipped: edge-tts not installed",
                                 'pip install "ai-voiceover-studio[edge]"'))
        else:
            try:
                seconds = (online_test or _edge_online_test)()
                checks.append(_check("online test", "ok", "edge voice rendered %.1fs of audio" % seconds))
            except Exception as exc:
                checks.append(_check("online test", "fail", "edge synthesis failed: %s" % exc,
                                     "Check your internet connection / proxy settings"))
    return checks


def _edge_online_test() -> float:
    from .studio import Studio
    from .audio import decode
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "doctor.wav"
        Studio("edge").say("Voiceover doctor check.", None, str(target))
        return decode(target.read_bytes(), "wav").duration


def format_report(checks: List[Check]) -> str:
    width = max(len(c["name"]) for c in checks)
    lines = []
    for c in checks:
        lines.append("%s %-*s  %s" % (MARK.get(c["status"], "?"), width, c["name"], c["detail"]))
        if c.get("fix") and c["status"] in ("fail", "warn", "info"):
            lines.append("  %s  -> %s" % (" " * width, c["fix"]))
    bad = [c for c in checks if c["status"] == "fail"]
    lines.append("")
    lines.append("All set." if not bad else "%d problem(s) to fix." % len(bad))
    return "\n".join(lines)
