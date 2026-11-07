import json
import wave

import pytest

from voiceover_studio import ConfigError, Studio
from voiceover_studio.audio import decode, wav_bytes, concat
from voiceover_studio.cli import main
from voiceover_studio.config import load_voices
from voiceover_studio.providers import Voice, available_providers, get_provider
from voiceover_studio.providers.dummy import DummyProvider, estimate_seconds

SCRIPT = "[NARRATOR]: Welcome to the channel.\n\n[ALEX](speed=1.2): Thanks for having me!\n[pause 1]\n[NARRATOR]: Let's go."


def test_registry():
    assert {"miragea", "dummy"} <= set(available_providers())
    with pytest.raises(ConfigError):
        get_provider("nope")


def test_estimate():
    assert estimate_seconds("one two three four five six") > 2
    assert estimate_seconds("你好世界你好世界你好") > 2
    assert estimate_seconds("x", speed=2) == 0.25


def test_concat_with_gaps():
    a = decode(wav_bytes(b"\x00\x00" * 24000, 24000, 1, 2))
    mix = concat([a, a], [0.5])
    assert abs(mix.duration - 2.5) < 1e-6


def test_render_script(tmp_path):
    script = tmp_path / "s.md"
    script.write_text(SCRIPT, encoding="utf-8")
    voices = tmp_path / "voices.json"
    voices.write_text(json.dumps({"NARRATOR": "n1", "ALEX": {"actor_id": "a1", "tags": ["warm"]}}))
    provider = DummyProvider()
    result = Studio(provider).render_script(script, tmp_path / "out", voices=voices,
                                            output_name="mix.wav", gap=0.25)
    assert [s.speaker for s in result.segments] == ["NARRATOR", "ALEX", "NARRATOR"]
    assert provider.calls[1][1].actor_id == "a1" and provider.calls[1][1].speed == 1.2
    assert provider.calls[1][1].tags == ["warm"]
    s = result.segments
    assert abs(s[1].start - (s[0].end + 0.25)) < 0.01
    assert abs(s[2].start - (s[1].end + 1.25)) < 0.01  # gap + explicit pause
    with wave.open(result.audio_path) as w:
        assert abs(w.getnframes() / w.getframerate() - result.duration) < 0.01
    srt = open(result.srt_path, encoding="utf-8").read()
    assert "Welcome to the channel." in srt and result.subtitle_source == "timing"
    manifest = json.load(open(result.manifest_path))
    assert manifest["provider"] == "dummy" and len(manifest["segments"]) == 3
    # second run hits the segment cache, no new synthesis
    Studio(provider).render_script(script, tmp_path / "out", voices=voices, output_name="mix.wav")
    assert len(provider.calls) == 3


def test_recognize_falls_back_to_timing(tmp_path):
    script = tmp_path / "s.md"
    script.write_text("Hello.", encoding="utf-8")
    result = Studio("dummy").render_script(script, tmp_path / "o", output_name="a.wav", subtitles="recognize")
    assert result.subtitle_source == "timing"


def test_missing_speaker_fails_before_synthesis(tmp_path):
    script = tmp_path / "s.md"
    script.write_text("[BOB]: hi", encoding="utf-8")
    provider = DummyProvider()
    voices = {"ALICE": Voice(actor_id="x")}
    with pytest.raises(ConfigError, match="BOB"):
        Studio(provider).render_script(script, tmp_path / "o", voices=voices)
    assert provider.calls == []


def test_yaml_voices(tmp_path):
    pytest.importorskip("yaml")
    f = tmp_path / "v.yaml"
    f.write_text("default: abc\nALEX:\n  reference_audio_url: https://x/a.wav\n  reference_text: hi\n")
    v = load_voices(f)
    assert v["DEFAULT"].actor_id == "abc" and v["ALEX"].reference_audio_url == "https://x/a.wav"


def test_cli_dry_run(tmp_path, capsys):
    script = tmp_path / "s.md"
    script.write_text(SCRIPT, encoding="utf-8")
    code = main(["script", str(script), "--dry-run", "-o", str(tmp_path / "out"), "--name", "v.wav", "--json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["segments"] == 3 and data["provider"] == "dummy"
    assert main(["say", "hello", "--dry-run", "-o", str(tmp_path / "hi.wav")]) == 0
    assert main(["voices", "--dry-run", "--json"]) == 0


def test_cli_missing_key_is_clean_error(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("MIRAGEA_API_KEY", raising=False)
    code = main(["say", "hello", "--voice", "1", "-o", str(tmp_path / "x.wav")])
    assert code == 2 and "MIRAGEA_API_KEY" in capsys.readouterr().err


def test_video(tmp_path):
    pytest.importorskip("moviepy")
    from PIL import Image
    from voiceover_studio.video import render_video
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    for i in range(2):
        Image.new("RGB", (320, 240), (i * 100, 50, 50)).save(imgs / ("%d.png" % i))
    script = tmp_path / "s.md"
    script.write_text("[A]: First slide.\n\n[A]: Second slide.", encoding="utf-8")
    out = render_video(Studio("dummy"), imgs, script, tmp_path / "v.mp4", size=(320, 240), fps=5)
    assert (tmp_path / "v.mp4").stat().st_size > 0 and out["subtitles"].endswith(".srt")
