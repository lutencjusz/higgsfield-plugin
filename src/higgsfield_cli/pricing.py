"""Przybliżony koszt Seedance 2.0 liczony lokalnie.

API /estimate dla Seedance zwraca tylko opis reguły (type=description), bez kwoty:
  tokeny = ceil(sekundy × szerokość × wysokość × 24 fps / 1024)
  za 1000 tokenów: 480p/720p/1080p $0.014, 4K $0.008 (przed rabatami)
Wymiary wyjścia nie są udokumentowane — przyjmujemy krótszy bok = rozdzielczość
(480/720/1080/2160) i dłuższy wg proporcji, więc wynik jest szacunkiem.
"""

import math

FPS = 24
SHORT_SIDE = {"480p": 480, "720p": 720, "1080p": 1080, "4k": 2160}
USD_PER_1K_TOKENS = {"480p": 0.014, "720p": 0.014, "1080p": 0.014, "4k": 0.008}
# image-to-video: kadr wynika z obrazu wejściowego — zakładamy 16:9
DEFAULT_ASPECT = "16:9"


def output_size(resolution: str, aspect_ratio: str) -> tuple[int, int]:
    w, h = (int(x) for x in aspect_ratio.split(":"))
    short = SHORT_SIDE[resolution]
    long_ = round(short * max(w, h) / min(w, h))
    return (long_, short) if w >= h else (short, long_)


def seedance_estimate(args: dict) -> dict:
    aspect = args.get("aspect_ratio")
    assumed = aspect is None
    aspect = aspect or DEFAULT_ASPECT
    width, height = output_size(args["resolution"], aspect)
    tokens = math.ceil(args["duration"] * width * height * FPS / 1024)
    usd = tokens / 1000 * USD_PER_1K_TOKENS[args["resolution"]]
    result = {
        "approx_usd": round(usd, 2),
        "video_tokens": tokens,
        "assumed_size": f"{width}x{height}",
        "duration": args["duration"],
    }
    if assumed:
        result["note"] = "Proporcje zależą od obrazu wejściowego — przyjęto 16:9."
    return result
