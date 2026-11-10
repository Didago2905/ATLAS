"""Read-only log viewer. Does not import workers, configuration, databases or Telegram."""
import argparse
from pathlib import Path
import re
import time

from app.core.bot_observability import CHANNELS, EVENTS, LOG_ROOT


def read_available(path: Path, position=(None, 0)):
    """Close files every poll so Windows rotation is never blocked by a reader."""
    identity, offset = position
    try:
        with path.open("rb") as source:
            import os
            stat = os.fstat(source.fileno())
            current = (stat.st_dev, stat.st_ino)
            if current != identity or stat.st_size < offset:
                offset = 0
            source.seek(offset)
            data = source.read(64 * 1024)
        end = data.rfind(b"\n") + 1
        lines = []
        for line in data[:end].decode("utf-8", errors="replace").splitlines():
            parts = line.split(" | ")
            if len(parts) == 3 and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", parts[0]) \
                    and parts[1] == path.stem and parts[1] in CHANNELS and parts[2] in EVENTS:
                lines.append(line)
        return lines, (current, offset + end)
    except OSError:
        return [], (None, 0)


def main():
    parser = argparse.ArgumentParser(description="ATLAS bot operational log viewer; never starts a bot")
    parser.add_argument("channel", choices=sorted(CHANNELS))
    args = parser.parse_args()
    print(args.channel + ": visor de logs; no inicia bots. Esperando eventos; no indica salud en tiempo real.", flush=True)
    position = (None, 0)
    try:
        while True:
            lines, position = read_available(LOG_ROOT / (args.channel + ".log"), position)
            for line in lines:
                print(line, flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
