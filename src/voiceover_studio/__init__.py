"""AI Voiceover Studio: turn scripts into voiceovers, subtitles and faceless videos."""

__version__ = "0.1.0"

from .errors import ConfigError, NotSupported, ProviderError, TaskFailed, VoiceoverError  # noqa: E402
from .providers import Voice, VoiceProvider, get_provider  # noqa: E402
from .script import Segment, parse_script  # noqa: E402
from .studio import RenderResult, Studio  # noqa: E402

__all__ = ["__version__", "Studio", "RenderResult", "Voice", "VoiceProvider", "get_provider",
           "Segment", "parse_script", "VoiceoverError", "ConfigError", "ProviderError",
           "TaskFailed", "NotSupported"]
