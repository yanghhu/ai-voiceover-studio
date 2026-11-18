"""Offline tests for the clip studio (yt-dlp and ffmpeg mocked, OpenRouter faked)."""
import base64
import json

import pytest

from voiceover_studio.clips import (build_library, build_video_script, catalog_path,
                                    classify_clip, cut_clip, extract_frames, find_sources,
                                    load_catalog, parse_vtt, probe_duration, save_catalog,
                                    search_commons, search_pixabay, search_youtube,
                                    select_clips, suggest_searches, suggest_segments,
                                    title_avoids_people, _transcript_excerpt)
from voiceover_studio.errors import ConfigError
from voiceover_studio.providers.miragea import HttpResponse

VTT = """WEBVTT

00:00:01.000 --> 00:00:04.000
<v Roger>Hello world

00:00:04.000 --> 00:00:08.000
Hello world

00:00:08.000 --> 00:00:12.000
<v Roger>Second <b>sentence</b> here
"""

SEGMENTS_JSON = ('[{"start": 5, "end": 15, "title": "Opening drone shot", '
                 '"reason": "establishing b-roll"}, '
                 '{"start": 9999, "end": 10005, "title": "Outro", "reason": "closing"}]')


def chat_client(fake, content):
    fake.add("POST", "https://openrouter.ai/api/v1/chat/completions",
             (200, {"choices": [{"message": {"content": content}}]}))
    from voiceover_studio.ai_video import OpenRouterClient
    return OpenRouterClient(api_key="test-key", transport=fake)


def test_parse_vtt_merges_and_cleans():
    text = parse_vtt(VTT)
    assert "[00:01] Hello world" in text
    assert "[00:08] Second sentence here" in text
    assert "<v Roger>" not in text and "<b>" not in text
    assert text.count("Hello world") == 1


def test_suggest_segments_clamps_to_duration(fake):
    client = chat_client(fake, SEGMENTS_JSON)
    segments = suggest_segments(client, "m", "text", duration=60.0, n_clips=2,
                                clip_seconds=10.0, title="Test video")
    assert segments[0]["start"] == 5.0 and segments[0]["end"] == 15.0
    assert segments[1]["end"] == 60.0 and segments[1]["start"] < segments[1]["end"]
    assert segments[1]["title"] == "Outro"


def test_suggest_segments_falls_back_without_transcript():
    segments = suggest_segments(None, "m", "", duration=90.0, n_clips=3, clip_seconds=10.0)
    assert len(segments) == 3
    assert all(seg["end"] > seg["start"] and seg["end"] <= 90.0 for seg in segments)


def test_cut_clip_uses_stream_copy(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("voiceover_studio.audio.ffmpeg_path", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr("voiceover_studio.audio._ffmpeg", lambda args: calls.append(args))
    src = tmp_path / "src.mp4"
    src.write_bytes(b"video")
    dest = cut_clip(src, 5.0, 12.5, tmp_path / "out" / "clip.mp4")
    assert dest.parent.name == "out"
    assert calls[0][:2] == ["-ss", "5.00"]
    assert "-t" in calls[0] and "7.50" in calls[0]
    assert "-c" in calls[0] and "copy" in calls[0]
    assert "-an" in calls[0]
    cut_clip(src, 5.0, 12.5, tmp_path / "out" / "audio.mp4", audio=True)
    assert "-an" not in calls[1]


def test_cut_clip_requires_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr("voiceover_studio.audio.ffmpeg_path", lambda: None)
    with pytest.raises(ConfigError):
        cut_clip(tmp_path / "src.mp4", 0, 5, tmp_path / "c.mp4")


def test_extract_frames_writes_pattern(monkeypatch, tmp_path):
    calls = []

    def fake_ffmpeg(args):
        calls.append(args)
        for i in (1, 2):
            (tmp_path / "clip_frames" / ("frame_%03d.jpg" % i)).write_bytes(b"jpg")

    monkeypatch.setattr("voiceover_studio.audio.ffmpeg_path", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr("voiceover_studio.audio._ffmpeg", fake_ffmpeg)
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"video")
    frames = extract_frames(src, tmp_path / "clip_frames", every=3.0)
    assert "fps=1/3.0" in calls[0][3]
    assert len(frames) == 2 and all(f.is_file() for f in frames)


def test_probe_duration_reads_ffprobe(monkeypatch, tmp_path):
    import subprocess
    media = tmp_path / "src.mp4"
    media.write_bytes(b"v")

    class Proc:
        stdout = b"42.5\n"
        stderr = b""

    monkeypatch.setattr("voiceover_studio.audio.ffmpeg_path", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Proc())
    assert probe_duration(media) == 42.5


def test_build_library_cuts_suggested_segments(fake, monkeypatch, tmp_path):
    from voiceover_studio import clips
    source = tmp_path / "sources" / "abc.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    monkeypatch.setattr(clips, "fetch_info",
                        lambda url, cookies=None: {"id": "abc", "title": "Vineyards",
                                                   "duration": 120.0})
    monkeypatch.setattr(clips, "download_video",
                        lambda url, dest, cookies=None, ranges=None, audio=False:
                        (source, {"id": "abc"}))
    monkeypatch.setattr(clips, "fetch_transcript", lambda url, dest, cookies=None: "[00:10] great shots")
    cut, frames = [], []
    monkeypatch.setattr(clips, "cut_clip",
                        lambda src, start, end, dest, audio=False:
                        (cut.append((start, end)), dest)[1])
    monkeypatch.setattr(clips, "extract_frames",
                        lambda src, dest, every=3.0: frames.append(dest)
                        or [dest / "frame_001.jpg", dest / "frame_002.jpg"])
    client = chat_client(fake, SEGMENTS_JSON)
    library = build_library(["https://youtu.be/abc"], tmp_path, client, "m",
                            n_clips=2, clip_seconds=10.0, stills=True)
    assert len(library["clips"]) == 2 and library["clips"][0].endswith("vineyards_01.mp4")
    assert cut[0] == (0.0, 10.0) and cut[1] == (10.0, 11.0)
    assert library["segments"][0]["source"] == "Vineyards"
    assert len(library["frames"]) == 4 and "frame_001.jpg" in library["frames"][0]


def test_build_library_skips_bad_urls(fake, monkeypatch, tmp_path):
    from voiceover_studio import clips
    monkeypatch.setattr(clips, "download_video", lambda *a: (_ for _ in ()).throw(AssertionError()))
    library = build_library(["", "not-a-url"], tmp_path, None, "m")
    assert library["clips"] == [] and library["errors"] == []


def test_build_library_continues_after_download_failure(fake, monkeypatch, tmp_path):
    from voiceover_studio import clips
    source = tmp_path / "sources" / "ok.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")

    def fake_info(url, cookies=None):
        if "blocked" in url:
            raise ConfigError("Sign in to confirm you're not a bot")
        return {"id": "ok", "title": "Good video", "duration": 60.0}

    monkeypatch.setattr(clips, "fetch_info", fake_info)
    monkeypatch.setattr(clips, "download_video",
                        lambda url, dest, cookies=None, ranges=None, audio=False:
                        (source, {"id": "ok"}))
    monkeypatch.setattr(clips, "fetch_transcript", lambda url, dest, cookies=None: "")
    monkeypatch.setattr(clips, "cut_clip", lambda src, start, end, dest, audio=False: dest)
    monkeypatch.setattr(clips, "extract_frames", lambda src, dest, every=3.0: [])
    monkeypatch.setattr(clips, "classify_clip",
                        lambda client, model, path, title, context: {"description": "x", "tags": []})
    library = build_library(["https://youtu.be/blocked", "https://youtu.be/ok"],
                            tmp_path, None, "m", n_clips=1, clip_seconds=10.0, stills=False,
                            delay=0.0)
    assert len(library["clips"]) == 1 and library["sources"] == ["Good video"]
    assert "bot check" in library["errors"][0] and "cookies.txt" in library["errors"][0]


def test_build_library_skips_overlong_sources(fake, monkeypatch, tmp_path):
    from voiceover_studio import clips
    downloads = []
    monkeypatch.setattr(clips, "fetch_info",
                        lambda url, cookies=None: {"id": "big", "title": "Huge video",
                                                   "duration": 4000.0})
    monkeypatch.setattr(clips, "download_video",
                        lambda url, dest, cookies=None, ranges=None, audio=False:
                        downloads.append(url) or (None, {}))
    library = build_library(["https://youtu.be/big"], tmp_path, None, "m", delay=0.0)
    assert downloads == []
    assert "exceeds" in library["errors"][0] and "Huge video" in library["errors"][0]


def test_build_library_deletes_source_unless_kept(fake, monkeypatch, tmp_path):
    from voiceover_studio import clips
    source = tmp_path / "sources" / "abc.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    monkeypatch.setattr(clips, "fetch_info",
                        lambda url, cookies=None: {"id": "abc", "title": "Vineyards",
                                                   "duration": 60.0})
    monkeypatch.setattr(clips, "download_video",
                        lambda url, dest, cookies=None, ranges=None, audio=False: (source, {}))
    monkeypatch.setattr(clips, "fetch_transcript", lambda url, dest, cookies=None: "")
    monkeypatch.setattr(clips, "cut_clip", lambda src, start, end, dest, audio=False: dest)
    monkeypatch.setattr(clips, "extract_frames", lambda src, dest, every=3.0: [])
    monkeypatch.setattr(clips, "classify_clip",
                        lambda client, model, path, title, context: {"description": "x", "tags": []})
    client = chat_client(fake, '[{"start": 5, "end": 15, "title": "A", "reason": "r"}]')
    build_library(["https://youtu.be/abc"], tmp_path, client, "m", n_clips=1,
                  clip_seconds=10.0, stills=False, delay=0.0)
    assert not source.exists()
    source.write_bytes(b"video")
    build_library(["https://youtu.be/abc"], tmp_path, client, "m", n_clips=1,
                  clip_seconds=10.0, stills=False, delay=0.0, keep_sources=True)
    assert source.exists()


def test_build_library_continues_after_clip_failure(fake, monkeypatch, tmp_path):
    from voiceover_studio import clips
    source = tmp_path / "sources" / "abc.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    monkeypatch.setattr(clips, "fetch_info",
                        lambda url, cookies=None: {"id": "abc", "title": "Vineyards",
                                                   "duration": 120.0})
    monkeypatch.setattr(clips, "download_video",
                        lambda url, dest, cookies=None, ranges=None, audio=False: (source, {}))
    monkeypatch.setattr(clips, "fetch_transcript", lambda url, dest, cookies=None: "[00:05] vines")

    def flaky_cut(src, start, end, dest, audio=False):
        if start == 0.0:
            raise ConfigError("ffmpeg failed: muxer exploded")
        return dest

    monkeypatch.setattr(clips, "cut_clip", flaky_cut)
    monkeypatch.setattr(clips, "extract_frames", lambda src, dest, every=3.0: [])
    monkeypatch.setattr(clips, "classify_clip",
                        lambda client, model, path, title, context: {"description": "x", "tags": []})
    client = chat_client(fake, '[{"start": 5, "end": 15, "title": "A", "reason": "r"}, '
                               '{"start": 30, "end": 40, "title": "B", "reason": "r"}]')
    library = build_library(["https://youtu.be/abc"], tmp_path, client, "m",
                            n_clips=None, clip_seconds=10.0, stills=False, delay=0.0)
    assert len(library["clips"]) == 1 and len(library["catalog"]) == 1
    assert any("vineyards_01" in error for error in library["errors"])
    assert not source.exists()


def test_build_library_stops_on_disk_full(fake, monkeypatch, tmp_path):
    from voiceover_studio import clips
    downloads = []
    source = tmp_path / "sources" / "abc.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    monkeypatch.setattr(clips, "fetch_info",
                        lambda url, cookies=None: {"id": "abc", "title": "Vineyards",
                                                   "duration": 120.0})

    def fake_download(url, dest, cookies=None, ranges=None, audio=False):
        downloads.append(url)
        return source, {}

    monkeypatch.setattr(clips, "download_video", fake_download)
    monkeypatch.setattr(clips, "fetch_transcript", lambda url, dest, cookies=None: "[00:05] vines")

    def full_cut(src, start, end, dest, audio=False):
        raise Exception("ffmpeg failed: Error muxing a packet: No space left on device")

    monkeypatch.setattr(clips, "cut_clip", full_cut)
    client = chat_client(fake, '[{"start": 5, "end": 15, "title": "A", "reason": "r"}]')
    library = build_library(["https://youtu.be/abc", "https://youtu.be/def"], tmp_path,
                            client, "m", n_clips=1, clip_seconds=10.0, stills=False, delay=0.0)
    assert len(downloads) == 1 and library["clips"] == []
    assert any("No space left on disk" in error for error in library["errors"])
    assert not source.exists()


def test_title_avoids_people_filters_subjects():
    assert title_avoids_people("Aerial drone view of Tuscan vineyards at sunset")
    assert not title_avoids_people("My VLOG: wine tasting in Tuscany")
    assert not title_avoids_people("Wine TUTORIAL for beginners")


def test_suggest_searches_parses_query_list(fake):
    queries_json = '["aerial drone vineyard hills", "italian countryside sunset", "wine cellar barrels"]'
    client = chat_client(fake, queries_json)
    queries = suggest_searches(client, "m", "enoturismo nelle Marche", n=3)
    assert queries == ["aerial drone vineyard hills", "italian countryside sunset",
                       "wine cellar barrels"]


class FakeYdl:
    def __init__(self, opts):
        FakeYdl.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        assert url.startswith("ytsearch") and download is False
        return {"entries": [
            {"id": "abc", "title": "Aerial drone vineyard hills", "duration": 300,
             "channel": "Scenery HD", "url": "https://www.youtube.com/watch?v=abc"},
            {"id": "bad", "title": "Wine tasting VLOG with friends", "duration": 600,
             "channel": "People TV", "url": "https://www.youtube.com/watch?v=bad"},
            {"id": "def", "title": "Italian countryside sunset", "duration": 240,
             "channel": "Nature", "url": None},
        ]}


def test_search_youtube_flat_and_filtered(monkeypatch):
    from voiceover_studio import clips
    monkeypatch.setattr(clips, "_import_yt_dlp",
                        lambda: type("M", (), {"YoutubeDL": FakeYdl}))
    results = search_youtube("vineyard aerial", limit=3)
    assert [r["id"] for r in results] == ["abc", "def"]
    assert results[1]["url"].endswith("watch?v=def")
    assert FakeYdl.opts["extract_flat"] is True


class DurationYdl:
    def __init__(self, opts):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        return {"entries": [
            {"id": "long", "title": "Full documentary aerial", "duration": 5400,
             "url": "https://youtu.be/long"},
            {"id": "short", "title": "Quick aerial shot", "duration": 10,
             "url": "https://youtu.be/short"},
            {"id": "ok", "title": "Aerial coastline", "duration": 600,
             "url": "https://youtu.be/ok"},
            {"id": "unknown", "title": "Aerial mountains", "duration": None,
             "url": "https://youtu.be/unknown"},
        ]}


def test_search_youtube_filters_duration(monkeypatch):
    from voiceover_studio import clips
    monkeypatch.setattr(clips, "_import_yt_dlp",
                        lambda: type("M", (), {"YoutubeDL": DurationYdl}))
    results = search_youtube("aerial", limit=4)
    assert [r["id"] for r in results] == ["short", "ok", "unknown"]


class FakeDownloadYdl:
    def __init__(self, opts):
        FakeDownloadYdl.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        return {"id": "abc", "title": "T"}

    def prepare_filename(self, info):
        return ""


def test_download_video_ranges_and_light_format(monkeypatch, tmp_path):
    from voiceover_studio import clips
    dest = tmp_path / "sources"
    dest.mkdir()
    (dest / "abc.mp4").write_bytes(b"v")
    monkeypatch.setattr(clips, "_import_yt_dlp",
                        lambda: type("M", (), {"YoutubeDL": FakeDownloadYdl}))
    path, info = clips.download_video("https://youtu.be/abc", dest,
                                      ranges=[(5, 15), (30, 40)])
    assert path.name == "abc.mp4"
    assert FakeDownloadYdl.opts["force_keyframes_at_cuts"] is True
    assert FakeDownloadYdl.opts["download_ranges"](None, None) == \
        [{"start": 5, "end": 15}, {"start": 30, "end": 40}]
    assert "height<=720" in FakeDownloadYdl.opts["format"]
    assert "+ba" not in FakeDownloadYdl.opts["format"]
    assert FakeDownloadYdl.opts["max_filesize"] == clips.MAX_SOURCE_BYTES
    clips.download_video("https://youtu.be/abc", dest, audio=True)
    assert "+ba" in FakeDownloadYdl.opts["format"]
    assert "download_ranges" not in FakeDownloadYdl.opts


def test_fetch_transcript_raises_on_rate_limit(monkeypatch, tmp_path):
    from voiceover_studio import clips
    from voiceover_studio.errors import ProviderError

    class RateLimitedYdl:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            raise Exception("Unable to download video subtitles for 'it': "
                            "HTTP Error 429: Too Many Requests")

    monkeypatch.setattr(clips, "_import_yt_dlp",
                        lambda: type("M", (), {"YoutubeDL": RateLimitedYdl}))
    with pytest.raises(ProviderError):
        clips.fetch_transcript("https://youtu.be/abc", tmp_path)


def test_find_sources_deduplicates_across_queries(fake, monkeypatch):
    from voiceover_studio import clips
    monkeypatch.setattr(clips, "search_youtube",
                        lambda query, limit=4, cookies=None: [
                            {"id": "abc", "title": "Aerial hills", "channel": "C",
                             "duration": 120.0, "url": "https://youtu.be/abc"}])
    client = chat_client(fake, '["q1", "q2", "q3"]')
    queries, candidates = find_sources(client, "m", "vineyards", sources=3)
    assert queries == ["q1", "q2", "q3"]
    assert len(candidates) == 1 and candidates[0]["query"] == "q1"


def test_transcript_excerpt_keeps_nearby_lines():
    transcript = "[00:05] opening line\n[00:30] middle line\n[02:00] far away"
    assert "opening line" in _transcript_excerpt(transcript, 8.0, 15.0)
    assert "middle line" not in _transcript_excerpt(transcript, 8.0, 15.0)
    assert "far away" in _transcript_excerpt(transcript, 115.0, 125.0)


def test_classify_clip_parses_details(fake, tmp_path, monkeypatch):
    image = tmp_path / "clip_01.mp4.frame.jpg"
    image.write_bytes(b"\xff\xd8fakejpeg")
    monkeypatch.setattr("voiceover_studio.ai_video._first_frame", lambda video, dest: True)
    answer = ('{"description": "Aerial view of green vineyard rows at sunset", '
              '"tags": ["aerial", "vineyard", "sunset"], "mood": "calm", '
              '"setting": "Italian countryside", "camera": "drone", '
              '"has_people": false, "usable": true}')
    client = chat_client(fake, answer)
    details = classify_clip(client, "m", tmp_path / "clip_01.mp4", "Vineyards", "wine talk")
    assert details["description"].startswith("Aerial view")
    assert "vineyard" in details["tags"] and details["has_people"] is False
    sent = fake.calls[-1]["body"].decode()
    assert base64.b64encode(b"\xff\xd8fakejpeg").decode() in sent


def test_classify_clip_falls_back_without_vision(fake, tmp_path, monkeypatch):
    from voiceover_studio.providers.miragea import HttpResponse
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"video")
    monkeypatch.setattr("voiceover_studio.ai_video._first_frame", lambda video, dest: False)

    def flaky(method, url, headers, body, timeout):
        payload = json.dumps({"choices": [{"message": {"content":
            '{"description": "barrels", "tags": ["cellar"], "usable": true}'}}]}).encode()
        if b"image_url" in (body or b""):
            return HttpResponse(404, {}, b'{"error": "no vision"}')
        return HttpResponse(200, {}, payload)

    from voiceover_studio.ai_video import OpenRouterClient
    client = OpenRouterClient(api_key="k", transport=flaky)
    details = classify_clip(client, "m", media, "Cellar video")
    assert details["description"] == "barrels" and details["tags"] == ["cellar"]


def test_catalog_roundtrip(tmp_path):
    entries = [{"id": "a_01", "description": "hills", "tags": ["hills"]}]
    save_catalog(tmp_path, entries)
    assert catalog_path(tmp_path).is_file()
    assert load_catalog(tmp_path) == entries
    assert load_catalog(tmp_path / "missing") == []


def test_select_clips_maps_ids_and_ignores_unknown(fake):
    catalog = [{"id": "a_01", "description": "green hills aerial", "tags": ["hills"],
                "camera": "drone", "has_people": False, "clip_path": "/tmp/a_01.mp4"},
               {"id": "b_01", "description": "wine barrels", "tags": ["cellar"],
                "camera": "static", "has_people": False, "clip_path": "/tmp/b_01.mp4"}]
    selection_json = '[{"id": "b_01", "narration": "Nelle cantine..."}, ' \
                     '{"id": "ghost_99", "narration": "ignored"}, ' \
                     '{"id": "a_01", "narration": "Colline a perdita d occhio."}]'
    client = chat_client(fake, selection_json)
    selected = select_clips(client, "m", "enoturismo", catalog, language="italian")
    assert [item["entry"]["id"] for item in selected] == ["b_01", "a_01"]
    assert selected[0]["narration"] == "Nelle cantine..."


def test_build_video_script_pairs_clips_and_narration():
    selected = [{"entry": {"id": "a_01", "clip_path": "/tmp/a_01.mp4"},
                 "narration": "Colline a perdita d occhio."},
                {"entry": {"id": "b_01", "clip_path": ""},
                 "narration": "Nelle cantine il tempo si ferma."}]
    text = build_video_script(selected, title="Enoturismo")
    assert text.startswith("# Enoturismo")
    assert "![](/tmp/a_01.mp4)" in text and "Colline" in text
    assert "b_01" not in text


def test_build_library_classifies_and_saves_catalog(fake, monkeypatch, tmp_path):
    from voiceover_studio import clips
    source = tmp_path / "sources" / "abc.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    monkeypatch.setattr(clips, "fetch_info",
                        lambda url, cookies=None: {"id": "abc", "title": "Vineyards",
                                                   "duration": 120.0})
    monkeypatch.setattr(clips, "download_video",
                        lambda url, dest, cookies=None, ranges=None, audio=False:
                        (source, {"id": "abc"}))
    monkeypatch.setattr(clips, "fetch_transcript", lambda url, dest, cookies=None: "[00:05] rows of vines")
    monkeypatch.setattr(clips, "cut_clip", lambda src, start, end, dest, audio=False: dest)
    monkeypatch.setattr(clips, "extract_frames", lambda src, dest, every=3.0: [])
    monkeypatch.setattr(clips, "classify_clip",
                        lambda client, model, path, title, context:
                        {"description": "Green hills", "tags": ["hills"], "mood": "calm",
                         "setting": "Tuscany", "camera": "drone", "has_people": False,
                         "usable": True})
    client = chat_client(fake, '[{"start": 5, "end": 15, "title": "Hills", "reason": "r"}, '
                               '{"start": 30, "end": 40, "title": "Rows", "reason": "r"}]')
    sleeps = []
    library = build_library(["https://youtu.be/abc"], tmp_path, client, "m",
                            n_clips=None, clip_seconds=10.0, stills=True, delay=7.0,
                            sleep=sleeps.append)
    assert len(library["catalog"]) == 2
    assert library["catalog"][0]["id"] == "vineyards_01"
    assert library["catalog"][0]["description"] == "Green hills"
    assert load_catalog(tmp_path)[1]["segment_title"] == "Rows"
    assert sleeps == [7.0]  # pause before the subtitle fetch, none between sources


def test_search_commons_parses_results():
    from voiceover_studio import clips
    from voiceover_studio.providers.miragea import HttpResponse
    payload = {"query": {"pages": {
        "1": {"title": "File:Vineyard hills.webm",
              "imageinfo": [{"url": "https://upload.wikimedia.org/x.webm",
                             "mime": "video/webm", "size": 5000000, "duration": 42.0}]},
        "2": {"title": "File:Huge documentary.webm",
              "imageinfo": [{"url": "https://upload.wikimedia.org/y.webm",
                             "mime": "video/webm", "size": 1000, "duration": 4000.0}]},
        "3": {"title": "File:Photo.jpg",
              "imageinfo": [{"url": "https://upload.wikimedia.org/z.jpg",
                             "mime": "image/jpeg", "size": 1000}]},
    }}}

    def transport(method, url, headers, body, timeout):
        assert "commons.wikimedia.org" in url and "filetype%3Avideo" in url
        return HttpResponse(200, {}, json.dumps(payload).encode())

    results = search_commons("vineyard hills", limit=4, transport=transport)
    assert len(results) == 1
    assert results[0]["title"] == "Vineyard hills"
    assert results[0]["source"] == "commons" and results[0]["duration"] == 42.0


def test_search_pixabay_parses_and_requires_key(monkeypatch):
    from voiceover_studio import clips
    from voiceover_studio.providers.miragea import HttpResponse
    monkeypatch.delenv("VOICEOVER_PIXABAY_KEY", raising=False)
    with pytest.raises(ConfigError):
        search_pixabay("vineyard", "  ", transport=lambda *a: None)
    payload = {"hits": [{"id": 7, "tags": "vineyard, aerial", "duration": 12,
                         "videos": {"large": {"url": "https://pixabay.com/videos/l.mp4"}}}]} 

    def transport(method, url, headers, body, timeout):
        assert "pixabay.com/api/videos" in url and "key=k" in url
        return HttpResponse(200, {}, json.dumps(payload).encode())

    results = search_pixabay("vineyard", "k", transport=transport)
    assert results[0]["id"] == "pixabay-7" and results[0]["url"].endswith("l.mp4")


def test_download_direct_writes_file(tmp_path):
    from voiceover_studio import clips
    from voiceover_studio.providers.miragea import HttpResponse

    def transport(method, url, headers, body, timeout):
        assert method == "GET" and url.endswith("hills.webm")
        return HttpResponse(200, {}, b"webmdata")

    path, info = clips.download_direct("https://upload.wikimedia.org/x/hills.webm",
                                       tmp_path / "sources", transport=transport)
    assert path.name == "hills.webm" and path.read_bytes() == b"webmdata"


def test_build_library_downloads_direct_sources(fake, monkeypatch, tmp_path):
    from voiceover_studio import clips
    source = tmp_path / "sources" / "hills.webm"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"v")
    monkeypatch.setattr(clips, "download_direct",
                        lambda url, dest: (source, {"title": "hills"}))
    monkeypatch.setattr(clips, "probe_duration", lambda path: 30.0)
    monkeypatch.setattr(clips, "cut_clip", lambda src, start, end, dest, audio=False: dest)
    monkeypatch.setattr(clips, "extract_frames", lambda src, dest, every=3.0: [])
    monkeypatch.setattr(clips, "classify_clip",
                        lambda client, model, path, title, context:
                        {"description": "hills", "tags": []})
    library = build_library(["https://upload.wikimedia.org/x/hills.webm"], tmp_path, None, "m",
                            n_clips=2, clip_seconds=10.0, stills=False, delay=0.0,
                            titles={"https://upload.wikimedia.org/x/hills.webm": "Vineyard hills"})
    assert len(library["clips"]) == 2 and library["sources"] == ["Vineyard hills"]
    assert library["catalog"][0]["source_title"] == "Vineyard hills"
    assert not source.exists()


def test_fallback_segments_respect_clip_seconds():
    from voiceover_studio.clips import _fallback_segments
    segments = _fallback_segments(30.0, 24, 10.0)
    assert len(segments) == 3
    assert all(seg["end"] - seg["start"] <= 10.0 for seg in segments)


def test_estimate_needs_scales_with_duration():
    from voiceover_studio.clips import estimate_needs
    assert estimate_needs(60, 10) == (6, 2)
    assert estimate_needs(30, 10)[0] >= 3
    assert estimate_needs(300, 10) == (30, 10)


def test_build_library_stops_when_target_reached(fake, monkeypatch, tmp_path):
    from voiceover_studio import clips
    source = tmp_path / "sources" / "abc.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    downloads, statuses = [], []
    monkeypatch.setattr(clips, "fetch_info",
                        lambda url, cookies=None: {"id": url[-3:], "title": "Video " + url[-3:],
                                                   "duration": 300.0})

    def fake_download(url, dest, cookies=None, ranges=None, audio=False):
        downloads.append(url)
        return source, {}

    monkeypatch.setattr(clips, "download_video", fake_download)
    monkeypatch.setattr(clips, "fetch_transcript", lambda url, dest, cookies=None: "[00:05] x")
    monkeypatch.setattr(clips, "cut_clip", lambda src, start, end, dest, audio=False: dest)
    monkeypatch.setattr(clips, "extract_frames", lambda src, dest, every=3.0: [])
    monkeypatch.setattr(clips, "classify_clip",
                        lambda client, model, path, title, context: {"description": "x", "tags": []})
    client = chat_client(fake, '[{"start": 5, "end": 15, "title": "A", "reason": "r"}, '
                               '{"start": 20, "end": 30, "title": "B", "reason": "r"}, '
                               '{"start": 40, "end": 50, "title": "C", "reason": "r"}, '
                               '{"start": 60, "end": 70, "title": "D", "reason": "r"}]')
    library = build_library(["https://youtu.be/abc", "https://youtu.be/def",
                             "https://youtu.be/ghi"], tmp_path, client, "m",
                            n_clips=None, clip_seconds=10.0, stills=False, delay=0.0,
                            target_clips=2, per_source=2,
                            progress=statuses.append)
    assert len(library["clips"]) == 2
    assert len(downloads) == 1
    assert any("Enough clips collected (2/2)" in status for status in statuses)


def test_build_library_per_source_cap_fills_target(fake, monkeypatch, tmp_path):
    from voiceover_studio import clips
    source = tmp_path / "sources" / "abc.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    downloads = []
    monkeypatch.setattr(clips, "fetch_info",
                        lambda url, cookies=None: {"id": url[-3:], "title": "Video " + url[-3:],
                                                   "duration": 300.0})

    def fake_download(url, dest, cookies=None, ranges=None, audio=False):
        downloads.append(url)
        return source, {}

    monkeypatch.setattr(clips, "download_video", fake_download)
    monkeypatch.setattr(clips, "fetch_transcript", lambda url, dest, cookies=None: "[00:05] x")
    monkeypatch.setattr(clips, "cut_clip", lambda src, start, end, dest, audio=False: dest)
    monkeypatch.setattr(clips, "extract_frames", lambda src, dest, every=3.0: [])
    monkeypatch.setattr(clips, "classify_clip",
                        lambda client, model, path, title, context: {"description": "x", "tags": []})
    client = chat_client(fake, '[{"start": 5, "end": 15, "title": "A", "reason": "r"}, '
                               '{"start": 20, "end": 30, "title": "B", "reason": "r"}, '
                               '{"start": 40, "end": 50, "title": "C", "reason": "r"}]')
    library = build_library(["https://youtu.be/abc", "https://youtu.be/def"], tmp_path,
                            client, "m", n_clips=None, clip_seconds=10.0, stills=False,
                            delay=0.0, target_clips=3, per_source=2)
    assert len(library["clips"]) == 3 and len(downloads) == 2
    assert len(library["catalog"]) == 3


def test_cookie_opts_from_argument_and_env(monkeypatch):
    from voiceover_studio.clips import _cookie_opts
    monkeypatch.delenv("VOICEOVER_YTDLP_COOKIES", raising=False)
    monkeypatch.delenv("VOICEOVER_YTDLP_COOKIES_FROM_BROWSER", raising=False)
    assert _cookie_opts() == {}
    assert _cookie_opts("/tmp/cookies.txt") == {"cookiefile": "/tmp/cookies.txt"}
    monkeypatch.setenv("VOICEOVER_YTDLP_COOKIES", "/env/cookies.txt")
    assert _cookie_opts() == {"cookiefile": "/env/cookies.txt"}
    monkeypatch.delenv("VOICEOVER_YTDLP_COOKIES")
    monkeypatch.setenv("VOICEOVER_YTDLP_COOKIES_FROM_BROWSER", "chrome:Profile 1")
    assert _cookie_opts() == {"cookiesfrombrowser": ("chrome",)}


def test_estimate_speech_seconds_matches_narration_length():
    from voiceover_studio.clips import estimate_speech_seconds
    script = ("# Title\n\n![](/tmp/a.mp4)\n\n" + "word " * 25 + "\n\n![](/tmp/b.mp4)\n\n"
              + "word " * 25)
    reading = estimate_speech_seconds(script)
    assert reading == 20.7  # 50 words / 2.5 wps + 2 segments * 0.35 s pause
    assert estimate_speech_seconds("") == 0.0
    assert estimate_speech_seconds("![](/tmp/a.mp4)\n\n# Only a header") == 0.0


def test_select_clips_passes_pacing_budget(fake):
    selection_json = '[{"id": "a_01", "narration": "Colline."}]'
    catalog = [{"id": "a_01", "description": "hills", "tags": ["hills"],
                "clip_path": "/tmp/a_01.mp4"}]
    client = chat_client(fake, selection_json)
    select_clips(client, "m", "enoturismo", catalog, max_shots=6, target_seconds=60)
    body = json.loads(fake.calls[-1]["body"])
    system = body["messages"][0]["content"]
    assert "about 60 seconds" in system
    assert "roughly 25 spoken words" in system  # 60 * 2.5 / 6 shots

    fake.calls.clear()
    client2 = chat_client(fake, selection_json)
    select_clips(client2, "m", "enoturismo", catalog, max_shots=6)
    body = json.loads(fake.calls[-1]["body"])
    assert "reading time" not in body["messages"][0]["content"]


NARRATION_JSON = ('{"narration": "Prima scena.\\n\\nSeconda scena.", "subtitles": true, '
                  '"reason": "video didattico"}')
SCENES_JSON = ('[{"scene": "Colline al tramonto dall\'alto", "query": "aerial vineyards sunset"}, '
               '{"scene": "Barili in cantina", "query": "wine cellar barrels"}]')
OVERLAYS_JSON = ('[{"scene": 1, "title": "Enoturismo", "bullets": ["4 valli", "12 strade del '
                 'Sacred Monte"], "icons": ["uva", "calice"]}, '
                 '{"scene": 9, "title": "out of range", "bullets": [], "icons": []}]')


def test_plan_narration_returns_script_and_subtitles(fake):
    from voiceover_studio.clips import plan_narration
    client = chat_client(fake, NARRATION_JSON)
    plan = plan_narration(client, "m", "enoturismo nelle Marche", language="it", duration=30.0)
    assert plan["narration"].startswith("Prima scena.")
    assert plan["subtitles"] is True
    assert "didattico" in plan["reason"]


def test_plan_narration_needs_a_prompt(fake):
    from voiceover_studio.clips import plan_narration
    client = chat_client(fake, NARRATION_JSON)
    with pytest.raises(ValueError):
        plan_narration(client, "m", "   ")


def test_plan_scene_queries_matches_paragraphs(fake):
    from voiceover_studio.clips import plan_scene_queries
    client = chat_client(fake, SCENES_JSON)
    scenes = plan_scene_queries(client, "m", "Prima scena.\n\nSeconda scena.", "enoturismo")
    assert [s["query"] for s in scenes] == ["aerial vineyards sunset", "wine cellar barrels"]
    assert "enoturismo" in fake.calls[-1]["body"].decode()


def test_plan_scene_queries_pads_missing_scenes(fake):
    from voiceover_studio.clips import plan_scene_queries
    client = chat_client(fake, '[{"scene": "solo una", "query": "one query"}]')
    scenes = plan_scene_queries(client, "m", "Prima.\n\nSeconda.\n\nTerza.")
    assert len(scenes) == 3 and scenes[1]["query"]


def test_plan_scene_queries_needs_narration(fake):
    from voiceover_studio.clips import plan_scene_queries
    client = chat_client(fake, SCENES_JSON)
    with pytest.raises(ValueError):
        plan_scene_queries(client, "m", "")


def test_plan_overlays_filters_invalid_scenes(fake):
    from voiceover_studio.clips import plan_overlays
    client = chat_client(fake, OVERLAYS_JSON)
    overlays = plan_overlays(client, "m", "Prima scena.\n\nSeconda scena.")
    assert len(overlays) == 1
    assert overlays[0]["scene"] == 1 and overlays[0]["title"] == "Enoturismo"
    assert overlays[0]["bullets"] and overlays[0]["icons"] == ["uva", "calice"]


def test_plan_overlays_needs_valid_json(fake):
    from voiceover_studio.clips import plan_overlays
    client = chat_client(fake, '{"not": "a list"}')
    with pytest.raises(ConfigError):
        plan_overlays(client, "m", "Prima scena.")


SELECTION_PRESERVE_JSON = '[{"scene": 1, "id": "a_01"}, {"scene": 2, "id": "b_01"}]'


def test_select_clips_preserves_the_narration(fake):
    catalog = [{"id": "a_01", "description": "green hills aerial", "tags": ["hills"],
                "camera": "drone", "has_people": False, "clip_path": "/tmp/a_01.mp4"},
               {"id": "b_01", "description": "wine barrels", "tags": ["cellar"],
                "camera": "static", "has_people": False, "clip_path": "/tmp/b_01.mp4"}]
    client = chat_client(fake, SELECTION_PRESERVE_JSON)
    narration = "Colline infinite al tramonto.\n\nNelle cantine il tempo si ferma."
    selected = select_clips(client, "m", "enoturismo", catalog, narration=narration)
    assert [item["narration"] for item in selected] == ["Colline infinite al tramonto.",
                                                        "Nelle cantine il tempo si ferma."]
    assert [item["entry"]["id"] for item in selected] == ["a_01", "b_01"]
    system = json.loads(fake.calls[-1]["body"])["messages"][0]["content"]
    assert "exactly as written" in system


def test_select_clips_narration_without_clip_stays_in_the_script(fake):
    catalog = [{"id": "a_01", "description": "green hills aerial", "tags": ["hills"],
                "clip_path": "/tmp/a_01.mp4"}]
    client = chat_client(fake, '[{"scene": 1, "id": "a_01"}, {"scene": 2, "id": "a_01"}]')
    narration = "Prima scena.\n\nSeconda scena senza clip."
    selected = select_clips(client, "m", "enoturismo", catalog, narration=narration)
    assert len(selected) == 2
    assert selected[1]["entry"].get("id") == ""
    assert selected[1]["narration"] == "Seconda scena senza clip."
    script = build_video_script(selected, title="T")
    assert "Seconda scena senza clip." in script and script.count("![](") == 1


def test_select_clips_narration_needs_paragraphs(fake):
    catalog = [{"id": "a_01", "description": "hills", "tags": [], "clip_path": "/tmp/a.mp4"}]
    client = chat_client(fake, SELECTION_PRESERVE_JSON)
    with pytest.raises(ValueError):
        select_clips(client, "m", "enoturismo", catalog, narration="# solo un titolo")
