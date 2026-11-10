"""Opt-in draft worker with its own Credential Manager entry; never publishes."""
import argparse
import re
import signal
import threading
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from app.core.incidents_instance import WorkerAlreadyRunning
from app.core.editorial_credentials import read_token, EditorialCredentialUnavailable
from app.editorial.config import Authorization, dedicated_database, load_settings
from app.editorial.instance import EditorialInstance
from app.editorial.media import MediaStore
from app.editorial.models import Base, Cursor
from app.editorial.service import EditorialService
from app.editorial.telegram import TelegramTransport, TransportError
from app.migrations.editorial import check_schema
from app.core.bot_observability import event


def run(engine, settings, transport, stop, *, once=False):
    auth = Authorization.load(settings)
    media = MediaStore(settings.media_root)
    service = EditorialService(engine, auth, media, transport, settings.download_limit_bytes,
                               catalog_database_url=getattr(settings, "catalog_database_url", None))
    with engine.connect() as connection:
        check_schema(connection)
    service.recover_replies()
    while not stop.is_set():
        # Revocations take effect without restarting. Invalid permissions fail closed.
        service.auth = Authorization.load(settings)
        try:
            # Resume persisted inbox/outbox before receiving more updates.
            for _ in range(20):
                if stop.is_set() or not service.process_one():
                    break
                service.flush_one()
            for _ in range(20):
                if stop.is_set() or not service.flush_one():
                    break
            if not stop.is_set():
                with Session(engine) as db:
                    # Read-only summaries never update the durable cursor. Advance
                    # this process's polling position so they cannot fill a batch.
                    offset = max(db.get(Cursor, 1).next_offset, service.readonly_offset)
                service.ingest(transport.get_updates(offset))
                for _ in range(20):
                    if stop.is_set() or not service.process_one():
                        break
                    service.flush_one()
        except TransportError:
            event("editorial", "transport_unavailable")
            if not once:
                stop.wait(5)
        if once:
            return 0
        stop.wait(2)
    return 0


def main(*, credentials=read_token):
    parser = argparse.ArgumentParser(description="Editorial draft worker; cannot publish")
    parser.add_argument("--once", action="store_true", help="One receive/process cycle; enabled mode contacts Telegram")
    args = parser.parse_args()
    engine = None
    token = None
    previous = {}
    event("editorial", "started")
    try:
        settings = load_settings()
        if not settings.enabled:
            event("editorial", "disabled")
            print("Editorial disabled; no credentials, storage or Telegram accessed")
            return 0
        if not settings.database_url:
            raise ValueError("Dedicated configuration required")
        database = dedicated_database(settings.database_url)
        if not database.is_file():
            raise ValueError("Explicit migration required")
        # Validate authorization and paths before lock/database/network access.
        Authorization.load(settings)
        MediaStore(settings.media_root)
        stop = threading.Event()
        signals = [signal.SIGINT, signal.SIGTERM]
        if hasattr(signal, "SIGBREAK"):
            signals.append(signal.SIGBREAK)
        previous = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in signals}
        with EditorialInstance(settings.database_url):
            engine = create_engine("sqlite:///" + database.as_posix(), connect_args={"timeout": 15})
            with engine.connect() as connection:
                check_schema(connection)
                if set(inspect(connection).get_table_names()) != set(Base.metadata.tables):
                    raise ValueError("Dedicated Editorial tables required")
            token = credentials()  # Direct lookup in THIS worker, never the supervisor or environment.
            if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,100}", token.get_secret_value()):
                raise EditorialCredentialUnavailable()
            return run(engine, settings, TelegramTransport(token), stop, once=args.once)
    except WorkerAlreadyRunning:
        event("editorial", "already_running")
        print("Editorial already running for this database; no second worker started")
        return 3
    except (ValueError, EditorialCredentialUnavailable, OSError):
        event("editorial", "configuration_error")
        print("Editorial stopped safely; inspect dedicated configuration/storage offline; private details suppressed")
        return 2
    except Exception:
        event("editorial", "operation_failed")
        print("Editorial unexpected failure; private details suppressed")
        return 1
    finally:
        if engine:
            engine.dispose()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        token = None
        event("editorial", "stopped")


if __name__ == "__main__":
    raise SystemExit(main())
