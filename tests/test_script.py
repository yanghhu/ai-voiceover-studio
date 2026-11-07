from voiceover_studio.script import clean_markdown, parse_script, speakers, split_text

SCRIPT = """# Title
<!-- a comment
spanning lines -->
[NARRATOR]: Hello **world**, see [docs](https://x.y).
This continues the narrator.

[ALEX](tags=happy|warm, speed=1.2): Hi there!
[pause 1.5]
Untagged paragraph keeps ALEX.

```
[NOT]: code is ignored
```
"""


def test_parse_speakers_and_continuation():
    segs = parse_script(SCRIPT)
    assert [s.speaker for s in segs] == ["NARRATOR", "ALEX", "ALEX"]
    assert segs[0].text == "Hello world, see docs. This continues the narrator."
    assert segs[1].options == {"tags": ["happy", "warm"], "speed": 1.2}
    assert segs[1].pause_after == 1.5
    assert speakers(segs) == ["NARRATOR", "ALEX"]


def test_default_speaker_and_plain_text():
    segs = parse_script("Just one line.\n\nAnother.")
    assert [s.speaker for s in segs] == ["NARRATOR", "NARRATOR"]


def test_cjk_speaker_names():
    segs = parse_script("[旁白]: 你好。\n[小林]: 嗨！")
    assert [s.speaker for s in segs] == ["旁白", "小林"]


def test_leading_pause():
    segs = parse_script("[pause 2]\n[A]: go")
    assert segs[0].text == "" and segs[0].pause_after == 2.0 and segs[1].text == "go"


def test_split_long_text():
    text = "One sentence here. " * 30
    chunks = split_text(text.strip(), 100)
    assert all(len(c) <= 100 for c in chunks) and "".join(chunks).count("One") == 30
    cjk = "这是一个句子。" * 40
    assert all(len(c) <= 50 for c in split_text(cjk, 50))


def test_clean_markdown():
    assert clean_markdown("- **bold** and `code` ![img](a.png)") == "bold and code"
