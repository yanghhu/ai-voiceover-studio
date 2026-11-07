"""High-level API used by the CLI and by Python callers.

    from voiceover_studio import Studio
    studio = Studio()                # free edge voices, or Miragea when MIRAGEA_API_KEY is set
    studio.say("Hello!", output="hello.mp3")
    result = studio.render_script("script.md", "out/")   # one voice per speaker, automatically
    print(result.audio_path, result.srt_path)
"""
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from . import audio as audiolib
from . import subtitles as srt
from .config import VoiceMap, load_voices, resolve
from .errors import ConfigError, NotSupported
from .providers import get_provider
from .providers.base import Voice, VoiceProvider
from .script import Segment, parse_script, speakers

log = logging.getLogger("voiceover_studio")
PathLike = Union[str, Path]


@dataclass
class SegmentResult:
    index: int
    speaker: str
    text: str
    voice: str
    start: float
    end: float
    file: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RenderResult:
    audio_path: str
    srt_path: Optional[str]
    manifest_path: str
    duration: float
    segments: List[SegmentResult]
    subtitle_source: str = "none"


class Studio:
    def __init__(self, provider: Union[str, VoiceProvider] = "auto", **provider_kwargs: Any):
        self.provider = get_provider(provider, **provider_kwargs) if isinstance(provider, str) else provider

    # -- single line ---------------------------------------------------------------
    def say(self, text: str, voice: Union[None, str, Voice], output: PathLike,
            **voice_options: Any) -> Dict[str, Any]:
        if voice is None or voice == "":
            picked = self.provider.auto_voice(0, voice_options.get("language")
                                              or _guess_language(text))
            if picked is None:
                raise ConfigError("No default voice available for the %s engine (for Miragea: the account "
                                  "has no saved voices yet). Pass --voice with a voice id from "
                                  "`voiceover voices`, or a reference audio URL." % self.provider.name)
            v = picked.merged(Voice(**{k: val for k, val in voice_options.items()
                                       if k in ("model", "speed", "tags", "language", "reference_text")
                                       and val is not None}))
        else:
            v = voice if isinstance(voice, Voice) else Voice.parse(voice, **voice_options)
        fmt = Path(output).suffix.lower().lstrip(".") or "mp3"
        native = fmt if fmt in ("mp3", "wav", "flac", "opus", "aac", "pcm") else "wav"
        if self.provider.name in ("dummy", "edge"):
            native = self.provider.native_format
        result = self.provider.synthesize(text, v, audio_format=native)
        path = audiolib.write_raw(result.audio, result.format, str(output))
        meta = {k: val for k, val in result.meta.items() if k != "sentences"}
        return {"output": path, "voice": v.describe(), **meta}

    # -- whole script ----------------------------------------------------------------
    def render_script(self, script: PathLike, outdir: PathLike, *,
                      voices: Union[None, PathLike, VoiceMap] = None,
                      default_voice: Optional[Union[str, Voice]] = None,
                      output_name: str = "voiceover.mp3", gap: float = 0.35,
                      subtitles: str = "timing", max_chars: Optional[int] = None,
                      use_cache: bool = True,
                      progress: Optional[Callable[[int, int, Segment], None]] = None) -> RenderResult:
        """Voice every segment, join them, write audio + SRT + manifest.json.

        ``subtitles``: ``timing`` (from segment durations, free and exact to the
        script text), ``recognize`` (provider speech recognition on the final mix;
        falls back to timing if unsupported) or ``none``.
        """
        if subtitles not in ("timing", "recognize", "none"):
            raise ConfigError("subtitles must be timing, recognize or none")
        script_path = Path(script)
        text = script_path.read_text(encoding="utf-8") if script_path.is_file() else None
        if text is None:
            raise ConfigError("Script not found: %s" % script)
        limit = max_chars if max_chars is not None else (self.provider.max_text_length or 0)
        if limit:
            limit = min(limit, 3000)  # keeps each request short, retries cheap
        segments = parse_script(text, max_chars=limit)
        if not any(s.text for s in segments):
            raise ConfigError("Script %s has no speakable text" % script)
        voice_map = dict(voices) if isinstance(voices, dict) else load_voices(voices)
        fallback = Voice.parse(default_voice) if isinstance(default_voice, str) else default_voice
        language = _guess_language(" ".join(s.text for s in segments))
        if fallback is None and "DEFAULT" not in voice_map and self.provider.supports_auto_voices:
            # No voice configured for some speakers: give each one its own voice.
            n = 0
            for name in speakers(segments):
                if name.upper() in voice_map:
                    continue
                seg_lang = next((s.options.get("language") for s in segments
                                 if s.speaker == name and s.options.get("language")), None)
                auto = self.provider.auto_voice(n, seg_lang or language)
                if auto is None:
                    break
                voice_map[name.upper()] = auto
                n += 1
        # Fail fast on missing speakers before spending anything.
        for seg in segments:
            if seg.text:
                resolve(voice_map, seg.speaker, fallback)

        out = Path(outdir)
        seg_dir = out / "segments"
        seg_dir.mkdir(parents=True, exist_ok=True)
        clips: List[audiolib.PcmAudio] = []
        gaps: List[float] = []
        results: List[SegmentResult] = []
        voiced = [s for s in segments if s.text]
        cursor = 0.0
        lead = sum(s.pause_after for s in segments if not s.text and s.index == 0)
        for n, seg in enumerate(voiced, 1):
            voice = resolve(voice_map, seg.speaker, fallback).merged(Voice(**_voice_opts(seg.options)))
            if progress:
                progress(n, len(voiced), seg)
            cache_id = _cache_id(self.provider.name, seg.text, voice)
            file = seg_dir / ("%03d_%s_%s.wav" % (seg.index + 1, _slug(seg.speaker), cache_id[:10]))
            timing_file = file.with_suffix(".timing.json")
            meta: Dict[str, Any] = {}
            sentences: List[Dict[str, Any]] = []
            if use_cache and file.is_file():
                pcm = audiolib.decode(file.read_bytes(), "wav")
                meta = {"cached": True}
                if timing_file.is_file():
                    try:
                        sentences = json.loads(timing_file.read_text(encoding="utf-8"))
                    except ValueError:
                        sentences = []
            else:
                res = self.provider.synthesize(seg.text, voice, audio_format="wav", cache_key=cache_id)
                pcm = audiolib.decode(res.audio, res.format)
                file.write_bytes(audiolib.wav_bytes(pcm.frames, pcm.sample_rate, pcm.channels, pcm.sample_width))
                meta = {k: v for k, v in res.meta.items() if k != "sentences"}
                sentences = list(res.meta.get("sentences") or [])
                if sentences:
                    timing_file.write_text(json.dumps(sentences, ensure_ascii=False), encoding="utf-8")
            if sentences:
                meta["sentences"] = sentences
            start = cursor + (lead if n == 1 else 0.0)
            pause = gap + seg.pause_after if n < len(voiced) else seg.pause_after
            results.append(SegmentResult(seg.index, seg.speaker, seg.text, voice.describe(),
                                         round(start, 3), round(start + pcm.duration, 3), str(file), meta))
            cursor = start + pcm.duration + pause
            clips.append(pcm)
            gaps.append(pause)
        if lead:  # script starts with [pause N]
            first = clips[0]
            clips.insert(0, audiolib.PcmAudio(b"", first.sample_rate, first.channels, first.sample_width))
            gaps.insert(0, lead)
        mix = audiolib.concat(clips, gaps)
        audio_path = audiolib.export(mix, str(out / output_name))

        srt_path: Optional[str] = None
        source = "none"
        if subtitles != "none":
            cues = None
            if subtitles == "recognize":
                try:
                    cues = srt.cues_from_transcript(self.provider.transcribe(audio_path))
                    source = "recognize"
                except NotSupported as exc:
                    log.warning("%s; using segment timing for subtitles", exc)
            if not cues:
                cues = srt.cues_from_segments(results)
                source = "timing"
            srt_path = str(Path(audio_path).with_suffix(".srt"))
            Path(srt_path).write_text(srt.to_srt(cues), encoding="utf-8")

        manifest = out / "manifest.json"
        manifest.write_text(json.dumps({
            "script": str(script_path), "provider": self.provider.name, "audio": audio_path,
            "subtitles": srt_path, "subtitle_source": source, "duration": round(mix.duration, 3),
            "segments": [asdict(r) for r in results]}, ensure_ascii=False, indent=2), encoding="utf-8")
        return RenderResult(audio_path, srt_path, str(manifest), mix.duration, results, source)


def _guess_language(text: str) -> str:
    from .providers.edge import detect_language
    return detect_language(text)


def _voice_opts(options: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in options.items() if k in ("speed", "tags", "model", "language")}


def _cache_id(provider: str, text: str, voice: Voice) -> str:
    blob = json.dumps([provider, text, asdict(voice)], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")[:24] or "speaker"
