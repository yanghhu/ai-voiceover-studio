"""Offline provider: renders silence (or a soft tone) with a realistic duration.

Used by the test-suite and by ``--dry-run`` so you can check script parsing,
timing, subtitles and video layout without an API key or spending credits.
"""
import math
import re
import struct
from typing import List, Optional, Tuple

from ..audio import wav_bytes
from .base import SynthesisResult, Voice, VoiceInfo, VoiceProvider

_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
_WORD = re.compile(r"[A-Za-z0-9\u00c0-\u024f\u0400-\u04ff']+")


def estimate_seconds(text: str, speed: float = 1.0) -> float:
    """Rough narration length: ~2.6 words/s for alphabetic text, ~4.5 chars/s for CJK."""
    cjk = len(_CJK.findall(text))
    words = len(_WORD.findall(_CJK.sub(" ", text)))
    pauses = len(re.findall(r"[.!?;:,。！？；：，、]", text)) * 0.08
    seconds = words / 2.6 + cjk / 4.5 + pauses
    return max(0.5, seconds) / max(0.25, speed or 1.0)


class DummyProvider(VoiceProvider):
    name = "dummy"
    max_text_length = 5000

    def __init__(self, sample_rate: int = 24000, tone: bool = False):
        self.sample_rate = sample_rate
        self.tone = tone
        self.calls: List[Tuple[str, Voice]] = []

    def synthesize(self, text: str, voice: Voice, *, audio_format: str = "wav",
                   cache_key: Optional[str] = None) -> SynthesisResult:
        self.calls.append((text, voice))
        frames = int(estimate_seconds(text, voice.speed or 1.0) * self.sample_rate)
        if self.tone:
            amp = 1200
            pcm = b"".join(struct.pack("<h", int(amp * math.sin(2 * math.pi * 220 * i / self.sample_rate)))
                           for i in range(frames))
        else:
            pcm = b"\x00\x00" * frames
        return SynthesisResult(wav_bytes(pcm, self.sample_rate, 1, 2), "wav",
                               {"provider": self.name, "voice": voice.describe()})

    def list_voices(self, limit: int = 20, offset: int = 0) -> Tuple[List[VoiceInfo], bool]:
        voices = [VoiceInfo("dummy-narrator", "Narrator (silent)", "en"),
                  VoiceInfo("dummy-host", "Host (silent)", "zh")]
        return voices[offset:offset + limit], offset + limit < len(voices)
