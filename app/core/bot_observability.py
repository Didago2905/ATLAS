"""Fixed operational events only: no payloads, IDs, exceptions or credentials."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time

LOG_ROOT = Path(__file__).resolve().parents[2] / "devtools/runtime/bot-logs"
MAX_BYTES = 512 * 1024
BACKUPS = 3
CHANNELS = frozenset({"notifications", "incidents", "editorial"})
EVENTS = frozenset({"started", "stopped", "disabled", "operation_ok", "operation_failed",
                    "transport_unavailable", "configuration_error", "already_running", "delivery_uncertain"})


class QuietRotatingHandler(RotatingFileHandler):
    def emit(self, record):
        if record.msg != "%s | %s" or not isinstance(record.args, tuple) or len(record.args) != 2 \
                or record.args[0] not in CHANNELS or record.args[1] not in EVENTS:
            return
        # Rebuild the record: even accidental exc_info/stack_info cannot reach disk.
        safe = logging.LogRecord(record.name, logging.INFO, "", 0, record.msg, record.args, None)
        safe.created = record.created
        super().emit(safe)

    def handleError(self, record):
        pass  # Observability failure must not interrupt a worker or print record/exception data.


def event(channel, name):
    if channel not in CHANNELS or name not in EVENTS:
        return  # No arbitrary strings can enter an operational log.
    try:
        path = LOG_ROOT / (channel + ".log")
        logger = logging.getLogger("atlas.bot_console." + channel)
        logger.propagate = False
        logger.setLevel(logging.INFO)
        if not any(isinstance(h, QuietRotatingHandler) and h.baseFilename == str(path.resolve())
                   for h in logger.handlers):
            LOG_ROOT.mkdir(parents=True, exist_ok=True)
            handler = QuietRotatingHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
            formatter = logging.Formatter("%(asctime)sZ | %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
            formatter.converter = time.gmtime
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.info("%s | %s", channel, name)
    except Exception:
        pass  # Disk/permission failures cannot change delivery or supervision behavior.
