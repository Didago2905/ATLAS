"""Generate a validated derivative without modifying its registered master."""

import os
from pathlib import Path
import tempfile
import warnings
import shutil
from dataclasses import replace

from PIL import Image, ImageOps, features

from app.core.icon_registry import ICON_REGISTRY

MAX_MASTER_BYTES = 25 * 1024 * 1024
MAX_MASTER_PIXELS = 25_000_000


def regenerate_icon(category: str, key: str) -> dict:
    """Accept identifiers only; paths and processing options are server-owned.

    Master installation is outside this helper. Failures before publication
    leave an existing derivative untouched.
    """
    spec = ICON_REGISTRY.get((category, key))
    if spec is None:
        raise ValueError("Unknown icon")
    return _generate(spec)


def _generate(spec):
    if spec.format not in {"PNG", "WEBP"} or min(spec.max_size) <= 0:
        raise ValueError("Invalid icon configuration")
    if spec.format == "WEBP" and not features.check("webp"):
        raise RuntimeError("Pillow WebP support is unavailable")

    temporary = None
    try:
        with spec.master.open("rb") as source:
            master_bytes = os.fstat(source.fileno()).st_size
            if master_bytes > MAX_MASTER_BYTES:
                raise ValueError("Master exceeds byte limit")
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(source) as original:
                    if original.format not in {"PNG", "WEBP"}:
                        raise ValueError("Only PNG and WebP masters are supported")
                    if getattr(original, "n_frames", 1) != 1:
                        raise ValueError("Animated masters are not supported")
                    if original.width * original.height > MAX_MASTER_PIXELS:
                        raise ValueError("Master exceeds pixel limit")
                    try:
                        original.load()
                    except OSError as error:
                        raise ValueError("Invalid or incomplete image file") from error
                    master_metadata = {
                        "width": original.width, "height": original.height,
                        "bytes": master_bytes, "format": original.format,
                        "has_alpha": "A" in original.getbands() or "transparency" in original.info,
                    }
                    with ImageOps.exif_transpose(original) as oriented:
                        image = oriented.convert("RGBA")

        with image:
            if spec.resize and (image.width > spec.max_size[0] or image.height > spec.max_size[1]):
                image.thumbnail(spec.max_size, Image.Resampling.LANCZOS)
            expected_size = image.size
            expected_alpha = image.getchannel("A").tobytes()
            image.info.clear()
            spec.derivative.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=spec.derivative.parent, prefix=".icon-", suffix=".tmp", delete=False,
            ) as output:
                temporary = Path(output.name)
                if spec.format == "WEBP":
                    image.save(output, format="WEBP", lossless=spec.lossless,
                               quality=spec.quality, method=6, exact=True)
                else:
                    image.save(output, format="PNG", compress_level=spec.compress_level)
                output.flush()
                os.fsync(output.fileno())

        with Image.open(temporary) as result:
            result.load()
            if result.format != spec.format or result.size != expected_size:
                raise ValueError("Invalid encoded derivative")
            with result.convert("RGBA") as rgba:
                if rgba.getchannel("A").tobytes() != expected_alpha:
                    raise ValueError("Derivative alpha was not preserved")
            derivative_metadata = {
                "width": result.width, "height": result.height,
                "bytes": temporary.stat().st_size, "format": result.format,
                "has_alpha": "A" in result.getbands(),
            }

        os.replace(temporary, spec.derivative)
        temporary = None
        return {"category": spec.category, "key": spec.key,
                "master": master_metadata, "derivative": derivative_metadata}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def replace_icon_master(category: str, key: str, source) -> dict:
    spec = ICON_REGISTRY.get((category, key))
    if spec is None:
        raise ValueError("Unknown icon")
    spec.master.parent.mkdir(parents=True, exist_ok=True)
    spec.derivative.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=spec.master.parent, prefix=".upload-") as folder:
        staging = Path(folder)
        candidate = staging / "master"
        with candidate.open("wb") as output:
            size = 0
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_MASTER_BYTES:
                    raise ValueError("Master exceeds byte limit")
                output.write(chunk)
        report = _generate(replace(spec, master=candidate, derivative=staging / "derivative"))
        backup = staging / "previous-master"
        had_master = spec.master.exists()
        if had_master:
            shutil.copyfile(spec.master, backup)
        os.replace(candidate, spec.master)
        try:
            os.replace(staging / "derivative", spec.derivative)
        except OSError:
            if had_master:
                os.replace(backup, spec.master)
            else:
                spec.master.unlink()
            raise
        return report


def list_icons() -> list:
    def inspect(path):
        if not path.exists():
            return {"status": "missing"}
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    return {"status": "present", "width": image.width, "height": image.height,
                            "bytes": path.stat().st_size, "format": image.format,
                            "has_alpha": "A" in image.getbands() or "transparency" in image.info}
        except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            return {"status": "unreadable"}

    results = []
    for spec in ICON_REGISTRY.values():
        master, derivative = inspect(spec.master), inspect(spec.derivative)
        status = "ready" if master["status"] == derivative["status"] == "present" else "incomplete"
        results.append({"category": spec.category, "key": spec.key, "status": status,
                        "rules": {"max_width": spec.max_size[0], "max_height": spec.max_size[1],
                                  "format": spec.format, "lossless": spec.lossless,
                                  "quality": spec.quality, "compress_level": spec.compress_level,
                                  "resize": spec.resize, "crop": False, "upscale": False},
                        "master": master, "derivative": derivative})
    return results
