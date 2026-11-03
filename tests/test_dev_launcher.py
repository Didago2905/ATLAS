"""No real API services, Credential Manager entries or Telegram connections."""
import ctypes
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pydantic import SecretStr
from sqlalchemy import create_engine

from app.core.incidents_credentials import CredentialUnavailable, Credential, enroll_token, read_token
from app.core.incidents_instance import WorkerAlreadyRunning, WorkerInstance
from app.core.windows_children import StartupFailure, WindowsChildren
from app.dev_launcher import BackendSupervisor, REPO, port_available


def settings(enabled=False):
    return SimpleNamespace(database_url="sqlite:///synthetic.sqlite3", telegram_incidents_enabled=enabled,
        telegram_incidents_chat_id=SecretStr("-123456789"), telegram_incidents_max_attempts=6,
        telegram_incidents_bot_token=SecretStr("123456:" + "x" * 35))


class Clock:
    now = 0
    def __call__(self):
        return self.now


class Stop:
    def __init__(self, clock, limit=5, callback=None):
        self.clock, self.limit, self.callback = clock, limit, callback
        self.stopped = False

    def is_set(self):
        return self.stopped

    def wait(self, _):
        self.clock.now += 1
        if self.callback:
            self.callback()
        if self.clock.now >= self.limit:
            self.stopped = True
        return self.stopped


class FakeChild:
    def __init__(self, exit_code=None):
        self.exit_code = exit_code
        self.interrupts = 0
        self.waits = []

    def poll(self):
        return self.exit_code

    def interrupt(self):
        self.interrupts += 1

    def wait(self, seconds):
        self.waits.append(seconds)
        return True

    def finish_tree(self):
        pass


class FakeChildren:
    def __init__(self, worker_exit=None):
        self.backend = FakeChild()
        self.worker_exit = worker_exit
        self.workers = []
        self.calls = []
        self.closed = False
        self.ready = True
        self.clock = None
        self.worker_times = []

    def spawn(self, command, environment, cwd):
        self.calls.append((list(command), dict(environment), cwd))
        if "uvicorn" in command:
            return self.backend
        worker = FakeChild(self.worker_exit)
        if self.clock:
            self.worker_times.append(self.clock())
        self.workers.append(worker)
        return worker

    def owns_listener(self, _):
        return self.ready

    def close(self):
        self.closed = True


class SupervisorTests(unittest.TestCase):
    def run_supervisor(self, enabled=False, children=None, limit=5, credentials=None, callback=None):
        clock = Clock()
        children = children or FakeChildren()
        children.clock = clock
        stop = Stop(clock, limit, callback)
        credentials = credentials or Mock(return_value=SecretStr("123456:" + "x" * 35))
        supervisor = BackendSupervisor(settings(enabled), children_factory=lambda: children,
            credentials=credentials, available=lambda _: True, clock=clock, stop=stop,
            environment={"PATH": "synthetic-path", "TELEGRAM_INCIDENTS_BOT_TOKEN": "SYNTHETIC_SECRET"})
        return supervisor.run(), children, credentials

    def test_disabled_has_compatible_backend_command_and_no_credential_access(self):
        code, children, credentials = self.run_supervisor()
        self.assertEqual(code, 0)
        self.assertEqual(len(children.calls), 1)
        command, environment, cwd = children.calls[0]
        self.assertEqual(command, [sys.executable, "-B", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"])
        self.assertEqual(environment["TELEGRAM_INCIDENTS_BOT_TOKEN"], "")
        self.assertEqual(environment["TELEGRAM_INCIDENTS_ENABLED"], "false")
        self.assertEqual(cwd, REPO)
        self.assertEqual(children.workers, [])
        credentials.assert_not_called()
        self.assertTrue(children.closed)

    def test_enabled_token_is_only_in_worker_environment_not_arguments_or_parent(self):
        before = dict(os.environ)
        code, children, credentials = self.run_supervisor(True)
        self.assertEqual(code, 0)
        self.assertEqual(len(children.workers), 1)
        command, environment, _ = children.calls[1]
        self.assertEqual(command[-1], "app.workers.incident_notifications")
        self.assertNotIn("SYNTHETIC_SECRET", " ".join(command))
        self.assertEqual(environment["TELEGRAM_INCIDENTS_ENABLED"], "true")
        self.assertEqual(environment["TELEGRAM_INCIDENTS_MAX_ATTEMPTS"], "6")
        self.assertEqual(environment["TELEGRAM_INCIDENTS_BOT_TOKEN"], "123456:" + "x" * 35)
        self.assertEqual(children.calls[0][1]["TELEGRAM_INCIDENTS_BOT_TOKEN"], "")
        self.assertEqual(dict(os.environ), before)
        credentials.assert_called_once()

    def test_occupied_port_starts_nothing(self):
        factory, credentials = Mock(), Mock()
        supervisor = BackendSupervisor(settings(True), children_factory=factory,
                                       credentials=credentials, available=lambda _: False)
        self.assertEqual(supervisor.run(), 2)
        factory.assert_not_called()
        credentials.assert_not_called()

    def test_readiness_must_belong_to_owned_job(self):
        children = FakeChildren()
        children.ready = False
        with self.assertRaises(StartupFailure):
            self.run_supervisor(True, children, limit=25)
        self.assertEqual(children.workers, [])
        self.assertTrue(children.closed)

    def test_three_worker_restarts_never_restart_or_terminate_backend(self):
        children = FakeChildren(worker_exit=1)
        observed = []

        def inspect_running():
            observed.append(children.backend.interrupts)

        _, children, credentials = self.run_supervisor(True, children, limit=200, callback=inspect_running)
        self.assertEqual(len(children.workers), 4)
        self.assertEqual(credentials.call_count, 4)
        for previous, current, delay in zip(children.worker_times, children.worker_times[1:], [5, 30, 120]):
            self.assertGreaterEqual(current - previous, delay)
            self.assertLessEqual(current - previous, delay + 2)
        self.assertEqual(sum("uvicorn" in call[0] for call in children.calls), 1)
        self.assertEqual(set(observed), {0})
        self.assertEqual(children.backend.interrupts, 1)  # Session shutdown only.

    def test_expected_and_permanent_exits_do_not_restart(self):
        for exit_code in [0, 2, 3, 4]:
            with self.subTest(exit_code=exit_code):
                _, children, _ = self.run_supervisor(True, FakeChildren(exit_code), limit=30)
                self.assertEqual(len(children.workers), 1)

    def test_missing_credential_leaves_backend_alive(self):
        credentials = Mock(side_effect=CredentialUnavailable())
        code, children, _ = self.run_supervisor(True, credentials=credentials)
        self.assertEqual(code, 0)
        self.assertEqual(children.workers, [])
        self.assertEqual(len(children.calls), 1)

    def test_backend_crash_stops_worker_without_backend_restart(self):
        children = FakeChildren()
        def fail_backend():
            children.backend.exit_code = 1
        code, children, _ = self.run_supervisor(True, children, callback=fail_backend)
        self.assertEqual(code, 1)
        self.assertEqual(len(children.calls), 2)
        self.assertEqual(children.workers[0].interrupts, 1)
        self.assertTrue(children.closed)

    def test_stop_during_backoff_does_not_start_another_worker(self):
        _, children, _ = self.run_supervisor(True, FakeChildren(1), limit=3)
        self.assertEqual(len(children.workers), 1)
        self.assertTrue(children.closed)

    def test_logs_do_not_echo_startup_exception_or_credentials(self):
        children = FakeChildren()
        original = children.spawn
        def fail_worker(command, environment, cwd):
            if "uvicorn" not in command:
                raise RuntimeError("SYNTHETIC_SECRET token-bearing-url")
            return original(command, environment, cwd)
        children.spawn = fail_worker
        with self.assertLogs("app.dev_launcher", level="ERROR") as logs:
            self.run_supervisor(True, children, limit=3)
        self.assertNotIn("SYNTHETIC_SECRET", " ".join(logs.output))
        self.assertTrue(children.closed)

    def test_port_probe_uses_disposable_port_only(self):
        with socket.socket() as held:
            held.bind(("0.0.0.0", 0))
            held.listen()
            self.assertFalse(port_available(held.getsockname()[1]))


class InstanceTests(unittest.TestCase):
    def test_same_database_and_canonical_alias_are_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "reports.sqlite3"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("CREATE TABLE marker(id INTEGER)")
                connection.commit()
            before = hashlib.sha256(database.read_bytes()).digest()
            url = "sqlite:///" + database.as_posix()
            alias = "sqlite:///" + (Path(directory) / "unused" / ".." / database.name).as_posix()
            with WorkerInstance(url):
                with self.assertRaises(WorkerAlreadyRunning):
                    with WorkerInstance(alias):
                        pass
                with WorkerInstance("sqlite:///" + (Path(directory) / "other.sqlite3").as_posix()):
                    pass
            with WorkerInstance(url):
                pass
            self.assertEqual(hashlib.sha256(database.read_bytes()).digest(), before)

    def test_lock_rejects_second_process_and_releases_after_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            url = "sqlite:///" + (Path(directory) / "reports.sqlite3").as_posix()
            script = "from app.core.incidents_instance import WorkerInstance,WorkerAlreadyRunning; import sys\ntry:\n with WorkerInstance(sys.argv[1]): pass\nexcept WorkerAlreadyRunning: sys.exit(3)"
            with WorkerInstance(url):
                result = subprocess.run([sys.executable, "-B", "-c", script, url], cwd=REPO, capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 3)
            result = subprocess.run([sys.executable, "-B", "-c", script, url], cwd=REPO, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0)


    def test_manual_once_and_continuous_cli_share_the_same_lock(self):
        from app.workers import incident_notifications as worker
        with tempfile.TemporaryDirectory() as directory:
            url = "sqlite:///" + (Path(directory) / "reports.sqlite3").as_posix()
            engine = create_engine(url)
            try:
                with WorkerInstance(url):
                    for arguments in [[], ["--once"]]:
                        with self.subTest(arguments=arguments), patch("sys.argv", ["worker"] + arguments), \
                                patch("app.core.config.settings", settings(True)), \
                                patch("app.core.database.engine", engine), patch.object(worker, "run_loop") as run, \
                                patch.object(worker.signal, "signal"), patch.object(worker.logging, "basicConfig"):
                            self.assertEqual(worker.main(), 3)
                            run.assert_not_called()
            finally:
                engine.dispose()

    @unittest.skipUnless(hasattr(signal, "SIGBREAK"), "Windows Ctrl+Break")
    def test_worker_ctrl_break_requests_graceful_stop(self):
        from app.workers import incident_notifications as worker
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine("sqlite:///" + (Path(directory) / "reports.sqlite3").as_posix())
            handlers = {}
            def install(sig, handler):
                handlers[sig] = handler
            def run(instance, stop, once=False):
                self.assertFalse(stop.is_set())
                handlers[signal.SIGBREAK](None, None)
                self.assertTrue(stop.is_set())
                return 0
            try:
                with patch("sys.argv", ["worker", "--once"]), patch("app.core.config.settings", settings(True)), \
                        patch("app.core.database.engine", engine), patch.object(worker, "run_loop", side_effect=run), \
                        patch.object(worker.signal, "signal", side_effect=install), patch.object(worker.logging, "basicConfig"):
                    self.assertEqual(worker.main(), 0)
            finally:
                engine.dispose()


class CredentialTests(unittest.TestCase):
    def test_fake_credential_loading_and_freeing(self):
        raw = ("123456:" + "x" * 35).encode("utf-16-le")
        buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        credential = Credential(CredentialBlob=buffer, CredentialBlobSize=len(raw))
        api = Mock()
        def fake_read(target, kind, flags, output):
            ctypes.cast(output, ctypes.POINTER(ctypes.POINTER(Credential)))[0] = ctypes.pointer(credential)
            return True
        api.CredReadW.side_effect = fake_read
        with patch("app.core.incidents_credentials._api", return_value=api):
            token = read_token()
        self.assertNotIn("123456", repr(token))
        api.CredFree.assert_called_once()

    def test_enrollment_writes_only_dedicated_target_with_fake_api(self):
        api = Mock()
        with patch("app.core.incidents_credentials._api", return_value=api):
            enroll_token("123456:" + "x" * 35)
        api.CredWriteW.assert_called_once()
        api.CredReadW.assert_not_called()


@unittest.skipUnless(os.name == "nt", "Windows process Job tests")
class WindowsJobTests(unittest.TestCase):
    def test_job_close_cleans_only_its_disposable_child(self):
        children = WindowsChildren()
        handle = None
        try:
            child = children.spawn([sys.executable, "-B", "-c", "import time; time.sleep(60)"], dict(os.environ), REPO)
            self.assertIsNone(child.poll())
            handle = children.kernel.OpenProcess(0x100000, False, child.pid)
            self.assertTrue(handle)
            children.close()
            self.assertEqual(children.kernel.WaitForSingleObject(handle, 5000), 0)
        finally:
            children.close()
            if handle:
                children.kernel.CloseHandle(handle)

    def test_unexpected_owner_death_kills_disposable_job_child(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "owned.json"
            child_marker = Path(directory) / "child.pid"
            script = """import json,os,sys,time
from pathlib import Path
from app.core.windows_children import WindowsChildren
p=Path(sys.argv[1]); p.write_text(json.dumps({'owner':os.getpid()}))
job=WindowsChildren()
child_code='import os,time; from pathlib import Path; Path('+repr(sys.argv[2])+').write_text(str(os.getpid())); time.sleep(60)'
child=job.spawn([sys.executable,'-B','-c',child_code],dict(os.environ),Path.cwd())
p.write_text(json.dumps({'owner':os.getpid(),'child':child.pid}))
time.sleep(60)
"""
            owner = subprocess.Popen([sys.executable, "-B", "-c", script, str(marker), str(child_marker)], cwd=REPO,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            data, handle, descendant_handle = {}, None, None
            kernel = None
            try:
                for _ in range(100):
                    try:
                        data = json.loads(marker.read_text())
                    except (OSError, ValueError):
                        pass
                    if "child" in data and child_marker.exists() or owner.poll() is not None:
                        break
                    time.sleep(0.1)
                self.assertIn("child", data)
                from app.core.windows_children import _kernel
                kernel = _kernel()
                handle = kernel.OpenProcess(0x100000, False, data["child"])
                self.assertTrue(handle)
                descendant_handle = kernel.OpenProcess(0x100000, False, int(child_marker.read_text()))
                self.assertTrue(descendant_handle)
                os.kill(data["owner"], signal.SIGTERM)  # Own temporary process only.
                owner.wait(timeout=10)
                self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
                self.assertEqual(kernel.WaitForSingleObject(descendant_handle, 5000), 0)
            finally:
                if owner.poll() is None:
                    if "owner" in data:
                        os.kill(data["owner"], signal.SIGTERM)
                    owner.kill()
                    owner.wait(timeout=5)
                if handle:
                    kernel.CloseHandle(handle)
                if descendant_handle:
                    kernel.CloseHandle(descendant_handle)


if __name__ == "__main__":
    unittest.main()
