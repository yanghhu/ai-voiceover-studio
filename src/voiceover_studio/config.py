"""Load the speaker -> voice map (``voices.json`` or ``voices.yaml``).

Example::

    {
      "default":  {"actor_id": "12345"},
      "NARRATOR": {"actor_id": "12345", "model": "standard"},
      "ALEX":     {"reference_audio_url": "https://example.com/alex.wav",
                   "reference_text": "Exact words spoken in alex.wav",
                   "tags": ["cheerful"], "speed": 1.05}
    }

A value may also be a plain string (actor id or reference audio URL).
"""
import json
from pathlib import Path
from typing import Dict, Optional, Union

from .errors import ConfigError
from .providers.base import Voice

VoiceMap = Dict[str, Voice]


def load_voices(path: Optional[Union[str, Path]]) -> VoiceMap:
    if not path:
        return {}
    file = Path(path)
    if not file.is_file():
        raise ConfigError("Voices file not found: %s" % file)
    raw = file.read_text(encoding="utf-8")
    if file.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError:
            raise ConfigError("Reading YAML needs PyYAML: pip install 'ai-voiceover-studio[yaml]' "
                              "(or use voices.json)") from None
        data = yaml.safe_load(raw) or {}
    else:
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise ConfigError("Invalid JSON in %s: %s" % (file, exc)) from None
    if isinstance(data, dict) and isinstance(data.get("voices"), dict):
        data = data["voices"]
    if not isinstance(data, dict):
        raise ConfigError("%s must map speaker names to voices" % file)
    voices: VoiceMap = {}
    for name, value in data.items():
        if str(name).startswith("$"):
            continue  # allow "$comment" keys
        if isinstance(value, (str, int)):
            voices[str(name).upper()] = Voice.parse(str(value))
        elif isinstance(value, dict):
            voices[str(name).upper()] = Voice.from_dict(value)
        else:
            raise ConfigError("Voice for %r must be a string or an object" % name)
    return voices


def resolve(voices: VoiceMap, speaker: str, fallback: Optional[Voice] = None) -> Voice:
    voice = voices.get(speaker.upper()) or voices.get("DEFAULT") or fallback
    if voice is None:
        raise ConfigError("No voice for speaker [%s]. Add it to your voices file or pass "
                          "--default-voice." % speaker)
    return voice
