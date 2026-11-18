"""Offline tests for the AI video builder (OpenRouter + keyless assets, all mocked)."""
import base64
import json

import pytest

from voiceover_studio.providers.miragea import HttpResponse

from voiceover_studio.ai_video import OpenRouterClient, Scene, build_script, find_asset, \
    generate_asset, plan_scenes, verify_asset
from voiceover_studio.errors import ConfigError, ProviderError

PLAN_JSON = '[{"narration": "Pyramids rise over the desert.", "query": "egypt pyramids"},' \
            '{"narration": "Inside, workers move giant blocks.", "query": "ancient workers"}]'


def client_with(fake, extra_routes=()):
    fake.add("POST", "https://openrouter.ai/api/v1/chat/completions",
             (200, {"choices": [{"message": {"content": PLAN_JSON}}]}))
    for route in extra_routes:
        fake.add(*route)
    return OpenRouterClient(api_key="test-key", transport=fake)


def chat_payload(content):
    return (200, {"choices": [{"message": {"content": content}}]})


def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        OpenRouterClient(transport=lambda *a: None)


def test_plan_scenes_parses_model_json(fake):
    scenes = plan_scenes(client_with(fake), "A short story about pyramids", duration=30.0)
    assert len(scenes) == 2
    assert scenes[0].narration.startswith("Pyramids")
    assert scenes[1].query == "ancient workers"
    assert [s.index for s in scenes] == [0, 1]


def test_plan_scenes_requires_prompt(fake):
    with pytest.raises(ValueError):
        plan_scenes(client_with(fake), "   ")


def test_find_asset_uses_openverse_then_downloads(fake, tmp_path):
    listing = (200, {"results": [{"url": "https://images.example.org/photo.jpg"}]})
    fake.add("GET", "https://commons.wikimedia.org/w/api.php", (200, {}))
    fake.add("GET", "https://api.openverse.org/v1/images/", listing)
    fake.add("GET", "https://images.example.org/photo.jpg", (200, b"jpeg-bytes"))
    path, source = find_asset("pyramids", "landscape", tmp_path, 0, transport=fake)
    assert source == "openverse image"
    assert path.read_bytes() == b"jpeg-bytes"


def test_find_asset_falls_back_to_generation(fake, tmp_path):
    fake.add("GET", "https://commons.wikimedia.org/w/api.php", (200, {}))
    fake.add("GET", "https://api.openverse.org/v1/images/", (200, {"results": []}))
    fake.add("GET", "https://image.pollinations.ai/prompt/", (200, b"generated-jpeg"))
    path, source = find_asset("desert dunes", "portrait", tmp_path, 3, transport=fake)
    assert source == "generated (pollinations)"
    assert path.read_bytes() == b"generated-jpeg"


def test_generate_asset_direct(fake, tmp_path):
    fake.add("GET", "https://image.pollinations.ai/prompt/", (200, b"gen"))
    path, source = generate_asset("space nebula", "landscape", tmp_path, 1, transport=fake)
    assert source == "generated (pollinations)" and path.is_file()


def test_find_asset_raises_when_everything_fails(fake, tmp_path):
    fake.add("GET", "https://commons.wikimedia.org/w/api.php", (200, {}))
    fake.add("GET", "https://api.openverse.org/v1/images/", (200, {"results": []}))
    fake.add("GET", "https://image.pollinations.ai/prompt/", (500, {"error": "down"}))
    with pytest.raises(ProviderError):
        find_asset("ocean", "landscape", tmp_path, 2, transport=fake)


def test_verify_asset_parses_verdict(fake, tmp_path):
    image = tmp_path / "scene.jpg"
    image.write_bytes(b"\xff\xd8fakejpeg")
    scene = Scene(0, "text", "egypt pyramids", asset_path=str(image))
    client = OpenRouterClient(api_key="k", transport=fake)
    fake.add("POST", "https://openrouter.ai/api/v1/chat/completions",
             chat_payload('{"match": false, "reason": "shows a city"}'))
    match, reason = verify_asset(client, scene, "google/gemini-2.0-flash-001")
    assert match is False and reason == "shows a city"
    sent = fake.calls[-1]["body"].decode()
    assert base64.b64encode(b"\xff\xd8fakejpeg").decode() in sent


def test_verify_asset_skips_video_without_ffmpeg(fake, tmp_path, monkeypatch):
    monkeypatch.delenv("FFMPEG_BINARY", raising=False)
    video = tmp_path / "scene.mp4"
    video.write_bytes(b"not-a-real-video")
    scene = Scene(0, "text", "query", asset_path=str(video))
    match, reason = verify_asset(OpenRouterClient(api_key="k", transport=fake), scene, "m")
    assert match is True and "ffmpeg" in reason


def test_verify_failure_does_not_break_the_plan(fake, tmp_path, monkeypatch):
    from voiceover_studio.ai_video import plan_and_fetch
    image = tmp_path / "scene.jpg"
    image.write_bytes(b"\xff\xd8fakejpeg")
    fake.add("GET", "https://commons.wikimedia.org/w/api.php", (200, {}))
    fake.add("GET", "https://api.openverse.org/v1/images/", (200, {"results": []}))
    fake.add("GET", "https://image.pollinations.ai/prompt/", (200, b"img"))
    def flaky(method, url, headers, body, timeout):
        if b"image_url" in (body or b""):
            return HttpResponse(404, {}, b'{"error": "model gone"}')
        payload = json.dumps({"choices": [{"message": {"content": PLAN_JSON}}]}).encode()
        return HttpResponse(200, {}, payload)

    client = OpenRouterClient(api_key="k", transport=flaky)
    scenes = plan_and_fetch(client, "pyramids", tmp_path, verify=True,
                            vision_model="google/gemini-2.0-flash-001", transport=fake)
    assert len(scenes) == 2
    assert scenes[0].verified is None and "skipped" in scenes[0].reason


def test_generate_asset_retries_with_new_seed(fake, tmp_path):
    fake.add("GET", "https://image.pollinations.ai/prompt/",
             (503, {"error": "overloaded"}), (200, b"gen"))
    path, source = generate_asset("space nebula", "landscape", tmp_path, 1, transport=fake)
    assert source == "generated (pollinations)" and path.read_bytes() == b"gen"
    poll_calls = [c for c in fake.calls if c["url"].startswith("https://image.pollinations.ai")]
    assert len(poll_calls) == 2
    assert poll_calls[0]["url"] != poll_calls[1]["url"]


def test_generate_asset_reports_unavailable_service(fake, tmp_path):
    fake.add("GET", "https://image.pollinations.ai/prompt/", (402, {"error": "payment"}))
    with pytest.raises(ProviderError) as excinfo:
        generate_asset("ocean", "landscape", tmp_path, 0, transport=fake)
    assert "rate-limited" in str(excinfo.value)
    poll_calls = [c for c in fake.calls if c["url"].startswith("https://image.pollinations.ai")]
    assert len(poll_calls) == 3


def test_find_asset_broadens_the_query(fake, tmp_path):
    fake.add("GET", "https://commons.wikimedia.org/w/api.php", (200, {}))
    fake.add("GET", "https://api.openverse.org/v1/images/",
             (200, {"results": []}), (200, {"results": []}),
             (200, {"results": [{"url": "https://images.example.org/hills.jpg"}]}))
    fake.add("GET", "https://images.example.org/hills.jpg", (200, b"jpeg"))
    path, source = find_asset("aerial vineyard sunset hills italy", "landscape",
                              tmp_path, 0, transport=fake)
    assert source == "openverse image"
    openverse_queries = [c["url"] for c in fake.calls
                         if c["url"].startswith("https://api.openverse.org")]
    assert len(openverse_queries) == 3
    assert "aerial+vineyard+sunset+hills+italy" in openverse_queries[0]
    assert "aerial+vineyard+sunset" in openverse_queries[2]


def test_plan_continues_when_a_scene_has_no_asset(fake, tmp_path):
    from voiceover_studio.ai_video import plan_and_fetch
    fake.add("GET", "https://commons.wikimedia.org/w/api.php", (200, {}))
    fake.add("GET", "https://api.openverse.org/v1/images/", (200, {"results": []}))
    fake.add("GET", "https://image.pollinations.ai/prompt/",
             (402, {"error": "payment"}), (402, {"error": "payment"}),
             (402, {"error": "payment"}), (200, b"img"))
    scenes = plan_and_fetch(client_with(fake), "pyramids", tmp_path, verify=False,
                            transport=fake)
    assert len(scenes) == 2
    assert scenes[0].asset_path is None and scenes[0].source == "none"
    assert "no asset" in scenes[0].reason
    assert scenes[1].asset_path is not None and scenes[1].source == "generated (pollinations)"
    text = build_script(scenes)
    assert "scene_00" not in text
    assert "scene_01.jpg" in text
    assert scenes[1].narration in text


def test_build_script_includes_assets_and_narration():
    scenes = [Scene(0, "First line.", "q1", asset_path="assets/scene_00.jpg"),
              Scene(1, "Second line.", "q2")]
    text = build_script(scenes, title="Pyramids")
    assert text.startswith("# Pyramids")
    assert "![](assets/scene_00.jpg)" in text
    assert "First line." in text and "Second line." in text


def test_best_value_models_ranks_by_price(fake):
    from voiceover_studio.ai_video import best_value_models
    fake.add("GET", "https://openrouter.ai/api/v1/models", (200, {"data": [
        {"id": "expensive/model", "context_length": 128000,
         "pricing": {"prompt": "0.00001", "completion": "0.00003"}},
        {"id": "free/fast-model", "context_length": 32000,
         "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "cheap/long-model", "context_length": 200000,
         "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
        {"id": "text/embed-model", "context_length": 8192,
         "pricing": {"prompt": "0", "completion": "0"}},
    ]}))
    ranked = best_value_models(OpenRouterClient(api_key="k", transport=fake))
    assert ranked[0] == "free/fast-model"
    assert "text/embed-model" not in ranked
    assert ranked.index("cheap/long-model") < ranked.index("expensive/model")


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-data"
WEBP_BYTES = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"x" * 12


def image_payload(url):
    return (200, {"choices": [{"message": {"images": [{"image_url": {"url": url}}]}}]})


def image_client(fake):
    return OpenRouterClient(api_key="test-key", transport=fake)


def test_generate_illustration_writes_data_url_png(fake, tmp_path):
    from voiceover_studio.ai_video import generate_illustration
    data_url = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()
    fake.add("POST", "https://openrouter.ai/api/v1/chat/completions", image_payload(data_url))
    path = generate_illustration(image_client(fake), "compost bins from pallets",
                                 tmp_path / "illu", style="Infografica illustrata")
    assert path.name == "illu.png"
    assert path.read_bytes() == PNG_BYTES
    body = json.loads(fake.calls[-1]["body"])
    assert body["modalities"] == ["image"]
    assert body["image_config"] == {"aspect_ratio": "16:9"}
    assert body["messages"][0]["content"].startswith("Illustrazione didattica")
    assert "compost bins" in body["messages"][0]["content"]


def test_generate_illustration_downloads_http_webp(fake, tmp_path):
    from voiceover_studio.ai_video import generate_illustration
    fake.add("POST", "https://openrouter.ai/api/v1/chat/completions",
             image_payload("https://img.example.org/pic"))
    fake.add("GET", "https://img.example.org/pic", (200, WEBP_BYTES))
    path = generate_illustration(image_client(fake), "vineyard hills", tmp_path / "illu")
    assert path.name == "illu.webp"
    assert path.read_bytes() == WEBP_BYTES


def test_generate_illustration_retries_without_aspect_ratio(fake, tmp_path):
    from voiceover_studio.ai_video import generate_illustration
    data_url = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()
    fake.add("POST", "https://openrouter.ai/api/v1/chat/completions",
             (400, {"error": {"message": "image_config not supported"}}),
             image_payload(data_url))
    path = generate_illustration(image_client(fake), "old map", tmp_path / "illu")
    assert path.suffix == ".png"
    bodies = [json.loads(call["body"]) for call in fake.calls if call["method"] == "POST"]
    assert "image_config" in bodies[0] and "image_config" not in bodies[1]


def test_generate_illustration_rejects_svg(fake, tmp_path):
    from voiceover_studio.ai_video import generate_illustration
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
    data_url = "data:image/svg+xml;base64," + base64.b64encode(svg).decode()
    fake.add("POST", "https://openrouter.ai/api/v1/chat/completions", image_payload(data_url))
    with pytest.raises(ProviderError):
        generate_illustration(image_client(fake), "timeline", tmp_path / "illu")


def test_error_messages_include_actionable_hint(fake):
    from voiceover_studio.ai_video import _status_hint
    assert "openrouter.ai/keys" in _status_hint(401)
    assert "credits" in _status_hint(402)
    assert "no longer served" in _status_hint(404)
    assert "Rate limited" in _status_hint(429)
    assert _status_hint(500) == ""
    fake.add("POST", "https://openrouter.ai/api/v1/chat/completions",
             (404, {"error": {"message": "model gone"}}))
    with pytest.raises(ProviderError) as excinfo:
        image_client(fake).chat("gone/model", [{"role": "user", "content": "hi"}])
    assert "no longer served" in str(excinfo.value)


def test_best_value_models_skips_pseudo_models_and_unpriced(fake):
    from voiceover_studio.ai_video import best_value_models
    fake.add("GET", "https://openrouter.ai/api/v1/models", (200, {"data": [
        {"id": "openrouter/auto", "context_length": 1000000,
         "pricing": {}},
        {"id": "mystery/model", "context_length": 64000,
         "pricing": {}},
        {"id": "free/fast-model", "context_length": 32000,
         "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "cheap/model", "context_length": 200000,
         "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
    ]}))
    ranked = best_value_models(OpenRouterClient(api_key="k", transport=fake))
    assert ranked == ["free/fast-model", "cheap/model"]
