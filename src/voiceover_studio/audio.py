"""Audio helpers: WAV in/out with the stdlib, optional ffmpeg for other formats."""
import io
import os
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .errors import ConfigError

TARGET_RATE = 24000


@dataclass
class PcmAudio:
    """Raw little-endian PCM."""

    frames: bytes
    sample_rate: int
    channels: int
    sample_width: int

    @property
    def duration(self) -> float:
        per_second = self.sample_rate * self.channels * self.sample_width
        return len(self.frames) / per_second if per_second else 0.0

    def same_layout(self, other: "PcmAudio") -> bool:
        return (self.sample_rate, self.channels, self.sample_width) == \
            (other.sample_rate, other.channels, other.sample_width)


def wav_bytes(frames: bytes, sample_rate: int, channels: int, sample_width: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        w.writeframes(frames)
    return buf.getvalue()


def ffmpeg_path() -> Optional[str]:
    return os.environ.get("FFMPEG_BINARY") or shutil.which("ffmpeg")


def _ffmpeg(args: List[str]) -> None:
    exe = ffmpeg_path()
    if not exe:
        raise ConfigError("ffmpeg is required for this audio format. Install ffmpeg "
                          "(https://ffmpeg.org) or use .wav output.")
    proc = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y"] + args,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise ConfigError("ffmpeg failed: " + proc.stderr.decode("utf-8", "replace").strip()[-500:])


def decode(data: bytes, fmt: str = "wav") -> PcmAudio:
    """Decode provider audio to PCM. WAV/PCM16 uses the stdlib; anything else uses ffmpeg."""
    if fmt == "wav":
        try:
            with wave.open(io.BytesIO(data), "rb") as w:
                return PcmAudio(w.readframes(w.getnframes()), w.getframerate(),
                                w.getnchannels(), w.getsampwidth())
        except (wave.Error, EOFError):
            pass  # e.g. float WAV: fall through to ffmpeg
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / ("in." + (fmt or "bin"))
        dst = Path(tmp) / "out.wav"
        src.write_bytes(data)
        _ffmpeg(["-i", str(src), "-ac", "1", "-ar", str(TARGET_RATE), "-sample_fmt", "s16", str(dst)])
        return decode(dst.read_bytes(), "wav")


def conform(audio: PcmAudio, like: PcmAudio) -> PcmAudio:
    """Make ``audio`` match ``like``'s sample layout (ffmpeg when it differs)."""
    if audio.same_layout(like):
        return audio
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "a.wav"
        dst = Path(tmp) / "b.wav"
        src.write_bytes(wav_bytes(audio.frames, audio.sample_rate, audio.channels, audio.sample_width))
        fmt = {1: "u8", 2: "s16", 4: "s32"}.get(like.sample_width, "s16")
        _ffmpeg(["-i", str(src), "-ac", str(like.channels), "-ar", str(like.sample_rate),
                 "-sample_fmt", fmt, str(dst)])
        return decode(dst.read_bytes(), "wav")


def silence(seconds: float, like: PcmAudio) -> bytes:
    frames = int(max(0.0, seconds) * like.sample_rate)
    return b"\x00" * (frames * like.channels * like.sample_width)


def concat(clips: List[PcmAudio], gaps: List[float]) -> PcmAudio:
    """Join clips; ``gaps[i]`` seconds of silence follow clip ``i``."""
    if not clips:
        raise ConfigError("Nothing to concatenate")
    first = clips[0]
    out = bytearray()
    for i, clip in enumerate(clips):
        out += conform(clip, first).frames
        if i < len(gaps) and gaps[i] > 0:
            out += silence(gaps[i], first)
    return PcmAudio(bytes(out), first.sample_rate, first.channels, first.sample_width)


def export(audio: PcmAudio, path: str) -> str:
    """Write ``audio`` to ``path``; the extension picks the format (wav natively, else ffmpeg)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = wav_bytes(audio.frames, audio.sample_rate, audio.channels, audio.sample_width)
    ext = target.suffix.lower().lstrip(".") or "wav"
    if ext == "wav":
        target.write_bytes(data)
        return str(target)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "mix.wav"
        src.write_bytes(data)
        extra = ["-b:a", "192k"] if ext in ("mp3", "aac", "m4a", "opus", "ogg") else []
        _ffmpeg(["-i", str(src)] + extra + [str(target)])
    return str(target)


def write_raw(data: bytes, fmt: str, path: str) -> str:
    """Save provider bytes; transcode only if the extension differs from ``fmt``."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ext = target.suffix.lower().lstrip(".")
    if not ext or ext == fmt:
        target.write_bytes(data)
        return str(target)
    return export(decode(data, fmt), str(target))
