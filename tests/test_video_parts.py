from pathlib import Path

import pytest

from voiceover_studio.captions import STYLES, ass_time, to_ass
from voiceover_studio.doctor import format_report, run_checks
from voiceover_studio.errors import ConfigError
from voiceover_studio.subtitles import Cue
from voiceover_studio.video import build_command, script_title


def test_ass_document():
    cues = [Cue(0.5, 2.0, "Hello\nworld", "NARRATOR"), Cue(2.0, 3.0, "{tricky}")]
    doc = to_ass(cues, (1920, 1080), style="clean", speaker_labels=True, title="My Title")
    assert "PlayResX: 1920" in doc and "PlayResY: 1080" in doc
    assert "Dialogue: 0,0:00:00.50,0:00:02.00,Caption" in doc
    assert "Hello\\Nworld" in doc and "Narrator" in doc
    assert "(tricky)" in doc  # braces cannot inject override tags
    assert ",Title,," in doc and "My Title" in doc
    bold = to_ass(cues, (1080, 1920), style="bold")
    assert "HELLO" in bold
    with pytest.raises(ConfigError):
        to_ass(cues, (10, 10), style="nope")
    assert ass_time(3725.456) == "1:02:05.46"
    assert set(STYLES) == {"clean", "box", "bold", "minimal"}


def test_build_command_timing():
    cmd = build_command("ffmpeg", [Path("a.png"), Path("b.png"), None], [2.0, 3.0, 4.0], "voice.wav", "o.mp4",
                        size=(1280, 720), fps=25, transition=0.5, ass_path="captions.ass",
                        progress_bar=True, total=9.0)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=fade:duration=0.500:offset=2.000" in graph
    assert "xfade=transition=fade:duration=0.500:offset=5.000" in graph
    assert "trim=end_frame=62" in graph       # (2.0 + 0.5) * 25 for the first slide
    assert "trim=end_frame=100[" in graph or "trim=end_frame=100," in graph  # last slide has no fade tail
    assert "ass=captions.ass" in graph and "overlay=x='-W+W*t/9.000'" in graph
    assert "gradients=" in " ".join(cmd)       # missing image -> generated background
    assert cmd[cmd.index("-map") + 3] == "3:a"


def test_build_command_cut_and_static():
    cmd = build_command("ffmpeg", [Path("a.png"), Path("b.png")], [1.0, 1.0], "v.wav", "o.mp4",
                        size=(640, 360), fps=10, transition=0, motion="none")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=2" in graph and "eval=frame" not in graph


def test_script_title(tmp_path):
    f = tmp_path / "s.md"
    f.write_text("<!-- c -->\n# Big Title #\n\ntext", encoding="utf-8")
    assert script_title(f) == "Big Title"
    assert script_title(tmp_path / "missing.md") is None


class _Proc:
    def __init__(self, out):
        self.stdout = out.encode()


def test_doctor_reports_without_leaking_keys():
    listing = " ... ass  V->V  x\n .S. xfade VV->V x\n TSC gblur V->V x\n"

    def runner(cmd, **kw):
        return _Proc(listing if "-filters" in cmd else "Noto Sans SC\n")

    checks = run_checks(environ={"MIRAGEA_API_KEY": "sk-SECRET"}, which=lambda n: "/usr/bin/" + n,
                        runner=runner, edge_available=True)
    text = format_report(checks)
    assert "SECRET" not in text
    by = {c["name"]: c for c in checks}
    assert by["ffmpeg"]["status"] == "ok" and by["default engine"]["detail"] == "miragea"
    assert text.endswith("All set.")


def test_doctor_flags_missing_pieces():
    checks = run_checks(environ={}, which=lambda n: None, runner=lambda *a, **k: _Proc(""),
                        edge_available=False, online=True)
    by = {c["name"]: c for c in checks}
    assert by["ffmpeg"]["status"] == "fail" and "install" in by["ffmpeg"]["fix"]
    assert by["engine: edge"]["status"] == "warn" and by["default engine"]["status"] == "fail"
    assert by["online test"]["status"] == "fail"
    assert "problem(s) to fix" in format_report(checks)


def test_doctor_online_uses_test_hook():
    checks = run_checks(environ={}, which=lambda n: None, runner=lambda *a, **k: _Proc(""),
                        edge_available=True, online=True, online_test=lambda: 1.5)
    assert {c["name"]: c for c in checks}["online test"]["status"] == "ok"
