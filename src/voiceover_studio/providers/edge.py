"""Free neural voices through the ``edge-tts`` package (no account, no key).

Install the extra: ``pip install "ai-voiceover-studio[edge]"``.

* ``Voice.actor_id`` is an Edge voice short name such as ``en-US-AndrewNeural``
  or ``zh-CN-XiaoxiaoNeural`` (``voiceover voices --provider edge``). Without
  one, a voice is picked from the language of the text (or ``--lang``).
* ``speed`` maps to the engine's rate (``1.25`` -> ``+25%``).
* Word timings reported by the engine are returned in ``meta["words"]`` (used for
  word-by-word animated captions) and grouped into ``meta["sentences"]`` (used for
  SRT timing). Older edge-tts versions only report sentences.
* Voice cloning (reference audio) is not available on this engine; use the
  ``miragea`` provider for that.

Set ``VOICEOVER_EDGE_PROXY`` to route this engine through a specific proxy.
"""
import asyncio
import inspect
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..errors import ConfigError, NotSupported, ProviderError
from ..words import sentences_from_words
from .base import SynthesisResult, Voice, VoiceInfo, VoiceProvider

_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_KANA = re.compile(r"[\u3040-\u30ff]")
_HANGUL = re.compile(r"[\uac00-\ud7af]")
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")

#: Two contrasting voices per language: the first speaker gets the first voice,
#: the second speaker the second one, and so on (round robin).
DEFAULT_VOICES: Dict[str, Tuple[str, ...]] = {
    "en": ("en-US-AndrewNeural", "en-US-AvaNeural", "en-US-BrianNeural", "en-US-EmmaNeural"),
    "zh": ("zh-CN-YunxiNeural", "zh-CN-XiaoxiaoNeural", "zh-CN-YunjianNeural", "zh-CN-XiaoyiNeural"),
    "ja": ("ja-JP-KeitaNeural", "ja-JP-NanamiNeural"),
    "ko": ("ko-KR-InJoonNeural", "ko-KR-SunHiNeural"),
    "es": ("es-ES-AlvaroNeural", "es-ES-ElviraNeural"),
    "fr": ("fr-FR-HenriNeural", "fr-FR-DeniseNeural"),
    "de": ("de-DE-ConradNeural", "de-DE-KatjaNeural"),
    "it": ("it-IT-DiegoNeural", "it-IT-ElsaNeural"),
    "pt": ("pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"),
    "ru": ("ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"),
}
TICKS_PER_SECOND = 10_000_000  # edge-tts offsets are in 100 ns units


def detect_language(text: str) -> str:
    """Very small script-based guess, enough to pick a sensible default voice."""
    if _KANA.search(text):
        return "ja"
    if _HANGUL.search(text):
        return "ko"
    if _CJK.search(text):
        return "zh"
    if _CYRILLIC.search(text):
        return "ru"
    return "en"


def voices_for(language: Optional[str]) -> Tuple[str, ...]:
    lang = (language or "en").lower().split("-")[0].split("_")[0]
    return DEFAULT_VOICES.get(lang, DEFAULT_VOICES["en"])


def rate_for(speed: Optional[float]) -> str:
    if speed is None:
        return "+0%"
    speed = float(speed)
    if not 0.25 <= speed <= 4:
        raise ConfigError("speed must be between 0.25 and 4")
    pct = int(round((speed - 1.0) * 100))
    return "%+d%%" % pct


def _run(coro_factory: Callable[[], Any]) -> Any:
    """Run a coroutine from sync code, also when an event loop is already running
    (Jupyter, async apps)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    box: Dict[str, Any] = {}

    def worker() -> None:
        try:
            box["value"] = asyncio.run(coro_factory())
        except BaseException as exc:  # pragma: no cover - re-raised below
            box["error"] = exc

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _import_edge():
    try:
        import edge_tts  # type: ignore
    except ImportError:
        raise ConfigError("The edge engine needs the edge-tts package: "
                          "pip install \"ai-voiceover-studio[edge]\"") from None
    return edge_tts


class EdgeProvider(VoiceProvider):
    """Microsoft Edge online neural voices via ``edge-tts``. Free, no API key."""

    name = "edge"
    max_text_length = 2000
    native_format = "mp3"
    supports_auto_voices = True

    def __init__(self, *, communicate: Optional[Callable[..., Any]] = None,
                 list_voices_fn: Optional[Callable[[], Any]] = None,
                 proxy: Optional[str] = None, max_retries: int = 3,
                 sleep: Callable[[float], None] = time.sleep, **_: Any):
        self._communicate = communicate
        self._list_voices_fn = list_voices_fn
        self.proxy = proxy if proxy is not None else (os.environ.get("VOICEOVER_EDGE_PROXY") or None)
        self.max_retries = max(1, max_retries)
        self.sleep = sleep
        if communicate is None:
            _import_edge()  # fail early with a clear install hint

    # -- voice choice ------------------------------------------------------------
    def auto_voice(self, n: int, language: Optional[str]) -> Voice:
        """Voice for the ``n``-th distinct speaker (0-based) of a script."""
        names = voices_for(language)
        return Voice(actor_id=names[n % len(names)])

    def _voice_name(self, text: str, voice: Voice) -> str:
        if voice.reference_audio_url:
            raise NotSupported("The edge engine cannot clone voices from reference audio. Use "
                               "--provider miragea for voice cloning, or pick an Edge voice name "
                               "(see `voiceover voices --provider edge`).")
        if voice.actor_id and re.match(r"^[a-z]{2,3}-[A-Za-z]{2,4}(-[A-Za-z]+)?-\w+Neural$", voice.actor_id):
            return voice.actor_id
        if voice.actor_id and voice.actor_id not in ("default", "auto"):
            raise ConfigError("%r is not an Edge voice name. Use one like en-US-AvaNeural "
                              "(list them with `voiceover voices --provider edge`)." % voice.actor_id)
        return voices_for(voice.language or detect_language(text))[0]

    # -- synthesis ---------------------------------------------------------------
    def _factory(self) -> Callable[..., Any]:
        return self._communicate or _import_edge().Communicate

    def _supports_word_boundary(self, factory: Callable[..., Any]) -> bool:
        try:
            return "boundary" in inspect.signature(factory).parameters
        except (TypeError, ValueError):
            return False

    async def _stream(self, text: str, name: str, rate: str
                      ) -> Tuple[bytes, List[Dict[str, Any]], List[Dict[str, Any]]]:
        kwargs: Dict[str, Any] = {"rate": rate}
        if self.proxy:
            kwargs["proxy"] = self.proxy
        factory = self._factory()
        if self._supports_word_boundary(factory):
            kwargs["boundary"] = "WordBoundary"
        comm = factory(text, name, **kwargs)
        audio = bytearray()
        sentences: List[Dict[str, Any]] = []
        words: List[Dict[str, Any]] = []
        async for chunk in comm.stream():
            kind = chunk.get("type")
            if kind == "audio":
                audio += chunk.get("data") or b""
            elif kind in ("SentenceBoundary", "WordBoundary"):
                start = float(chunk.get("offset", 0)) / TICKS_PER_SECOND
                item = {"start": round(start, 3),
                        "end": round(start + float(chunk.get("duration", 0)) / TICKS_PER_SECOND, 3),
                        "text": str(chunk.get("text", "")).strip()}
                (words if kind == "WordBoundary" else sentences).append(item)
        if words and not sentences:
            sentences = sentences_from_words(text, words)
        return bytes(audio), sentences, words

    def synthesize(self, text: str, voice: Voice, *, audio_format: str = "mp3",
                   cache_key: Optional[str] = None) -> SynthesisResult:
        if not text.strip():
            raise ConfigError("Cannot synthesize empty text")
        name = self._voice_name(text, voice)
        rate = rate_for(voice.speed)
        last: Optional[BaseException] = None
        for attempt in range(self.max_retries):
            try:
                audio, sentences, words = _run(lambda: self._stream(text, name, rate))
            except (ConfigError, NotSupported):
                raise
            except ValueError as exc:
                if "login" in str(exc).lower():  # aiohttp rejects some proxy URLs with credentials
                    raise ProviderError("Your HTTPS proxy URL could not be used by edge-tts (%s). "
                                        "Set VOICEOVER_EDGE_PROXY to a proxy without credentials, or "
                                        "unset HTTPS_PROXY for this command." % exc,
                                        code="proxy_unsupported") from None
                last = exc
            except Exception as exc:  # network errors, service hiccups
                last = exc
            else:
                if audio:
                    meta: Dict[str, Any] = {"provider": self.name, "voice": name, "rate": rate,
                                            "sentences": sentences}
                    if words:
                        meta["words"] = words
                    return SynthesisResult(audio, "mp3", meta)
                last = ProviderError("No audio received for voice %s" % name, code="no_audio")
            if attempt + 1 < self.max_retries:
                self.sleep(min(2.0 ** attempt, 8.0))
        raise ProviderError("Edge TTS failed after %d attempts: %s. Check your internet connection "
                            "(run `voiceover doctor --online`)." % (self.max_retries, last),
                            code="request_failed", retryable=True)

    # -- voices ------------------------------------------------------------------
    def list_voices(self, limit: int = 20, offset: int = 0) -> Tuple[List[VoiceInfo], bool]:
        fn = self._list_voices_fn or _import_edge().list_voices
        raw = _run(fn) or []
        items = sorted((VoiceInfo(v.get("ShortName", ""),
                                  "%s (%s)" % (v.get("FriendlyName") or v.get("ShortName", ""),
                                               v.get("Gender", "")),
                                  v.get("Locale", "")) for v in raw), key=lambda v: (v.language, v.voice_id))
        return items[offset:offset + limit], offset + limit < len(items)
