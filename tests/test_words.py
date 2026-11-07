from types import SimpleNamespace

from voiceover_studio.words import (Word, align, estimate, join_words, key_phrase, paginate,
                                    segment_words, sentences_from_words, tokenize)


def test_tokenize_latin_and_cjk():
    assert tokenize("Hello, world! It's 2,500 years.") == ["Hello", "world", "It's", "2,500", "years"]
    assert tokenize("今晚抬头看到的星光，可能") == ["今晚", "抬头", "看到", "的星", "光", "可能"] or \
        tokenize("今晚抬头看到的星光，可能")[0] == "今晚"
    assert tokenize("三个字") == ["三个字"]                  # never leaves one character alone
    assert join_words(["今晚", "抬头", "AI", "配音"]) == "今晚抬头 AI 配音"


def test_estimate_covers_the_span_in_order():
    words = estimate(1.0, 4.0, "Short words, then a much longer sentence.")
    assert words[0].start == 1.0 and words[-1].end <= 4.0 + 1e-9
    assert all(a.start < b.start for a, b in zip(words, words[1:]))
    assert words[1].tail == "," and words[-1].tail == "."


def test_sentences_from_engine_words():
    text = "Cleopatra was born. Later, she ruled!"
    raw = [{"start": 0.1, "end": 0.6, "text": "Cleopatra"}, {"start": 0.6, "end": 0.8, "text": "was"},
           {"start": 0.8, "end": 1.2, "text": "born"}, {"start": 1.5, "end": 1.9, "text": "Later"},
           {"start": 2.0, "end": 2.2, "text": "she"}, {"start": 2.2, "end": 2.6, "text": "ruled"}]
    out = sentences_from_words(text, raw)
    assert out == [{"start": 0.1, "end": 1.2, "text": "Cleopatra was born."},
                   {"start": 1.5, "end": 2.6, "text": "Later, she ruled!"}]
    zh = sentences_from_words("星光很亮。宇宙很大！", [{"start": 0, "end": 0.5, "text": "星光"},
                                                  {"start": 0.5, "end": 0.9, "text": "很亮"},
                                                  {"start": 1.0, "end": 1.4, "text": "宇宙"},
                                                  {"start": 1.4, "end": 1.8, "text": "很大"}])
    assert [s["text"] for s in zh] == ["星光很亮。", "宇宙很大！"]


def test_segment_words_from_engine_and_estimate():
    seg = SimpleNamespace(start=10.0, end=12.0, text="The Moon landing, 1969.", emphasis=["Moon landing"],
                          meta={"words": [{"start": 0.1, "end": 0.3, "text": "The"},
                                          {"start": 0.3, "end": 0.6, "text": "Moon"},
                                          {"start": 0.6, "end": 1.0, "text": "landing"},
                                          {"start": 1.1, "end": 1.8, "text": "1969"}]})
    words = segment_words(seg)
    assert [w.text for w in words] == ["The", "Moon", "landing", "1969"]
    assert words[0].start == 10.1 and words[2].tail == "," and words[3].tail == "."
    assert [w.key for w in words] == [False, True, True, True]  # emphasis + numbers
    seg.meta = {}
    est = segment_words(seg)
    assert len(est) == 4 and est[0].start == 10.0 and est[-1].end <= 12.0


def test_paginate_rules():
    words = [Word(0, 0.2, "one"), Word(0.2, 0.4, "two"), Word(0.4, 0.6, "three"), Word(0.6, 0.8, "four", "."),
             Word(2.0, 2.2, "after"), Word(2.2, 2.4, "pause")]
    pages = paginate(words, max_weight=40, max_words=3)
    assert [[w.text for w in p.words] for p in pages] == [["one", "two", "three"], ["four"], ["after", "pause"]]
    assert pages[0].end == pages[1].start and pages[1].end < pages[2].start
    narrow = paginate(words[:4], max_weight=9, max_words=9)
    assert all(sum(len(w.text) + 1 for w in p.words) <= 9 for p in narrow)


def test_key_phrase():
    seg = SimpleNamespace(text="Woolly mammoths were still alive on a remote island.", emphasis=[])
    assert key_phrase(seg) == "Woolly mammoths remote island"
    assert key_phrase(SimpleNamespace(text="Short one.", emphasis=[])) == "Short one"
    assert key_phrase(SimpleNamespace(text="x", emphasis=["Moon landing"])) == "Moon landing"
    assert key_phrase(SimpleNamespace(text="光每秒能跑三十万公里，可宇宙实在太大了。", emphasis=[])) == "光每秒能跑三十万公里"


def test_align_tolerates_unknown_words():
    words = align("Hello there.", [Word(0, 1, "Hello"), Word(1, 2, "missing"), Word(2, 3, "there")])
    assert words[2].tail == "."
