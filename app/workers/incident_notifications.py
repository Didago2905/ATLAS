"""Standalone leased incident delivery worker; never imported by app.main."""
import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
import random
import signal
import threading
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update

from app.migrations.issue_report_delivery import DeliverySchemaError, check_delivery_schema
from app.core.incidents_instance import WorkerAlreadyRunning, WorkerInstance
from app.models.issue_report import IssueReport
from app.services.incident_telegram import (
    DeliveryResult, IncidentConfigurationError, NotificationContent, TelegramTransport,
    format_notification, incident_config,
)

logger = logging.getLogger(__name__)
LEASE_SECONDS = 120  # Longer than the transport's hard 30-second deadline.
BASE_DELAY_SECONDS = 30
MAX_DELAY_SECONDS = 1800


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class Claim:
    report_id: str
    token: str = field(repr=False)
    attempts: int
    content: NotificationContent = field(repr=False)


def _eligible(now):
    row = IssueReport
    lease_free = or_(row.notification_lease_expires_at.is_(None), row.notification_lease_expires_at <= now)
    due = or_(row.notification_next_attempt_at.is_(None), row.notification_next_attempt_at <= now)
    return and_(row.notification_destination == "incidents", lease_free,
                or_(and_(row.notification_state == "pending", due),
                    and_(row.notification_state == "sending", row.notification_lease_expires_at <= now)))


def claim_report(engine, now, max_attempts):
    row = IssueReport
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            cooldown = connection.scalar(select(func.max(row.notification_next_attempt_at)).where(
                row.notification_destination == "incidents", row.notification_error_code == "rate_limited",
                row.notification_next_attempt_at > now))
            if cooldown is not None:
                connection.commit()
                return None
            connection.execute(update(row).where(_eligible(now), row.notification_attempts >= max_attempts).values(
                notification_state="failed", notification_error_code="attempts_exhausted",
                notification_lease_token=None, notification_lease_expires_at=None, notification_next_attempt_at=None))
            # Never load screenshot bytes, original filenames, or more than 501
            # description characters into the notification worker.
            report = connection.execute(select(
                row.id, row.created_at, row.categories, func.substr(row.description, 1, 501).label("excerpt"),
                row.diagnostic_consent, row.diagnostics, row.screenshot.is_not(None).label("has_screenshot"),
                row.notification_attempts,
            ).where(_eligible(now), row.notification_attempts < max_attempts)
                .order_by(row.created_at, row.id).limit(1)).mappings().first()
            if not report:
                connection.commit()
                return None
            token = str(uuid4())
            attempts = report["notification_attempts"] + 1
            connection.execute(update(row).where(row.id == report["id"]).values(
                notification_state="sending", notification_attempts=attempts,
                notification_lease_token=token, notification_lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
                notification_next_attempt_at=None))
            connection.commit()
            content = NotificationContent(report["id"], report["created_at"], report["categories"], report["excerpt"],
                                          report["diagnostic_consent"], report["diagnostics"], report["has_screenshot"])
            return Claim(report["id"], token, attempts, content)
        except BaseException:
            connection.rollback()
            raise


def acknowledge(engine, claim, result, now, max_attempts, jitter):
    values = {"notification_lease_token": None, "notification_lease_expires_at": None,
              "notification_next_attempt_at": None}
    if result.code == "sent" and type(result.message_id) is int and result.message_id > 0:
        values.update(notification_state="sent", notification_sent_at=now,
                      telegram_message_id=result.message_id, notification_error_code=None)
    elif result.permanent or claim.attempts >= max_attempts:
        values.update(notification_state="failed", notification_error_code=result.code)
        if result.retry_after is not None:
            # A final exhausted report still carries the destination cooldown;
            # it remains failed and will never itself be claimed automatically.
            values["notification_next_attempt_at"] = now + timedelta(seconds=result.retry_after)
    else:
        exponential = min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * 2 ** (claim.attempts - 1))
        delay = exponential + max(0, min(exponential * 0.2, jitter(exponential * 0.2)))
        if result.retry_after is not None:
            delay = max(delay, result.retry_after)
        values.update(notification_state="pending", notification_error_code=result.code,
                      notification_next_attempt_at=now + timedelta(seconds=delay))
    row = IssueReport
    with engine.begin() as connection:
        changed = connection.execute(update(row).where(
            row.id == claim.report_id, row.notification_state == "sending",
            row.notification_lease_token == claim.token, row.notification_lease_expires_at > now,
        ).values(**values)).rowcount
    return bool(changed)


class IncidentWorker:
    def __init__(self, engine, settings, *, transport=None, clock=utc_now, jitter=lambda bound: random.uniform(0, bound)):
        self.engine = engine
        self.settings = settings
        self.transport = transport
        self.clock = clock
        self.jitter = jitter
        self.schema_checked = False

    def run_once(self):
        config = incident_config(self.settings)
        if config is None:
            return "disabled"
        if not self.schema_checked:
            check_delivery_schema(self.engine)
            self.schema_checked = True
        claim = claim_report(self.engine, self.clock(), config.max_attempts)
        if claim is None:
            return "idle"
        try:
            message = format_notification(claim.content)
        except Exception:
            result = DeliveryResult("invalid_report_content", permanent=True)
        else:
            try:
                result = (self.transport or TelegramTransport(config)).send(message)
                if not isinstance(result, DeliveryResult):
                    result = DeliveryResult("delivery_unknown")
            except Exception:
                # An injected or future transport must not leak credentials via
                # exception logging. Sending may have succeeded remotely.
                result = DeliveryResult("delivery_unknown")
        owned = acknowledge(self.engine, claim, result, self.clock(), config.max_attempts, self.jitter)
        # Only fixed outcomes, never raw errors, message text, chat IDs or URLs.
        if not owned:
            logger.warning("Incident delivery lease lost; remote outcome may be ambiguous")
        elif result.code == "sent":
            logger.info("Incident delivery acknowledged")
        else:
            logger.warning("Incident delivery deferred or failed")
        if result.stop_worker:
            return "configuration_error"
        return "processed" if owned else "lease_lost"


def run_loop(worker, stop, *, once=False):
    while not stop.is_set():
        status = worker.run_once()
        if status == "disabled":
            logger.info("Incidents disabled; no reports claimed")
            return 0
        if status == "configuration_error":
            logger.error("Incidents delivery configuration requires operator attention")
            return 2
        if once:
            return 0
        if status in {"idle", "lease_lost"}:
            stop.wait(2)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Standalone ATLAS Incidents outbound worker")
    parser.add_argument("--once", action="store_true", help="Process at most one eligible report")
    args = parser.parse_args()
    # Configuration/engine imports do not connect or create tables.
    from app.core.config import settings
    from app.core.database import engine

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, lambda *_: stop.set())
    try:
        # Validate before locking: disabled/incomplete configuration never opens
        # a lock file or the database. Manual --once uses the same OS lock.
        if incident_config(settings) is None:
            logger.info("Incidents disabled; no reports claimed")
            return 0
        with WorkerInstance(engine.url):
            return run_loop(IncidentWorker(engine, settings), stop, once=args.once)
    except WorkerAlreadyRunning:
        logger.warning("Incidents worker already running for this database")
        return 3
    except DeliverySchemaError:
        logger.error("Incidents schema requires explicit migration; no automatic restart")
        return 4
    except IncidentConfigurationError:
        logger.error("Incidents enabled but dedicated configuration is missing or invalid; no delivery attempted")
        return 2
    except Exception:
        logger.error("Incidents worker stopped safely; check migration, database and configuration offline")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
