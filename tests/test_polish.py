"""Offline tests for the AI review & polish loop (vision answers faked, ffmpeg optional)."""
import shutil
from pathlib import Path

import pytest

from voiceover_studio.errors import ConfigError
from voiceover_studio.polish import (apply_color_fix, parse_script_blocks, polish_video,
                                     restyle_shot_card, review_video, swap_shot_media)

REVIEW_LOW = ('{"score": 5, "issues": [{"frame": 1, "label": "unreadable", '
              '"detail": "overlay text too small"}, {"frame": 2, "label": "dark", '
              '"detail": "underexposed"}]}')
REVIEW_GOOD = '{"score": 9, "issues": []}'
REVIEW_MISMATCH = ('{"score": 4, "issues": [{"frame": 1, "label": "mismatch", '
                   '"detail": "city footage for a vineyard story"}]}')


def _client(fake, *responses):
    scripted = [(200, {"choices": [{"message": {"content": response}}]})
                for response in responses]
    fake.add("POST", "https://openrouter.ai/api/v1/chat/completions", *scripted)
    from voiceover_studio.ai_video import OpenRouterClient
    return OpenRouterClient(api_key="test-key", transport=fake)


def _fake_frames(tmp_path, n=2):
    from PIL import Image
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    frames = []
    for i in range(1, n + 1):
        path = tmp_path / ("frame_%02d.jpg" % i)
        Image.new("RGB", (64, 36), (i * 40, 60, 90)).save(path)
        frames.append(path)
    return frames


def test_parse_script_blocks(tmp_path):
    script = ("# T\n\n![](/a.mp4)\n\n![](/card.png){overlay}\n\nTesto della scena.\n\n"
              "![](/b.mp4)\n\nAltro testo.")
    blocks = parse_script_blocks(script)
    assert [b["media"] for b in blocks] == ["/a.mp4", "/card.png", "/b.mp4"]
    assert blocks[1]["overlay"] is True
    assert blocks[0]["text"] == "Testo della scena."
    assert blocks[2]["text"] == "Altro testo."


def test_review_video_parses_score_and_issues(tmp_path, fake):
    client = _client(fake, REVIEW_LOW)
    report = review_video(client, "m", tmp_path / "x.mp4", "Testo.", frames=_fake_frames(tmp_path))
    assert report["score"] == 5
    assert [i["label"] for i in report["issues"]] == ["unreadable", "dark"]
    body = fake.calls[-1]["body"].decode()
    assert "image_url" in body and "Frame 1:" in body


def test_swap_shot_media_picks_best_match(tmp_path):
    clip_b = tmp_path / "b.mp4"
    clip_b.write_bytes(b"x")
    script = "![](/a.mp4)\n\nVigne al tramonto sulle colline."
    catalog = [{"clip_path": str(clip_b), "tags": ["citta", "traffico"],
                "description": "city traffic"},
               {"clip_path": "/missing.mp4", "tags": ["vigne", "colline", "tramonto"],
                "description": "vineyard hills at sunset"}]
    new_script, description = swap_shot_media(script, 1, catalog)
    assert description is None  # the matching entry has no file on disk


def test_swap_shot_media_replaces_the_path(tmp_path):
    clip_b = tmp_path / "b.mp4"
    clip_b.write_bytes(b"x")
    script = "![](/a.mp4)\n\nVigne al tramonto sulle colline."
    catalog = [{"clip_path": str(clip_b), "tags": ["vigne", "colline", "tramonto"],
                "description": "vineyard hills at sunset"},
               {"clip_path": "/c.mp4", "tags": ["citta"], "description": "city"}]
    new_script, description = swap_shot_media(script, 1, catalog)
    assert str(clip_b) in new_script and "/a.mp4" not in new_script
    assert "vineyard hills" in description


def test_restyle_shot_card_redraws_with_new_style(tmp_path):
    from PIL import Image
    card = tmp_path / "old_card.png"
    Image.new("RGBA", (32, 18), (0, 0, 0, 0)).save(card)
    script = "![](/a.mp4)\n\n![](%s){overlay}\n\nTesto." % card
    new_script, path = restyle_shot_card(script, 1, {"title": "T", "bullets": [], "icons": []},
                                         tmp_path, "Chiaro")
    assert path and path.endswith(".png") and Path(path).is_file()
    assert str(path) in new_script and str(card) not in new_script


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_apply_color_fix_reencodes(tmp_path):
    import subprocess
    video = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x180:rate=10",
                    "-pix_fmt", "yuv420p", str(video)], capture_output=True)
    out = apply_color_fix(video, tmp_path, ["dark", "flat"])
    assert out.is_file() and out != video and out.stat().st_size > 0


def test_polish_loop_restores_and_stops_when_good(tmp_path, fake, monkeypatch):
    import voiceover_studio.polish as polish_mod
    monkeypatch.setattr(polish_mod, "extract_frames",
                        lambda video, dest, n=6: _fake_frames(Path(dest), n))
    monkeypatch.setattr(polish_mod, "apply_color_fix",
                        lambda video, workdir, labels: Path(str(video) + ".fixed.mp4"))
    client = _client(fake, REVIEW_LOW, REVIEW_GOOD)
    card = tmp_path / "card.png"
    from PIL import Image
    Image.new("RGBA", (32, 18), (0, 0, 0, 0)).save(card)
    script = "![](/a.mp4)\n\n![](%s){overlay}\n\nTesto della scena uno." % card
    log = []
    rerenders = []

    def rerender(script_text):
        rerenders.append(script_text)
        return str(tmp_path / "preview_2.mp4")

    result = polish_video(client, "m", tmp_path / "preview.mp4", script, tmp_path,
                          overlay_plan=[{"scene": 1, "title": "T", "bullets": [], "icons": []}],
                          rerender=rerender, progress=log.append, n_frames=2)
    assert result["rounds"] == 2 and result["score"] == 9
    assert any("redrawn" in f for f in result["fixes"])
    assert any("color correction" in f for f in result["fixes"])
    assert len(rerenders) == 1 and result["video"].endswith("preview_2.mp4")
    assert result["script"] != script


def test_polish_loop_swaps_mismatched_clip(tmp_path, fake, monkeypatch):
    import voiceover_studio.polish as polish_mod
    monkeypatch.setattr(polish_mod, "extract_frames",
                        lambda video, dest, n=6: _fake_frames(Path(dest), n))
    client = _client(fake, REVIEW_MISMATCH)
    clip_b = tmp_path / "b.mp4"
    clip_b.write_bytes(b"x")
    script = "![](/a.mp4)\n\nVigne al tramonto sulle colline."
    catalog = [{"clip_path": str(clip_b), "tags": ["vigne", "colline", "tramonto"],
                "description": "vineyard hills at sunset"}]
    result = polish_video(client, "m", tmp_path / "preview.mp4", script, tmp_path,
                          catalog=catalog, rerender=None, n_frames=2)
    assert any("replaced" in f for f in result["fixes"])
    assert str(clip_b) in result["script"]


def test_polish_needs_frames(tmp_path, fake, monkeypatch):
    import voiceover_studio.polish as polish_mod
    monkeypatch.setattr(polish_mod, "extract_frames", lambda *a, **k: [])
    client = _client(fake, REVIEW_GOOD)
    with pytest.raises(ConfigError):
        review_video(client, "m", tmp_path / "x.mp4", "t.", frames=[])
