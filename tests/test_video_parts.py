from pathlib import Path

import pytest

from types import SimpleNamespace

from voiceover_studio.captions import STYLES, animated_ass, ass_time, build_pages, default_style, to_ass
from voiceover_studio.doctor import format_report, run_checks
from voiceover_studio.errors import ConfigError
from voiceover_studio.subtitles import Cue
from voiceover_studio.video import Shot, build_command, plan_shots, script_title
from voiceover_studio.words import Word


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
    assert set(STYLES) == {"tiktok", "clean", "box", "bold", "minimal"}
    assert default_style((1080, 1920)) == "tiktok" and default_style((1920, 1080)) == "clean"


def _shots(*specs):
    return [Shot(d, kind, Path(src) if src else None, phrase) for d, kind, src, phrase in specs]


def test_build_command_timing():
    shots = _shots((2.0, "image", "a.png", ""), (3.0, "image", "b.png", ""), (4.0, "kinetic", None, "Hi"))
    cmd = build_command("ffmpeg", shots, "voice.wav", "o.mp4", size=(1280, 720), fps=25, transition=0.5,
                        ass_path="captions.ass", progress_bar=True, total=9.0)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=smoothleft:duration=0.500:offset=2.000" in graph
    assert "xfade=transition=zoomin:duration=0.500:offset=5.000" in graph
    assert "zoompan=" in graph and ":d=62:" in graph          # (2.0 + 0.5) * 25 frames for the first still
    assert "trim=end_frame=100," in graph                     # last shot has no transition tail
    assert "ass=captions.ass" in graph and "overlay=x='-W+W*t/9.000'" in graph
    assert "vignette" in graph and "noise=" in graph           # cinematic grade by default
    assert "gradients=" in " ".join(cmd)                      # picture-less shot -> animated background
    assert cmd[cmd.index("-map") + 3] == "3:a"
    assert cmd[cmd.index("-t") + 1] == "9.000"


def test_build_command_cut_static_and_old_ffmpeg():
    shots = _shots((1.0, "image", "a.png", ""), (1.0, "kinetic", None, ""))
    cmd = build_command("ffmpeg", shots, "v.wav", "o.mp4", size=(640, 360), fps=10, transition=0,
                        motion="none", grade="none", caps=(frozenset({"fade"}), False, False))
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=2" in graph and "zoompan" not in graph and "vignette" not in graph
    assert "color=c=" in " ".join(cmd) and "gradients" not in " ".join(cmd)
    # an ffmpeg without the fancy transitions falls back to a plain fade
    cmd = build_command("ffmpeg", _shots((2, "image", "a.png", ""), (2, "image", "b.png", "")), "v.wav",
                        "o.mp4", size=(640, 360), fps=10, caps=(frozenset({"fade", "wipeleft"}), True, True))
    assert "xfade=transition=fade" in cmd[cmd.index("-filter_complex") + 1]
    with pytest.raises(ConfigError):
        build_command("ffmpeg", shots, "v.wav", "o.mp4", size=(640, 360), fps=10, transition_style="spin")


def test_build_command_video_clip_and_music():
    shots = _shots((2.0, "video", "clip.mp4", ""), (2.0, "image", "b.jpg", ""))
    cmd = build_command("ffmpeg", shots, "v.wav", "o.mp4", size=(1080, 1920), fps=30, music="ambient",
                        music_builtin=True, music_volume=0.4, total=4.0)
    joined = " ".join(cmd)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "-stream_loop -1 -t" in joined and "clip.mp4" in joined
    assert "aevalsrc=" in joined                               # generated ambient bed
    assert "sidechaincompress" in graph and "amix=inputs=2" in graph and "volume=0.400" in graph
    assert cmd[cmd.index("-map") + 3] == "[aout]"
    cmd = build_command("ffmpeg", shots, "v.wav", "o.mp4", size=(640, 360), fps=10, music="song.mp3",
                        duck=False, total=4.0)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "song.mp3" in " ".join(cmd) and "sidechaincompress" not in graph and "anullsink" in graph


def _seg(start, end, text, visuals=(), emphasis=(), meta=None):
    return SimpleNamespace(start=start, end=end, text=text, visuals=list(visuals), emphasis=list(emphasis),
                           meta=meta or {}, speaker="N")


def test_plan_shots(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.mp4").write_bytes(b"x")
    (tmp_path / "c.png").write_bytes(b"x")
    render = SimpleNamespace(duration=10.0, segments=[
        _seg(0.1, 3.0, "One.", ["a.jpg", "b.mp4"]), _seg(3.3, 6.0, "Two **big** facts.", emphasis=["big"]),
        _seg(6.3, 9.8, "Three.")])
    shots = plan_shots(render, media=[tmp_path / "c.png"], script_dir=tmp_path)
    assert [s.kind for s in shots] == ["image", "video", "image", "kinetic"]
    assert abs(shots[0].duration - 1.65) < 1e-6 and shots[2].source == tmp_path / "c.png"
    assert shots[3].phrase == "Three" and abs(shots[3].start - 6.3) < 1e-6
    assert abs(sum(s.duration for s in shots) - 10.0) < 1e-6
    # no script B-roll: classic folder behaviour, even split
    render.segments = [_seg(0, 5, "a"), _seg(5, 10, "b"), _seg(10, 12, "c")]
    shots = plan_shots(render, media=[tmp_path / "a.jpg", tmp_path / "c.png"])
    assert [s.duration for s in shots] == [5.0, 5.0]
    render.segments = [_seg(0, 3, "x", ["missing.jpg"])]
    with pytest.raises(ConfigError, match="B-roll file not found"):
        plan_shots(render, script_dir=tmp_path)


def test_animated_ass_tiktok():
    words = [Word(0.0, 0.4, "Cleopatra"), Word(0.4, 0.7, "lived"), Word(0.7, 1.0, "closer", ","),
             Word(1.0, 1.3, "Moon", key=True), Word(1.3, 1.8, "landing", "."), Word(2.6, 3.0, "Next")]
    pages = build_pages(words, (1920, 1080), "tiktok")
    assert [len(p.words) for p in pages] == [3, 2, 1]
    assert all(len(p.words) <= 2 for p in build_pages(words, (1080, 1920), "tiktok"))  # narrow frame
    assert pages[0].end == pages[1].start                      # captions hand over without a gap
    doc = animated_ass(pages, (1920, 1080), style="tiktok", font="Montserrat", hook="Big hook",
                       kinetic=[(3.0, 6.0, "Kinetic words")])
    assert "Style: Caption,Montserrat," in doc and "CLEOPATRA" in doc
    assert "\\fscx118\\fscy118\\t(0," in doc                 # the spoken word pops
    assert STYLES["tiktok"].active in doc and STYLES["tiktok"].key in doc
    assert "\\move(960," in doc and ",Hook,," in doc and ",Shade,," in doc and "BIG HOOK" in doc
    assert ",Kinetic,," in doc and "KINETIC" in doc
    assert doc.count(",Caption,,") == len(words)               # one event per spoken word
    reveal = animated_ass(build_pages(words, (1920, 1080), "bold"), (1920, 1080), style="bold")
    assert "\\alpha&HFF&" in reveal                             # upcoming words hidden until spoken
    static = animated_ass([], (1920, 1080), style="minimal", static_cues=[Cue(0, 1, "Plain line")])
    assert "Plain line" in static and "\\fscx118" not in static


def test_animated_ass_cjk():
    words = [Word(0.0, 0.3, "今晚"), Word(0.3, 0.6, "抬头", "，"), Word(0.6, 1.0, "早已", key=True),
             Word(1.0, 1.4, "消失", key=True)]
    doc = animated_ass(build_pages(words, (1080, 1920), "tiktok"), (1080, 1920), style="tiktok")
    assert "今晚" in doc and "，" not in doc                     # no punctuation in pop captions
    assert "早已{" in doc or "早已" in doc
    assert "今晚 " not in doc                                   # no spaces between CJK words


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
