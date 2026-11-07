"""Voice providers.

Built in:

* ``edge``    free Microsoft Edge neural voices (``pip install "ai-voiceover-studio[edge]"``),
              the default when no ``MIRAGEA_API_KEY`` is set
* ``miragea`` Miragea API: voice cloning, expressive models, subtitle recognition
* ``openai``  OpenAI text to speech (``OPENAI_API_KEY``)
* ``dummy``   offline silence with realistic timing, for tests and ``--dry-run``

Third-party packages can register more under the entry-point group
``ai_voiceover_studio.providers``::

    [project.entry-points."ai_voiceover_studio.providers"]
    myengine = "my_package.provider:MyProvider"
"""
from typing import Any, Callable, Dict
import importlib.util
import os

from ..errors import ConfigError
from .base import SynthesisResult, TranscriptSegment, Voice, VoiceInfo, VoiceProvider

ENTRY_POINT_GROUP = "ai_voiceover_studio.providers"


def _miragea(**kwargs: Any) -> VoiceProvider:
    from .miragea import MirageaProvider
    return MirageaProvider(**kwargs)


def _dummy(**kwargs: Any) -> VoiceProvider:
    from .dummy import DummyProvider
    return DummyProvider(**kwargs)


def _edge(**kwargs: Any) -> VoiceProvider:
    from .edge import EdgeProvider
    return EdgeProvider(**kwargs)


def _openai(**kwargs: Any) -> VoiceProvider:
    from .openai import OpenAIProvider
    return OpenAIProvider(**kwargs)


BUILTIN: Dict[str, Callable[..., VoiceProvider]] = {"edge": _edge, "miragea": _miragea,
                                                    "openai": _openai, "dummy": _dummy}


def edge_installed() -> bool:
    return importlib.util.find_spec("edge_tts") is not None


def default_provider_name() -> str:
    """``VOICEOVER_PROVIDER`` if set, else ``miragea`` when ``MIRAGEA_API_KEY`` is set,
    else the free ``edge`` engine."""
    explicit = os.environ.get("VOICEOVER_PROVIDER", "").strip()
    if explicit:
        return explicit
    if os.environ.get("MIRAGEA_API_KEY"):
        return "miragea"
    return "edge"


def _entry_points() -> Dict[str, Any]:
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return {}
    eps = entry_points()
    selected = eps.select(group=ENTRY_POINT_GROUP) if hasattr(eps, "select") \
        else eps.get(ENTRY_POINT_GROUP, [])  # Python 3.9
    return {ep.name: ep for ep in selected}


def available_providers() -> list:
    return sorted(set(BUILTIN) | set(_entry_points()))


def get_provider(name: str = "auto", **kwargs: Any) -> VoiceProvider:
    """Instantiate a provider by name (``auto`` -> :func:`default_provider_name`)."""
    if not name or name == "auto":
        name = default_provider_name()
    if name in BUILTIN:
        return BUILTIN[name](**kwargs)
    eps = _entry_points()
    if name in eps:
        return eps[name].load()(**kwargs)
    raise ConfigError("Unknown provider %r. Available: %s" % (name, ", ".join(available_providers())))


__all__ = ["VoiceProvider", "Voice", "VoiceInfo", "SynthesisResult", "TranscriptSegment",
           "get_provider", "available_providers", "default_provider_name", "edge_installed"]
