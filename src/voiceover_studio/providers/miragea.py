"""Miragea voice provider (https://miragea.ai).

Uses the documented asynchronous Agent API (``GET /v1/schema``):

* ``GET  /capabilities``            models, limits, subtitle rate
* ``GET  /actors?limit&offset``     voices saved in your account
* ``POST /audio/generations``       create a TTS / voice-cloning task (Idempotency-Key)
* ``POST /subtitles/recognitions``  create a subtitle task (multipart, Idempotency-Key)
* ``GET  /tasks/{task_id}``         poll until ``succeeded`` or ``failed``

Configuration: ``MIRAGEA_API_KEY`` (required) and ``MIRAGEA_BASE_URL``
(optional, default ``https://miragea.ai/v1``). The key is only ever sent in the
``Authorization`` header to the API host and never printed or logged.
"""
import hashlib
import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .. import __version__
from ..errors import ConfigError, ProviderError, TaskFailed
from .base import SynthesisResult, TranscriptSegment, Voice, VoiceInfo, VoiceProvider

DEFAULT_BASE_URL = "https://miragea.ai/v1"
# Some edge networks reject unknown clients, so identify as a regular browser plus the tool name.
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0 Safari/537.36 ai-voiceover-studio/%s" % __version__)
TERMINAL = ("succeeded", "failed")
RETRYABLE_STATUS = (429, 502, 503)


@dataclass
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8")) if self.body else {}


Transport = Callable[[str, str, Dict[str, str], Optional[bytes], float], HttpResponse]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # pragma: no cover
        return None  # never forward the Authorization header to another host


def urllib_transport(method: str, url: str, headers: Dict[str, str], body: Optional[bytes],
                     timeout: float) -> HttpResponse:
    """Default transport (stdlib only). Returns non-2xx responses instead of raising."""
    opener = urllib.request.build_opener(_NoRedirect()) if "Authorization" in headers \
        else urllib.request.build_opener()
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(request, timeout=timeout) as response:
            return HttpResponse(response.status, dict(response.headers), response.read())
    except urllib.error.HTTPError as exc:
        return HttpResponse(exc.code, dict(exc.headers or {}), exc.read() or b"")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConnectionError(str(getattr(exc, "reason", exc))) from None


def stable_key(payload: Dict[str, Any], salt: str = "") -> str:
    """Deterministic idempotency key: re-running the same line returns the same task
    instead of paying for it twice."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False) + "|" + salt
    return "avs-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]


class MirageaClient:
    """Thin, dependency-free client for the Miragea Agent API."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, *,
                 timeout: float = 60.0, wait_timeout: float = 600.0,
                 transport: Optional[Transport] = None,
                 sleep: Callable[[float], None] = time.sleep, max_retries: int = 3):
        self._api_key = api_key if api_key is not None else os.environ.get("MIRAGEA_API_KEY", "")
        if not self._api_key:
            raise ConfigError("MIRAGEA_API_KEY is not set. Create a key at "
                              "https://miragea.ai/workspace/api and `export MIRAGEA_API_KEY=...`, "
                              "or add `--dry-run` for an offline test run.")
        self.base_url = (base_url or os.environ.get("MIRAGEA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        parts = urllib.parse.urlsplit(self.base_url)
        if parts.scheme not in ("http", "https") or not parts.netloc or parts.username \
                or parts.password or parts.query or parts.fragment:
            raise ConfigError("MIRAGEA_BASE_URL must be an http(s) API root such as %s "
                              "(no credentials, query or fragment)." % DEFAULT_BASE_URL)
        self.timeout = timeout
        self.wait_timeout = wait_timeout
        self.transport = transport or urllib_transport
        self.sleep = sleep
        self.max_retries = max_retries
        self._capabilities: Optional[Dict[str, Any]] = None

    def __repr__(self) -> str:  # never leak the key
        return "MirageaClient(base_url=%r, api_key=%s)" % (self.base_url, "***" if self._api_key else "<unset>")

    # -- low level -----------------------------------------------------------------
    def request(self, method: str, path: str, *, body: Optional[bytes] = None,
                content_type: Optional[str] = None, idempotency_key: Optional[str] = None) -> Any:
        headers = {"Authorization": "Bearer " + self._api_key, "Accept": "application/json",
                   "User-Agent": USER_AGENT}
        if content_type:
            headers["Content-Type"] = content_type
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        attempts = self.max_retries if idempotency_key or method == "GET" else 1
        last: Optional[ProviderError] = None
        for attempt in range(max(1, attempts)):
            try:
                response = self.transport(method, self.base_url + path, headers, body, self.timeout)
            except ConnectionError as exc:
                last = ProviderError("Network error talking to Miragea: %s. If this was a create "
                                     "request its outcome is unknown; retrying with the same "
                                     "idempotency key is safe." % exc, code="request_failed",
                                     retryable=True, idempotency_key=idempotency_key)
            else:
                if 200 <= response.status < 300:
                    try:
                        return response.json()
                    except ValueError:
                        raise ProviderError("Miragea returned invalid JSON", status=response.status,
                                            code="invalid_response") from None
                last = self._error(response, idempotency_key)
                if not (last.retryable or (response.status in RETRYABLE_STATUS and last.code is None)):
                    raise last
                retry_after = response.headers.get("Retry-After") or response.headers.get("retry-after")
                if retry_after and str(retry_after).isdigit():
                    self.sleep(min(float(retry_after), 60.0))
                    continue
            if attempt + 1 < attempts:
                self.sleep(min(2.0 ** attempt, 30.0))
        assert last is not None
        raise last

    @staticmethod
    def _error(response: HttpResponse, idempotency_key: Optional[str]) -> ProviderError:
        try:
            err = (response.json() or {}).get("error") or {}
        except (ValueError, AttributeError):
            err = {}
        if not isinstance(err, dict):
            err = {"message": str(err)}
        return ProviderError(err.get("message") or "Miragea API returned HTTP %s" % response.status,
                             status=response.status, code=err.get("code"), param=err.get("param"),
                             retryable=bool(err.get("retryable", False)),
                             idempotency_key=idempotency_key)

    # -- endpoints ------------------------------------------------------------------
    def capabilities(self, refresh: bool = False) -> Dict[str, Any]:
        if self._capabilities is None or refresh:
            self._capabilities = self.request("GET", "/capabilities")
        return self._capabilities

    def actors(self, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ConfigError("limit must be 1-100 and offset >= 0")
        return self.request("GET", "/actors?" + urllib.parse.urlencode({"limit": limit, "offset": offset}))

    def create_generation(self, payload: Dict[str, Any], idempotency_key: str) -> Dict[str, Any]:
        return self.request("POST", "/audio/generations", body=json.dumps(payload).encode("utf-8"),
                            content_type="application/json", idempotency_key=idempotency_key)

    def create_recognition(self, media_path: str, expected_rate: Any,
                           idempotency_key: str) -> Dict[str, Any]:
        body, ctype = _multipart(Path(media_path), expected_rate)
        return self.request("POST", "/subtitles/recognitions", body=body, content_type=ctype,
                            idempotency_key=idempotency_key)

    def task(self, task_id: str) -> Dict[str, Any]:
        return self.request("GET", "/tasks/" + urllib.parse.quote(task_id, safe=""))

    def wait(self, task: Dict[str, Any], idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """Poll a task (dict from a create call) until it finishes."""
        task_id = task.get("task_id")
        deadline = time.monotonic() + self.wait_timeout
        while task.get("status") not in TERMINAL:
            if not task_id:
                raise ProviderError("Task response has no task_id", code="invalid_response")
            if time.monotonic() >= deadline:
                raise ProviderError("Still %s after %ss; it keeps running on the server. Do not "
                                    "resubmit with a new key." % (task.get("status"), int(self.wait_timeout)),
                                    code="wait_timeout", task_id=task_id, idempotency_key=idempotency_key)
            pause = task.get("poll_after_seconds")
            if not isinstance(pause, (int, float)) or pause <= 0:
                pause = (self._capabilities or {}).get("task_poll_interval_seconds", 3)
            self.sleep(min(float(pause), 30.0))
            try:
                task = self.task(task_id)
            except ProviderError as exc:
                exc.task_id = task_id
                exc.idempotency_key = idempotency_key
                raise
        if task.get("status") == "failed":
            err = task.get("error") or {}
            raise TaskFailed(err.get("message") or "Miragea task failed", code=err.get("code") or "task_failed",
                             param=err.get("param"), retryable=bool(err.get("retryable", False)),
                             task_id=task_id, idempotency_key=idempotency_key)
        return task

    def download(self, url: str) -> bytes:
        """Fetch a result URL. The API key is deliberately NOT sent (it may be a CDN)."""
        if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
            raise ProviderError("Invalid audio_url in task result", code="invalid_response")
        last: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = self.transport("GET", url, {"User-Agent": USER_AGENT}, None, max(self.timeout, 120))
            except ConnectionError as exc:
                last = exc
            else:
                if 200 <= response.status < 300:
                    return response.body
                last = ProviderError("Downloading audio failed", status=response.status, code="download_failed")
                if response.status not in RETRYABLE_STATUS:
                    break
            self.sleep(min(2.0 ** attempt, 30.0))
        if isinstance(last, ProviderError):
            raise last
        raise ProviderError("Downloading audio failed: %s" % last, code="download_failed", retryable=True)


def _multipart(path: Path, expected_rate: Any) -> Tuple[bytes, str]:
    boundary = "avs-" + uuid.uuid4().hex
    name = path.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if isinstance(expected_rate, float) and expected_rate.is_integer():
        expected_rate = int(expected_rate)
    head = ("--{b}\r\nContent-Disposition: form-data; name=\"expected_rate\"\r\n\r\n{r}\r\n"
            "--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{n}\"\r\n"
            "Content-Type: {m}\r\n\r\n").format(b=boundary, r=expected_rate, n=name, m=mime)
    return (head.encode("utf-8") + path.read_bytes() + ("\r\n--%s--\r\n" % boundary).encode(),
            "multipart/form-data; boundary=" + boundary)


class MirageaProvider(VoiceProvider):
    """Text to speech and voice cloning through Miragea."""

    name = "miragea"
    supports_auto_voices = True

    def __init__(self, client: Optional[MirageaClient] = None, *, fresh: bool = False, **client_kwargs: Any):
        self.client = client or MirageaClient(**client_kwargs)
        self.fresh = fresh  # True -> random idempotency keys (new take every run)
        self._actors: Optional[List[str]] = None

    def auto_voice(self, n: int, language: Optional[str]) -> Optional[Voice]:
        """Use the voices saved in the account, in order (one listing call, no generation)."""
        if self._actors is None:
            self._actors = [str(a.get("actor_id")) for a in self.client.actors(20, 0).get("items", [])
                            if a.get("actor_id") is not None]
        if not self._actors:
            return None
        return Voice(actor_id=self._actors[n % len(self._actors)])

    @property
    def max_text_length(self) -> Optional[int]:  # type: ignore[override]
        try:
            value = (self.client.capabilities().get("audio") or {}).get("max_text_length")
        except ProviderError:
            return None
        return int(value) if isinstance(value, (int, float)) and value > 0 else None

    @staticmethod
    def build_payload(text: str, voice: Voice, audio_format: str) -> Dict[str, Any]:
        if not text.strip():
            raise ConfigError("Cannot synthesize empty text")
        if bool(voice.actor_id) == bool(voice.reference_audio_url):
            raise ConfigError("Miragea needs exactly one voice source: an actor id (see `voiceover "
                              "voices`) or a reference audio URL (voice cloning).")
        payload: Dict[str, Any] = {"text": text, "format": audio_format}
        if voice.actor_id:
            payload["actor_id"] = str(voice.actor_id)
        else:
            payload["reference_audio_url"] = voice.reference_audio_url
            if voice.reference_text:
                payload["reference_text"] = voice.reference_text
        if voice.model:
            payload["model"] = voice.model
        if voice.speed is not None:
            speed = float(voice.speed)
            if not 0.25 <= speed <= 4:
                raise ConfigError("speed must be between 0.25 and 4")
            payload["speed"] = speed
        if voice.tags:
            payload["tags"] = list(voice.tags)
        if voice.language:
            payload["language"] = voice.language
        return payload

    def synthesize(self, text: str, voice: Voice, *, audio_format: str = "wav",
                   cache_key: Optional[str] = None) -> SynthesisResult:
        payload = self.build_payload(text, voice, audio_format)
        key = str(uuid.uuid4()) if self.fresh else stable_key(payload, cache_key or "")
        task = self.client.create_generation(payload, key)
        task = self.client.wait(task, key)
        result = task.get("result") or {}
        url = result.get("audio_url")
        if not url:
            raise ProviderError("Task succeeded without audio_url", code="invalid_response",
                                task_id=task.get("task_id"), idempotency_key=key)
        audio = self.client.download(url)
        return SynthesisResult(audio=audio, format=result.get("format") or audio_format,
                               meta={"provider": self.name, "task_id": task.get("task_id"),
                                     "idempotency_key": key, "usage": task.get("usage")})

    def list_voices(self, limit: int = 20, offset: int = 0) -> Tuple[List[VoiceInfo], bool]:
        data = self.client.actors(limit, offset)
        items = [VoiceInfo(str(a.get("actor_id")), a.get("name", ""), a.get("language", ""))
                 for a in data.get("items", [])]
        return items, bool(data.get("has_more"))

    def transcribe(self, media_path: str) -> List[TranscriptSegment]:
        caps = self.client.capabilities(refresh=True)
        subs = caps.get("subtitles") or {}
        rate = subs.get("points_per_second")
        if rate is None:
            raise ProviderError("Capabilities did not include subtitles.points_per_second",
                                code="invalid_response")
        max_mb = subs.get("max_upload_mb")
        if max_mb and os.path.getsize(media_path) > float(max_mb) * 1024 * 1024:
            raise ConfigError("%s is larger than the %s MB upload limit" % (media_path, max_mb))
        digest = hashlib.sha256(Path(media_path).read_bytes()).hexdigest()
        key = str(uuid.uuid4()) if self.fresh else "avs-sub-%s-%s" % (digest[:32], rate)
        task = self.client.wait(self.client.create_recognition(media_path, rate, key), key)
        result = task.get("result") or {}
        segments = [TranscriptSegment(float(s["start"]), float(s["end"]), str(s.get("text", "")).strip())
                    for s in result.get("segments") or [] if "start" in s and "end" in s]
        if not segments and result.get("srt"):
            from ..subtitles import parse_srt
            segments = parse_srt(result["srt"])
        return segments
