import pytest

from voiceover_studio.music import BUILTIN, builtin_input, generator_expr, mix_filter, parse_music, rms_db


def test_parse_music():
    assert parse_music(None) == (None, False) and parse_music("none") == (None, False)
    assert parse_music("Ambient") == ("ambient", True)
    assert parse_music("song.mp3") == ("song.mp3", False)


def test_builtin_tracks_are_generated_expressions():
    for name in BUILTIN:
        expr = generator_expr(name)
        assert "sin(2*PI*" in expr and "exp(" in expr
        args = builtin_input(name, 12.0)
        assert args[:3] == ["-f", "lavfi", "-i"] and args[3].startswith("aevalsrc=") and "d=12.500" in args[3]
        assert "\\," in args[3]                                  # commas escaped for the lavfi graph
    with pytest.raises(ValueError):
        builtin_input("jazz", 3)


def test_mix_filter_ducks_under_voice():
    graph = mix_filter("1:a", "2:a", "out", duration=30, volume=0.3, builtin=True)
    assert "[mus][sc]sidechaincompress" in graph and "loudnorm" in graph and "aecho" in graph
    assert "afade=t=out:st=27.500" in graph and graph.endswith("[out]")
    flat = mix_filter("1:a", "2:a", "out", duration=30, duck=False)
    assert "sidechaincompress" not in flat and "aecho" not in flat


def test_rms_db():
    assert rms_db([]) == -120.0
    assert abs(rms_db([1.0, -1.0]) - 0.0) < 1e-9
