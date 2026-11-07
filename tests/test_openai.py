import json

import pytest

from voiceover_studio.errors import ConfigError, NotSupported, ProviderError
from voiceover_studio.providers import get_provider
from voiceover_studio.providers.base import Voice
from voiceover_studio.providers.miragea import HttpResponse
from voiceover_studio.providers.openai import OpenAIProvider

from conftest import SILENCE

URL = "https://api.openai.com/v1/audio/speech"


def make(fake, **kw):
    return OpenAIProvider(api_key="sk-oa-SECRET", transport=fake, sleep=lambda s: None, **kw)


def test_missing_key():
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        get_provider("openai")


def test_synthesize(fake):
    fake.add("POST", URL, (200, SILENCE))
    p = make(fake)
    res = p.synthesize("Hello", Voice(actor_id="nova", speed=1.2, tags=["warm"]), audio_format="wav")
    assert res.audio == SILENCE and res.format == "wav"
    call = fake.calls[0]
    assert call["headers"]["Authorization"] == "Bearer sk-oa-SECRET"
    assert json.loads(call["body"]) == {"model": "gpt-4o-mini-tts", "input": "Hello", "voice": "nova",
                                        "response_format": "wav", "speed": 1.2,
                                        "instructions": "Speak in a warm tone."}
    assert "SECRET" not in repr(p)


def test_errors(fake):
    fake.add("POST", URL, (400, {"error": {"message": "bad voice", "code": "invalid"}}))
    with pytest.raises(ProviderError, match="bad voice"):
        make(fake).synthesize("Hi", Voice(actor_id="alloy"))
    with pytest.raises(ConfigError):
        make(fake).synthesize("Hi", Voice(actor_id="nobody"))
    with pytest.raises(NotSupported):
        make(fake).synthesize("Hi", Voice(reference_audio_url="https://x/a.wav"))


def test_retry_on_429(fake):
    fake.add("POST", URL, (429, {"error": {"message": "slow down"}}), (200, SILENCE))
    assert make(fake).synthesize("Hi", Voice()).audio == SILENCE
    assert len(fake.calls) == 2


def test_auto_voices(fake):
    p = make(fake)
    assert p.auto_voice(0, "en").actor_id != p.auto_voice(1, "en").actor_id
