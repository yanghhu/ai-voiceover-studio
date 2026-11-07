"""Voice providers.

Built in: ``miragea`` (default, remote) and ``dummy`` (offline silence).
Third-party packages can register more under the entry-point group
``ai_voiceover_studio.providers``::

    [project.entry-points."ai_voiceover_studio.providers"]
    myengine = "my_package.provider:MyProvider"
"""
from typing import Any, Callable, Dict

from ..errors import ConfigError
from .base import SynthesisResult, TranscriptSegment, Voice, VoiceInfo, VoiceProvider

ENTRY_POINT_GROUP = "ai_voiceover_studio.providers"


def _miragea(**kwargs: Any) -> VoiceProvider:
    from .miragea import MirageaProvider
    return MirageaProvider(**kwargs)


def _dummy(**kwargs: Any) -> VoiceProvider:
    from .dummy import DummyProvider
    return DummyProvider(**kwargs)


BUILTIN: Dict[str, Callable[..., VoiceProvider]] = {"miragea": _miragea, "dummy": _dummy}


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


def get_provider(name: str = "miragea", **kwargs: Any) -> VoiceProvider:
    """Instantiate a provider by name."""
    if name in BUILTIN:
        return BUILTIN[name](**kwargs)
    eps = _entry_points()
    if name in eps:
        return eps[name].load()(**kwargs)
    raise ConfigError("Unknown provider %r. Available: %s" % (name, ", ".join(available_providers())))


__all__ = ["VoiceProvider", "Voice", "VoiceInfo", "SynthesisResult", "TranscriptSegment",
           "get_provider", "available_providers"]
