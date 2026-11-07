"""`voiceover` command line.

    voiceover say "Hello world" -o hello.mp3
    voiceover script script.md -o out/
    voiceover video --script script.md -o video.mp4 --music ambient
    voiceover video --script short.md --vertical --style tiktok -o short.mp4
    voiceover voices --provider edge --filter en-GB
    voiceover doctor
    voiceover task TASK_ID --wait -o result.mp3        (miragea)

Engines: edge (free, default without MIRAGEA_API_KEY), miragea, openai, dummy.

Exit codes: 0 success, 1 a provider task failed, 2 usage/config/API error.
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .errors import VoiceoverError
from .providers import available_providers, default_provider_name
from .studio import Studio


def _size(value: str):
    try:
        w, h = value.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT, e.g. 1920x1080") from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="voiceover", description="AI voiceover, subtitles and faceless "
                                "videos from a script. Default engine: free Edge neural voices, or "
                                "Miragea when MIRAGEA_API_KEY is set.")
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--provider", default="auto",
                        help="voice engine: auto, %s (auto = env VOICEOVER_PROVIDER, else miragea when "
                        "MIRAGEA_API_KEY is set, else edge)" % ", ".join(available_providers()))
    common.add_argument("--dry-run", action="store_true",
                        help="use the offline dummy provider (silence); no API key, no network")
    common.add_argument("--json", action="store_true", help="machine-readable output")
    common.add_argument("-v", "--verbose", action="store_true")
    common.add_argument("--wait-timeout", type=float, default=600, help="max seconds to wait per task")

    voice_opts = argparse.ArgumentParser(add_help=False)
    voice_opts.add_argument("--model", help="synthesis model id, e.g. expressive or standard")
    voice_opts.add_argument("--speed", type=float, help="0.25 - 4.0")
    voice_opts.add_argument("--tag", action="append", dest="tags", help="emotion/style tag (repeatable)")
    voice_opts.add_argument("--lang", dest="language", help="language hint for reference audio, e.g. en, zh, ja")
    voice_opts.add_argument("--fresh", action="store_true",
                            help="new take: random idempotency keys and no segment cache")

    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    say = sub.add_parser("say", parents=[common, voice_opts], help="voice one piece of text")
    say.add_argument("text", nargs="?", help="text to speak (or --text-file)")
    say.add_argument("--text-file", type=Path)
    say.add_argument("--voice", required=False, help="voice id from `voiceover voices` (e.g. "
                     "en-US-AvaNeural for edge), or an http(s) URL of reference audio to clone (miragea); "
                     "default: picked from the text's language")
    say.add_argument("--ref-text", dest="reference_text", help="exact transcript of the reference audio")
    say.add_argument("-o", "--output", default="voiceover.mp3")

    script = sub.add_parser("script", parents=[common, voice_opts], help="voice a whole (multi-speaker) script")
    script.add_argument("script", type=Path)
    script.add_argument("-o", "--outdir", type=Path, default=Path("voiceover_out"))
    _script_args(script)
    script.add_argument("--name", default="voiceover.mp3", help="output file name (.mp3/.wav/.m4a...)")
    script.add_argument("--subtitles", choices=("timing", "recognize", "none"), default="timing",
                        help="timing: from segment durations (default, no extra API call); recognize: speech "
                        "recognition on the final mix (one extra API call)")

    voices = sub.add_parser("voices", parents=[common], help="list voices in your account")
    voices.add_argument("--limit", type=int, default=50)
    voices.add_argument("--offset", type=int, default=0)
    voices.add_argument("--all", action="store_true", help="follow pagination")
    voices.add_argument("--filter", help="only voices whose id, name or language contains this text")

    video = sub.add_parser("video", parents=[common, voice_opts], help="faceless video with motion and "
                           "styled captions (needs ffmpeg)")
    video.add_argument("--images", type=Path, help="folder of images / clips, used in name order for "
                       "segments without ![](b-roll) in the script (default: kinetic text on an animated "
                       "gradient)")
    video.add_argument("--script", type=Path, required=True)
    video.add_argument("-o", "--output", type=Path, default=Path("video.mp4"))
    _script_args(video)
    video.add_argument("--size", type=_size, default=(1920, 1080), help="e.g. 1920x1080 or 1080x1920 (Shorts)")
    video.add_argument("--vertical", action="store_true", help="shortcut for --size 1080x1920")
    video.add_argument("--fps", type=int, default=30)
    video.add_argument("--fit", choices=("cover", "contain"), default="cover")
    video.add_argument("--subtitles", choices=("burn", "sidecar", "none"), default="burn",
                       help="burn animated captions into the video (default; an .srt is written too), "
                       "sidecar .srt only, or none")
    video.add_argument("--subtitle-source", choices=("timing", "recognize"), default="timing")
    video.add_argument("--style", choices=("auto", "tiktok", "bold", "clean", "minimal", "box"), default="auto",
                       help="caption style: tiktok (word-by-word pop, default for vertical), bold, clean "
                       "(default for landscape), minimal, box")
    video.add_argument("--motion", choices=("kenburns", "none"), default="kenburns")
    video.add_argument("--transition", type=float, default=0.5, help="transition seconds (0 = cut)")
    video.add_argument("--transition-style", choices=("mix", "fade", "slide", "zoom", "cut"), default="mix",
                       help="mix (slide/zoom/fade, default), fade, slide, zoom or cut")
    video.add_argument("--grade", choices=("cinematic", "none"), default="cinematic",
                       help="cinematic: gentle contrast, vignette and film grain (default)")
    video.add_argument("--hook", "--title", dest="title", help="hook card text for the first seconds "
                       "(default: the script's first # heading)")
    video.add_argument("--hook-seconds", type=float, default=2.2)
    video.add_argument("--no-hook", "--no-title", dest="no_title", action="store_true")
    video.add_argument("--music", help="background music: ambient or pulse (built in, generated, "
                       "royalty-free) or a path to an audio file; ducked under the voice")
    video.add_argument("--music-volume", type=float, default=0.5,
                       help="music level, 0-1 (default 0.5); the track is levelled first")
    video.add_argument("--no-duck", action="store_true", help="do not lower the music while speaking")
    video.add_argument("--speaker-labels", action="store_true",
                       help="show the speaker name above captions (static styles)")
    video.add_argument("--no-progress-bar", action="store_true")
    video.add_argument("--font", help="caption font family or .ttf/.otf path (CJK: e.g. 'Noto Sans SC')")

    doctor = sub.add_parser("doctor", help="check ffmpeg, engines and API keys")
    doctor.add_argument("--online", action="store_true", help="also synthesize one short test line "
                        "with the free edge engine (no account needed)")
    doctor.add_argument("--json", action="store_true")

    task = sub.add_parser("task", parents=[common], help="check or resume a Miragea task")
    task.add_argument("task_id")
    task.add_argument("--wait", action="store_true")
    task.add_argument("-o", "--output", help="save audio (or SRT for subtitle tasks) when finished")
    return p


def _script_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--voices", type=Path, help="voices.json / voices.yaml mapping speakers to voices")
    parser.add_argument("--default-voice", help="voice for speakers missing from --voices")
    parser.add_argument("--gap", type=float, default=0.35, help="seconds of silence between segments")
    parser.add_argument("--max-chars", type=int, help="split segments longer than this")


def _provider_name(args: argparse.Namespace) -> str:
    if args.dry_run:
        return "dummy"
    return default_provider_name() if args.provider in (None, "", "auto") else args.provider


def _studio(args: argparse.Namespace) -> Studio:
    name = _provider_name(args)
    kwargs = {}
    if name == "miragea":
        kwargs = {"fresh": getattr(args, "fresh", False), "wait_timeout": args.wait_timeout}
    return Studio(name, **kwargs)


def _voice_overrides(args: argparse.Namespace) -> dict:
    return {k: getattr(args, k, None) for k in ("model", "speed", "tags", "language")}


def _emit(args: argparse.Namespace, data: dict, human: str) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else human)


def _apply_cli_voice(args):
    from .config import load_voices
    from .providers.base import Voice
    vm = load_voices(args.voices)
    overrides = Voice(**{k: v for k, v in _voice_overrides(args).items() if v is not None})
    return {k: v.merged(overrides) for k, v in vm.items()}, overrides


def cmd_say(args: argparse.Namespace) -> int:
    text = args.text if args.text is not None else (
        args.text_file.read_text(encoding="utf-8") if args.text_file else None)
    if not text or not text.strip():
        raise VoiceoverError("Give the text to speak, or --text-file")
    studio = _studio(args)
    result = studio.say(text.strip(), args.voice or None, args.output, reference_text=args.reference_text,
                        **_voice_overrides(args))
    _emit(args, result, "Saved %s" % result["output"])
    return 0


def cmd_script(args: argparse.Namespace) -> int:
    studio = _studio(args)
    voices, overrides = _apply_cli_voice(args)
    default = None
    if args.default_voice:
        from .providers.base import Voice
        default = Voice.parse(args.default_voice).merged(overrides)

    def progress(n, total, seg):
        if not args.json:
            print("[%d/%d] %s: %s" % (n, total, seg.speaker, seg.text[:60] + ("..." if len(seg.text) > 60 else "")),
                  file=sys.stderr)

    result = studio.render_script(args.script, args.outdir, voices=voices, default_voice=default,
                                  output_name=args.name, gap=args.gap, subtitles=args.subtitles,
                                  max_chars=args.max_chars, use_cache=not args.fresh,
                                  voice_overrides=overrides, progress=progress)
    data = {"audio": result.audio_path, "subtitles": result.srt_path, "manifest": result.manifest_path,
            "duration": round(result.duration, 2), "segments": len(result.segments),
            "subtitle_source": result.subtitle_source, "provider": studio.provider.name}
    _emit(args, data, "Audio:     %s (%.1fs, %d segments)\nSubtitles: %s\nManifest:  %s" % (
        result.audio_path, result.duration, len(result.segments), result.srt_path or "-", result.manifest_path))
    return 0


def cmd_voices(args: argparse.Namespace) -> int:
    studio = _studio(args)
    found, offset = [], args.offset
    while True:
        items, more = studio.provider.list_voices(min(max(args.limit, 1), 100), offset)
        found.extend(items)
        offset += len(items)
        if not ((args.all or args.filter) and more and items):
            break
    if args.filter:
        needle = args.filter.lower()
        found = [v for v in found if needle in ("%s %s %s" % (v.voice_id, v.name, v.language)).lower()]
        more = False
    if args.json:
        print(json.dumps({"items": [v.__dict__ for v in found], "has_more": more}, ensure_ascii=False, indent=2))
    else:
        if not found:
            print("No voices yet. Create one in your provider's workspace, or use a reference audio URL.")
        for v in found:
            print("%-24s %-6s %s" % (v.voice_id, v.language or "-", v.name))
        if more and not args.all:
            print("... more available: --offset %d or --all" % offset, file=sys.stderr)
    return 0


def cmd_video(args: argparse.Namespace) -> int:
    from .video import render_video
    studio = _studio(args)
    voices, overrides = _apply_cli_voice(args)
    default = None
    if args.default_voice:
        from .providers.base import Voice
        default = Voice.parse(args.default_voice).merged(overrides)
    def progress(n, total, seg):
        if not args.json:
            print("[%d/%d] %s: %s" % (n, total, seg.speaker, seg.text[:60] + ("..." if len(seg.text) > 60 else "")),
                  file=sys.stderr)

    title = False if args.no_title else (args.title or "auto")
    size = (1080, 1920) if args.vertical else args.size
    result = render_video(studio, args.images, args.script, args.output, voices=voices,
                          default_voice=default, size=size, fps=args.fps, subtitles=args.subtitles,
                          fit=args.fit, subtitle_source=args.subtitle_source, style=args.style,
                          motion=args.motion, transition=args.transition,
                          transition_style=args.transition_style, title=title,
                          hook_seconds=args.hook_seconds, speaker_labels=args.speaker_labels,
                          progress_bar=not args.no_progress_bar, font=args.font, music=args.music,
                          music_volume=args.music_volume, duck=not args.no_duck, grade=args.grade,
                          gap=args.gap, max_chars=args.max_chars, use_cache=not args.fresh,
                          voice_overrides=overrides, progress=progress)
    result["provider"] = studio.provider.name
    _emit(args, result, "Video:     %s (%.1fs, %d shots, %s captions%s)\nAudio:     %s\nSubtitles: %s" % (
        result["video"], result["duration"], result["shots"], result["style"],
        ", music: %s" % result["music"] if result.get("music") else "", result["audio"],
        result["subtitles"] or "-"))
    return 0


def cmd_task(args: argparse.Namespace) -> int:
    if _provider_name(args) != "miragea":
        raise VoiceoverError("`task` is only available for the miragea provider")
    from .audio import write_raw
    from .providers.miragea import MirageaClient
    client = MirageaClient(wait_timeout=args.wait_timeout)
    task = client.task(args.task_id)
    if args.wait:
        task = client.wait(task)
    if args.output and task.get("status") == "succeeded":
        result = task.get("result") or {}
        if task.get("kind") == "audio_generation":
            write_raw(client.download(result["audio_url"]), result.get("format", "mp3"), args.output)
        else:
            Path(args.output).write_text(result.get("srt", ""), encoding="utf-8")
        task["saved_to"] = args.output
    _emit(args, task, json.dumps(task, ensure_ascii=False, indent=2))
    return 1 if task.get("status") == "failed" else 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import run_checks, format_report
    checks = run_checks(online=args.online)
    if args.json:
        print(json.dumps({"checks": checks, "ok": all(c["status"] != "fail" for c in checks)},
                         ensure_ascii=False, indent=2))
    else:
        print(format_report(checks))
    return 0 if all(c["status"] != "fail" for c in checks) else 2


COMMANDS = {"say": cmd_say, "script": cmd_script, "voices": cmd_voices, "video": cmd_video, "task": cmd_task,
            "doctor": cmd_doctor}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if getattr(args, "verbose", False) else logging.WARNING,
                        format="%(levelname)s %(message)s")
    try:
        return COMMANDS[args.command](args)
    except VoiceoverError as exc:
        if args.json:
            print(json.dumps(exc.to_dict(), ensure_ascii=False, indent=2))
        else:
            print("error: %s" % exc, file=sys.stderr)
        return exc.exit_code
    except (OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        print("interrupted (submitted tasks keep running; re-run to reuse them)", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
