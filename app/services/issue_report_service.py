from collections import deque
from datetime import timezone
from hashlib import sha256
from io import BytesIO
import json
import logging
import math
import threading
import time
from uuid import uuid4
import warnings

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.models.issue_report import IssueReport

MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_DIMENSION = 16_384
MAX_REQUEST_BYTES = MAX_SCREENSHOT_BYTES + 64 * 1024
MAX_REPORT_BYTES = 32 * 1024
logger = logging.getLogger(__name__)


class ReportRateLimiter:
    """Bounded process-local limits. Proxy/shared limits are required for a fleet."""

    def __init__(self):
        self.lock = threading.Lock()
        self.clients = {}
        self.global_attempts = deque()

    def check(self, client):
        now = time.monotonic()
        window = settings.issue_report_rate_window_seconds
        with self.lock:
            for key in list(self.clients):
                attempts = self.clients[key]
                while attempts and attempts[0] <= now - window:
                    attempts.popleft()
                if not attempts:
                    del self.clients[key]
            while self.global_attempts and self.global_attempts[0] <= now - 60:
                self.global_attempts.popleft()
            attempts = self.clients.get(client, deque())
            retry = 0
            if len(attempts) >= settings.issue_report_rate_limit:
                retry = max(1, math.ceil(attempts[0] + window - now))
            if len(self.global_attempts) >= settings.issue_report_global_per_minute:
                retry = max(retry, max(1, math.ceil(self.global_attempts[0] + 60 - now)))
            if client not in self.clients and len(self.clients) >= 4096:
                retry = max(retry, window)
            if retry:
                raise HTTPException(429, "Too many reports; retry later", headers={"Retry-After": str(retry)})
            attempts.append(now)
            self.clients[client] = attempts
            self.global_attempts.append(now)


limiter = ReportRateLimiter()


def normalize_screenshot(source):
    if source is None:
        return None
    if not source or len(source) > MAX_SCREENSHOT_BYTES:
        raise HTTPException(413, "Screenshot must be nonempty and at most 5 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(source)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                    raise HTTPException(415, "Use a single-frame JPEG, PNG or WebP")
                width, height = image.size
                if min(width, height) < 1 or max(width, height) > MAX_DIMENSION or width * height > MAX_PIXELS:
                    raise HTTPException(413, "Screenshot exceeds dimension or pixel limits")
                image.load()
                oriented = ImageOps.exif_transpose(image)
                try:
                    # Fresh pixel-only canvas strips EXIF, GPS, comments and profiles.
                    with oriented.convert("RGBA") as rgba, Image.new("RGB", oriented.size, "white") as clean:
                        clean.paste(rgba, mask=rgba.getchannel("A"))
                        clean.thumbnail((2048, 2048))
                        output = BytesIO()
                        clean.save(output, "JPEG", quality=85, optimize=True)
                        normalized = output.getvalue()
                finally:
                    oriented.close()
        if len(normalized) > 3 * 1024 * 1024:
            raise HTTPException(413, "Normalized screenshot exceeds storage limit")
        return normalized
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise HTTPException(413, "Screenshot exceeds decoder safety limit") from error
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as error:
        raise HTTPException(415, "Invalid screenshot content") from error


def _receipt(report):
    return {"report_id": report.id, "stored_at": report.created_at.replace(tzinfo=timezone.utc)}


def store_report(db, payload, source):
    canonical = payload.model_dump(mode="json", exclude={"idempotency_key"})
    # Digest the original file bytes so replacing an attachment conflicts even if
    # two differently encoded files normalize to the same visible pixels.
    canonical["screenshot_sha256"] = sha256(source).hexdigest() if source is not None else None
    digest = sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    def original():
        return db.scalar(select(IssueReport).where(IssueReport.idempotency_key == payload.idempotency_key))

    def replay(report):
        if report.payload_digest != digest:
            raise HTTPException(409, "Idempotency key already used with different content")
        return _receipt(report), True

    try:
        existing = original()
        if existing:
            return replay(existing)
        screenshot = normalize_screenshot(source)
        report = IssueReport(
            id=str(uuid4()), categories=payload.categories, description=payload.description,
            diagnostic_consent=payload.diagnostic_consent, schema_version=payload.schema_version,
            diagnostics=payload.diagnostics.model_dump(mode="json") if payload.diagnostics is not None else None,
            screenshot=screenshot, screenshot_mime="image/jpeg" if screenshot else None,
            idempotency_key=payload.idempotency_key, payload_digest=digest,
            notification_state="pending",
        )
        db.add(report)
        try:
            db.commit()
        except IntegrityError:
            # The unique DB constraint, rather than a process lock, arbitrates races.
            db.rollback()
            existing = original()
            if existing:
                return replay(existing)
            raise
        return _receipt(report), False
    except SQLAlchemyError as error:
        db.rollback()
        # SQLAlchemy exception strings may include report text/binary parameters.
        logger.error("Issue report storage failed (%s)", type(error).__name__)
        raise HTTPException(503, "Report storage temporarily unavailable; retry with the same key") from error
