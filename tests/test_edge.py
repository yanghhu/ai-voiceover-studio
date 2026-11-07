import asyncio

import pytest

from voiceover_studio import Studio
from voiceover_studio.errors import ConfigError, NotSupported, ProviderError
from voiceover_studio.providers.base import Voice
from voiceover_studio.providers.edge import EdgeProvider, detect_language, rate_for, voices_for

from conftest import SILENCE


class FakeCommunicate:
    """Stands in for edge_tts.Communicate: yields audio chunks and sentence boundaries."""

    calls = []
    fail_times = 0
    audio = SILENCE

    def __init__(self, text, voice, **kwargs):
        self.text, self.voice, self.kwargs = text, voice, kwargs
        FakeCommunicate.calls.append(self)

    async def stream(self):
        if FakeCommunicate.fail_times > 0:
            FakeCommunicate.fail_times -= 1
            raise OSError("connection reset")
        yield {"type": "SentenceBoundary", "offset": 1_000_000, "duration": 5_000_000, "text": self.text}
        half = len(self.audio) // 2
        yield {"type": "audio", "data": self.audio[:half]}
        yield {"type": "audio", "data": self.audio[half:]}


@pytest.fixture
def edge():
    FakeCommunicate.calls = []
    FakeCommunicate.fail_times = 0
    return EdgeProvider(communicate=FakeCommunicate, sleep=lambda s: None)


def test_language_and_rate_helpers():
    assert detect_language("Hello there") == "en"
    assert detect_language("你好，世界") == "zh"
    assert detect_language("こんにちは") == "ja"
    assert detect_language("안녕하세요") == "ko"
    assert detect_language("Привет") == "ru"
    assert voices_for("zh-CN")[0].startswith("zh-CN-")
    assert voices_for("xx") == voices_for("en")
    assert rate_for(None) == "+0%" and rate_for(1.25) == "+25%" and rate_for(0.8) == "-20%"
    with pytest.raises(ConfigError):
        rate_for(9)


def test_synthesize_collects_audio_and_sentences(edge):
    res = edge.synthesize("Hello world.", Voice(speed=1.1))
    assert res.audio == SILENCE and res.format == "mp3"
    call = FakeCommunicate.calls[0]
    assert call.voice == "en-US-AndrewNeural" and call.kwargs["rate"] == "+10%"
    assert res.meta["sentences"] == [{"start": 0.1, "end": 0.6, "text": "Hello world."}]


def test_voice_choice(edge):
    edge.synthesize("你好", Voice())
    edge.synthesize("Hi", Voice(actor_id="en-GB-SoniaNeural"))
    edge.synthesize("Hola", Voice(language="es"))
    assert [c.voice for c in FakeCommunicate.calls] == ["zh-CN-YunxiNeural", "en-GB-SoniaNeural",
                                                        "es-ES-AlvaroNeural"]
    with pytest.raises(ConfigError, match="not an Edge voice"):
        edge.synthesize("Hi", Voice(actor_id="12345"))
    with pytest.raises(NotSupported, match="miragea"):
        edge.synthesize("Hi", Voice(reference_audio_url="https://x/a.wav"))
    assert edge.auto_voice(0, "en").actor_id != edge.auto_voice(1, "en").actor_id


def test_retries_then_fails_clearly(edge):
    FakeCommunicate.fail_times = 1
    assert edge.synthesize("Hi", Voice()).audio == SILENCE
    FakeCommunicate.fail_times = 10
    with pytest.raises(ProviderError, match="after 3 attempts"):
        edge.synthesize("Hi", Voice())


def test_runs_inside_an_event_loop(edge):
    async def inner():
        return edge.synthesize("Hi", Voice())
    assert asyncio.run(inner()).audio == SILENCE


def test_list_voices():
    async def fake_list():
        return [{"ShortName": "en-US-AvaNeural", "FriendlyName": "Ava", "Gender": "Female", "Locale": "en-US"},
                {"ShortName": "de-DE-KatjaNeural", "FriendlyName": "Katja", "Gender": "Female", "Locale": "de-DE"}]
    p = EdgeProvider(communicate=FakeCommunicate, list_voices_fn=fake_list)
    items, more = p.list_voices(1, 0)
    assert items[0].voice_id == "de-DE-KatjaNeural" and more


def test_multi_speaker_script_with_edge(edge, tmp_path):
    script = tmp_path / "s.md"
    script.write_text("[HOST]: Welcome.\n\n[GUEST]: Thanks!\n\n[HOST]: Bye.", encoding="utf-8")
    result = Studio(edge).render_script(script, tmp_path / "out", output_name="mix.wav")
    assert [s.voice for s in result.segments] == ["actor:en-US-AndrewNeural", "actor:en-US-AvaNeural",
                                                  "actor:en-US-AndrewNeural"]
    srt = open(result.srt_path, encoding="utf-8").read()
    assert srt.startswith("1\n00:00:00,100 --> ")


def test_missing_package_message(monkeypatch):
    import builtins
    real = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "edge_tts":
            raise ImportError
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ConfigError, match=r"\[edge\]"):
        EdgeProvider()
