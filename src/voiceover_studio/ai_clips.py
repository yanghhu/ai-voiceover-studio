"""AI video clips: OpenRouter's async video API turns a prompt into a real MP4.

Unlike the GIF modes (where the AI draws frames/images and the motion is assembled
locally), here the provider animates everything: models such as Veo, Seedance, Kling,
Wan or Hailuo generate a true short video clip from text (or from a first frame). The
clip lands in the session folder as a normal ``.mp4`` and the render engine already
treats video shots as loopable (``-stream_loop -1``), so the clip can replace stock
footage in the final video directly.

The OpenRouter video API is asynchronous:

    POST /api/v1/videos          submit the job        -> {"id", "polling_url", ...}
    GET  /api/v1/videos/{id}     poll until completed  -> {"unsigned_urls": [...]}
    GET  unsigned_urls[0]        download the MP4      (needs the API key header)

HTTP goes through the same injectable transport as the rest of the project, so tests
run fully offline.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .errors import ProviderError

VIDEO_MODELS = [
    "google/veo-3.1-lite",
    "bytedance/seedance-2.0-fast",
    "x-ai/grok-imagine-video-1.5-lite",
    "alibaba/wan-2.7",
    "minimax/hailuo-2.3",
]

CLIP_PROMPT_SYSTEM = (
    "You write prompts for a text-to-video model (Veo, Seedance, Kling, Wan). From the "
    "user's scene idea return ONE vivid English prompt of max ~80 words that describes a "
    "SINGLE shot with concrete motion: subject, action, camera (locked tripod / slow "
    "push-in / gentle pan), lighting and mood. Keep the camera steady so the clip loops "
    "well. No on-screen text, no captions, no watermark; no people unless explicitly asked."
)


def video_catalog(client: Any) -> List[Dict[str, Any]]:
    """The live OpenRouter video model catalog (slugs, supported durations/aspect ratios)."""
    data = client.request("GET", "/videos/models")
    return [item for item in data.get("data", []) if item.get("id")]


def plan_clip_prompt(client: Any, model: str, scene: str, motion: str = "",
                     extra: str = "") -> str:
    """Scene idea (+ what moves) -> one cinematic text-to-video prompt (editable)."""
    user = (scene or "").strip()
    if (motion or "").strip():
        user += "\nWhat happens and how: %s" % motion.strip()
    if (extra or "").strip():
        user += "\nStyle: %s" % extra.strip()
    prompt = client.chat(model, [
        {"role": "system", "content": CLIP_PROMPT_SYSTEM},
        {"role": "user", "content": user}])
    return prompt.strip().strip('"').strip("`")


def generate_video_clip(client: Any, model: str, prompt: str, dest_base: Path, *,
                        duration: int = 5, resolution: str = "720p",
                        aspect_ratio: str = "16:9", generate_audio: bool = False,
                        poll_seconds: float = 15.0, timeout: float = 900.0,
                        progress: Optional[Callable[[str], None]] = None) -> Path:
    """Submit the video job, poll it and download the finished MP4 to ``dest_base``(.mp4).

    ``progress`` receives one line per poll (suitable for the Gradio live log). Raises
    ``ProviderError`` when the job fails or the deadline expires; the API's own validation
    errors (unsupported duration/aspect ratio for the model) surface with the model's
    supported values in the message.
    """
    if not (prompt or "").strip():
        raise ValueError("Describe the clip first (scene, action, camera, lighting).")
    body: Dict[str, Any] = {"model": model, "prompt": prompt.strip(),
                            "duration": int(duration), "resolution": resolution,
                            "aspect_ratio": aspect_ratio, "generate_audio": bool(generate_audio)}
    report = progress
    if report is not None:
        report("Submitting the video job to **%s** (%ds, %s)... watch the OpenRouter costs."
               % (model, int(duration), aspect_ratio))
    job = client.request("POST", "/videos", body)
    job_id = (job or {}).get("id")
    if not job_id:
        raise ProviderError("OpenRouter did not return a video job id: %s"
                            % str(job)[:200])
    deadline = time.monotonic() + max(30.0, float(timeout))
    last_state = ""
    while True:
        if time.monotonic() > deadline:
            raise ProviderError("The AI clip job %s did not finish in %.0f s (video "
                                "generation usually takes 1-5 minutes; try again or pick "
                                "a faster model)." % (job_id, float(timeout)))
        status = client.request("GET", "/videos/%s" % job_id)
        state = str((status or {}).get("status") or "pending")
        if state != last_state:
            if progress is not None:
                progress("AI clip job %s: **%s**" % (str(job_id)[:12], state))
            last_state = state
        if state == "completed":
            urls = [u for u in (status.get("unsigned_urls") or
                                status.get("urls") or []) if u]
            if not urls:
                raise ProviderError("The AI clip job finished but returned no video URL.")
            dest = Path(dest_base)
            if dest.suffix.lower() != ".mp4":
                dest = Path(str(dest) + ".mp4")
            dest.parent.mkdir(parents=True, exist_ok=True)
            started = time.monotonic()
            response = client.transport("GET", urls[0], client._headers(), None, 120.0)
            if response.status >= 400 or not response.body:
                raise ProviderError("AI clip download failed (%d)." % response.status)
            dest.write_bytes(response.body)
            if progress is not None:
                progress("Downloaded the MP4 (%.1f MB, %.1f s)."
                         % (len(response.body) / 1e6, time.monotonic() - started))
            return dest
        if state in ("failed", "cancelled", "expired"):
            raise ProviderError("The AI clip job %s: %s"
                                % (state, (status or {}).get("error") or "unknown error"))
        time.sleep(max(1.0, min(60.0, float(poll_seconds))))
