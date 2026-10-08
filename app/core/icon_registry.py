"""Closed, server-owned configuration for the first ten AdminIcons assets."""

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MASTER_ROOT = PROJECT_ROOT / "data" / "icons" / "masters"
DERIVATIVE_ROOT = PROJECT_ROOT / "static" / "icons"


@dataclass(frozen=True)
class IconSpec:
    category: str
    key: str
    master: Path
    derivative: Path
    max_size: tuple[int, int]
    format: Literal["PNG", "WEBP"]
    lossless: bool = True
    quality: int = 90
    compress_level: int = 9
    resize: bool = True


def _webp(category: str, key: str, filename: str, size: tuple[int, int]) -> IconSpec:
    return IconSpec(category, key, MASTER_ROOT / category / filename,
                    DERIVATIVE_ROOT / category / Path(filename).with_suffix(".webp"),
                    size, "WEBP")


ICON_REGISTRY = MappingProxyType({
    ("home", "museum"): IconSpec(
        "home", "museum", MASTER_ROOT / "home" / "museum-leviathan-icon-final.png",
        DERIVATIVE_ROOT / "home" / "museum-leviathan-icon-final.webp", (1200, 1200),
        "WEBP", lossless=False, quality=90,
    ),
    ("home", "order"): IconSpec(
        "home", "order", MASTER_ROOT / "home" / "sort-imperial-transparent.png",
        DERIVATIVE_ROOT / "home" / "sort-imperial-transparent.webp", (1200, 1200),
        "WEBP", lossless=False, quality=90,
    ),
    ("home", "tap_list"): IconSpec(
        "home", "tap_list", MASTER_ROOT / "home" / "tap-list-icon-transparent.png",
        DERIVATIVE_ROOT / "home" / "tap-list-icon-transparent.webp", (1200, 1200),
        "WEBP", lossless=False, quality=90,
    ),
    ("tutorial", "triton_intro"): IconSpec(
        "tutorial", "triton_intro", MASTER_ROOT / "tutorial" / "triton-intro-taplist.png",
        DERIVATIVE_ROOT / "tutorial" / "triton-intro-taplist.webp", (900, 600),
        "WEBP", lossless=False, quality=90,
    ),
    ("tutorial", "triton_beerdetail_details"): IconSpec(
        "tutorial", "triton_beerdetail_details", MASTER_ROOT / "tutorial" / "triton-beerdetail-details.png",
        DERIVATIVE_ROOT / "tutorial" / "triton-beerdetail-details.webp", (900, 600),
        "WEBP", lossless=False, quality=90,
    ),
    ("tutorial", "triton_beerdetail_brewery_left"): IconSpec(
        "tutorial", "triton_beerdetail_brewery_left", MASTER_ROOT / "tutorial" / "triton-beerdetail-brewery-left.png",
        DERIVATIVE_ROOT / "tutorial" / "triton-beerdetail-brewery-left.webp", (900, 600),
        "WEBP", lossless=False, quality=90,
    ),
    ("branding", "tiburon"): IconSpec(
        "branding", "tiburon", MASTER_ROOT / "branding" / "tiburon.png",
        DERIVATIVE_ROOT / "branding" / "tiburon.webp", (512, 512), "WEBP",
        lossless=True, resize=False,
    ),
    ("glassware", "taster"): IconSpec(
        "glassware", "taster", MASTER_ROOT / "glassware" / "taster-120ml.png",
        DERIVATIVE_ROOT / "glassware" / "taster-120ml.webp", (1254, 1254),
        "WEBP", lossless=False, quality=90, resize=False,
    ),
    ("glassware", "pinta_chica"): IconSpec(
        "glassware", "pinta_chica", MASTER_ROOT / "glassware" / "pint-small-330ml.png",
        DERIVATIVE_ROOT / "glassware" / "pint-small-330ml.webp", (1133, 1388),
        "WEBP", lossless=False, quality=90, resize=False,
    ),
    ("glassware", "pinta_grande"): IconSpec(
        "glassware", "pinta_grande", MASTER_ROOT / "glassware" / "pint-large-500ml.png",
        DERIVATIVE_ROOT / "glassware" / "pint-large-500ml.webp", (1254, 1254),
        "WEBP", lossless=False, quality=90, resize=False,
    ),
    ("glassware", "jarra_chica"): IconSpec(
        "glassware", "jarra_chica", MASTER_ROOT / "glassware" / "pitcher-small-1l.png",
        DERIVATIVE_ROOT / "glassware" / "pitcher-small-1l.webp", (1305, 1206),
        "WEBP", lossless=False, quality=90, resize=False,
    ),
    ("glassware", "jarra_grande"): IconSpec(
        "glassware", "jarra_grande", MASTER_ROOT / "glassware" / "pitcher-large-1-9l.png",
        DERIVATIVE_ROOT / "glassware" / "pitcher-large-1-9l.webp", (1305, 1206),
        "WEBP", lossless=False, quality=90, resize=False,
    ),
})
