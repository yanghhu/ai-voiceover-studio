"""Offline tests for the Lottie motion-design module (AI writes the animation JSON)."""
import json
from pathlib import Path

import pytest

pytest.importorskip("lottie")

from voiceover_studio.errors import ConfigError


def chat_client(fake, content):
    from voiceover_studio.ai_video import OpenRouterClient
    fake.add("POST", "https://openrouter.ai/api/v1/chat/completions",
             (200, {"choices": [{"message": {"content": content}}]}))
    return OpenRouterClient(api_key="test-key", transport=fake)


def lottie_answer(name="A bouncing dot", layers=1):
    from lottie import objects
    V = objects.NVector
    an = objects.animation.Animation(60)
    for _ in range(layers):
        layer = objects.ShapeLayer()
        an.add_layer(layer)
        ell = layer.add_shape(objects.Ellipse(objects.Color([255, 120, 0]), V([60, 60])))
        ell.position.value = V([256, 256])
        pos = layer.transform.position
        pos.add_keyframe(0, V([256, 256]))
        pos.add_keyframe(30, V([256, 150]))
        pos.add_keyframe(60, V([256, 256]))  # seamless loop
    return json.dumps(an.to_dict())


def test_generate_lottie_normalizes_the_timeline(fake, tmp_path):
    from voiceover_studio.lottie_motion import generate_lottie
    data = generate_lottie(chat_client(fake, lottie_answer()), "m", "a bouncing dot",
                           tmp_path / "motion", width=960, height=540, n_frames=60)
    # timeline is forced: deterministic size and frame count, seamless loop
    data = json.loads((tmp_path / "motion.json").read_text(encoding="utf-8"))
    assert data["fr"] == 30 and data["ip"] == 0 and data["op"] == 60
    assert data["w"] == 960 and data["h"] == 540
    assert len(data["layers"]) == 1


def test_generate_lottie_parses_fenced_json(fake, tmp_path):
    from voiceover_studio.lottie_motion import generate_lottie
    fenced = "```json\n%s\n```" % lottie_answer(layers=2)
    generate_lottie(chat_client(fake, fenced), "m", "a bouncing dot", tmp_path / "motion")
    data = json.loads((tmp_path / "motion.json").read_text(encoding="utf-8"))
    assert len(data["layers"]) == 2


def test_generate_lottie_needs_a_prompt(fake, tmp_path):
    from voiceover_studio.lottie_motion import generate_lottie
    with pytest.raises(ValueError):
        generate_lottie(chat_client(fake, lottie_answer()), "m", "  ", tmp_path / "motion")


def test_generate_lottie_rejects_layerless_json(fake, tmp_path):
    from voiceover_studio.lottie_motion import generate_lottie
    with pytest.raises(ConfigError, match="no layers"):
        generate_lottie(chat_client(fake, '{"fr": 30, "op": 60}'), "m", "dot",
                        tmp_path / "motion")


def test_generate_lottie_rejects_plain_prose(fake, tmp_path):
    from voiceover_studio.lottie_motion import generate_lottie
    with pytest.raises(Exception):
        generate_lottie(chat_client(fake, "Here is your animation!"), "m", "dot",
                        tmp_path / "motion")


def test_lottie_to_gif_html_preview_always_works(fake, tmp_path):
    from voiceover_studio.lottie_motion import generate_lottie, lottie_to_gif
    generate_lottie(chat_client(fake, lottie_answer()), "m", "dot", tmp_path / "motion")
    gif, html = lottie_to_gif(tmp_path / "motion.json", tmp_path / "rendering" / "loop")
    assert html and Path(html).is_file()
    assert "lottie" in Path(html).read_text(encoding="utf-8").lower()
    if gif is None:
        pytest.skip("cairo-based GIF renderer not installed in this environment")


def test_lottie_to_gif_loop_is_seamless(fake, tmp_path):
    from voiceover_studio.lottie_motion import generate_lottie, lottie_to_gif
    generate_lottie(chat_client(fake, lottie_answer()), "m", "dot", tmp_path / "motion")
    gif, _html = lottie_to_gif(tmp_path / "motion.json", tmp_path / "rendering" / "loop",
                               loop_seconds=1.0)
    if gif is None:
        pytest.skip("cairo-based GIF renderer not installed in this environment")
    from PIL import Image
    with Image.open(gif) as im:
        assert im.info.get("loop", 0) == 0  # loops forever
        assert im.size == (960, 540)


class _RecordingClient:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def chat(self, model, messages):
        self.calls.append(messages)
        return self.content


def test_generate_lottie_cartoon_uses_the_character_prompt(tmp_path):
    from voiceover_studio.lottie_motion import generate_lottie
    client = _RecordingClient(lottie_answer())
    generate_lottie(client, "m", "a small fox walking in place", tmp_path / "motion",
                    kind="Cartoon character")
    system = client.calls[0][0]["content"]
    assert "walk cycle" in system.lower()
    assert "blink" in system.lower()
    assert "squash" in system.lower()


def test_generate_lottie_default_is_infographic(tmp_path):
    from voiceover_studio.lottie_motion import LOTTIE_FRAMERATE, LOTTIE_SYSTEM, generate_lottie
    client = _RecordingClient(lottie_answer())
    generate_lottie(client, "m", "a bouncing dot", tmp_path / "motion")
    system = client.calls[0][0]["content"]
    assert "walk cycle" not in system.lower()
    assert LOTTIE_SYSTEM % {"fr": LOTTIE_FRAMERATE, "op": 60, "w": 960, "h": 540} == system
