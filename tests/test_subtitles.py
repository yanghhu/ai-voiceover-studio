from voiceover_studio.subtitles import (chunk_text, cues_from_timing, format_timestamp, parse_srt,
                                        to_srt, wrap)


def test_timestamps():
    assert format_timestamp(3661.5) == "01:01:01,500"
    assert format_timestamp(-1) == "00:00:00,000"


def test_roundtrip():
    cues = cues_from_timing([(0.0, 2.0, "Hello there."), (2.5, 4.0, "Bye.")])
    srt = to_srt(cues)
    assert srt.startswith("1\n00:00:00,000 --> ")
    parsed = parse_srt(srt)
    assert len(parsed) == 2 and parsed[1].start == 2.5 and parsed[1].end == 4.0


def test_chunks_prefer_sentences():
    text = "Sunlight contains every colour of the rainbow. When it enters the atmosphere, it bumps into molecules."
    chunks = chunk_text(text, 60)
    assert chunks[0] == "Sunlight contains every colour of the rainbow."


def test_cue_timing_is_contiguous():
    cues = cues_from_timing([(1.0, 9.0, "First sentence is here. Second one follows. Third.")], max_chars=30)
    assert cues[0].start == 1.0 and abs(cues[-1].end - 9.0) < 1e-6
    for a, b in zip(cues, cues[1:]):
        assert abs(a.end - b.start) < 1e-6


def test_wrap_two_lines():
    assert wrap("short", 42) == "short"
    assert wrap("a " * 40, 42).count("\n") == 1
    zh = wrap("进入大气层后，波长短的蓝光比红光更容易被散射，于是整片天空都泛着蓝。", 30)
    assert zh.count("\n") == 1 and not zh.split("\n")[1].startswith("，")
