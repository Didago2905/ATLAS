"""Focused reporter tests, using temporary SQLite/storage; never import app.main."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api import issue_reports
from app.core.config import settings
from app.core.database import Base, get_db
from app.models.issue_report import IssueReport
from app.services import issue_report_service as service


def picture(format="PNG", size=(100, 60), metadata=False):
    output = BytesIO()
    with Image.new("RGB", size, "red") as image:
        options = {}
        if metadata and format == "JPEG":
            exif = Image.Exif()
            exif[274] = 6
            exif[270] = "PRIVATE EXIF COMMENT"
            options = {"exif": exif, "icc_profile": b"PRIVATE PROFILE"}
        if metadata and format == "PNG":
            info = PngImagePlugin.PngInfo()
            info.add_text("private", "PRIVATE PNG COMMENT")
            options = {"pnginfo": info}
        image.save(output, format, **options)
    return output.getvalue()


class IssueReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = create_engine(f"sqlite:///{(self.root / 'reports.db').as_posix()}",
                                    connect_args={"check_same_thread": False, "timeout": 15})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        app = FastAPI()
        app.include_router(issue_reports.router)
        (self.root / "static").mkdir()
        app.mount("/static", StaticFiles(directory=self.root / "static"))

        def database():
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        for name, value in [("issue_report_rate_limit", 100), ("issue_report_global_per_minute", 1000)]:
            override = patch.object(settings, name, value)
            override.start()
            self.addCleanup(override.stop)
        override = patch.object(issue_reports, "limiter", service.ReportRateLimiter())
        override.start()
        self.addCleanup(override.stop)

    def payload(self, **changes):
        return {"schema_version": 1, "categories": ["Tap List"],
                "description": "La lista no aparece al abrir la página.",
                "diagnostic_consent": False, "idempotency_key": str(uuid4()), **changes}

    def submit(self, payload=None, image=None, mime="image/png"):
        parts = {"report": (None, json.dumps(payload if payload is not None else self.payload()), "application/json")}
        if image is not None:
            parts["screenshot"] = ("../../private.png", image, mime)
        return self.client.post("/public/issue-reports", files=parts)

    def count(self):
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(IssueReport))

    def stored(self, report_id):
        with Session(self.engine) as session:
            return session.get(IssueReport, report_id)

    def test_valid_submission_persists_after_connection_reopened(self):
        response = self.submit(self.payload(description="  La lista no aparece al abrir la página.  "))
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        receipt = response.json()
        self.engine.dispose()
        report = self.stored(receipt["report_id"])
        self.assertEqual(report.description, "La lista no aparece al abrir la página.")
        self.assertEqual(report.categories, ["Tap List"])
        self.assertIsNone(report.diagnostics)
        self.assertIsNone(report.screenshot)
        self.assertFalse(report.diagnostic_consent)
        self.assertEqual(report.schema_version, 1)
        self.assertEqual(report.notification_state, "pending")
        self.assertTrue(receipt["stored_at"].endswith("Z"))

    def test_invalid_categories_descriptions_keys_and_unknown_fields(self):
        for changes in [
            {"categories": []}, {"categories": ["arbitrary"]}, {"categories": ["Otro", "Otro"]},
            {"description": "   short   "}, {"description": "x" * 2001}, {"description": " " * 100},
            {"description": "🐟" * 10},
            {"description": 123}, {"idempotency_key": "not-a-uuid"},
            {"diagnostic_consent": "false"}, {"token": "DO NOT ECHO"}, {"schema_version": 2},
        ]:
            with self.subTest(changes=changes):
                response = self.submit(self.payload(**changes))
                self.assertEqual(response.status_code, 422, response.text)
                self.assertNotIn("DO NOT ECHO", response.text)
        self.assertEqual(self.count(), 0)

    def snapshot(self, **changes):
        return {"schemaVersion": 1, "timestamp": "2026-11-02T12:00:00.000Z", "timezone": "America/Mexico_City",
                "route": "/", "viewport": {"width": 390, "height": 844}, "network": None, **changes}

    def test_consent_off_rejects_snapshot_and_consent_on_stores_allowlist(self):
        response = self.submit(self.payload(diagnostics=self.snapshot()))
        self.assertEqual(response.status_code, 422)
        response = self.submit(self.payload(diagnostic_consent=True, diagnostics=self.snapshot()))
        self.assertEqual(response.status_code, 201, response.text)
        report = self.stored(response.json()["report_id"])
        self.assertEqual(report.diagnostics["route"], "/")
        self.assertIsNone(report.diagnostics["network"])
        self.assertIsNone(report.diagnostics["browser"])

    def test_diagnostics_reject_sensitive_unknown_unbounded_and_invalid_values(self):
        for changes in [
            {"cookies": "PRIVATE COOKIE"}, {"route": "/?token=PRIVATE TOKEN"},
            {"route": "/admin/beers"}, {"route": "/arbitrary/PRIVATE"},
            {"viewport": {"width": -1}}, {"browser": {"name": "Safari", "token": "PRIVATE"}},
            {"timezone": "x" * 201}, {"timestamp": "not-a-date"},
            {"timestamp": "2026-11-02T12:00:00"}, {"network": {"rttMs": float("inf")}},
        ]:
            with self.subTest(changes=changes):
                response = self.submit(self.payload(diagnostic_consent=True, diagnostics=self.snapshot(**changes)))
                self.assertEqual(response.status_code, 422, response.text)
                self.assertNotIn("PRIVATE", response.text)

    def test_jpeg_orientation_and_metadata_stripping(self):
        response = self.submit(image=picture("JPEG", metadata=True), mime="image/jpeg")
        self.assertEqual(response.status_code, 201, response.text)
        report = self.stored(response.json()["report_id"])
        with Image.open(BytesIO(report.screenshot)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (60, 100))
            self.assertFalse(image.getexif())
            self.assertNotIn("icc_profile", image.info)
        self.assertNotIn(b"PRIVATE", report.screenshot)
        self.assertEqual(report.screenshot_mime, "image/jpeg")

    def test_png_webp_content_detection_and_normalization(self):
        for format in ["PNG", "WEBP"]:
            with self.subTest(format=format):
                response = self.submit(image=picture(format, (2400, 1200), metadata=True), mime="text/plain")
                self.assertEqual(response.status_code, 201, response.text)
                raw = self.stored(response.json()["report_id"]).screenshot
                self.assertNotIn(b"PRIVATE", raw)
                with Image.open(BytesIO(raw)) as image:
                    self.assertEqual(image.size, (2048, 1024))
                    self.assertEqual(image.format, "JPEG")

    def test_malformed_unsupported_animated_and_oversize_images(self):
        animated = BytesIO()
        with Image.new("RGB", (10, 10), "red") as first, Image.new("RGB", (10, 10), "blue") as second:
            first.save(animated, "PNG", save_all=True, append_images=[second])
        for source, status in [(b"<svg/>", 415), (b"broken", 415),
                               (picture("GIF"), 415), (animated.getvalue(), 415),
                               (b"x" * (service.MAX_SCREENSHOT_BYTES + 1), 413), (b"", 413)]:
            with self.subTest(size=len(source)):
                self.assertEqual(self.submit(image=source).status_code, status)
        self.assertEqual(self.count(), 0)

    def test_pixel_and_dimension_limits_before_decode(self):
        self.assertEqual(self.submit(image=picture(size=(5000, 4001))).status_code, 413)
        self.assertEqual(self.submit(image=picture(size=(16_385, 1))).status_code, 413)
        with patch.object(service, "MAX_PIXELS", 5000):
            self.assertEqual(self.submit(image=picture(size=(100, 100))).status_code, 413)
        with patch.object(service, "MAX_DIMENSION", 50):
            self.assertEqual(self.submit(image=picture()).status_code, 413)

    def test_request_limits_declared_and_chunked(self):
        response = self.client.post("/public/issue-reports", content=b"x",
            headers={"content-type": "multipart/form-data; boundary=x", "content-length": str(service.MAX_REQUEST_BYTES + 1)})
        self.assertEqual(response.status_code, 413)
        with patch.object(issue_reports, "MAX_REQUEST_BYTES", 100):
            response = self.client.post("/public/issue-reports", content=iter([b"x" * 60, b"x" * 60]),
                headers={"content-type": "multipart/form-data; boundary=x"})
            self.assertEqual(response.status_code, 413)
        self.assertEqual(self.count(), 0)

    def test_multipart_bounds_and_no_json_endpoint(self):
        self.assertEqual(self.client.post("/public/issue-reports", json=self.payload()).status_code, 415)
        self.assertEqual(self.client.post("/public/issue-reports", files={"report": (None, "x" * 40000)}).status_code, 400)
        self.assertEqual(self.client.post("/public/issue-reports", files=[
            ("report", (None, json.dumps(self.payload()))), ("report", (None, "{}"))]).status_code, 400)
        self.assertEqual(self.client.post("/public/issue-reports", files={"other": (None, "{}")}).status_code, 422)
        self.assertEqual(self.client.post("/public/issue-reports", content=b"broken",
            headers={"content-type": "multipart/form-data"}).status_code, 400)

    def test_idempotent_retries_conflicts_and_attachment_digest(self):
        payload = self.payload(categories=["Otro", "Tap List"])
        source = picture()
        first = self.submit(payload, source)
        second = self.submit({**payload, "categories": ["Tap List", "Otro"]}, source)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(self.submit({**payload, "description": "Una descripción distinta del mismo problema."}, source).status_code, 409)
        self.assertEqual(self.submit(payload, picture(size=(80, 80))).status_code, 409)
        self.assertEqual(self.count(), 1)

    def test_concurrent_requests_create_one_row(self):
        payload = self.payload()
        barrier = threading.Barrier(2)
        normalize = service.normalize_screenshot

        def simultaneous(source):
            barrier.wait(timeout=10)
            return normalize(source)

        with patch.object(service, "normalize_screenshot", side_effect=simultaneous):
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(lambda _: self.submit(payload), range(2)))
        self.assertEqual(sorted(item.status_code for item in responses), [200, 201])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(self.count(), 1)

    def test_concurrent_different_payloads_with_same_key_conflict(self):
        payload = self.payload()
        barrier = threading.Barrier(2)

        def simultaneous(source):
            barrier.wait(timeout=10)
            return None

        with patch.object(service, "normalize_screenshot", side_effect=simultaneous):
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(self.submit, [payload, {
                    **payload, "description": "Este es otro problema distinto del primero.",
                }]))
        self.assertEqual(sorted(item.status_code for item in responses), [201, 409])
        self.assertEqual(self.count(), 1)

    def test_rate_limit_and_retry_after_before_body_processing(self):
        with patch.object(settings, "issue_report_rate_limit", 2):
            self.assertEqual(self.submit().status_code, 201)
            self.assertEqual(self.submit().status_code, 201)
            response = self.submit()
            self.assertEqual(response.status_code, 429)
            self.assertGreater(int(response.headers["retry-after"]), 0)
            self.assertEqual(self.client.post("/public/issue-reports", headers={"X-Forwarded-For": "different"}).status_code, 429)
        self.assertEqual(self.count(), 2)

    def test_global_limit_and_expiration(self):
        with patch.object(settings, "issue_report_global_per_minute", 1):
            limiter = service.ReportRateLimiter()
            with patch.object(service.time, "monotonic", return_value=1000):
                limiter.check("one")
                with self.assertRaises(Exception) as error:
                    limiter.check("two")
                self.assertEqual(error.exception.status_code, 429)
            with patch.object(service.time, "monotonic", return_value=1700):
                limiter.check("two")
                self.assertNotIn("one", limiter.clients)

    def test_no_public_report_or_attachment_access(self):
        response = self.submit(image=picture())
        report_id = response.json()["report_id"]
        for path in ["/public/issue-reports", f"/public/issue-reports/{report_id}",
                     f"/public/issue-reports/{report_id}/screenshot", f"/static/{report_id}.jpg"]:
            self.assertIn(self.client.get(path).status_code, [404, 405])
        self.assertEqual(list((self.root / "static").iterdir()), [])

    def test_commit_failure_is_not_success_and_can_retry(self):
        payload = self.payload()
        with patch.object(Session, "commit", side_effect=OperationalError("private statement", {}, Exception("private"))):
            response = self.submit(payload)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", response.text)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.submit(payload).status_code, 201)


if __name__ == "__main__":
    unittest.main()
