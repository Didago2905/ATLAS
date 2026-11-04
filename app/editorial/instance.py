"""Editorial-only namespace over the established OS-held SQLite-path lock."""
from pathlib import Path
from app.core.incidents_instance import WorkerInstance
from app.editorial.config import dedicated_database


class EditorialInstance(WorkerInstance):
    def __init__(self, url):
        path = dedicated_database(url)
        # Parent constructor calculates a path only; it never opens Incidents' lock.
        super().__init__(url)
        self.path = Path(str(path) + ".editorial-worker.lock")
