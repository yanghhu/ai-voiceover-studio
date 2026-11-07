"""Exception types shared by the library, providers and CLI."""
from typing import Any, Dict, Optional


class VoiceoverError(Exception):
    """Base class for every error raised by ai-voiceover-studio."""

    exit_code = 2

    def to_dict(self) -> Dict[str, Any]:
        return {"error": {"code": "voiceover_error", "message": str(self)}}


class ConfigError(VoiceoverError):
    """Bad input: missing API key, unknown speaker, invalid voices file, ..."""

    def to_dict(self) -> Dict[str, Any]:
        return {"error": {"code": "config_error", "message": str(self)}}


class ProviderError(VoiceoverError):
    """An error reported by (or while talking to) a voice provider."""

    _HINTS = {
        400: "Fix the request: check text length, model, tags, speed or voice fields.",
        401: "The API key was rejected. Check MIRAGEA_API_KEY (the key is never logged).",
        403: "This key's account has no API access. Check API permissions in your workspace.",
        404: "Task or resource not found for this account.",
        409: "Idempotency key was reused with different input, or the subtitle rate changed. "
             "Re-check and submit again with a new key.",
        413: "Upload too large. Use a smaller or shorter media file.",
        429: "Quota exhausted or rate limited. Wait, or top up credits, then retry.",
        502: "Service temporarily unavailable. Retry later.",
        503: "Service temporarily unavailable. Retry later.",
    }

    def __init__(self, message: str, *, status: Optional[int] = None, code: Optional[str] = None,
                 param: Optional[str] = None, retryable: bool = False,
                 task_id: Optional[str] = None, idempotency_key: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.param = param
        self.retryable = retryable
        self.task_id = task_id
        self.idempotency_key = idempotency_key

    @property
    def hint(self) -> Optional[str]:
        return self._HINTS.get(self.status) if self.status else None

    def __str__(self) -> str:
        parts = []
        if self.status:
            parts.append("HTTP %s" % self.status)
        if self.code:
            parts.append(self.code)
        head = " ".join(parts)
        text = "%s: %s" % (head, self.message) if head else self.message
        if self.param:
            text += " (param: %s)" % self.param
        if self.hint:
            text += "\nHint: " + self.hint
        if self.task_id:
            text += "\nTask: %s (resume with `voiceover task %s --wait`)" % (self.task_id, self.task_id)
        return text

    def to_dict(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {"code": self.code or "provider_error", "message": self.message,
                                "retryable": self.retryable}
        if self.status:
            body["http_status"] = self.status
        if self.param:
            body["param"] = self.param
        out: Dict[str, Any] = {"error": body}
        if self.task_id:
            out["task_id"] = self.task_id
        if self.idempotency_key:
            out["idempotency_key"] = self.idempotency_key
        return out


class TaskFailed(ProviderError):
    """The provider accepted the job but it finished with status ``failed``."""

    exit_code = 1


class NotSupported(VoiceoverError):
    """The selected provider does not implement this capability."""
