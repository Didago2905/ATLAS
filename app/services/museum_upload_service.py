"""The two Museum upload routes and automatic Tap Image archiving.

No dependency on the external historical archive. All writers share one lock;
files are staged on their destination filesystem and restored on failure.
"""
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
from uuid import NAMESPACE_URL, uuid5
import warnings

from fastapi import HTTPException
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 50_000_000
CATEGORIES = {
    "fichas/antiguas": "carta_vieja", "fichas/actuales": "carta_nueva",
    "tap": "tap_list", "botellas": "etiquetas",
    "carta_vieja": "carta_vieja", "carta_nueva": "carta_nueva",
    "tap_list": "tap_list", "etiquetas": "etiquetas",
    "packaging": "packaging", "otros": "otros",
}
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp",
           "TIFF": "tif", "BMP": "bmp", "GIF": "gif"}
_thread_lock = threading.Lock()
logger = logging.getLogger(__name__)


@contextmanager
def _publication_lock():
    # OS lock also serializes independent server workers on this host.
    with _thread_lock:
        folder = ROOT / "data"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / ".museum-upload.lock").open("a+b") as lock:
            lock.seek(0, os.SEEK_END)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            deadline = time.monotonic() + 15
            while True:
                try:
                    lock.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise HTTPException(503, "Another Museum upload is in progress; retry")
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock, fcntl.LOCK_UN)


def read_registry():
    path = ROOT / "data/museum.json"
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_bytes())
        if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
            raise ValueError("Expected an artwork array")
        return items
    except (OSError, ValueError) as error:
        raise HTTPException(503, "Museum registry is unreadable; no upload published") from error


def _prepare(file):
    source = file.file.read(MAX_BYTES + 1)
    if len(source) > MAX_BYTES:
        raise HTTPException(413, "Image exceeds 25 MiB limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(source)) as image:
                extension = FORMATS.get(image.format)
                if not extension or getattr(image, "n_frames", 1) != 1:
                    raise HTTPException(415, "Use a single-frame JPEG, PNG, WebP, TIFF, BMP or GIF")
                if image.width * image.height > MAX_PIXELS:
                    raise HTTPException(413, "Image exceeds 50 megapixel limit")
                image.load()
                ImageOps.exif_transpose(image, in_place=True)
                # Keep raw source bytes separately; only normalize the derivatives.
                alpha = image.convert("RGBA").getchannel("A") if (
                    "A" in image.getbands() or "transparency" in image.info
                ) else None
                profile = image.info.get("icc_profile")
                if profile:
                    color = image if image.mode in {"RGB", "CMYK", "L"} else image.convert("RGB")
                    try:
                        rgb = ImageCms.profileToProfile(
                            color, ImageCms.ImageCmsProfile(BytesIO(profile)),
                            ImageCms.createProfile("sRGB"), outputMode="RGB",
                        )
                    finally:
                        if color is not image:
                            color.close()
                else:
                    rgb = image.convert("RGB")
                with rgb:
                    if alpha is not None:
                        with alpha, Image.new("RGB", rgb.size, "white") as white:
                            white.paste(rgb, mask=alpha)
                            rgb.paste(white)
                    rgb.thumbnail((800, 1000))
                    museum = BytesIO()
                    rgb.save(museum, "JPEG", quality=75, optimize=True, progressive=True)
                    rgb.thumbnail((600, 800))
                    operational = BytesIO()
                    rgb.save(operational, "JPEG", quality=75, optimize=True, progressive=True)
        return source, extension, museum.getvalue(), operational.getvalue()
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise HTTPException(413, "Image exceeds decoder safety limit") from error
    except (UnidentifiedImageError, OSError, ValueError, ImageCms.PyCMSError, SyntaxError) as error:
        raise HTTPException(400, "Invalid image data or color profile; nothing published") from error


def _stage(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".upload-", delete=False) as output:
        staged = Path(output.name)
        try:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            output.close()
            staged.unlink(missing_ok=True)
            raise
    return staged


def _publish(changes, commit=None, rollback=None):
    """Rollback normal I/O/DB failures; not a distributed crash transaction."""
    staged, backups, published, failures = {}, {}, [], []
    try:
        # Prepare every replacement and rollback file before publishing anything.
        for path, content in changes.items():
            staged[path] = _stage(path, content)
            backups[path] = _stage(path, path.read_bytes()) if path.exists() else None
        for path, candidate in staged.items():
            os.replace(candidate, path)
            published.append(path)
        if commit:
            commit()
    except BaseException as error:
        if rollback:
            try:
                rollback()
            except Exception as recovery_error:
                failures.append(recovery_error)
        for path in reversed(published):
            try:
                if backups[path] is None:
                    path.unlink(missing_ok=True)
                else:
                    os.replace(backups[path], path)
            except OSError as recovery_error:
                failures.append(recovery_error)
        if failures:
            # Retain rollback files for operator recovery if the filesystem fails again.
            logger.critical("Museum upload rollback incomplete; retain backups: %s", backups,
                            exc_info=True)
            raise HTTPException(500, "Publication recovery incomplete; administrator review required") from error
        raise
    finally:
        for candidate in staged.values():
            _cleanup(candidate)
        # A backup already restored is absent. Keep any remaining backups if recovery failed.
        if not failures:
            for backup in backups.values():
                if backup:
                    _cleanup(backup)


def _cleanup(path):
    # Cleanup errors must not turn a committed publication into a false failure.
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove upload temporary file: %s", path, exc_info=True)


def artwork_identity(category, digest, beer_id=None):
    """Read-only identity/path calculation shared by uploads and local audits."""
    if category not in CATEGORIES:
        raise HTTPException(400, "Unknown Museum category")
    scope = f"beer:{beer_id}" if beer_id is not None else f"museum:{CATEGORIES[category]}"
    artwork_id = str(uuid5(NAMESPACE_URL, f"atlas:{scope}:{digest}"))
    return artwork_id, f"{CATEGORIES[category]}/{artwork_id}.jpg"


def upload_artwork(file, category, metadata=None, *, beer=None, db=None, register=True):
    if category not in CATEGORIES:
        raise HTTPException(400, "Unknown Museum category")
    source, extension, museum, operational = _prepare(file)
    digest = sha256(source).hexdigest()
    artwork_id, relative = artwork_identity(category, digest, beer.id if beer is not None else None)
    museum_url = f"/static/museum/{relative}"
    master = ROOT / f"data/museum/masters/{digest}.{extension}"
    destination = ROOT / "static/museum" / relative
    with _publication_lock():
        if beer is not None:
            db.refresh(beer)
            if beer.is_deleted:
                raise HTTPException(404, "Beer not found")
        registry = read_registry()
        existing = next((item for item in registry if item.get("id") == artwork_id), None)
        artwork = existing or {
            "id": artwork_id, **(metadata or {}), "type": category,
            "category": CATEGORIES[category], "image_url": museum_url,
            "image_sha256": sha256(museum).hexdigest(),
            "source_sha256": digest,
            "source_filename": (file.filename or "upload").replace("\\", "/").split("/")[-1],
            "source_path": master.relative_to(ROOT).as_posix(),
            "source_beer_id": beer.id if beer is not None else None,
        }
        changes = {}
        # Immutable content-addressed source and artwork: never replace existing files.
        if master.exists():
            if master.read_bytes() != source:
                raise HTTPException(409, "Historical source identity conflict")
        else:
            changes[master] = source
        if not destination.exists():
            changes[destination] = museum
        elif sha256(destination.read_bytes()).hexdigest() != artwork["image_sha256"]:
            raise HTTPException(409, "Historical artwork identity conflict")
        image_url = None
        if beer is not None:
            image_url = f"/images/beerTablesTapList/{beer.id}.jpg?v={digest}"
            changes[ROOT / f"frontend/public/images/beerTablesTapList/{beer.id}.jpg"] = operational
        if register and existing is None:
            changes[ROOT / "data/museum.json"] = json.dumps(
                [*registry, artwork], ensure_ascii=False, indent=2,
            ).encode("utf-8")
        try:
            if beer is not None:
                beer.image_url = image_url
            _publish(changes, db.commit if beer is not None else None,
                     db.rollback if beer is not None else None)
        except HTTPException:
            raise
        except Exception as error:
            logger.exception("Museum publication failed")
            raise HTTPException(500, "Upload failed; previous publication restored") from error
        return {**artwork, "image_url": image_url or artwork["image_url"],
                "operational_updated": beer is not None,
                "historical_archived": register,
                "historical_created": register and existing is None,
                "historical_image_url": artwork["image_url"]}
