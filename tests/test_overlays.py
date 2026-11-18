"""Offline tests for the locally drawn overlay cards."""
from pathlib import Path

import pytest

from voiceover_studio.errors import ConfigError
from voiceover_studio.overlays import CARD_STYLES, render_card

pytest.importorskip("PIL")

ITEM = {"title": "Enoturismo nelle Marche",
        "bullets": ["4 valli da esplorare", "12 strade del vino"],
        "icons": ["check", "freccia", "stella"]}


def test_render_card_creates_transparent_png(tmp_path):
    path = render_card(ITEM, tmp_path / "card", style="Scuro")
    from PIL import Image
    img = Image.open(path)
    assert img.size == (1600, 900) and img.mode == "RGBA"
    alpha = img.getchannel("A")
    assert alpha.getextrema()[0] < 250 and alpha.getextrema()[1] > 0


def test_render_card_styles(tmp_path):
    for style in CARD_STYLES:
        path = render_card(ITEM, tmp_path / ("card_%s" % style), style=style)
        assert path.is_file() and path.stat().st_size > 0


def test_render_card_unknown_style_falls_back(tmp_path):
    path = render_card(ITEM, tmp_path / "card", style="inventato")
    assert path.is_file()


def test_render_card_minimal_item(tmp_path):
    path = render_card({"title": "Solo titolo"}, tmp_path / "card_min")
    assert path.is_file()


def test_render_card_needs_pillow(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_pil(name, *args, **kwargs):
        if name.startswith("PIL"):
            raise ImportError("no PIL")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pil)
    with pytest.raises(ConfigError):
        render_card(ITEM, tmp_path / "card")
