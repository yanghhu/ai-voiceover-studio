"""AI video builder: prompt -> scene plan -> keyless stock assets -> script.

The pipeline behind the *AI Video* tab:

    plan_scenes()     prompt -> [{narration, query}] via an OpenRouter chat model
    find_asset()      keyless sources: Wikimedia Commons (video and images), Openverse,
                      then a generated image from Pollinations when nothing matches
    verify_asset()    optional vision check via OpenRouter: does the picture match the scene?
    build_script()    scenes + assets -> Markdown script for :func:`video.render_video`

HTTP goes through the same injectable transport as the voice providers, so tests
run fully offline.
"""
from __future__ import annotations

import base64
import json
import os
import random
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .errors import ConfigError, ProviderError
from .providers.miragea import HttpResponse, Transport, urllib_transport

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
USER_AGENT = "ai-voiceover-studio (+https://github.com/yanghhu/ai-voiceover-studio)"

DEFAULT_MODELS = [
    "google/gemini-4-hydrogen",
    "inclusionai/ling-3.2-flash:free",
    "google/gemini-4-carbon",
    "anthropic/claude-fable-5.2",
    "qwen/qwen4-max",
    "meta/muse-ember",
]

PLAN_SYSTEM = (
    "You are a video director. Break the user's idea into {n} short scenes for a narrated "
    "faceless video. Respond with ONLY a JSON array, no markdown fences, no commentary:\n"
    '[{{"narration": "one or two spoken sentences in {language}", '
    '"query": "2-5 simple English keywords for a stock footage search"}}]\n'
    "The narrations must flow as one continuous script: hook first, then the story, "
    "then a closing line. The whole script must read in about {duration:.0f} seconds "
    "(roughly {pace_words} spoken words per scene)."
)

VERIFY_PROMPT = (
    'Does this picture plausibly illustrate the scene "{query}"? '
    'Answer with ONLY a JSON object: {{"match": true or false, "reason": "short reason"}}'
)

ILLUSTRATION_MODELS = [
    "recraft/recraft-v4.1-flash-v2",
    "black-forest-labs/flux-3-image-klein",
    "openai/gpt-image-2",
    "qwen/qwen-image-3",
]

ILLUSTRATION_STYLES = {
    "": "",
    "Infografica illustrata": "Illustrazione didattica in stile infografica, colori chiari, "
                             "forme semplici e leggibili, sfondo bianco. ",
    "Vettoriale piatto": "Illustrazione vettoriale piatta, colori pieni, forme geometriche "
                         "semplici, nessuna sfumatura, sfondo chiaro. ",
    "Schema botanico": "Tavola illustrata in stile manuale botanico, linee sottili precise, "
                       "colori naturali tenui, sfondo color carta antica. ",
    "Quaderno di campo": "Pagina di quaderno di campo con schizzo a matita colorata, tratti "
                         "rapidi, sfondo color carta crema. ",
    "Acquerello": "Illustrazione ad acquerello morbido, colori che sfumano, texture della "
                  "carta, sfondo bianco. ",
    "Gouache": "Illustrazione a gouache, colori piatti e opachi, pennellate visibili, "
               "palette calda e morbida. ",
    "Tempera": "Illustrazione a tempera, colori pieni e coprenti, pennellate decise, "
               "aspetto da dipinto naif. ",
    "Fumetto": "Illustrazione in stile fumetto, contorni neri decisi, colori piatti con "
               "ombreggiature semplici. ",
    "Pennarelli": "Illustrazione a pennarelli colorati, contorni netti, riempimenti vivaci "
                  "con leggere sovrapposizioni, sfondo bianco. ",
    "Schizzo a colori": "Illustrazione in stile schizzo a colori, linee a matita visibili, "
                        "colori tenui, sfondo chiaro. ",
    "Matite colorate": "Illustrazione a matite colorate, tratteggio incrociato visibile, "
                       "colori sfumati per sovrapposizione, sfondo bianco. ",
    "Carboncino": "Disegno a carboncino su carta, tratti scuri e sfumati, forti contrasti "
                  "di luce e ombra, bianco e nero. ",
    "Inchiostro e colore e penna": "Illustrazione a penna e inchiostro con riempimenti di "
                                    "colore pastello, sfondo chiaro. ",
    "Gessetti colorati": "Illustrazione a gessetti colorati su carta ruvida, tratti morbidi "
                         "e polverosi, colori vivaci sfumati con le dita, texture granulosa "
                         "visibile. ",
    "Gessetto su lavagna": "Disegno a gessetto bianco e colorato su lavagna nera, tratti "
                            "polverosi, aspetto da lavagna di scuola o di locale. ",
    "Pastelli a olio": "Illustrazione a pastelli a olio, tratti grassi e materici, colori "
                        "saturi sovrapposti, texture della carta visibile. ",
    "Pastelli a cera (stile bambino)": "Illustrazione a pastelli a cera, tratti semplici e "
                                        "un po' irregolari, colori brillanti, sfondo bianco, "
                                        "stile da disegno per bambini. ",
    "Linoleografia": "Illustrazione in stile linoleografia, forme nette, contrasti forti, "
                     "due o tre colori piatti, texture di stampa visibile. ",
    "Acquaforte / incisione": "Illustrazione in stile incisione antica, tratteggio fitto a "
                               "inchiostro, aspetto da stampa botanica d'epoca. ",
    "Collage di carta": "Illustrazione in stile collage di carta ritagliata, forme semplici "
                         "sovrapposte, colori piatti, bordi leggermente irregolari. ",
}


@dataclass
class Scene:
    index: int
    narration: str
    query: str
    asset_path: Optional[str] = None
    source: str = ""
    verified: Optional[bool] = None
    reason: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


class OpenRouterClient:
    """Minimal OpenAI-compatible client for openrouter.ai (stdlib only)."""

    def __init__(self, api_key: Optional[str] = None, base_url: str = OPENROUTER_BASE_URL,
                 transport: Optional[Transport] = None, timeout: float = 120.0):
        self.api_key = (api_key or os.environ.get("OPENROUTER_API_KEY") or "").strip()
        if not self.api_key:
            raise ConfigError("OpenRouter needs an API key: set OPENROUTER_API_KEY "
                              "(https://openrouter.ai/keys)")
        self.base_url = base_url.rstrip("/")
        self.transport = transport or urllib_transport
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": "Bearer %s" % self.api_key,
                "Content-Type": "application/json", "User-Agent": USER_AGENT}

    def request(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        response = self.transport(method, self.base_url + path, self._headers(), payload, self.timeout)
        if response.status >= 400:
            detail = response.body.decode("utf-8", "replace")[:300]
            raise ProviderError("OpenRouter %s %s failed (%d): %s%s"
                                % (method, path, response.status, detail,
                                   _status_hint(response.status)))
        return response.json()

    def chat(self, model: str, messages: List[Dict[str, Any]], max_tokens: int = 2000) -> str:
        data = self.request("POST", "/chat/completions",
                            {"model": model, "messages": messages, "max_tokens": max_tokens})
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Unexpected OpenRouter response shape: %s" % exc) from None

    def image(self, model: str, prompt: str, aspect_ratio: Optional[str] = None,
              modalities: Optional[List[str]] = None) -> List[str]:
        """Image generation: returns the image URLs (data: or https:) of the answer."""
        body: Dict[str, Any] = {"model": model,
                                "modalities": list(modalities or ["image"]),
                                "messages": [{"role": "user", "content": prompt}]}
        if aspect_ratio:
            body["image_config"] = {"aspect_ratio": aspect_ratio}
        data = self.request("POST", "/chat/completions", body)
        message = (data.get("choices") or [{}])[0].get("message", {})
        return [img.get("image_url", {}).get("url", "")
                for img in message.get("images", []) if img.get("image_url")]

    def models(self) -> List[str]:
        data = self.request("GET", "/models")
        return sorted(item["id"] for item in data.get("data", []) if item.get("id"))


def _status_hint(status: int) -> str:
    """A short, actionable hint for the most common OpenRouter HTTP errors."""
    if status in (401, 403):
        return " Check OPENROUTER_API_KEY (create or rotate it at https://openrouter.ai/keys)."
    if status == 402:
        return (" The OpenRouter account has no credits for this model: pick a free one "
                "or top up at https://openrouter.ai/credits.")
    if status == 404:
        return " This model is no longer served: pick another model from the dropdown."
    if status == 429:
        return " Rate limited: wait a minute, or pick another (cheaper/free) model."
    return ""


def best_value_models(client: OpenRouterClient, limit: int = 8) -> List[str]:
    """Model ids ranked by lowest price per token, preferring long-context chat models."""
    try:
        data = client.request("GET", "/models")
    except (ProviderError, ConnectionError):
        return list(DEFAULT_MODELS)
    ranked = []
    for item in data.get("data", []):
        model_id = item.get("id")
        if not model_id or model_id == "openrouter/auto":  # router pseudo-model, not a real choice
            continue
        if any(tag in model_id for tag in ("embed", "whisper", "moderation")):
            continue
        pricing = item.get("pricing") or {}
        if pricing.get("prompt") in (None, "") and pricing.get("completion") in (None, ""):
            continue  # no published pricing: cannot be ranked by value
        try:
            cost = float(pricing.get("prompt") or 0) + float(pricing.get("completion") or 0)
        except (TypeError, ValueError):
            continue
        ranked.append((round(cost, 8), -int(item.get("context_length") or 0), model_id))
    ranked.sort()
    return [item[2] for item in ranked[:limit]] or list(DEFAULT_MODELS)


def _parse_json(text: str) -> Any:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except ValueError:
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start >= 0 and end > start:
            return json.loads(cleaned[start:end + 1])
        raise ProviderError("The model did not return valid JSON: %s" % text[:200]) from None


def plan_scenes(client: OpenRouterClient, prompt: str, *, duration: float = 30.0,
                language: str = "auto", model: str = DEFAULT_MODELS[0]) -> List[Scene]:
    """Ask the model for a scene breakdown; returns scenes with narration + search query."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Write a prompt describing the video you want.")
    n = max(3, min(12, round(duration / 8.0)))
    lang = "the same language as the prompt" if language in ("", "auto") else language
    content = client.chat(model, [{"role": "system",
                                   "content": PLAN_SYSTEM.format(n=n, language=lang,
                                                                 duration=duration,
                                                                 pace_words=round(duration / n * 2.5))},
                                  {"role": "user", "content": prompt}])
    raw = _parse_json(content)
    if not isinstance(raw, list) or not raw:
        raise ProviderError("The model returned no scenes.")
    scenes = []
    for i, item in enumerate(raw[:12]):
        if not isinstance(item, dict) or not item.get("narration"):
            continue
        scenes.append(Scene(i, str(item["narration"]).strip(),
                            str(item.get("query", "")).strip() or prompt[:60]))
    if not scenes:
        raise ProviderError("The model returned scenes without narration.")
    for i, scene in enumerate(scenes):
        scene.index = i
    return scenes


def _download(url: str, dest: Path, transport: Transport) -> Path:
    response = transport("GET", url, {"User-Agent": USER_AGENT}, None, 60.0)
    if response.status >= 400 or not response.body:
        raise ProviderError("Download failed (%d): %s" % (response.status, url[:120]))
    dest.write_bytes(response.body)
    return dest


def _commons_search(query: str, filetype: str, transport: Transport) -> List[Dict[str, Any]]:
    params = urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": "%s filetype:%s" % (query, filetype), "gsrlimit": "6", "gsrnamespace": "6",
        "prop": "imageinfo", "iiprop": "url|size|mime"})
    url = "https://commons.wikimedia.org/w/api.php?" + params
    try:
        data = transport("GET", url, {"User-Agent": USER_AGENT}, None, 20.0)
        if data.status >= 400:
            return []
        pages = data.json().get("query", {}).get("pages", {})
    except (ConnectionError, ValueError):
        return []
    items = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("url"):
            items.append(info)
    return items


def _openverse_search(query: str, orientation: str, transport: Transport) -> List[Dict[str, Any]]:
    params = {"q": query, "page_size": "6"}
    if orientation == "portrait":
        params["aspect_ratio"] = "tall"
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params)
    try:
        data = transport("GET", url, {"User-Agent": USER_AGENT}, None, 20.0)
        if data.status >= 400:
            return []
        return data.json().get("results", [])
    except (ConnectionError, ValueError):
        return []


def _pollinations_url(query: str, width: int, height: int) -> str:
    seed = random.randint(1, 10**6)
    prompt = urllib.parse.quote(query)
    return ("https://image.pollinations.ai/prompt/%s?width=%d&height=%d&nologo=true&seed=%d"
            % (prompt, width, height, seed))


def _query_variants(query: str) -> List[str]:
    """Progressively broader keyword sets: the full query first, then shorter prefixes."""
    words = query.split()
    variants: List[str] = []
    for n in range(len(words), 1, -1):
        variant = " ".join(words[:n])
        if variant not in variants:
            variants.append(variant)
    return variants[:3] or [query]


def find_asset(query: str, orientation: str, workdir: Path, index: int,
               transport: Optional[Transport] = None) -> Tuple[Path, str]:
    """Find or generate one visual for a scene. Returns (path, source description)."""
    transport = transport or urllib_transport
    workdir.mkdir(parents=True, exist_ok=True)
    query = (query or "").strip() or "abstract background"
    portrait = orientation == "portrait"
    width, height = (720, 1280) if portrait else (1280, 720)

    for info in _commons_search(query, "video", transport):
        mime = info.get("mime", "")
        if mime in ("video/webm", "video/mp4") and info.get("size", 10**9) < 80 * 1024 * 1024:
            ext = "webm" if mime == "video/webm" else "mp4"
            try:
                path = _download(info["url"], workdir / ("scene_%02d.%s" % (index, ext)), transport)
                return path, "wikimedia video"
            except ProviderError:
                continue

    for variant in _query_variants(query):
        for item in _openverse_search(variant, orientation, transport):
            url = item.get("url") or item.get("thumbnail")
            if not url:
                continue
            try:
                path = _download(url, workdir / ("scene_%02d.jpg" % index), transport)
                return path, "openverse image"
            except ProviderError:
                continue

    for variant in _query_variants(query):
        for info in _commons_search(variant, "bitmap", transport):
            if info.get("width", 0) >= 640:
                try:
                    path = _download(info["url"], workdir / ("scene_%02d.jpg" % index), transport)
                    return path, "wikimedia image"
                except ProviderError:
                    continue

    return generate_asset(query, orientation, workdir, index, transport)


POLLINATIONS_ATTEMPTS = 3


def generate_asset(query: str, orientation: str, workdir: Path, index: int,
                   transport: Optional[Transport] = None) -> Tuple[Path, str]:
    """Generate one image for the scene with Pollinations (keyless), retrying on failures."""
    transport = transport or urllib_transport
    workdir.mkdir(parents=True, exist_ok=True)
    query = (query or "").strip() or "abstract background"
    width, height = (720, 1280) if orientation == "portrait" else (1280, 720)
    last: Optional[ProviderError] = None
    for _ in range(POLLINATIONS_ATTEMPTS):
        try:
            path = _download(_pollinations_url(query, width, height),
                             workdir / ("scene_%02d.jpg" % index), transport)
            return path, "generated (pollinations)"
        except ProviderError as exc:
            last = exc
    raise ProviderError(
        "No asset found for scene %d (%r): Pollinations failed %d times (%s). "
        "The free image service may be rate-limited or temporarily down."
        % (index, query, POLLINATIONS_ATTEMPTS, str(last)[:160])) from None


def _image_extension(raw: bytes) -> str:
    """File extension from magic bytes; SVG is rejected (ffmpeg cannot rasterize it)."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    head = raw.lstrip()[:80].lower()
    if b"<svg" in head or head.startswith(b"<?xml"):
        raise ProviderError("The model returned an SVG image, which the renderer cannot use.")
    raise ProviderError("Unrecognized image format (first bytes: %r)" % raw[:12])


def _rasterize_svg(raw: bytes, width: int = 1600) -> bytes:
    """SVG -> PNG bytes via cairosvg when it is installed (Colab notebooks have it)."""
    try:
        import cairosvg  # noqa: F401  (import may also fail at C-library load time)
    except (ImportError, OSError):
        raise ProviderError("The model returned an SVG image: install cairosvg to use it "
                            "(pip install cairosvg), or pick a different image model.") from None
    try:
        return cairosvg.svg2png(bytestring=raw, output_width=width)
    except Exception as exc:
        raise ProviderError("The model returned an invalid SVG image: %s" % str(exc)[:200]) \
            from None


def generate_illustration(client: OpenRouterClient, prompt: str, dest_base: Path,
                          model: str = ILLUSTRATION_MODELS[0], style: str = "",
                          aspect_ratio: str = "16:9", extra: str = "") -> Path:
    """Generate one illustration with an OpenRouter image model, saved as dest_base.<ext>.

    ``style`` picks a preset prefix from ``ILLUSTRATION_STYLES``; ``extra`` is any free-text
    style detail the user adds on top. Some models reject ``image_config`` or the pure
    "image" modality: both fall back automatically before giving up."""
    parts = (ILLUSTRATION_STYLES.get(style, ""), (extra or "").strip(), (prompt or "").strip())
    text = " ".join(p for p in parts if p).strip()
    if not text:
        raise ValueError("Describe what the illustration should show.")
    urls: List[str] = []
    for aspect, mods in ((aspect_ratio, ["image"]), (None, ["image"]),
                         (aspect_ratio, ["image", "text"])):
        try:
            urls = client.image(model, text, aspect, mods)
        except ProviderError:
            if aspect is None:
                raise
            continue
        if urls:
            break
    for url in urls:
        try:
            if url.startswith("data:"):
                raw = base64.b64decode(url.split(",", 1)[1])
            else:
                response = client.transport("GET", url, {"User-Agent": USER_AGENT}, None, 60.0)
                raw = response.body if response.status < 400 else b""
        except (ProviderError, ConnectionError):
            continue
        if not raw:
            continue
        head = raw.lstrip()[:512].lower()
        if b"<svg" in head or head.startswith(b"<?xml"):
            try:
                raw = _rasterize_svg(raw)
            except ProviderError:
                continue
        try:
            ext = _image_extension(raw)
        except ProviderError:
            continue
        dest = Path(str(dest_base) + "." + ext)
        dest.write_bytes(raw)
        return dest
    raise ProviderError("The image model %s returned no usable image." % model) from None


def _first_frame(video: Path, dest: Path) -> bool:
    from .audio import ffmpeg_path, _ffmpeg
    if not ffmpeg_path():
        return False
    try:
        _ffmpeg(["-ss", "1", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(dest)])
        return dest.is_file()
    except ConfigError:
        return False


def verify_asset(client: OpenRouterClient, scene: Scene, model: str) -> Tuple[bool, str]:
    """Vision check: does the asset plausibly match the scene? Videos are checked on one frame."""
    path = scene.asset_path
    if not path or not Path(path).is_file():
        return False, "no asset"
    media = Path(path)
    frame = media
    if media.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv"):
        frame = media.with_suffix(".frame.jpg")
        if not _first_frame(media, frame):
            return True, "skipped: video frame check needs ffmpeg"
    encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
    content = [{"type": "text", "text": VERIFY_PROMPT.format(query=scene.query)},
               {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}}]
    answer = client.chat(model, [{"role": "user", "content": content}], max_tokens=200)
    try:
        verdict = _parse_json_object(answer)
        return bool(verdict.get("match")), str(verdict.get("reason", ""))[:200]
    except ProviderError:
        return True, "skipped: unreadable vision answer"


def _parse_json_object(text: str) -> Dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
    except ValueError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ProviderError("no JSON object in vision answer") from None
        data = json.loads(cleaned[start:end + 1])
    if not isinstance(data, dict):
        raise ProviderError("vision answer is not an object")
    return data


def build_script(scenes: List[Scene], title: str = "") -> str:
    """Scenes -> Markdown script with ![](asset) per scene, ready for render_video."""
    lines = []
    if title.strip():
        lines += ["# " + title.strip(), ""]
    for scene in scenes:
        if scene.asset_path:
            lines += ["![](%s)" % scene.asset_path, ""]
        lines += [scene.narration, ""]
    return "\n".join(lines).strip() + "\n"


def plan_and_fetch(client: OpenRouterClient, prompt: str, workdir: Path, *,
                   duration: float = 30.0, language: str = "auto",
                   model: str = DEFAULT_MODELS[0], orientation: str = "landscape",
                   verify: bool = True, vision_model: str = DEFAULT_MODELS[0],
                   transport: Optional[Transport] = None,
                   progress: Optional[Any] = None) -> List[Scene]:
    """Full builder: plan scenes, fetch one asset each, optionally verify with vision."""
    scenes = plan_scenes(client, prompt, duration=duration, language=language, model=model)
    for scene in scenes:
        try:
            path, source = find_asset(scene.query, orientation, workdir, scene.index, transport)
        except (ProviderError, ConnectionError) as exc:
            scene.asset_path, scene.source = None, "none"
            scene.reason = "no asset: %s" % str(exc)[:120]
            if progress:
                progress(scene)
            continue
        scene.asset_path, scene.source = str(path), source
        if progress:
            progress(scene)
        if verify and client.api_key:
            try:
                scene.verified, scene.reason = verify_asset(client, scene, vision_model)
            except (ProviderError, ConnectionError) as exc:
                scene.verified, scene.reason = None, "skipped: %s" % str(exc)[:120]
    return scenes
