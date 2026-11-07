"""`voiceover` command line.

    voiceover say "Hello world" --voice ACTOR_ID -o hello.mp3
    voiceover script script.md --voices voices.json -o out/
    voiceover voices
    voiceover video --images slides/ --script script.md -o video.mp4
    voiceover task TASK_ID --wait -o result.mp3

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
from .providers import available_providers
from .studio import Studio


def _size(value: str):
    try:
        w, h = value.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT, e.g. 1920x1080") from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="voiceover", description="AI voiceover, subtitles and faceless "
                                "videos from a script. Default engine: Miragea (MIRAGEA_API_KEY).")
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--provider", default=os.environ.get("VOICEOVER_PROVIDER", "miragea"),
                        help="voice engine (%s); env VOICEOVER_PROVIDER" % ", ".join(available_providers()))
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
    say.add_argument("--voice", required=False, help="actor id from `voiceover voices`, or an http(s) "
                     "URL of reference audio to clone")
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

    video = sub.add_parser("video", parents=[common, voice_opts], help="faceless slideshow video (needs moviepy)")
    video.add_argument("--images", type=Path, required=True, help="folder of images, used in name order")
    video.add_argument("--script", type=Path, required=True)
    video.add_argument("-o", "--output", type=Path, default=Path("video.mp4"))
    _script_args(video)
    video.add_argument("--size", type=_size, default=(1920, 1080), help="e.g. 1920x1080 or 1080x1920 (Shorts)")
    video.add_argument("--fps", type=int, default=30)
    video.add_argument("--fit", choices=("cover", "contain"), default="cover")
    video.add_argument("--subtitles", choices=("sidecar", "burn", "none"), default="sidecar")
    video.add_argument("--subtitle-source", choices=("timing", "recognize"), default="timing")

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
    return "dummy" if args.dry_run else args.provider


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
    voice = args.voice or ("dummy-narrator" if studio.provider.name == "dummy" else None)
    if not voice:
        raise VoiceoverError("--voice is required: an actor id (see `voiceover voices`) or a "
                             "reference audio URL")
    result = studio.say(text.strip(), voice, args.output, reference_text=args.reference_text,
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
                                  max_chars=args.max_chars, use_cache=not args.fresh, progress=progress)
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
        if not (args.all and more and items):
            break
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
    result = render_video(studio, args.images, args.script, args.output, voices=voices,
                          default_voice=default, size=args.size, fps=args.fps, subtitles=args.subtitles,
                          fit=args.fit, subtitle_source=args.subtitle_source, gap=args.gap,
                          max_chars=args.max_chars, use_cache=not args.fresh)
    _emit(args, result, "Video:     %s (%.1fs, %d images)\nSubtitles: %s" % (
        result["video"], result["duration"], result["images"], result["subtitles"] or "-"))
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


COMMANDS = {"say": cmd_say, "script": cmd_script, "voices": cmd_voices, "video": cmd_video, "task": cmd_task}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
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
