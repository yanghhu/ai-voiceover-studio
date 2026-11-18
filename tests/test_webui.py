"""Offline tests for the Gradio web studio (skipped when gradio is not installed)."""
import json
import time
from pathlib import Path

import pytest

pytest.importorskip("gradio")

from voiceover_studio.webui import _sample_sentence, build_ui, example_scripts, generate_voiceover, \
    list_voices, new_session, pick_voice, save_broll, say_line  # noqa: E402
from voiceover_studio.webui import test_voice as preview_voice_line  # noqa: E402


class _Evt:
    def __init__(self, index):
        self.index = index


def test_build_ui(tmp_path):
    app = build_ui(workdir=tmp_path)
    assert app is not None


def test_new_session(tmp_path):
    session = new_session(tmp_path)
    assert session["dir"].is_dir()


def test_generate_voiceover_with_dummy(tmp_path):
    session = new_session(tmp_path)
    status, audio, srt, rows = generate_voiceover(
        "# Demo\n\nHello world, this is the studio.\n\n[NARRATOR] Second segment.",
        "dummy", "auto", 1.0, 0.35, "voiceover.wav", session)
    assert "2" in status
    assert audio and audio.endswith(".wav")
    assert srt and srt.endswith(".srt")
    assert len(rows) == 2
    assert rows[0][1] == "DEFAULT" or rows[1][1] == "NARRATOR"


def test_generate_voiceover_empty_script(tmp_path):
    session = new_session(tmp_path)
    with pytest.raises(ValueError):
        generate_voiceover("   ", "dummy", "auto", 1.0, 0.35, "voiceover.wav", session)


def test_say_line_with_dummy(tmp_path):
    session = new_session(tmp_path)
    status, audio = say_line("One line only.", "dummy", "", "auto", 1.0, session)
    assert audio and Path(audio).is_file()


def test_list_voices_with_dummy(tmp_path):
    status, rows = list_voices("dummy", "")
    assert "dummy" in status
    assert isinstance(rows, list)


def test_example_scripts_found():
    scripts = example_scripts()
    assert any(s.endswith("script.md") for s in scripts)


def test_test_voice_with_dummy(tmp_path):
    session = new_session(tmp_path)
    status, audio = preview_voice_line("dummy-voice", "dummy", session)
    assert audio and Path(audio).is_file()


def test_test_voice_without_selection(tmp_path):
    session = new_session(tmp_path)
    with pytest.raises(ValueError):
        preview_voice_line("", "dummy", session)


def test_sample_sentence_matches_voice_language():
    assert "prova" in _sample_sentence("it-IT-GiuseppeNeural")
    assert _sample_sentence("xx-XX-Unknown") == _sample_sentence("en-US-AvaNeural")


def test_pick_voice_uses_clicked_row():
    rows = [["it-IT-GiuseppeNeural", "it", "Giuseppe"], ["en-US-AvaNeural", "en-US", "Ava"]]
    assert pick_voice(_Evt([1, 0]), rows) == "en-US-AvaNeural"
    assert pick_voice(_Evt(None), rows) == ""


def test_save_broll_copies_in_upload_order(tmp_path):
    session = new_session(tmp_path)
    a = tmp_path / "moon.jpg"
    a.write_bytes(b"x")
    b = tmp_path / "stars.jpg"
    b.write_bytes(b"y")
    folder = save_broll([str(a), str(b)], session)
    names = sorted(p.name for p in folder.iterdir())
    assert names == ["001_moon.jpg", "002_stars.jpg"]


def test_new_session_is_absolute(tmp_path):
    session = new_session(tmp_path / "rel")
    assert Path(session["dir"]).is_absolute()


def test_ai_regenerate_replaces_asset(tmp_path, monkeypatch):
    import voiceover_studio.ai_video as ai_video
    from voiceover_studio.webui import ai_plan, ai_regenerate

    def fake_plan(client, prompt, workdir, **kwargs):
        scene = ai_video.Scene(0, "Line one.", "pyramids")
        scene.asset_path, scene.source = str(workdir / "scene_00.jpg"), "openverse image"
        return [scene]

    def fake_generate(query, orientation, workdir, index, transport=None):
        workdir.mkdir(parents=True, exist_ok=True)
        target = workdir / "scene_00.jpg"
        target.write_bytes(b"new")
        return target, "generated (pollinations)"

    monkeypatch.setattr(ai_video, "plan_and_fetch", fake_plan)
    monkeypatch.setattr(ai_video, "generate_asset", fake_generate)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    ai_plan("pyramids", 30.0, "auto", "landscape", "m", False, "m", session)
    status, gallery = ai_regenerate("1", "landscape", session)
    assert "regenerated" in status
    assert gallery[0][0].endswith("scene_00.jpg")


def test_save_broll_empty(tmp_path):
    session = new_session(tmp_path)
    assert save_broll(None, session) is None
    assert save_broll([], session) is None


def test_save_broll_includes_library_picks(tmp_path):
    session = new_session(tmp_path)
    asset = tmp_path / "clip_01.mp4"
    asset.write_bytes(b"video")
    folder = save_broll(None, session, extra=[str(asset)])
    assert folder is not None and list(folder.glob("*clip_01.mp4"))


def test_clip_search_populates_candidates(tmp_path, monkeypatch):
    from voiceover_studio.webui import clip_search
    import voiceover_studio.clips as clips

    def fake_search(query, limit=4, cookies=None):
        return [{"id": "abc", "title": "Aerial vineyard hills", "channel": "Scenery",
                 "duration": 305.0, "url": "https://youtu.be/abc"},
                {"id": "def", "title": "Wine cellar barrels closeup", "channel": "Nature",
                 "duration": 95.0, "url": "https://youtu.be/def"}]

    monkeypatch.setattr(clips, "search_youtube", fake_search)
    monkeypatch.setattr(clips, "suggest_searches",
                        lambda client, model, prompt, n=5:
                        ["aerial vineyards", "wine cellar barrels"])
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    status, rows, previews, update = clip_search("enoturismo Marche", "some/model", 5, "", "",
                                                 ["YouTube"], "", session)
    assert "**2** searches, **2** candidate" in status
    assert rows[0][1] == "Aerial vineyard hills"
    assert "youtube.com/embed/abc" in previews and "youtube.com/embed/def" in previews
    assert update["choices"][0].startswith("Aerial vineyard hills")
    assert session["clip_labels"][update["choices"][0]] == "https://youtu.be/abc"


def test_clip_search_uses_manual_queries_without_llm(tmp_path, monkeypatch):
    from voiceover_studio.webui import clip_search
    import voiceover_studio.clips as clips

    def fake_search(query, limit=4, cookies=None):
        return [{"id": query[:3], "title": "Result of %s" % query, "channel": "C",
                 "duration": 120.0, "url": "https://youtu.be/" + query[:3]}]

    monkeypatch.setattr(clips, "search_youtube", fake_search)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    session = new_session(tmp_path)
    status, rows, previews, update = clip_search("enoturismo Marche", "best value (auto)", 5,
                                                 "aerial vineyard hills\n\nwine cellar barrels",
                                                 "", ["YouTube"], "", session)
    assert "**2** searches, **2** candidate" in status
    assert rows[0][3] == "aerial vineyard hills" and rows[1][3] == "wine cellar barrels"
    assert session["clip_labels"][update["choices"][0]].endswith("aer")


def test_clip_search_merges_commons_candidates(tmp_path, monkeypatch):
    from voiceover_studio.webui import clip_search
    import voiceover_studio.clips as clips

    def fake_commons(query, limit=4, transport=None):
        return [{"id": "commons-hills", "title": "Vineyard hills",
                 "channel": "Wikimedia Commons", "duration": 42.0,
                 "url": "https://upload.wikimedia.org/hills.webm", "source": "commons"}]

    monkeypatch.setattr(clips, "search_commons", fake_commons)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    session = new_session(tmp_path)
    status, rows, previews, update = clip_search("enoturismo", "", 5, "vineyard hills", "",
                                                 ["Wikimedia Commons"], "", session)
    assert rows[0][2] == "Wikimedia Commons"
    assert "<video" in previews and "hills.webm" in previews
    assert session["clip_titles"]["https://upload.wikimedia.org/hills.webm"] == "Vineyard hills"
    assert session["clip_labels"][update["choices"][0]] == "https://upload.wikimedia.org/hills.webm"


def test_clip_suggest_fills_editable_queries(tmp_path, monkeypatch):
    from voiceover_studio.webui import clip_suggest
    import voiceover_studio.clips as clips

    monkeypatch.setattr(clips, "suggest_searches",
                        lambda client, model, prompt, n=5:
                        ["q%d" % i for i in range(1, n + 1)])
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    status, text = clip_suggest("enoturismo Marche", "some/model", 3, session)
    assert "**3** queries" in status
    assert text == "q1\nq2\nq3"


def test_clip_build_uses_selected_sources(tmp_path, monkeypatch):
    import voiceover_studio.clips as clips
    from voiceover_studio.webui import clip_build

    def fake_build(urls, workdir, client, model, **kwargs):
        assert urls == ["https://youtu.be/abc", "https://youtu.be/xyz"]
        assert kwargs.get("keep_audio", False) is False
        assert kwargs["n_clips"] is None and kwargs["delay"] == 5.0
        assert kwargs["target_clips"] == 9
        kwargs["progress"]("Downloading https://youtu.be/abc")
        time.sleep(1.5)
        catalog = [{"id": "c_01", "source_title": "Vineyards",
                    "clip_path": str(workdir / "clip_library" / "clips" / "c_01.mp4"),
                    "description": "Green hills", "tags": ["hills"]}]
        return {"clips": [str(workdir / "clip_library" / "clips" / "c_01.mp4")],
                "frames": [str(workdir / "clip_library" / "frames" / "f_001.jpg")],
                "segments": [{"source": "Vineyards", "title": "Drone shot", "start": 5.0,
                              "end": 15.0, "reason": "b-roll"}],
                "sources": ["Vineyards"], "errors": [], "catalog": catalog}

    monkeypatch.setattr(clips, "build_library", fake_build)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    session["clip_labels"] = {"Aerial hills — C (5:00)": "https://youtu.be/abc"}
    yields = list(clip_build(
        ["Aerial hills — C (5:00)"], "https://youtu.be/xyz", "some/model", True, 2,
        10, True, 5.0, 60, session))
    assert len(yields) >= 2
    assert "Downloading https://youtu.be/abc" in yields[-2][0]
    status, clip_files, frames, catalog_rows, update = yields[-1]
    assert "Target: a **60 s** video → **6** shots" in status
    assert "audio-free clips and **1** frames" in status and "Catalog: **1** entries" in status
    assert "Drone shot" in status
    assert clip_files[0].endswith("c_01.mp4")
    assert catalog_rows[0][0] == "c_01"
    assert update["choices"][0].endswith("c_01.mp4")
    assert session["library"]["clips"]


def test_clip_build_needs_a_source(tmp_path, monkeypatch):
    """Generator body: even early validation errors must be readable gr.Error popups."""
    import gradio as gr

    from voiceover_studio.webui import clip_build

    session = new_session(tmp_path)
    with pytest.raises(gr.Error, match="Select at least one video source"):
        list(clip_build([], "", "some/model", True, 2, 10, True, 5.0, 60, session))


def test_clip_build_raises_a_readable_error(tmp_path, monkeypatch):
    """A crash in the worker thread surfaces with class + detail, not a bare 'Error'."""
    import gradio as gr
    from voiceover_studio.errors import ConfigError
    from voiceover_studio.webui import clip_build
    import voiceover_studio.clips as clips

    def failing_build(urls, workdir, client, model, **kwargs):
        raise ConfigError('The clip studio needs yt-dlp: pip install "ai-voiceover-studio[clip]"')

    monkeypatch.setattr(clips, "build_library", failing_build)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    with pytest.raises(gr.Error, match=r"The clip studio needs yt-dlp"):
        list(clip_build([], "https://youtu.be/abc", "some/model", True, 2,
                        10, True, 5.0, 60, session))


def test_clip_build_no_clips_reports_the_source_errors(tmp_path, monkeypatch):
    """If nothing was cut, the per-source failures must reach the user, not vanish."""
    import gradio as gr
    from voiceover_studio.webui import clip_build
    import voiceover_studio.clips as clips

    def empty_build(urls, workdir, client, model, **kwargs):
        return {"clips": [], "frames": [], "segments": [],
                "sources": [], "errors": ["https://youtu.be/abc: Sign in to confirm you are "
                                          "not a bot (bot check)"], "catalog": []}

    monkeypatch.setattr(clips, "build_library", empty_build)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    with pytest.raises(gr.Error, match="Step 5 produced no clips.*bot check"):
        list(clip_build([], "https://youtu.be/abc", "some/model", True, 2,
                        10, True, 5.0, 60, session))


def test_clip_select_builds_script(tmp_path, monkeypatch):
    import voiceover_studio.clips as clips
    from voiceover_studio.webui import clip_select

    def fake_select(client, model, prompt, catalog, language="the user's language",
                    max_shots=8, target_seconds=0.0):
        assert language == "italian" and max_shots == 6 and target_seconds == 60.0
        return [{"entry": catalog[0], "narration": "Colline infinite."}]

    monkeypatch.setattr(clips, "select_clips", fake_select)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    clips.save_catalog(session["dir"], [{"id": "c_01", "description": "hills",
                                         "tags": ["hills"], "clip_path": "/tmp/c_01.mp4"}])
    status, script, rows = clip_select("enoturismo", "some/model", "italian", 60, 10, session)
    assert "Selected **1** clips" in status
    assert "![](/tmp/c_01.mp4)" in script and "Colline infinite." in script
    assert rows[0][2] == "Colline infinite."
    assert session["selected_clips"] == ["c_01"]


def test_voice_choices_never_crashes(tmp_path):
    from voiceover_studio.webui import voice_choices
    update = voice_choices("dummy")
    assert "choices" in update


def test_clip_illustrate_draws_cards_from_the_plan(tmp_path):
    from voiceover_studio.webui import clip_illustrate

    session = new_session(tmp_path)
    session["overlay_plan"] = [{"scene": 2, "title": "Enoturismo", "bullets": ["4 valli"],
                                "icons": ["uva"]}]
    script = ("# Marche\n\n![](/tmp/c_01.mp4)\n\nColline infinite.\n\n"
              "![](/tmp/c_02.mp4)\n\nVigne al tramonto.")
    status, out = clip_illustrate(script, "2", "Scuro", session)
    assert "Added **1** overlay cards" in status
    assert "){overlay}" in out
    card = Path(str(Path(session["dir"]) / "illustrations" / "overlay_01.png"))
    assert card.is_file() and card.stat().st_size > 0
    assert out.index("overlay_01.png") < out.index("Vigne al tramonto.")
    assert out.index("overlay_01.png") > out.index("c_02.mp4")


def test_clip_illustrate_without_plan_uses_the_narration(tmp_path):
    from voiceover_studio.webui import clip_illustrate

    session = new_session(tmp_path)
    script = "Prima frase.\n\nSeconda frase.\n\nTerza frase."
    status, out = clip_illustrate(script, "1", "Chiaro", session)
    assert "Added **3** overlay cards" in status
    assert out.count("){overlay}") == 3
    cards = sorted((Path(session["dir"]) / "illustrations").glob("overlay_*.png"))
    assert len(cards) == 3


def test_clip_illustrate_needs_a_script(tmp_path):
    from voiceover_studio.webui import clip_illustrate
    with pytest.raises(ValueError):
        clip_illustrate("", "1", "Scuro", new_session(tmp_path))


def test_clip_preview_uses_dummy_and_small_size(tmp_path, monkeypatch):
    import voiceover_studio.webui as webui
    from voiceover_studio.webui import clip_preview

    captured = {}

    def fake_render(script, provider, language, speed, vertical, style, music, broll,
                    session, **kwargs):
        captured.update(kwargs, provider=provider, vertical=vertical)
        return "ok", "/tmp/preview.mp4"

    monkeypatch.setattr(webui, "render_video_clip", fake_render)
    session = new_session(tmp_path)
    status, video = clip_preview("![](/tmp/c_01.mp4)\n\nTesto.", False, session)
    assert status == "ok" and video == "/tmp/preview.mp4"
    assert captured["provider"] == "dummy"
    assert captured["small"] is True
    assert captured["output_name"] == "preview.mp4"


def test_clip_select_reports_reading_time(tmp_path, monkeypatch):
    import voiceover_studio.clips as clips
    from voiceover_studio.webui import clip_select

    seen = []

    def fake_select(client, model, prompt, catalog, language="the user's language",
                    max_shots=8, target_seconds=0.0):
        seen.append(target_seconds)
        return [{"entry": catalog[0], "narration": "word " * 25}]

    monkeypatch.setattr(clips, "select_clips", fake_select)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    clips.save_catalog(session["dir"], [{"id": "c_01", "description": "hills",
                                         "tags": ["hills"], "clip_path": "/tmp/c_01.mp4"}])
    status, script, rows = clip_select("enoturismo", "some/model", "italian", 60, 10, session)
    assert "reads in about **10 s**" in status  # 25 words / 2.5 + 0.35 pause
    assert "Target was 60 s" in status

    status2, _, _ = clip_select("enoturismo", "some/model", "italian", 60, 10, session,
                                match_narration=False)
    assert seen == [60.0, 0.0]
    assert "Target was 60 s" not in status2
    assert "reads in about" in status2


def test_clip_suggest_falls_back_to_default_model(tmp_path, monkeypatch):
    import voiceover_studio.ai_video as ai_video
    from voiceover_studio.errors import ProviderError
    from voiceover_studio.webui import clip_suggest

    def fake_best_value(client, limit=8):
        return ["broken/model"]

    def fake_suggest(client, model, prompt, n=5):
        if model == "broken/model":
            raise ProviderError("OpenRouter POST /chat/completions failed (404)")
        assert model == ai_video.DEFAULT_MODELS[0]
        return ["hills aerial", "wine cellar"]

    monkeypatch.setattr(ai_video, "best_value_models", fake_best_value)
    monkeypatch.setattr("voiceover_studio.clips.suggest_searches", fake_suggest)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    status, queries = clip_suggest("enoturismo", "best value (auto)", 5, session)
    assert "fallback from broken/model" in status
    assert queries == "hills aerial\nwine cellar"


class _FakeWizardClient:
    """Stands in for OpenRouterClient; answers by the system prompt of each wizard step."""

    def __init__(self, *args, **kwargs):
        pass

    def chat(self, model, messages, max_tokens=None):
        system = messages[0]["content"]
        if "documentary narrator" in system:
            return json.dumps({"narration": "Prima scena.\n\nSeconda scena.",
                               "subtitles": True, "reason": "video didattico"})
        if "art director" in system:
            return json.dumps([{"scene": "Colline al tramonto", "query": "aerial vineyards"},
                               {"scene": "Barili in cantina", "query": "wine cellar"}])
        if "infographic overlays" in system:
            return json.dumps([{"scene": 1, "title": "Enoturismo",
                                "bullets": ["4 valli"], "icons": ["uva"]}])
        raise AssertionError("unexpected system prompt: %s" % system[:60])


@pytest.fixture
def wizard_env(monkeypatch):
    import voiceover_studio.ai_video as ai_video
    monkeypatch.setattr(ai_video, "OpenRouterClient", _FakeWizardClient)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")


def test_wizard_narrate_writes_narration_and_duration(tmp_path, wizard_env):
    from voiceover_studio.webui import wizard_narrate
    session = new_session(tmp_path)
    status, narration, advice, update = wizard_narrate("enoturismo nelle Marche", "m", "it",
                                                       60.0, session)
    assert "reading time" in status
    assert narration == "Prima scena.\n\nSeconda scena."
    assert session["wizard_narration"] == narration
    assert "Subtitles: yes" in advice
    assert update["value"] >= 15


def test_wizard_scenes_prefill_the_queries(tmp_path, wizard_env):
    from voiceover_studio.webui import wizard_scenes
    session = new_session(tmp_path)
    status, rows, queries = wizard_scenes("Prima scena.\n\nSeconda scena.",
                                          "enoturismo", "m", session)
    assert len(rows) == 2 and rows[0][2] == "aerial vineyards"
    assert queries == "aerial vineyards\nwine cellar"
    assert session["wizard_scenes"][0]["query"] == "aerial vineyards"


def test_wizard_scenes_need_the_narration(tmp_path, wizard_env):
    from voiceover_studio.webui import wizard_scenes
    with pytest.raises(ValueError):
        wizard_scenes("", "enoturismo", "m", new_session(tmp_path))


def test_wizard_overlays_and_presentation_toggle(tmp_path, wizard_env):
    from voiceover_studio.webui import set_presentation, wizard_overlays
    session = new_session(tmp_path)
    assert "off" in set_presentation("no", session)
    status, rows = wizard_overlays("Prima scena.\n\nSeconda scena.", "enoturismo", "m", session)
    assert len(rows) == 1 and rows[0][1] == "Enoturismo"
    assert session["overlay_plan"][0]["icons"] == ["uva"]
    set_presentation("no", session)
    assert "overlay_plan" not in session


def test_reading_time_updates_the_duration_slider(tmp_path):
    from voiceover_studio.webui import reading_time
    md, update = reading_time("One two three four five six seven eight.")
    assert "Reading time" in md
    assert update["value"] >= 15


def test_clip_render_passes_transitions(tmp_path, monkeypatch):
    import voiceover_studio.webui as webui
    from voiceover_studio.webui import clip_render

    calls = {}

    def fake_render(script, provider_, language, speed, vertical, style, music, broll, session,
                    **kwargs):
        calls.update(kwargs)
        return "ok", "video.mp4"

    monkeypatch.setattr(webui, "render_video_clip", fake_render)
    status, out = clip_render("# T\n\nTesto.", "dummy", "auto", 1.0, "", False, "auto", "",
                              "zoom", 0.8, new_session(tmp_path))
    assert calls["transition_style"] == "zoom" and calls["transition"] == 0.8


def test_clip_select_uses_the_step1_narration_verbatim(tmp_path, monkeypatch):
    import voiceover_studio.clips as clips
    from voiceover_studio.webui import clip_select

    captured = {}

    def fake_select(client, model, prompt, catalog, language="the user's language",
                    max_shots=8, target_seconds=0.0, narration=""):
        captured["narration"] = narration
        return [{"entry": catalog[0], "narration": "Colline infinite al tramonto.",
                 "scene": 1}]

    monkeypatch.setattr(clips, "select_clips", fake_select)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    clips.save_catalog(session["dir"], [{"id": "c_01", "description": "hills",
                                         "tags": ["hills"], "clip_path": "/tmp/c_01.mp4"}])
    status, script, rows = clip_select("enoturismo", "some/model", "italian", 60, 10, session,
                                       "Colline infinite al tramonto.\n\nSeconda scena.")
    assert captured["narration"] == "Colline infinite al tramonto.\n\nSeconda scena."
    assert "exactly as written" in status
    assert "Colline infinite al tramonto." in script
    assert session["selected_clips"] == ["c_01"]


def test_clip_select_falls_back_to_session_narration(tmp_path, monkeypatch):
    import voiceover_studio.clips as clips
    from voiceover_studio.webui import clip_select

    captured = {}

    def fake_select(client, model, prompt, catalog, language="the user's language",
                    max_shots=8, target_seconds=0.0, narration=""):
        captured["narration"] = narration
        return [{"entry": {"id": "", "description": ""}, "narration": narration,
                 "scene": 1}]

    monkeypatch.setattr(clips, "select_clips", fake_select)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    clips.save_catalog(session["dir"], [{"id": "c_01", "description": "hills",
                                         "tags": [], "clip_path": "/tmp/c_01.mp4"}])
    session["wizard_narration"] = "Testo dalla sessione."
    status, script, rows = clip_select("enoturismo", "some/model", "auto", 60, 10, session)
    assert captured["narration"] == "Testo dalla sessione."


def test_ill_describe_prefills_the_prompts_box(tmp_path, monkeypatch):
    import voiceover_studio.illustrations as illustrations
    from voiceover_studio.webui import ill_describe

    monkeypatch.setattr(illustrations, "plan_image_prompts",
                        lambda client, model, narration, prompt="": [
                            "Green hills from above", "Barrels in a cellar"])
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    status, text = ill_describe("Colline.\n\nCantine.", "enoturismo", "m", session)
    assert "one per scene" in status
    assert text == "Green hills from above\nBarrels in a cellar"
    assert session["ill_prompts"] == ["Green hills from above", "Barrels in a cellar"]


def test_ill_generate_streams_progress_and_saves(tmp_path, monkeypatch):
    import time as time_lib

    import voiceover_studio.illustrations as illustrations
    from voiceover_studio.webui import ill_generate

    def fake_stills(client, model, prompts, out_dir, **kwargs):
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        for i, prompt in enumerate(prompts, 1):
            kwargs["progress"]("Generating illustration %d/%d: %s" % (i, len(prompts), prompt))
            time_lib.sleep(0.1)
            Path(str(out_dir / ("still_%02d" % i)) + ".png").write_bytes(b"x")
            kwargs["progress"]("Illustration %d/%d done (ok)" % (i, len(prompts)))
        stills = [str(out_dir / ("still_%02d.png" % i)) for i in range(1, len(prompts) + 1)]
        return stills, []

    monkeypatch.setattr(illustrations, "generate_stills", fake_stills)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    yields = list(ill_generate("recraft/recraft-v4.1-flash-v2", "Acquerello", "",
                               "16:9", "Hills from above\nBarrels in a cellar", session))
    status, files = yields[-1]
    assert "**2**/2 illustrations generated (style **Acquerello**)" in status
    assert len(files) == 2 and files[0].endswith("still_01.png")
    assert session["ill_aspect"] == "16:9"
    assert session["ill_stills"] == files


def test_ill_generate_needs_prompts(tmp_path, monkeypatch):
    import gradio as gr

    from voiceover_studio.webui import ill_generate

    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    with pytest.raises(gr.Error, match="Describe the illustrations first"):
        list(ill_generate("m", "Acquerello", "", "16:9", "  \n ", session))


def test_ill_animate_bakes_cards_over_gifs(tmp_path):
    from PIL import Image

    from voiceover_studio.webui import ill_animate

    session = new_session(tmp_path)
    still = Path(session["dir"]) / "illustrations" / "still_01.png"
    still.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (960, 540), (30, 90, 150)).save(still)
    session["ill_stills"] = [str(still)]
    session["wizard_narration"] = "Colline infinite al tramonto."
    session["ill_overlay_plan"] = [{"scene": 1, "title": "Vineyards",
                                    "bullets": ["Sunny hills"], "icons": ["star"]}]
    status, gifs = ill_animate("push-in", True, "Scuro", session)
    assert len(gifs) == 1 and gifs[0].endswith("slide_01.gif")
    assert Path(gifs[0]).is_file()
    assert session["ill_slides"][0]["scene"] == 1
    assert "animated GIF(s) ready" in status


def test_ill_build_script_keeps_the_step1_narration(tmp_path):
    from voiceover_studio.webui import ill_build_script

    session = new_session(tmp_path)
    narration = "Colline infinite al tramonto.\n\nNelle cantine il tempo si ferma."
    session["wizard_narration"] = narration
    session["ill_slides"] = [{"scene": 1, "gif": "slide_01.gif"},
                             {"scene": 2, "gif": "slide_02.gif"}]
    status, script = ill_build_script(narration, session)
    assert script.startswith("![](slide_01.gif)\n\nColline infinite al tramonto.")
    assert "Nelle cantine il tempo si ferma." in script
    assert script.count("![](") == 2
    assert "exactly as written in step 1" in status


def test_gf_plan_writes_the_cycle_prompts(tmp_path, monkeypatch):
    import voiceover_studio.illustrations as illustrations
    from voiceover_studio.webui import gf_plan

    prompts = ["Field, ears left", "Field, ears upright", "Field, ears right"]
    monkeypatch.setattr(illustrations, "plan_motion_frames",
                        lambda client, model, prompt, motion, n_frames=4: prompts)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    status, text = gf_plan("Wheat field at sunset", "the ears sway in the wind", 3, "m",
                           "AI frames", session)
    assert "loops seamlessly" in status
    assert text == "Field, ears left\nField, ears upright\nField, ears right"
    assert session["gf_prompts"] == prompts


def test_gf_plan_procedural_mode_needs_no_llm(tmp_path):
    from voiceover_studio.webui import gf_plan

    session = new_session(tmp_path)
    status, text = gf_plan("Wheat field at sunset", "the ears sway in the wind", 4, "m",
                           "One image + procedural motion", session)
    assert "Procedural mode" in status
    assert "Go straight to step 2" in status
    assert text == "" 


def test_gf_generate_and_assemble_full_cycle(tmp_path, monkeypatch):
    import voiceover_studio.illustrations as illustrations
    from voiceover_studio.webui import gf_assemble, gf_generate

    def fake_stills(client, model, prompts, out_dir, **kwargs):
        from PIL import Image

        Path(out_dir).mkdir(parents=True, exist_ok=True)
        for i in range(len(prompts)):
            Image.new("RGB", (480, 270), (i * 30, 120, 60)).save(out_dir / ("still_%02d.png" % (i + 1)))
        kwargs["progress"]("Generating illustration 1/%d" % len(prompts))
        return [str(out_dir / ("still_%02d.png" % (i + 1))) for i in range(len(prompts))], []

    monkeypatch.setattr(illustrations, "generate_stills", fake_stills)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    yields = list(gf_generate("some/model", "Acquerello", "", "16:9",
                              "Field, ears left\nField, ears upright\nField, ears right",
                              "AI frames", "", "m", "", "v/model", 5, session))
    status, files = yields[-1]
    assert "**3**/3 frame image(s) generated" in status
    assert len(files) == 3
    assert session["gf_stills"] == files

    gif_status, gif, _extras = gf_assemble(1.0, 1, True, "AI frames", "wind", 1.0, session)
    assert "ping-pong" in gif_status
    from PIL import Image
    with Image.open(gif) as g:
        # ping-pong: 2*3-2 = 4 base frames, blend=1 inserts one cross-fade per frame
        assert g.n_frames == (3 * 2 - 2) + (3 * 2 - 2) * 1
    assert gif.endswith(".gif")


def test_gf_generate_needs_two_prompts(tmp_path, monkeypatch):
    import gradio as gr

    from voiceover_studio.webui import gf_generate

    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    with pytest.raises(gr.Error, match="At least two frame prompts"):
        list(gf_generate("m", "Acquerello", "", "16:9", "Only one prompt", "AI frames", "", "m", "",
                         "v/model", 5, session))


def test_gf_generate_needs_text_model_row_for_lottie(tmp_path, monkeypatch):
    """Lottie mode: the TEXT model writes the whole animation; the GIF never drifts."""
    import voiceover_studio.lottie_motion as lottie_motion
    from voiceover_studio.webui import gf_assemble, gf_generate

    def fake_gen(client, model, prompt, out_path, **kwargs):
        assert "bouncing" in prompt
        assert kwargs.get("kind") == "Cartoon character"
        out_path = Path(str(out_path) + ".json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("{}")
        return {"layers": [{"ty": 4}]}

    monkeypatch.setattr(lottie_motion, "generate_lottie", fake_gen)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    yields = list(gf_generate("img/model", "Acquerello", "", "16:9", "",
                              "Motion design (Lottie)", "A bouncing dot, seamless loop",
                              "m", "Cartoon character", "v/model", 5, session))
    status, files = yields[-1]
    assert "Lottie animation ready" in status
    assert files == []
    assert Path(session["gf_lottie"]).name == "motion.json"

    def fake_to_gif(json_path, dest_base, **kwargs):
        gif = Path(str(dest_base) + ".gif")
        html = Path(str(dest_base) + ".html")
        gif.parent.mkdir(parents=True, exist_ok=True)
        gif.write_bytes(b"GIF89a")
        html.write_text("<html>lottie</html>")
        return gif, html

    monkeypatch.setattr(lottie_motion, "lottie_to_gif", fake_to_gif)
    status2, gif, extras = gf_assemble(1.2, 2, True, "Motion design (Lottie)", "wind", 1.0,
                                       session)
    assert "Motion-design GIF ready" in status2
    assert gif.endswith(".gif")
    assert any(str(e).endswith(".html") for e in extras)


def test_gf_procedural_mode_one_image_no_drift(tmp_path, monkeypatch):
    """Procedural mode: ONE image is generated and the loop is built locally."""
    import voiceover_studio.illustrations as illustrations
    from voiceover_studio.webui import gf_assemble, gf_generate

    def fake_stills(client, model, prompts, out_dir, **kwargs):
        from PIL import Image

        assert len(prompts) == 1
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        im = Image.new("RGB", (480, 270))
        px = im.load()
        for y in range(270):
            for x in range(0, 480, 8):
                px[x, y] = (x * 255 // 480, y * 255 // 270, 128)
        still = out_dir / "still_01.png"
        im.save(still)
        return [str(still)], []

    monkeypatch.setattr(illustrations, "generate_stills", fake_stills)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    # No planned prompts: the scene comes straight from step 1's prompt box.
    yields = list(gf_generate("some/model", "Acquerello", "", "16:9", "",
                              "One image + procedural motion", "Wheat field at sunset", "m", "",
                              "v/model", 5, session))
    status, files = yields[-1]
    assert "**1**/1 frame image(s) generated" in status
    assert "procedural" in status
    assert len(files) == 1
    assert session["gf_stills"] == files

    gif_status, gif, extras = gf_assemble(1.2, 2, True, "One image + procedural motion",
                                          "wind", 1.0, session)
    assert "no AI " in gif_status
    assert "procedural frames" in gif_status
    assert extras == []
    from PIL import Image
    with Image.open(gif) as g:
        assert g.n_frames >= 8
        assert g.info.get("loop", 0) == 0


def test_gf_ai_clip_mode_generates_an_mp4(tmp_path, monkeypatch):
    """"AI clip (text-to-video)' mode: the video model animates everything inside the
    scene and returns a real MP4 that goes straight into the video pipeline."""
    import voiceover_studio.ai_clips as ai_clips
    from voiceover_studio.webui import gf_assemble, gf_generate

    def fake_clip(client, model, prompt, dest_base, **kwargs):
        assert model == "v/model"
        assert "wheat" in prompt.lower()
        assert int(kwargs["duration"]) == 5
        assert kwargs["aspect_ratio"] == "16:9"
        kwargs.setdefault("progress", None)
        dest_base = Path(str(dest_base) + ".mp4")
        dest_base.parent.mkdir(parents=True, exist_ok=True)
        dest_base.write_bytes(b"\x00\x00\x00\x18ftypisom")
        return dest_base

    monkeypatch.setattr(ai_clips, "generate_video_clip", fake_clip)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    session = new_session(tmp_path)
    yields = list(gf_generate("img/model", "Acquerello", "", "16:9",
                              "A locked shot of wheat swaying at sunset",
                              "AI clip (text-to-video)", "Campo di grano", "m", "",
                              "v/model", 5, session))
    status, files = yields[-1]
    assert "AI clip ready" in status
    assert files == []
    assert Path(session["gf_clip"]).name == "ai_clip.mp4"
    # gif is None (not an error): a real MP4 needs no GIF assembly
    status2, out, extras = gf_assemble(1.2, 2, True, "AI clip (text-to-video)", "wind", 1.0,
                                       session)
    assert "Nothing to assemble" in status2
    assert out == session["gf_clip"] and extras == [session["gf_clip"]]
