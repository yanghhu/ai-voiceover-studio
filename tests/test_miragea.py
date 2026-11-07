import json

import pytest

from voiceover_studio.errors import ConfigError, ProviderError, TaskFailed
from voiceover_studio.providers.base import Voice
from voiceover_studio.providers.miragea import MirageaClient, MirageaProvider, stable_key

from conftest import API, SILENCE, task

AUDIO_URL = "https://cdn.example.com/a.wav"


def succeed(fake):
    fake.add("POST", API + "/audio/generations", (202, task("queued")))
    fake.add("GET", API + "/tasks/t1", (200, task("running")),
             (200, task("succeeded", result={"audio_url": AUDIO_URL, "format": "wav"})))
    fake.add("GET", AUDIO_URL, (200, SILENCE))


def test_missing_key(monkeypatch):
    monkeypatch.delenv("MIRAGEA_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="MIRAGEA_API_KEY"):
        MirageaClient()


def test_env_vars_and_bad_base_url(monkeypatch):
    monkeypatch.setenv("MIRAGEA_API_KEY", "k")
    monkeypatch.setenv("MIRAGEA_BASE_URL", "https://self.host/api/v1/")
    assert MirageaClient().base_url == "https://self.host/api/v1"
    monkeypatch.setenv("MIRAGEA_BASE_URL", "https://user:pw@host/v1")
    with pytest.raises(ConfigError):
        MirageaClient()


def test_repr_hides_key(client):
    assert "SECRET" not in repr(client)


def test_synthesize_actor_polls_and_downloads(client, fake):
    succeed(fake)
    provider = MirageaProvider(client)
    result = provider.synthesize("Hello", Voice(actor_id="42", model="standard", speed=1.1, tags=["calm"]))
    assert result.audio == SILENCE and result.format == "wav"
    post = fake.calls[0]
    assert post["headers"]["Authorization"] == "Bearer sk-test-SECRET"
    assert post["headers"]["Content-Type"] == "application/json"
    assert post["headers"]["Idempotency-Key"].startswith("avs-")
    assert json.loads(post["body"]) == {"text": "Hello", "format": "wav", "actor_id": "42",
                                        "model": "standard", "speed": 1.1, "tags": ["calm"]}
    assert [c["url"] for c in fake.calls[1:3]] == [API + "/tasks/t1"] * 2
    download = fake.calls[-1]
    assert download["url"] == AUDIO_URL and "Authorization" not in download["headers"]
    assert client.sleeps == [1, 1]  # honours poll_after_seconds
    assert result.meta["task_id"] == "t1"


def test_reference_audio_payload():
    payload = MirageaProvider.build_payload(
        "Hi", Voice(reference_audio_url="https://x/ref.wav", reference_text="ref words", language="en"), "mp3")
    assert payload == {"text": "Hi", "format": "mp3", "reference_audio_url": "https://x/ref.wav",
                       "reference_text": "ref words", "language": "en"}


@pytest.mark.parametrize("voice", [Voice(), Voice(actor_id="1", reference_audio_url="https://x")])
def test_exactly_one_voice_source(voice):
    with pytest.raises(ConfigError):
        MirageaProvider.build_payload("Hi", voice, "mp3")


def test_speed_range():
    with pytest.raises(ConfigError):
        MirageaProvider.build_payload("Hi", Voice(actor_id="1", speed=9), "mp3")


def test_idempotency_key_is_stable_per_input():
    a = stable_key({"text": "x", "actor_id": "1"})
    assert a == stable_key({"actor_id": "1", "text": "x"})
    assert a != stable_key({"text": "y", "actor_id": "1"})


def test_fresh_uses_random_key(client, fake):
    succeed(fake)
    MirageaProvider(client, fresh=True).synthesize("Hello", Voice(actor_id="1"))
    assert not fake.calls[0]["headers"]["Idempotency-Key"].startswith("avs-")


@pytest.mark.parametrize("status,needle", [(401, "API key"), (403, "API access"), (429, "rate limited")])
def test_http_errors_have_hints_and_never_leak_key(client, fake, status, needle):
    fake.add("POST", API + "/audio/generations",
             (status, {"error": {"code": "x_err", "message": "nope", "type": "t", "retryable": False}}))
    with pytest.raises(ProviderError) as info:
        MirageaProvider(client).synthesize("Hi", Voice(actor_id="1"))
    err = info.value
    assert err.status == status and err.code == "x_err" and needle in str(err)
    assert "SECRET" not in str(err) and "SECRET" not in json.dumps(err.to_dict())
    assert len(fake.calls) == 1  # not retryable -> no retry


def test_retryable_error_retries_with_same_key(client, fake):
    fake.add("POST", API + "/audio/generations",
             (503, {"error": {"code": "busy", "message": "later", "type": "t", "retryable": True}}),
             (202, task("succeeded", result={"audio_url": AUDIO_URL, "format": "wav"})))
    fake.add("GET", AUDIO_URL, (200, SILENCE))
    MirageaProvider(client).synthesize("Hi", Voice(actor_id="1"))
    keys = [c["headers"]["Idempotency-Key"] for c in fake.calls if c["method"] == "POST"]
    assert len(keys) == 2 and keys[0] == keys[1]


def test_network_error_retries_then_reports_key(client, fake):
    fake.add("POST", API + "/audio/generations", ConnectionError("reset"))
    with pytest.raises(ProviderError) as info:
        MirageaProvider(client).synthesize("Hi", Voice(actor_id="1"))
    assert info.value.code == "request_failed" and info.value.idempotency_key
    assert len(fake.calls) == client.max_retries


def test_failed_task(client, fake):
    fake.add("POST", API + "/audio/generations",
             (202, task("failed", error={"code": "synthesis_failed", "message": "boom"})))
    with pytest.raises(TaskFailed) as info:
        MirageaProvider(client).synthesize("Hi", Voice(actor_id="1"))
    assert info.value.task_id == "t1" and info.value.exit_code == 1


def test_wait_timeout_keeps_task_id(fake):
    clock = iter(range(0, 10000, 400))
    import voiceover_studio.providers.miragea as m
    client = MirageaClient(api_key="k", transport=fake, sleep=lambda s: None, wait_timeout=500)
    fake.add("POST", API + "/audio/generations", (202, task("queued")))
    fake.add("GET", API + "/tasks/t1", (200, task("running")))
    real = m.time.monotonic
    m.time.monotonic = lambda: next(clock)
    try:
        with pytest.raises(ProviderError) as info:
            MirageaProvider(client).synthesize("Hi", Voice(actor_id="1"))
    finally:
        m.time.monotonic = real
    assert info.value.code == "wait_timeout" and info.value.task_id == "t1"


def test_list_voices(client, fake):
    fake.add("GET", API + "/actors", (200, {"items": [{"actor_id": "7", "name": "Ava", "language": "en"}],
                                            "has_more": True}))
    voices, more = MirageaProvider(client).list_voices(limit=5, offset=10)
    assert voices[0].voice_id == "7" and voices[0].name == "Ava" and more
    assert fake.calls[0]["url"] == API + "/actors?limit=5&offset=10"


def test_transcribe_multipart(client, fake, tmp_path):
    media = tmp_path / "mix.wav"
    media.write_bytes(SILENCE)
    fake.add("GET", API + "/capabilities", (200, {"subtitles": {"points_per_second": 2, "max_upload_mb": 10}}))
    fake.add("POST", API + "/subtitles/recognitions", (202, task(
        "succeeded", kind="subtitle_recognition",
        result={"text": "hi", "language": "en", "segments": [{"start": 0, "end": 1.5, "text": "hi"}],
                "srt": "", "txt": "hi"})))
    segments = MirageaProvider(client).transcribe(str(media))
    assert segments[0].end == 1.5 and segments[0].text == "hi"
    post = fake.calls[1]
    assert post["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'name="expected_rate"\r\n\r\n2\r\n' in post["body"]
    assert b'filename="mix.wav"' in post["body"]
    assert post["headers"]["Idempotency-Key"]


def test_transcribe_rejects_large_file(client, fake, tmp_path):
    media = tmp_path / "big.wav"
    media.write_bytes(b"0" * 2048)
    fake.add("GET", API + "/capabilities", (200, {"subtitles": {"points_per_second": 1, "max_upload_mb": 0.001}}))
    with pytest.raises(ConfigError):
        MirageaProvider(client).transcribe(str(media))
