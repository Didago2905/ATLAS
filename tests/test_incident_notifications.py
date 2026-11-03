"""Temporary SQLite and fake HTTPS/Telegram only. Never import app.main."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from pathlib import Path
import socket
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import Session

from app.api import issue_reports
from app.core.database import get_db
from app.migrations.issue_report_delivery import DeliverySchemaError, check_delivery_schema, migrate
from app.models.issue_report import IssueReport
from app.services.incident_telegram import (
    CONNECT_TIMEOUT, MAX_RESPONSE_BYTES, READ_TIMEOUT, DeliveryResult, IncidentConfigurationError,
    NotificationContent, TelegramTransport, format_notification, incident_config,
)
from app.services.issue_report_service import ReportRateLimiter
from app.workers.incident_notifications import IncidentWorker, LEASE_SECONDS, acknowledge, claim_report, main, run_loop

PHASE2_SQL = """CREATE TABLE issue_reports (
 id VARCHAR(36) NOT NULL PRIMARY KEY, created_at DATETIME NOT NULL,
 categories JSON NOT NULL, description TEXT NOT NULL, diagnostic_consent BOOLEAN NOT NULL,
 schema_version INTEGER NOT NULL, diagnostics JSON, screenshot BLOB, screenshot_mime VARCHAR(32),
 idempotency_key VARCHAR(36) NOT NULL UNIQUE, payload_digest VARCHAR(64) NOT NULL,
 notification_state VARCHAR(16) NOT NULL)"""
NOW = datetime(2026, 11, 2, 12)


def configuration(enabled=True, max_attempts=6):
    # Synthetic values only; never read devtools credentials.
    return SimpleNamespace(telegram_incidents_enabled=enabled,
        telegram_incidents_bot_token=SecretStr("123456:" + "x" * 35),
        telegram_incidents_chat_id=SecretStr("-123456789"), telegram_incidents_max_attempts=max_attempts)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine("sqlite:///" + (Path(self.temp.name) / "reports.sqlite3").as_posix(),
                                    connect_args={"check_same_thread": False, "timeout": 15})
        self.addCleanup(self.engine.dispose)

    def report(self, **changes):
        with Session(self.engine, expire_on_commit=False) as session:
            report = IssueReport(id=str(uuid4()), created_at=NOW, categories=["Tap List"],
                description="Un problema sintético suficientemente detallado.", diagnostic_consent=False,
                schema_version=1, idempotency_key=str(uuid4()), payload_digest="a" * 64,
                notification_state="pending", **changes)
            session.add(report)
            session.commit()
            return report.id

    def stored(self, key):
        with Session(self.engine) as session:
            return session.get(IssueReport, key)

    def worker(self, result=None, clock=None, config=None):
        transport = Mock()
        transport.send.return_value = result or DeliveryResult("sent", message_id=42)
        return IncidentWorker(self.engine, config or configuration(), transport=transport,
                              clock=clock or (lambda: NOW), jitter=lambda _: 0)

    def test_fresh_schema_and_idempotent_migration(self):
        self.assertEqual(len(migrate(self.engine)), 8)
        check_delivery_schema(self.engine)
        self.assertEqual(migrate(self.engine), [])
        key = self.report()
        row = self.stored(key)
        self.assertEqual(row.notification_attempts, 0)
        self.assertEqual(row.notification_destination, "incidents")
        self.assertIsNone(row.notification_lease_token)

    def test_phase2_migration_preserves_all_original_values_and_states(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql(PHASE2_SQL)
            for state in ["pending", "sent", "historical"]:
                connection.execute(text("INSERT INTO issue_reports VALUES (:id,:created,:categories,:description,0,1,:diagnostics,:screenshot,:mime,:key,:digest,:state)"),
                    {"id": str(uuid4()), "created": NOW.isoformat(" "), "categories": '["Tap List"]',
                     "description": "Original private report survives unchanged.", "diagnostics": '{"route":"/"}',
                     "screenshot": b"private-screenshot-bytes", "mime": "image/jpeg", "key": str(uuid4()), "digest": "b" * 64, "state": state})
            before = connection.exec_driver_sql("SELECT * FROM issue_reports ORDER BY id").fetchall()
        self.assertEqual(len(migrate(self.engine)), 8)
        self.assertEqual(migrate(self.engine), [])
        with self.engine.connect() as connection:
            after = connection.exec_driver_sql("SELECT * FROM issue_reports ORDER BY id").fetchall()
        self.assertEqual([tuple(r[:12]) for r in after], [tuple(r) for r in before])
        worker = self.worker()
        self.assertEqual(worker.run_once(), "processed")
        self.assertEqual(worker.run_once(), "idle")
        with Session(self.engine) as session:
            self.assertEqual(len(session.scalars(select(IssueReport)).all()), 3)

    def test_unsupported_schema_fails_without_changes(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql(PHASE2_SQL)
            connection.exec_driver_sql("ALTER TABLE issue_reports ADD COLUMN unexpected TEXT")
        with self.assertRaises(DeliverySchemaError):
            migrate(self.engine)
        self.assertNotIn("notification_attempts", [c["name"] for c in inspect(self.engine).get_columns("issue_reports")])

    def test_wrong_partial_delivery_column_fails_safely(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql(PHASE2_SQL)
            connection.exec_driver_sql("ALTER TABLE issue_reports ADD COLUMN notification_attempts TEXT")
        with self.assertRaises(DeliverySchemaError):
            migrate(self.engine)
        self.assertEqual(len(inspect(self.engine).get_columns("issue_reports")), 13)

    def test_incompatible_named_index_is_rejected_before_alter(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql(PHASE2_SQL)
            connection.exec_driver_sql("CREATE INDEX ix_issue_reports_delivery ON issue_reports (created_at)")
        with self.assertRaises(DeliverySchemaError):
            migrate(self.engine)
        self.assertEqual(len(inspect(self.engine).get_columns("issue_reports")), 12)

    def test_additive_partial_migration_and_ddl_rollback(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql(PHASE2_SQL)
            connection.exec_driver_sql("ALTER TABLE issue_reports ADD COLUMN notification_attempts INTEGER NOT NULL DEFAULT 0")

        def fail(connection, cursor, statement, parameters, context, executemany):
            if "ADD COLUMN" in statement and "notification_lease_token" in statement:
                raise RuntimeError("simulated DDL interruption")

        event.listen(self.engine, "before_cursor_execute", fail)
        try:
            with self.assertRaises(RuntimeError):
                migrate(self.engine)
        finally:
            event.remove(self.engine, "before_cursor_execute", fail)
        self.assertEqual(len(inspect(self.engine).get_columns("issue_reports")), 13)
        self.assertEqual(len(migrate(self.engine)), 7)

    def test_concurrent_migration_is_idempotent(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: migrate(self.engine), range(2)))
        self.assertEqual(sorted(len(item) for item in results), [0, 8])

    def test_success_and_network_outside_transaction(self):
        migrate(self.engine)
        key = self.report(screenshot=b"DO NOT SEND IMAGE")
        worker = self.worker()

        def send(message):
            # Independent writer can obtain a write lock during the HTTP call.
            with self.engine.connect() as connection:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                state = connection.exec_driver_sql("SELECT notification_state FROM issue_reports").scalar()
                connection.rollback()
            self.assertEqual(state, "sending")
            self.assertNotIn("DO NOT SEND IMAGE", message)
            return DeliveryResult("sent", message_id=42)

        worker.transport.send.side_effect = send
        self.assertEqual(worker.run_once(), "processed")
        row = self.stored(key)
        self.assertEqual(row.notification_state, "sent")
        self.assertEqual(row.notification_attempts, 1)
        self.assertEqual(row.telegram_message_id, 42)
        self.assertEqual(row.notification_sent_at, NOW)
        self.assertIsNone(row.notification_lease_token)
        self.assertEqual(row.screenshot, b"DO NOT SEND IMAGE")

    def test_concurrent_claims_cannot_claim_same_report(self):
        migrate(self.engine)
        self.report()
        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(lambda _: claim_report(self.engine, NOW, 6), range(2)))
        self.assertEqual(sum(claim is not None for claim in claims), 1)

    def test_crash_recovery_fences_old_lease_and_late_ack(self):
        migrate(self.engine)
        key = self.report()
        old = claim_report(self.engine, NOW, 6)
        later = NOW + timedelta(seconds=LEASE_SECONDS + 1)
        self.assertIsNone(claim_report(self.engine, NOW + timedelta(seconds=1), 6))
        self.assertFalse(acknowledge(self.engine, old, DeliveryResult("sent", message_id=1), later, 6, lambda _: 0))
        current = claim_report(self.engine, later, 6)
        self.assertNotEqual(current.token, old.token)
        self.assertFalse(acknowledge(self.engine, old, DeliveryResult("sent", message_id=1), later, 6, lambda _: 0))
        self.assertTrue(acknowledge(self.engine, current, DeliveryResult("sent", message_id=2), later, 6, lambda _: 0))
        self.assertEqual(self.stored(key).notification_attempts, 2)
        self.assertEqual(self.stored(key).telegram_message_id, 2)

    def test_backoff_maximum_attempts_and_ambiguous_outcome(self):
        migrate(self.engine)
        key = self.report()
        clock = [NOW]
        worker = self.worker(DeliveryResult("delivery_unknown"), clock=lambda: clock[0], config=configuration(max_attempts=3))
        for attempt, delay in [(1, 30), (2, 60), (3, None)]:
            self.assertEqual(worker.run_once(), "processed")
            row = self.stored(key)
            self.assertEqual(row.notification_attempts, attempt)
            self.assertEqual(row.notification_error_code, "delivery_unknown")
            if delay:
                self.assertEqual(row.notification_next_attempt_at, clock[0] + timedelta(seconds=delay))
                self.assertEqual(worker.run_once(), "idle")
                clock[0] = row.notification_next_attempt_at
        self.assertEqual(self.stored(key).notification_state, "failed")
        self.assertEqual(worker.run_once(), "idle")

    def test_retry_after_applies_to_whole_destination_and_survives_restart(self):
        migrate(self.engine)
        key = self.report()
        self.assertEqual(self.worker(DeliveryResult("rate_limited", retry_after=3600)).run_once(), "processed")
        next_time = self.stored(key).notification_next_attempt_at
        self.assertEqual(next_time, NOW + timedelta(seconds=3600))
        self.report()
        self.assertEqual(self.worker().run_once(), "idle")
        self.assertEqual(self.worker(clock=lambda: next_time).run_once(), "processed")

    def test_permanent_failure_and_worker_stop(self):
        migrate(self.engine)
        key = self.report()
        self.report()
        worker = self.worker(DeliveryResult("bot_unauthorized", permanent=True, stop_worker=True))
        self.assertEqual(run_loop(worker, threading.Event()), 2)
        rows = []
        with Session(self.engine) as session:
            rows = session.scalars(select(IssueReport)).all()
        self.assertEqual(sorted(row.notification_attempts for row in rows), [0, 1])
        self.assertIn(self.stored(key).notification_state, {"pending", "failed"})

    def test_crash_on_last_attempt_exhausts_without_another_send(self):
        migrate(self.engine)
        key = self.report()
        claim_report(self.engine, NOW, 1)
        worker = self.worker(clock=lambda: NOW + timedelta(seconds=LEASE_SECONDS + 1), config=configuration(max_attempts=1))
        self.assertEqual(worker.run_once(), "idle")
        worker.transport.send.assert_not_called()
        self.assertEqual(self.stored(key).notification_error_code, "attempts_exhausted")

    def test_disabled_and_incomplete_configuration_do_not_connect_or_send(self):
        engine = Mock()
        worker = IncidentWorker(engine, configuration(enabled=False), transport=Mock())
        self.assertEqual(worker.run_once(), "disabled")
        self.assertEqual(run_loop(worker, threading.Event()), 0)
        bad = configuration()
        bad.telegram_incidents_bot_token = None
        with self.assertRaises(IncidentConfigurationError):
            IncidentWorker(engine, bad).run_once()
        engine.connect.assert_not_called()
        worker.transport.send.assert_not_called()

    def test_schema_is_checked_without_automatic_migration(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql(PHASE2_SQL)
        with self.assertRaises(DeliverySchemaError):
            self.worker().run_once()
        self.assertEqual(len(inspect(self.engine).get_columns("issue_reports")), 12)

    def test_logs_never_include_transport_exceptions_user_text_or_secrets(self):
        migrate(self.engine)
        self.report()
        worker = self.worker()
        secret = "https://api.telegram.org/botSYNTHETIC_SECRET/sendMessage user-private-text"
        worker.transport.send.side_effect = RuntimeError(secret)
        with self.assertLogs("app.workers.incident_notifications", level="WARNING") as logs:
            worker.run_once()
        self.assertNotIn(secret, " ".join(logs.output))
        self.assertNotIn("SYNTHETIC_SECRET", " ".join(logs.output))
        self.assertNotIn("user-private-text", " ".join(logs.output))

    def test_report_submission_is_independent_of_telegram_outage(self):
        migrate(self.engine)
        app = FastAPI()
        app.include_router(issue_reports.router)

        def database():
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_db] = database
        with patch.object(issue_reports, "limiter", ReportRateLimiter()), \
                patch("app.core.config.settings.telegram_incidents_enabled", True), \
                patch("app.core.config.settings.telegram_incidents_bot_token", None), \
                patch("app.core.config.settings.telegram_incidents_chat_id", None), \
                patch.object(TelegramTransport, "send", side_effect=AssertionError("No transport in request")), TestClient(app) as client:
            payload = {"categories": ["Otro"], "description": "Un reporte nuevo durante una falla de Telegram.",
                       "diagnostic_consent": False, "idempotency_key": str(uuid4())}
            response = client.post("/public/issue-reports", files={"report": (None, json.dumps(payload))})
        self.assertEqual(response.status_code, 201)
        row = self.stored(response.json()["report_id"])
        self.assertEqual(row.notification_state, "pending")
        self.assertEqual(row.notification_attempts, 0)

    def test_graceful_stop_does_not_claim_another_report(self):
        stop = threading.Event()
        worker = Mock()
        worker.run_once.side_effect = lambda: (stop.set() or "processed")
        self.assertEqual(run_loop(worker, stop), 0)
        worker.run_once.assert_called_once()

    def test_cli_disabled_and_missing_configuration_statuses_are_safe(self):
        for enabled, expected in [(False, 0), (True, 2)]:
            config = configuration(enabled=enabled)
            config.telegram_incidents_chat_id = None
            database = Mock()
            with patch("app.core.config.settings", config), patch("app.core.database.engine", database), \
                    patch("sys.argv", ["worker", "--once"]), \
                    patch("app.workers.incident_notifications.signal.signal"), \
                    patch("app.workers.incident_notifications.logging.basicConfig"), \
                    self.assertLogs("app.workers.incident_notifications", level="INFO") as logs:
                self.assertEqual(main(), expected)
            database.connect.assert_not_called()
            self.assertNotIn("123456", " ".join(logs.output))


class TransportAndFormattingTests(unittest.TestCase):
    def transport(self, status=200, data=None, raw=None):
        response = Mock(status=status)
        response.read.return_value = raw if raw is not None else json.dumps(data if data is not None else {"ok": True, "result": {"message_id": 55}}).encode()
        connection = Mock()
        connection.getresponse.return_value = response
        factory = Mock(return_value=connection)
        return TelegramTransport(incident_config(configuration()), connection_factory=factory), connection, factory

    def test_success_validates_status_json_and_uses_https_timeouts_plain_text(self):
        transport, connection, factory = self.transport()
        result = transport.send("Mensaje sintético")
        self.assertEqual(result.message_id, 55)
        self.assertEqual(factory.call_args.args, ("api.telegram.org",))
        self.assertEqual(factory.call_args.kwargs["timeout"], CONNECT_TIMEOUT)
        connection.sock.settimeout.assert_called_with(READ_TIMEOUT)
        body = json.loads(connection.request.call_args.kwargs["body"])
        self.assertTrue(body["link_preview_options"]["is_disabled"])
        self.assertNotIn("parse_mode", body)
        self.assertEqual(connection.request.call_args.args[0], "POST")
        connection.close.assert_called()

    def test_response_validation_and_failure_classification(self):
        cases = [
            (200, {"ok": False, "error_code": 401}, "bot_unauthorized"),
            (200, {"ok": True, "result": {"message_id": True}}, "delivery_unknown"),
            (200, {"ok": True, "result": {}}, "delivery_unknown"),
            (200, [], "delivery_unknown"), (503, {}, "telegram_unavailable"),
            (401, {}, "bot_unauthorized"), (403, {}, "destination_forbidden"),
            (400, {"parameters": {"migrate_to_chat_id": -123}}, "destination_changed"),
            (400, {}, "payload_rejected"), (302, {}, "protocol_rejected"),
        ]
        for status, data, code in cases:
            with self.subTest(status=status, code=code):
                transport, _, _ = self.transport(status, data)
                self.assertEqual(transport.send("synthetic").code, code)
        for raw in [b"not json", b"x" * (MAX_RESPONSE_BYTES + 1)]:
            transport, _, _ = self.transport(raw=raw)
            self.assertEqual(transport.send("synthetic").code, "delivery_unknown")

    def test_429_and_timeout_ambiguity(self):
        transport, _, _ = self.transport(429, {"parameters": {"retry_after": 3600}})
        result = transport.send("synthetic")
        self.assertEqual(result.retry_after, 3600)
        self.assertFalse(result.permanent)
        transport, connection, _ = self.transport()
        connection.getresponse.side_effect = socket.timeout("token-bearing-private-error")
        self.assertEqual(transport.send("synthetic").code, "delivery_unknown")
        transport, _, _ = self.transport(429, {"parameters": {"retry_after": "invalid"}})
        self.assertTrue(transport.send("synthetic").stop_worker)

    def test_config_repr_and_errors_are_secret_free(self):
        settings = configuration()
        self.assertNotIn(settings.telegram_incidents_bot_token.get_secret_value(), repr(incident_config(settings)))
        settings.telegram_incidents_chat_id = None
        with self.assertRaises(IncidentConfigurationError) as error:
            incident_config(settings)
        self.assertNotIn("123456", str(error.exception))
        from app.core.config import Settings
        with self.assertRaises(ValidationError) as error:
            Settings(_env_file=None, secret_key="synthetic", database_url="sqlite://",
                     telegram_incidents_bot_token="SYNTHETIC_SECRET", telegram_incidents_max_attempts=0)
        self.assertNotIn("input_value", str(error.exception))
        self.assertNotIn("SYNTHETIC_SECRET", str(error.exception))

    def test_total_deadline_bounds_dns_and_prevents_late_send(self):
        transport, connection, _ = self.transport()
        unblock = threading.Event()
        finished = threading.Event()
        connection.connect.side_effect = lambda: unblock.wait(2)
        connection.close.side_effect = lambda: finished.set()
        with patch("app.services.incident_telegram.TOTAL_TIMEOUT", 0.02):
            self.assertEqual(transport.send("synthetic").code, "delivery_unknown")
        finished.clear()
        unblock.set()
        self.assertTrue(finished.wait(2))
        connection.request.assert_not_called()

    def content(self, description="Un problema sintético suficientemente detallado.", consent=False):
        return NotificationContent("a55cb47c-9b4d-4a57-babe-36cda04eff04", NOW, ["Tap List"], description, consent,
            {"route": "/museum", "browser": {"name": "Safari", "version": "18.0"}, "os": "iOS/iPadOS",
             "viewport": {"width": 390, "height": 844}, "online": True, "private": "DO NOT INCLUDE"}, True)

    def test_consent_filtering_excerpt_bound_and_complete_message_bound(self):
        message = format_notification(self.content(consent=False))
        for forbidden in ["Safari", "iOS", "/museum", "390", "DO NOT INCLUDE", "Diagnóstico"]:
            self.assertNotIn(forbidden, message)
        consented = format_notification(self.content(consent=True))
        self.assertIn("Safari 18.0", consented)
        self.assertIn("ventana 390×844", consented)
        self.assertNotIn("DO NOT INCLUDE", consented)
        self.assertIn("Captura: sí, privada en ATLAS", consented)
        message = format_notification(self.content(description="🐟" * 501, consent=True))
        excerpt = message.split("Descripción:\n")[1].split("\n")[0]
        self.assertEqual(len(excerpt), 500)
        self.assertIn("Descripción truncada", message)
        self.assertLess(len(message.encode("utf-16-le")) // 2, 4096)
        self.assertNotIn("Descripción truncada", format_notification(self.content(description="x" * 500)))

    def test_controls_urls_and_bidi_are_sanitized(self):
        message = format_notification(self.content(description="Una prueba\x00\r\n\u202e con https://private.invalid/report y www.private.invalid/text"))
        self.assertNotIn("\x00", message)
        self.assertNotIn("\r", message)
        self.assertNotIn("\u202e", message)
        self.assertNotIn("private.invalid", message)
        self.assertIn("[enlace omitido]", message)


if __name__ == "__main__":
    unittest.main()
