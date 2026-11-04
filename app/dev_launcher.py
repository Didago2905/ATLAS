"""Canonical backend-pane supervisor. Does not register Windows startup tasks."""
import logging
import os
from pathlib import Path
import re
import signal
import socket
import sys
import threading
import time

from app.core.incidents_credentials import CredentialUnavailable, read_token
from app.core.incidents_instance import database_path
from app.core.windows_children import StartupFailure, WindowsChildren

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parent.parent
RESTART_DELAYS = (5, 30, 120)  # Three restarts after the initial worker attempt.


def port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if os.name == "nt":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


class BackendSupervisor:
    def __init__(self, settings, *, children_factory=WindowsChildren, credentials=read_token,
                 available=port_available, clock=time.monotonic, stop=None, environment=None,
                 editorial_settings=None):
        self.settings = settings
        self.children_factory = children_factory
        self.credentials = credentials
        self.available = available
        self.clock = clock
        self.stop = stop if stop is not None else threading.Event()
        self.environment = dict(os.environ if environment is None else environment)
        self.editorial_settings = editorial_settings

    def base_environment(self):
        environment = {key: value for key, value in self.environment.items()
                       if key.upper() not in {"TELEGRAM_INCIDENTS_BOT_TOKEN", "ATLAS_EDITORIAL_BOT_TOKEN"}}
        # Empty overrides .env too. The API never receives the dedicated token.
        environment.update(TELEGRAM_INCIDENTS_BOT_TOKEN="", TELEGRAM_INCIDENTS_ENABLED="false",
                           DATABASE_URL="sqlite:///" + database_path(self.settings.database_url).as_posix(),
                           PYTHONDONTWRITEBYTECODE="1")
        environment["ATLAS_EDITORIAL_ENABLED"] = "false"
        return environment

    def spawn_editorial(self, children):
        # Nonsecret settings only. The child loads its own dedicated credential.
        settings = self.editorial_settings
        environment = self.base_environment()
        environment.update(ATLAS_EDITORIAL_ENABLED="true", ATLAS_EDITORIAL_DATABASE_URL=settings.database_url,
                           ATLAS_EDITORIAL_MEDIA_ROOT=str(settings.media_root),
                           ATLAS_EDITORIAL_PERMISSIONS_FILE=str(settings.permissions_file),
                           ATLAS_EDITORIAL_CHAT_ID=str(settings.chat_id),
                           ATLAS_EDITORIAL_DOWNLOAD_LIMIT_BYTES=str(settings.download_limit_bytes))
        return children.spawn([sys.executable, "-B", "-m", "app.workers.editorial"], environment, REPO)

    def spawn_worker(self, children):
        chat = self.settings.telegram_incidents_chat_id
        if not chat or not re.fullmatch(r"-?[0-9]{1,20}", chat.get_secret_value()) or int(chat.get_secret_value()) == 0:
            raise CredentialUnavailable()
        token = self.credentials()  # Exact dedicated Credential Manager entry only.
        environment = self.base_environment()
        try:
            environment.update(TELEGRAM_INCIDENTS_ENABLED="true",
                               TELEGRAM_INCIDENTS_BOT_TOKEN=token.get_secret_value(),
                               TELEGRAM_INCIDENTS_CHAT_ID=chat.get_secret_value(),
                               TELEGRAM_INCIDENTS_MAX_ATTEMPTS=str(self.settings.telegram_incidents_max_attempts))
            return children.spawn([sys.executable, "-B", "-m", "app.workers.incident_notifications"], environment, REPO)
        finally:
            environment.pop("TELEGRAM_INCIDENTS_BOT_TOKEN", None)
            token = None

    def run(self):
        if not self.available(8001):
            logger.error("Backend port 8001 is occupied; no children started")
            return 2
        children = self.children_factory()
        backend = worker = editorial = None
        editorial_allowed = bool(self.editorial_settings and self.editorial_settings.enabled)
        editorial_restarts, editorial_next_start = 0, 0
        try:
            backend = children.spawn([sys.executable, "-B", "-m", "uvicorn", "app.main:app",
                                      "--host", "0.0.0.0", "--port", "8001"], self.base_environment(), REPO)
            started = self.clock()
            ready = False
            worker_allowed = self.settings.telegram_incidents_enabled
            restart_count = 0
            next_start = started
            if not worker_allowed:
                logger.info("Incidents disabled; credentials will not be accessed")
            while not self.stop.is_set():
                code = backend.poll()
                if code is not None:
                    return 0 if code == 0 else 1
                if not ready:
                    ready = children.owns_listener(8001)
                    if not ready and self.clock() - started >= 20:
                        raise StartupFailure("Owned FastAPI listener did not become ready")
                failed = False
                if worker is not None:
                    exit_code = worker.poll()
                    if exit_code is not None:
                        worker.finish_tree()  # Reap any surviving interpreter descendants, not FastAPI.
                        worker = None
                        if exit_code in {0, 2, 3, 4}:
                            worker_allowed = False
                            logger.warning("Incidents stopped; configuration or instance status requires review")
                        else:
                            failed = True
                if ready and worker_allowed and worker is None and not failed and self.clock() >= next_start:
                    try:
                        worker = self.spawn_worker(children)
                    except CredentialUnavailable:
                        worker_allowed = False
                        logger.error("Dedicated Incidents credential/configuration unavailable; backend continues")
                    except Exception:
                        failed = True
                        logger.error("Incidents child could not start; backend continues")
                if failed:
                    if restart_count < len(RESTART_DELAYS):
                        next_start = self.clock() + RESTART_DELAYS[restart_count]
                        restart_count += 1
                        logger.warning("Incidents restart scheduled within session budget")
                    else:
                        worker_allowed = False
                        logger.error("Incidents restart budget exhausted; backend continues")
                # Independent child and restart budget. Incidents logic above is unchanged.
                editorial_failed = False
                if editorial is not None and editorial.poll() is not None:
                    editorial_exit = editorial.poll()
                    editorial.finish_tree()
                    editorial = None
                    if editorial_exit in {0, 2, 3, 4}:
                        editorial_allowed = False
                        logger.warning("Editorial stopped; configuration or instance requires review")
                    else:
                        editorial_failed = True
                if ready and editorial_allowed and editorial is None and not editorial_failed and self.clock() >= editorial_next_start:
                    try:
                        editorial = self.spawn_editorial(children)
                    except Exception:
                        editorial_failed = True
                        logger.error("Editorial child could not start; other services continue")
                if editorial_failed:
                    if editorial_restarts < len(RESTART_DELAYS):
                        editorial_next_start = self.clock() + RESTART_DELAYS[editorial_restarts]
                        editorial_restarts += 1
                        logger.warning("Editorial restart scheduled within session budget")
                    else:
                        editorial_allowed = False
                        logger.error("Editorial restart budget exhausted; other services continue")
                self.stop.wait(0.2)
            return 0
        finally:
            # Address only process groups created by THIS supervisor. Each has
            # its own group; never broadcast to other Terminal panes/services.
            try:
                for child in (editorial, worker, backend):
                    if child is not None:
                        child.interrupt()
                deadline = self.clock() + 90
                for child in (editorial, worker, backend):
                    if child is not None:
                        child.wait(max(0, deadline - self.clock()))
            finally:
                children.close()  # Enforces descendant cleanup on timeout too.
                self.environment.pop("TELEGRAM_INCIDENTS_BOT_TOKEN", None)
                self.environment.pop("ATLAS_EDITORIAL_BOT_TOKEN", None)


def main():
    from app.core.config import settings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    editorial_settings = None
    try:
        from app.editorial.config import load_settings
        editorial_settings = load_settings()
    except Exception:
        logger.error("Editorial configuration unavailable; Editorial disabled; other services continue")
    stop = threading.Event()
    signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        signals.append(signal.SIGBREAK)
    previous = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in signals}
    try:
        return BackendSupervisor(settings, stop=stop, editorial_settings=editorial_settings).run()
    except Exception:
        logger.error("Backend supervisor stopped; owned children cleaned up; private details suppressed")
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
