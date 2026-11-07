<div align="center">

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · **Español**

# AI Voiceover Studio — locución con IA, texto a voz y clonación de voz para YouTube y vídeos sin rostro

**AI Voiceover Studio es una herramienta de línea de comandos y librería de Python de código abierto que convierte un guion escrito en una locución con IA terminada —narración con varios personajes, clonación de voz, subtítulos SRT y un vídeo sencillo sin rostro (faceless)— con un solo comando.**

[![Tests](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/yanghhu/ai-voiceover-studio/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

```bash
voiceover script guion.md --voices voices.json -o out/
# -> out/voiceover.mp3  out/voiceover.srt  out/manifest.json
```

## Demo

<!-- Marcador de posición: sustituir por docs/assets/demo.gif -->

> 🎬 *El GIF de demostración llegará pronto.* Mientras tanto, la ejecución sin conexión (`--dry-run`) recorre todo el proceso (tiempos, subtítulos, vídeo) con audio en silencio y sin clave de API.

## Funciones: locución con IA, texto a voz y subtítulos

| | Qué obtienes |
| --- | --- |
| 🗣️ **Texto a voz (TTS)** | `voiceover say "..."`: una frase a MP3/WAV, con velocidad y etiquetas de estilo/emoción |
| 🎭 **Guiones con varios personajes** | líneas `[NARRADOR]:` / `[ALEX]:` en Markdown o TXT, cada personaje con su propia voz |
| 🧬 **Clonación de voz** | usa la URL de un audio de referencia (y su transcripción) como voz |
| 💬 **Subtítulos** | SRT a partir de la duración exacta de cada segmento, o por reconocimiento de voz |
| 🎞️ **Vídeo sin rostro** | imágenes + guion → MP4 tipo presentación con locución y subtítulos |
| ♻️ **Repetir de forma segura** | caché por línea y claves de idempotencia deterministas: lo que no cambia no se regenera |
| 🔌 **Motores intercambiables** | interfaz `VoiceProvider`; el motor remoto incluido es [Miragea](https://miragea.ai), y `dummy` funciona sin conexión |
| 🪶 **Ligero** | solo la biblioteca estándar de Python 3.9+; `moviepy` y `PyYAML` son opcionales; usa `ffmpeg` si está instalado |

## Inicio rápido

```bash
git clone https://github.com/yanghhu/ai-voiceover-studio.git
cd ai-voiceover-studio
pip install -e .

voiceover script examples/script.md --dry-run -o out/      # sin conexión ni clave

export MIRAGEA_API_KEY=...      # créala en https://miragea.ai/workspace/api
voiceover voices                # voces de tu cuenta (actor id)
voiceover say "¡Bienvenidos de nuevo al canal!" --voice <actor_id> -o hola.mp3
```

La clave solo se lee del entorno y solo se envía en la cabecera `Authorization` al servidor de la API; nunca se imprime ni se guarda. La salida MP3 requiere [ffmpeg](https://ffmpeg.org) (sin él, usa `.wav`).

## Guiones con varios personajes (diálogo y doblaje)

```markdown
[NARRADOR]: En un día despejado el cielo es azul. Pero la luz del sol es blanca.
[ALEX](tags=curious): ¿Blanca? A mí me parece amarilla.
[pause 0.8]
[NARRADOR](speed=1.05): La luz azul, de onda corta, se dispersa mucho más en la atmósfera.
```

`[NOMBRE]:` define quién habla, las líneas sin etiqueta continúan con el mismo personaje, una línea en blanco empieza un segmento nuevo y `[pause 1.5]` inserta silencio. Asigna voces en `voices.json` ([ejemplo](examples/voices.example.json)).

## Clonación de voz con un audio de referencia

```bash
voiceover say "Esta es mi propia voz, generada a partir de texto." \
  --voice https://example.com/mi-voz.wav --ref-text "Lo que dije exactamente en mi-voz.wav." \
  --lang es -o clonada.mp3
```

Clona solo tu propia voz o voces para las que tengas permiso explícito.

## Subtítulos (SRT) para YouTube

`--subtitles timing` (por defecto, texto literal del guion, sin llamadas extra a la API), `recognize` (reconocimiento de voz sobre la mezcla final) o `none`.

## Vídeo de YouTube sin rostro a partir de imágenes y un guion

```bash
pip install -e ".[video]"
voiceover video --images examples/slides/ --script examples/script.md -o video.mp4 --subtitles burn
voiceover video ... --size 1080x1920 -o short.mp4     # vertical para Shorts / Reels / TikTok
```

## Idiomas compatibles

Con el motor Miragea incluido: **chino, inglés, japonés, coreano, alemán, francés, ruso, portugués, español e italiano**.

## Preguntas frecuentes

Más respuestas en [docs/FAQ.md](docs/FAQ.md) (en inglés).

**¿Cómo añado una locución con IA a un vídeo de YouTube?** Escribe la narración en Markdown, ejecuta `voiceover script`, coloca `voiceover.mp3` en tu editor y sube `voiceover.srt` como subtítulos.

**¿Puedo clonar mi propia voz?** Sí: publica una grabación en una URL accesible para la API y usa `--voice` con `--ref-text`.

**¿Puedo probarlo sin clave de API?** Sí, `--dry-run` funciona totalmente sin conexión.

## Arquitectura, comparación y hoja de ruta

Consulta [Architecture](README.md#architecture), [How it compares](README.md#how-it-compares) y [Roadmap](README.md#roadmap) en la versión en inglés.

## Contribuir

Se agradecen issues y pull requests. Consulta [CONTRIBUTING.md](CONTRIBUTING.md); las pruebas (`pytest`) funcionan sin conexión.

## Licencia

[MIT](LICENSE) © 2026 Miragea contributors
