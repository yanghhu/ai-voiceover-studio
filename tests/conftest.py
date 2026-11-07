import json

import pytest

from voiceover_studio.audio import wav_bytes
from voiceover_studio.providers.miragea import HttpResponse, MirageaClient

API = "https://miragea.ai/v1"


class FakeTransport:
    """Records requests and replays scripted responses keyed by (method, url-prefix)."""

    def __init__(self):
        self.calls = []
        self.routes = []

    def add(self, method, url, *responses):
        self.routes.append([method, url, list(responses)])
        return self

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        for route in self.routes:
            if route[0] == method and url.startswith(route[1]) and route[2]:
                item = route[2][0] if len(route[2]) == 1 else route[2].pop(0)
                if isinstance(item, Exception):
                    raise item
                status, payload = item
                body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                return HttpResponse(status, {}, body)
        raise AssertionError("unexpected request %s %s" % (method, url))


def task(status, **extra):
    data = {"task_id": "t1", "kind": "audio_generation", "status": status,
            "poll_after_seconds": 0 if status in ("succeeded", "failed") else 1,
            "status_path": "/v1/tasks/t1", "result": None, "error": None,
            "usage": {"points": 0, "estimated_points": 5}, "created_at": "2026-11-07T00:00:00Z",
            "finished_at": None}
    data.update(extra)
    return data


SILENCE = wav_bytes(b"\x00\x00" * 2400, 24000, 1, 2)  # 0.1 s


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Tests never depend on the developer's keys or engine choice, and never hit the network."""
    for name in ("MIRAGEA_API_KEY", "MIRAGEA_BASE_URL", "OPENAI_API_KEY", "OPENAI_BASE_URL",
                 "VOICEOVER_PROVIDER", "VOICEOVER_EDGE_PROXY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake():
    return FakeTransport()


@pytest.fixture
def client(fake, monkeypatch):
    monkeypatch.delenv("MIRAGEA_BASE_URL", raising=False)
    sleeps = []
    c = MirageaClient(api_key="sk-test-SECRET", transport=fake, sleep=sleeps.append)
    c.sleeps = sleeps
    return c
