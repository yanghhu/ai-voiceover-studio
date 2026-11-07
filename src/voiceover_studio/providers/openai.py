"""OpenAI text-to-speech (``POST /v1/audio/speech``), standard library only.

Configuration: ``OPENAI_API_KEY`` (required), ``OPENAI_BASE_URL`` (optional,
default ``https://api.openai.com/v1``) and ``VOICEOVER_OPENAI_MODEL``
(optional, default ``gpt-4o-mini-tts``). ``Voice.actor_id`` is a voice name
such as ``alloy``, ``nova`` or ``onyx``; ``tags`` become a short speaking-style
instruction on models that accept one.
"""
import json
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..errors import ConfigError, NotSupported, ProviderError
from .base import SynthesisResult, Voice, VoiceInfo, VoiceProvider
from .miragea import Transport, urllib_transport

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini-tts"
VOICES = ("alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer")
SPEAKER_ROTATION = ("onyx", "nova", "echo", "shimmer", "fable", "alloy")
FORMATS = ("mp3", "wav", "flac", "opus", "aac", "pcm")


class OpenAIProvider(VoiceProvider):
    name = "openai"
    max_text_length = 4096
    native_format = "wav"
    supports_auto_voices = True

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, *,
                 model: Optional[str] = None, transport: Optional[Transport] = None,
                 timeout: float = 120.0, max_retries: int = 3,
                 sleep: Callable[[float], None] = time.sleep, **_: Any):
        self._api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        if not self._api_key:
            raise ConfigError("OPENAI_API_KEY is not set. `export OPENAI_API_KEY=...`, or use the free "
                              "edge engine (--provider edge).")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("VOICEOVER_OPENAI_MODEL") or DEFAULT_MODEL
        self.transport = transport or urllib_transport
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.sleep = sleep

    def __repr__(self) -> str:
        return "OpenAIProvider(base_url=%r, model=%r, api_key=***)" % (self.base_url, self.model)

    def auto_voice(self, n: int, language: Optional[str]) -> Voice:
        return Voice(actor_id=SPEAKER_ROTATION[n % len(SPEAKER_ROTATION)])

    def build_payload(self, text: str, voice: Voice, audio_format: str) -> Dict[str, Any]:
        if not text.strip():
            raise ConfigError("Cannot synthesize empty text")
        if voice.reference_audio_url:
            raise NotSupported("The openai engine cannot clone voices; use --provider miragea.")
        name = (voice.actor_id or "alloy").lower()
        if name not in VOICES:
            raise ConfigError("Unknown OpenAI voice %r. Choose one of: %s" % (name, ", ".join(VOICES)))
        payload: Dict[str, Any] = {"model": voice.model or self.model, "input": text, "voice": name,
                                   "response_format": audio_format if audio_format in FORMATS else "wav"}
        if voice.speed is not None:
            speed = float(voice.speed)
            if not 0.25 <= speed <= 4:
                raise ConfigError("speed must be between 0.25 and 4")
            payload["speed"] = speed
        if voice.tags and payload["model"].startswith("gpt-"):
            payload["instructions"] = "Speak in a %s tone." % ", ".join(voice.tags)
        return payload

    def synthesize(self, text: str, voice: Voice, *, audio_format: str = "wav",
                   cache_key: Optional[str] = None) -> SynthesisResult:
        payload = self.build_payload(text, voice, audio_format)
        headers = {"Authorization": "Bearer " + self._api_key, "Content-Type": "application/json",
                   "Accept": "*/*"}
        body = json.dumps(payload).encode("utf-8")
        last: Optional[ProviderError] = None
        for attempt in range(self.max_retries):
            try:
                resp = self.transport("POST", self.base_url + "/audio/speech", headers, body, self.timeout)
            except ConnectionError as exc:
                last = ProviderError("Network error talking to OpenAI: %s" % exc, code="request_failed",
                                     retryable=True)
            else:
                if 200 <= resp.status < 300 and resp.body:
                    return SynthesisResult(resp.body, payload["response_format"],
                                           {"provider": self.name, "voice": payload["voice"],
                                            "model": payload["model"]})
                try:
                    err = (json.loads(resp.body.decode("utf-8")) or {}).get("error") or {}
                except (ValueError, AttributeError):
                    err = {}
                last = ProviderError(err.get("message") or "OpenAI returned HTTP %s" % resp.status,
                                     status=resp.status, code=err.get("code"),
                                     retryable=resp.status in (429, 500, 502, 503))
                if not last.retryable:
                    raise last
            if attempt + 1 < self.max_retries:
                self.sleep(min(2.0 ** attempt, 20.0))
        assert last is not None
        raise last

    def list_voices(self, limit: int = 20, offset: int = 0) -> Tuple[List[VoiceInfo], bool]:
        items = [VoiceInfo(v, v.capitalize(), "multi") for v in VOICES]
        return items[offset:offset + limit], offset + limit < len(items)
