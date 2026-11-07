"""Provider interface. Implement :class:`VoiceProvider` to add a new TTS engine.

A provider only has to turn one piece of text into audio bytes. Everything else
(script parsing, concatenation, subtitles, video) is handled by the studio.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..errors import NotSupported


@dataclass
class Voice:
    """How a line should sound. Use either ``actor_id`` or ``reference_audio_url``."""

    actor_id: Optional[str] = None
    reference_audio_url: Optional[str] = None
    reference_text: Optional[str] = None
    model: Optional[str] = None
    speed: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    language: Optional[str] = None

    @classmethod
    def parse(cls, spec: str, **overrides: Any) -> "Voice":
        """``"https://.../me.wav"`` -> reference audio; anything else -> actor id."""
        spec = (spec or "").strip()
        if spec.lower().startswith(("http://", "https://")):
            voice = cls(reference_audio_url=spec)
        else:
            voice = cls(actor_id=spec or None)
        for key, value in overrides.items():
            if value is not None and value != []:
                setattr(voice, key, value)
        return voice

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Voice":
        known = {k: data[k] for k in ("actor_id", "reference_audio_url", "reference_text",
                                      "model", "speed", "tags", "language") if k in data}
        if "voice" in data and not ("actor_id" in known or "reference_audio_url" in known):
            return cls.parse(str(data["voice"]), **known)
        if "actor_id" in known and known["actor_id"] is not None:
            known["actor_id"] = str(known["actor_id"])
        known["tags"] = list(known.get("tags") or [])
        return cls(**known)

    def merged(self, other: "Voice") -> "Voice":
        """Return a copy where non-empty fields of ``other`` override ours."""
        data = dict(self.__dict__)
        for key, value in other.__dict__.items():
            if value not in (None, []):
                data[key] = value
        if other.actor_id:
            data["reference_audio_url"] = None
            data["reference_text"] = other.reference_text
        elif other.reference_audio_url:
            data["actor_id"] = None
        return Voice(**data)

    def describe(self) -> str:
        if self.actor_id:
            return "actor:%s" % self.actor_id
        if self.reference_audio_url:
            return "ref:%s" % self.reference_audio_url
        return "default"


@dataclass
class SynthesisResult:
    audio: bytes
    format: str
    meta: Dict[str, Any] = field(default_factory=dict)  # task_id, idempotency_key, usage, ...


@dataclass
class VoiceInfo:
    voice_id: str
    name: str
    language: str = ""


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


class VoiceProvider(ABC):
    """Base class for voice engines."""

    name = "base"
    #: Largest text a single ``synthesize`` call accepts (None = unknown/unbounded).
    max_text_length: Optional[int] = None
    #: Audio format the engine returns most cheaply (used by ``Studio.say``).
    native_format: str = "wav"
    #: True when :meth:`auto_voice` can pick a voice per speaker without a voices file.
    supports_auto_voices: bool = False

    @abstractmethod
    def synthesize(self, text: str, voice: Voice, *, audio_format: str = "wav",
                   cache_key: Optional[str] = None) -> SynthesisResult:
        """Render ``text`` with ``voice``. ``cache_key`` is a stable id for this exact
        request; remote providers should use it as an idempotency key."""

    def auto_voice(self, n: int, language: Optional[str]) -> Optional[Voice]:
        """Voice for the ``n``-th distinct speaker when the user configured none.
        Return ``None`` to require an explicit voice."""
        return None

    def list_voices(self, limit: int = 20, offset: int = 0) -> Tuple[List[VoiceInfo], bool]:
        """Return ``(voices, has_more)``."""
        raise NotSupported("%s cannot list voices" % self.name)

    def transcribe(self, media_path: str) -> List[TranscriptSegment]:
        """Speech-to-text with timestamps, used for accurate subtitles."""
        raise NotSupported("%s cannot recognize subtitles" % self.name)
