"""One OS-held worker lock per canonical SQLite file; no database writes."""
import os
from pathlib import Path

from sqlalchemy.engine import make_url


class WorkerAlreadyRunning(RuntimeError):
    pass


def database_path(url):
    parsed = make_url(str(url))
    if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:" or parsed.query:
        raise ValueError("Incidents requires a local SQLite file")
    return Path(os.path.normcase(str(Path(parsed.database).resolve())))


class WorkerInstance:
    def __init__(self, url):
        self.path = Path(str(database_path(url)) + ".incidents-worker.lock")
        self.file = None

    def __enter__(self):
        self.file = self.path.open("a+b")
        try:
            if self.path.stat().st_size == 0:
                self.file.write(b"0")
                self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            raise WorkerAlreadyRunning("Incidents worker already owns this database") from None
        return self

    def __exit__(self, *_):
        if self.file:
            try:
                self.file.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            finally:
                self.file.close()
                self.file = None
        # Keep the runtime lock file: unlinking it races other contenders.
