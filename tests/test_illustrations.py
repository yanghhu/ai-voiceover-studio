"""Offline tests for the AI-illustration slides module (no clips, only animated GIFs)."""
import base64
import json
from pathlib import Path

import pytest

pytest.importorskip("PIL")

from PIL import Image

from voiceover_studio.illustrations import (ASPECT_SIZES, MOTIONS, animate_still,
                                            build_slide_script, plan_image_prompts)
from voiceover_studio.errors import ConfigError


def chat_client(fake, content):
    from voiceover_studio.ai_video import OpenRouterClient
    fake.add("POST", "https://openrouter.ai/api/v1/chat/completions",
             (200, {"choices": [{"message": {"content": content}}]}))
    return OpenRouterClient(api_key="test-key", transport=fake)


NARRATION = "Colline Infinite al tramonto.\n\nNelle cantine il tempo si ferma."
IMAGES_JSON = json.dumps(["Aerial green hills at sunset",
                          "Old barrels resting in a dark cellar"])


def test_plan_image_prompts_one_per_paragraph(fake):
    prompts = plan_image_prompts(chat_client(fake, IMAGES_JSON), "m", NARRATION,
                                 prompt="enoturismo")
    assert prompts == ["Aerial green hills at sunset", "Old barrels resting in a dark cellar"]


def test_plan_image_prompts_pads_missing_paragraphs(fake):
    short = json.dumps(["Only the first prompt"])
    prompts = plan_image_prompts(chat_client(fake, short), "m", NARRATION)
    assert len(prompts) == 2
    assert prompts[1].startswith("Nelle cantine il tempo si ferma")


def test_plan_image_prompts_needs_narration(fake):
    with pytest.raises(ValueError):
        plan_image_prompts(chat_client(fake, IMAGES_JSON), "m", "# solo un titolo")


def _gradient(path, width=800, height=450):
    im = Image.new("RGB", (width, height))
    px = im.load()
    for y in range(height):
        for x in range(0, width, 8):
            px[x, y] = (x * 255 // width, y * 255 // height, 128)
    im.save(path)


def test_animate_still_makes_a_looping_gif(tmp_path):
    src = tmp_path / "still_01.png"
    _gradient(src)
    dest = animate_still(src, tmp_path / "slide_01", size=(640, 360), frames=10,
                         loop_seconds=1.0)
    assert dest.name == "slide_01.gif"
    with Image.open(dest) as gif:
        assert getattr(gif, "n_frames", 1) > 1
        assert getattr(gif, "info", {}).get("loop", 0) == 0  # loops forever


def test_animate_still_bakes_the_overlay_card(tmp_path):
    src = tmp_path / "still_01.png"
    _gradient(src)
    card = tmp_path / "card.png"
    Image.new("RGBA", (1600, 900), (10, 10, 10, 255)).save(card)
    plain = animate_still(src, tmp_path / "plain", size=(640, 360), frames=6)
    over = animate_still(src, tmp_path / "over", overlay=card, size=(640, 360), frames=6)
    assert plain.read_bytes() != over.read_bytes()  # the card is baked into the frames
    assert over.name == "over.gif" and MOTIONS and ASPECT_SIZES["16:9"] == (960, 540)


def test_animate_still_all_motions(tmp_path):
    src = tmp_path / "still.png"
    _gradient(src, 640, 360)
    for motion in MOTIONS:
        dest = animate_still(src, tmp_path / ("m_" + motion.replace(" ", "_")),
                             size=(320, 180), frames=4)
        assert dest.is_file()


def test_build_slide_script_keeps_the_narration_verbatim(tmp_path):
    slides = [{"scene": 1, "gif": str(tmp_path / "slide_01.gif")},
              {"scene": 2, "gif": str(tmp_path / "slide_02.gif")}]
    script = build_slide_script(slides, NARRATION, title="Enoturismo")
    assert "Colline Infinite al tramonto." in script
    assert "Nelle cantine il tempo si ferma." in script
    assert script.count("![](") == 2
    assert str(tmp_path / "slide_01.gif") in script
    assert script.startswith("# Enoturismo\n\n![](")


def test_build_slide_script_without_gif_is_text_only(tmp_path):
    script = build_slide_script([], NARRATION)
    assert "![](" not in script
    assert "Colline Infinite al tramonto." in script


def test_generate_stills_continues_after_failure(fake, tmp_path, monkeypatch):
    import voiceover_studio.ai_video as ai_video
    import voiceover_studio.illustrations as ill
    from voiceover_studio.ai_video import OpenRouterClient

    calls = []

    def fake_generate(client, prompt, dest_base, **kwargs):
        calls.append(prompt)
        if prompt == "bad":
            raise RuntimeError("model exploded")
        dest = Path(str(dest_base) + ".png")
        dest.write_bytes(b"\x89PNG\r\n\x1a\n")
        return dest

    monkeypatch.setattr(ai_video, "generate_illustration", fake_generate)
    logs = []
    stills, errors = ill.generate_stills(
        OpenRouterClient(api_key="k", transport=fake), "m",
        ["good", "bad", "good too"], tmp_path, progress=logs.append)
    assert len(stills) == 3 and stills[0] and stills[2]
    assert stills[1] is None
    assert "Illustration 2 failed" in errors[0]
    assert logs and "1/3" in logs[0]


def _needs_ffmpeg():
    from voiceover_studio.audio import ffmpeg_path
    import pytest as _pytest
    return _pytest.mark.skipif(not ffmpeg_path(), reason="ffmpeg not installed")


@_needs_ffmpeg()
def test_gif_shots_render_into_a_video(tmp_path):
    """Integration: animated GIF slides work as shots of the real render engine."""
    from voiceover_studio.studio import Studio
    from voiceover_studio.video import render_video

    im = Image.new("RGB", (960, 540))
    px = im.load()
    for y in range(540):
        for x in range(0, 960, 8):
            px[x, y] = (x * 255 // 960, y * 255 // 540, 128)
    grad = tmp_path / "still.png"
    im.save(grad)
    gif1 = animate_still(grad, tmp_path / "slide_01", frames=8)
    gif2 = animate_still(grad, tmp_path / "slide_02", frames=8, motion="pan")
    script = tmp_path / "script.md"
    script.write_text("# Compost\n\n![](%s)\n\nI pallet diventano compost in pochi mesi.\n\n"
                      "![](%s)\n\nIl calore trasforma i rifiuti in terra." % (gif1, gif2),
                      encoding="utf-8")
    out = tmp_path / "final.mp4"
    render_video(Studio(provider="dummy"), "", script, out, size=(320, 180))
    assert out.is_file() and out.stat().st_size > 10000


def test_plan_motion_frames_assembles_the_cycle(fake):
    from voiceover_studio.illustrations import plan_motion_frames
    cycle = json.dumps(["Wheat field at sunset, ears leaning left",
                        "Wheat field at sunset, ears upright",
                        "Wheat field at sunset, ears leaning right",
                        "Wheat field at sunset, ears upright again"])
    prompts = plan_motion_frames(chat_client(fake, cycle), "m",
                                 "A wheat field at sunset", "the ears sway in the wind", 4)
    assert len(prompts) == 4
    assert all(p.startswith("Wheat field at sunset") for p in prompts)


def test_plan_motion_frames_needs_a_scene(fake):
    from voiceover_studio.illustrations import plan_motion_frames
    with pytest.raises(ValueError):
        plan_motion_frames(chat_client(fake, "[]"), "m", "  ", "sway")


def test_build_gif_pingpong_returns_to_the_start(tmp_path):
    from voiceover_studio.illustrations import build_gif
    frames = []
    for i in range(4):
        im = Image.new("RGB", (320, 180), (i * 20, 120, 200))
        path = tmp_path / ("f_%d.png" % i)
        im.save(path)
        frames.append(path)
    dest = build_gif(frames, tmp_path / "loop", loop_seconds=1.0)
    with Image.open(dest) as gif:
        assert gif.n_frames == 2 * 4 - 2  # forward + backward, endpoints not doubled
    first = frames[0].read_bytes()
    assert dest.is_file()


def test_build_gif_blend_inserts_crossfades(tmp_path):
    from voiceover_studio.illustrations import build_gif
    frames = []
    for i in range(3):
        im = Image.new("RGB", (320, 180), (i * 40 + 10, 100, 30))
        path = tmp_path / ("b_%d.png" % i)
        im.save(path)
        frames.append(path)
    plain = build_gif(frames, tmp_path / "plain", loop_seconds=1.0)
    with Image.open(plain) as gif:
        plain_n = gif.n_frames
    blended = build_gif(frames, tmp_path / "soft", loop_seconds=1.0, blend=2)
    with Image.open(blended) as gif:
        assert gif.n_frames == plain_n + plain_n * 2
    assert plain.read_bytes() != blended.read_bytes()


def test_build_gif_needs_two_frames(tmp_path):
    from voiceover_studio.illustrations import build_gif
    single = tmp_path / "only.png"
    Image.new("RGB", (64, 64), (1, 2, 3)).save(single)
    with pytest.raises(ValueError):
        build_gif([single], tmp_path / "loop")


def test_animate_loop_is_a_seamless_cyclic_gif(tmp_path):
    """One image + procedural wind: the shift is sinusoidal in 2*pi, so it loops exactly."""
    from voiceover_studio.illustrations import animate_loop
    src = tmp_path / "still_01.png"
    _gradient(src, 640, 360)
    dest = animate_loop(src, tmp_path / "loop", size=(480, 270), motion="wind", intensity=1.0,
                        frames=10, loop_seconds=1.5)
    assert dest.name == "loop.gif"
    with Image.open(dest) as gif:
        # Pillow may drop duplicated resting frames (sin(0)=sin(pi) shifts of zero), but the
        # vast majority of the cycle must survive; the GIF must loop forever.
        assert gif.n_frames >= 8
        assert gif.info.get("loop", 0) == 0
        assert gif.size == (480, 270)


def test_animate_loop_supports_all_motions(tmp_path):
    from voiceover_studio.illustrations import LOOP_MOTIONS, animate_loop
    src = tmp_path / "still.png"
    _gradient(src, 640, 360)
    for motion in LOOP_MOTIONS:
        dest = animate_loop(src, tmp_path / ("l_" + motion), size=(320, 180), motion=motion,
                            frames=8)
        assert dest.is_file()
    unknown = animate_loop(src, tmp_path / "unknown", size=(320, 180), motion="nonsense",
                           frames=8)
    assert unknown.is_file()  # unknown presets fall back to "wind"


def test_animate_loop_bakes_the_overlay_card(tmp_path):
    from voiceover_studio.illustrations import animate_loop
    src = tmp_path / "still.png"
    _gradient(src, 640, 360)
    card = tmp_path / "card.png"
    Image.new("RGBA", (1600, 900), (10, 10, 10, 255)).save(card)
    plain = animate_loop(src, tmp_path / "plain", size=(480, 270), frames=8)
    over = animate_loop(src, tmp_path / "over", overlay=card, size=(480, 270), frames=8)
    assert plain.read_bytes() != over.read_bytes()
