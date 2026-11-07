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
    assert {"edge", "miragea", "openai", "dummy"} <= set(available_providers())
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


class NoAutoProvider(DummyProvider):
    supports_auto_voices = False


def test_missing_speaker_fails_before_synthesis(tmp_path):
    script = tmp_path / "s.md"
    script.write_text("[BOB]: hi", encoding="utf-8")
    provider = NoAutoProvider()
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


def test_cli_missing_key_is_clean_error(tmp_path, capsys):
    code = main(["say", "hello", "--provider", "miragea", "--voice", "1", "-o", str(tmp_path / "x.wav")])
    assert code == 2 and "MIRAGEA_API_KEY" in capsys.readouterr().err


def test_auto_voices_per_speaker(tmp_path):
    script = tmp_path / "s.md"
    script.write_text(SCRIPT, encoding="utf-8")
    provider = DummyProvider()
    result = Studio(provider).render_script(script, tmp_path / "o", output_name="a.wav")
    voices = {s.speaker: s.voice for s in result.segments}
    assert voices == {"NARRATOR": "actor:dummy-narrator", "ALEX": "actor:dummy-host"}


def test_lang_override_picks_auto_voices(tmp_path):
    script = tmp_path / "s.md"
    script.write_text("[NARRADOR]: Hola a todos.\n\n[ALEX]: Gracias.", encoding="utf-8")
    seen = []

    class Recorder(DummyProvider):
        def auto_voice(self, n, language):
            seen.append(language)
            return super().auto_voice(n, language)

    Studio(Recorder()).render_script(script, tmp_path / "o", output_name="a.wav",
                                     voice_overrides=Voice(language="es"))
    assert seen == ["es", "es"]


def test_explicit_voice_wins_over_auto(tmp_path):
    script = tmp_path / "s.md"
    script.write_text(SCRIPT, encoding="utf-8")
    result = Studio(DummyProvider()).render_script(script, tmp_path / "o", output_name="a.wav",
                                                   voices={"ALEX": Voice(actor_id="mine")})
    assert {s.speaker: s.voice for s in result.segments}["ALEX"] == "actor:mine"


def test_sentence_timings_drive_subtitles(tmp_path):
    class Timed(DummyProvider):
        def synthesize(self, text, voice, **kw):
            res = super().synthesize(text, voice, **kw)
            res.meta["sentences"] = [{"start": 0.1, "end": 0.6, "text": "First part."},
                                     {"start": 0.9, "end": 1.4, "text": "Second part."}]
            return res
    script = tmp_path / "s.md"
    script.write_text("First part. Second part.", encoding="utf-8")
    result = Studio(Timed()).render_script(script, tmp_path / "o", output_name="a.wav")
    srt = open(result.srt_path, encoding="utf-8").read()
    assert "00:00:00,100 --> 00:00:00,900\nFirst part." in srt
    assert "00:00:00,900 --> " in srt and "Second part." in srt
    # timings survive a cached re-run
    again = Studio(Timed()).render_script(script, tmp_path / "o", output_name="a.wav")
    assert again.segments[0].meta.get("cached") and open(again.srt_path, encoding="utf-8").read() == srt


def test_default_provider_resolution(monkeypatch):
    from voiceover_studio.providers import default_provider_name
    assert default_provider_name() == "edge"
    monkeypatch.setenv("MIRAGEA_API_KEY", "k")
    assert default_provider_name() == "miragea"
    monkeypatch.setenv("VOICEOVER_PROVIDER", "dummy")
    assert default_provider_name() == "dummy"


def _ffmpeg_with(*filters):
    import shutil, subprocess
    exe = shutil.which("ffmpeg")
    if not exe:
        return False
    listing = subprocess.run([exe, "-hide_banner", "-filters"], stdout=subprocess.PIPE).stdout.decode()
    return all(" %s " % f in listing for f in filters)


@pytest.mark.skipif(not _ffmpeg_with("ass", "xfade"), reason="needs ffmpeg with libass")
def test_video(tmp_path):
    import subprocess
    from voiceover_studio.video import render_video
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    for i in range(2):  # tiny solid-colour images made by ffmpeg itself
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x%02x5050:s=320x240" % (i * 90),
                        "-frames:v", "1", str(imgs / ("%d.png" % i))], check=True)
    script = tmp_path / "s.md"
    script.write_text("# Title\n\n[A]: First slide.\n\n[B]: Second slide.", encoding="utf-8")
    out = render_video(Studio("dummy"), imgs, script, tmp_path / "v.mp4", size=(320, 240), fps=10,
                       speaker_labels=True, title=True)
    assert (tmp_path / "v.mp4").stat().st_size > 0 and out["subtitles"].endswith(".srt")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                            str(tmp_path / "v.mp4")], stdout=subprocess.PIPE).stdout.decode()
    assert abs(float(probe) - out["duration"]) < 0.5


@pytest.mark.skipif(not _ffmpeg_with("ass", "xfade", "gradients"), reason="needs ffmpeg with libass")
def test_video_without_images(tmp_path):
    from voiceover_studio.video import render_video
    script = tmp_path / "s.md"
    script.write_text("# Hello\n\nJust a script, no pictures.", encoding="utf-8")
    out = render_video(Studio("dummy"), None, script, tmp_path / "v.mp4", size=(320, 180), fps=10,
                       motion="none", transition=0)
    assert out["images"] == 0 and out["shots"] == 1 and (tmp_path / "v.mp4").stat().st_size > 0


@pytest.mark.skipif(not _ffmpeg_with("ass", "xfade", "zoompan", "sidechaincompress"),
                    reason="needs ffmpeg with libass")
def test_video_with_broll_music_and_tiktok_captions(tmp_path):
    import subprocess
    from voiceover_studio.video import render_video
    (tmp_path / "broll").mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x305080:s=360x640",
                    "-frames:v", "1", str(tmp_path / "broll" / "a.png")], check=True)
    script = tmp_path / "s.md"
    script.write_text("# Hook line\n\n![](broll/a.png)\nFirst **fact** here.\n\nSecond part has no picture.",
                      encoding="utf-8")
    out = render_video(Studio("dummy"), None, script, tmp_path / "v.mp4", size=(180, 320), fps=10,
                       music="ambient")
    assert out["style"] == "tiktok" and out["shots"] == 2 and out["images"] == 1
    assert out["music"] == "ambient" and (tmp_path / "v.mp4").stat().st_size > 0
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                              str(tmp_path / "v.mp4")], stdout=subprocess.PIPE).stdout.decode().split()
    assert streams == ["video", "audio"]


def test_timing_cache_formats(tmp_path):
    from voiceover_studio.studio import _read_timing
    f = tmp_path / "t.json"
    assert _read_timing(f) == {}
    f.write_text('[{"start": 0, "end": 1, "text": "Hi."}]', encoding="utf-8")
    assert list(_read_timing(f)) == ["sentences"]           # cache written by v0.2
    f.write_text('{"sentences": [], "words": [{"start": 0, "end": 1, "text": "Hi"}]}', encoding="utf-8")
    assert list(_read_timing(f)) == ["words"]
    f.write_text("not json", encoding="utf-8")
    assert _read_timing(f) == {}


def test_segments_carry_broll_and_emphasis(tmp_path):
    script = tmp_path / "s.md"
    script.write_text("![](a.jpg)\n\nThe **big** idea.", encoding="utf-8")
    result = Studio(DummyProvider()).render_script(script, tmp_path / "out", output_name="m.wav")
    seg = result.segments[0]
    assert seg.visuals == ["a.jpg"] and seg.emphasis == ["big"] and seg.text == "The big idea."
    assert json.load(open(result.manifest_path))["segments"][0]["visuals"] == ["a.jpg"]
