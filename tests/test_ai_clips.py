"""Offline tests for the AI clip generation (OpenRouter async video API)."""
import json

import pytest

from voiceover_studio.ai_clips import (CLIP_PROMPT_SYSTEM, VIDEO_MODELS, generate_video_clip,
                                       plan_clip_prompt, video_catalog)
from voiceover_studio.errors import ProviderError

MP4_BYTES = b"\x00\x00\x00\x18ftypisom" + b"fake-video" * 20

JOB = {"id": "job-abc123", "polling_url": "https://openrouter.ai/api/v1/videos/job-abc123",
       "status": "pending"}


def chat_client(fake, content):
    from voiceover_studio.ai_video import OpenRouterClient
    fake.add("POST", "https://openrouter.ai/api/v1/chat/completions",
             (200, {"choices": [{"message": {"content": content}}]}))
    return OpenRouterClient(api_key="sk-test", transport=fake)


def video_client(fake, poll_responses, content=MP4_BYTES):
    """An OpenRouterClient whose /videos POST returns a job and whose poll states are scripted."""
    from voiceover_studio.ai_video import OpenRouterClient
    fake.add("POST", "https://openrouter.ai/api/v1/videos", (202, JOB))
    # the content route must come FIRST: prefixes are matched in insertion order
    fake.add("GET", "https://openrouter.ai/api/v1/videos/job-abc123/content", (200, content))
    fake.add("GET", "https://openrouter.ai/api/v1/videos/job-abc123", *poll_responses)
    return OpenRouterClient(api_key="sk-test", transport=fake)


def poll(status, **extra):
    data = {"id": "job-abc123", "status": status}
    data.update(extra)
    return data


def test_video_models_catalog_shape():
    """The default list only contains real OpenRouter video model slugs (videá format)."""
    assert all(model.count("/") == 1 for model in VIDEO_MODELS) and VIDEO_MODELS


def test_plan_clip_prompt_uses_the_cinematic_system(fake):
    client = chat_client(fake, "  A locked shot of wheat swaying at sunset.  ")
    prompt = plan_clip_prompt(client, "google/veo-3.1-lite", "campo di grano",
                              "le spighe ondeggiano", extra="golden light")
    assert prompt == "A locked shot of wheat swaying at sunset."
    body = json.loads(fake.calls[0]["body"])
    assert body["messages"][0]["content"].startswith("You write prompts")


def test_generate_video_clip_submits_polls_and_downloads(fake, tmp_path, monkeypatch):
    monkeypatch.setattr("voiceover_studio.ai_clips.time.sleep", lambda s: None)
    client = video_client(fake, [(200, poll("pending")),
                                 (200, poll("in_progress")),
                                 (200, poll("completed",
                                            unsigned_urls=["https://openrouter.ai/api/v1/videos/job-abc123/content"]))])
    lines = []
    dest = generate_video_clip(client, "google/veo-3.1-lite", "wheat swaying at sunset",
                               tmp_path / "clip", duration=5, aspect_ratio="9:16",
                               poll_seconds=1.0, timeout=60, progress=lines.append)
    assert dest == tmp_path / "clip.mp4"
    assert dest.read_bytes() == MP4_BYTES
    submit = json.loads(fake.calls[0]["body"])
    assert submit == {"model": "google/veo-3.1-lite", "prompt": "wheat swaying at sunset",
                      "duration": 5, "resolution": "720p", "aspect_ratio": "9:16",
                      "generate_audio": False}
    # the content download carried the API key in the Authorization header
    content_call = fake.calls[-1]
    assert content_call["headers"]["Authorization"] == "Bearer sk-test"
    assert any("pending" in line for line in lines)
    assert any("in_progress" in line for line in lines)
    assert any("Downloaded" in line for line in lines)


def test_generate_video_clip_reports_failed_jobs(fake, tmp_path, monkeypatch):
    monkeypatch.setattr("voiceover_studio.ai_clips.time.sleep", lambda s: None)
    client = video_client(fake, [(200, poll("failed", error="Content policy violation"))])
    with pytest.raises(ProviderError, match="Content policy violation"):
        generate_video_clip(client, "google/veo-3.1-lite", "sparks", tmp_path / "clip",
                            poll_seconds=1.0, timeout=60)


def test_generate_video_clip_times_out(fake, tmp_path, monkeypatch):
    monkeypatch.setattr("voiceover_studio.ai_clips.time.sleep", lambda s: None)
    client = video_client(fake, [(200, poll("pending"))] * 50)
    with pytest.raises(ProviderError, match="did not finish in 60 s"):
        generate_video_clip(client, "google/veo-3.1-lite", "sparks", tmp_path / "clip",
                            poll_seconds=1.0, timeout=60)
