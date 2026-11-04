"""Persistent Editorial integration: temporary storage, fake WinCred/Telegram only."""
import ctypes
from contextlib import closing
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.core import editorial_credentials as credentials
from app.core.incidents_credentials import Credential
from app.editorial.config import EditorialSettings, load_settings, dedicated_database
from app.editorial.media import MediaStore
from app.editorial.models import Asset, Cursor, Draft, Version, Update, Reply
from app.editorial.storage import copy_storage, snapshot
from app.migrations.editorial import migrate
from app.workers import editorial as worker
from app.dev_launcher import BackendSupervisor
from tests.test_dev_launcher import FakeChildren, FakeChild, Clock, Stop, settings as incident_settings
from tests.test_editorial import FakeTelegram, png

TOKEN = "123456:" + "x" * 35


class EditorialIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.path = self.source / "editorial.sqlite3"
        self.url = "sqlite:///" + self.path.as_posix()
        self.engine = create_engine(self.url)
        self.addCleanup(self.engine.dispose)
        migrate(self.engine)
        self.media = MediaStore(self.source / "media")
        self.permissions = self.source / "permissions.json"
        self.permissions.write_text('{"17":["artwork.submit"]}')
        self.settings = EditorialSettings(enabled=True, database_url=self.url, media_root=self.media.root,
                                          permissions_file=self.permissions, chat_id=-456)
        guard = patch.object(socket.socket, "connect", side_effect=AssertionError("Real network forbidden"))
        guard.start()
        self.addCleanup(guard.stop)

    def test_credential_roundtrip_only_uses_dedicated_target(self):
        raw = TOKEN.encode("utf-16-le")
        buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        record = Credential(CredentialBlob=buffer, CredentialBlobSize=len(raw))
        api = Mock()
        def read(target, kind, flags, output):
            self.assertEqual(target, "ATLAS/Editorial/BotToken")
            ctypes.cast(output, ctypes.POINTER(ctypes.POINTER(Credential)))[0] = ctypes.pointer(record)
            return True
        api.CredReadW.side_effect = read
        with patch.object(credentials, "_api", return_value=api):
            self.assertEqual(credentials.read_token().get_secret_value(), TOKEN)
            def write(pointer, flags):
                value = ctypes.cast(pointer, ctypes.POINTER(Credential)).contents
                self.assertEqual(value.TargetName, "ATLAS/Editorial/BotToken")
                self.assertEqual(value.Persist, 2)
                return True
            api.CredWriteW.side_effect = write
            credentials.enroll_token(TOKEN)
        api.CredFree.assert_called_once()
        api.CredWriteW.assert_called_once()

    def test_missing_invalid_credentials_and_hidden_enrollment_fail_safely(self):
        api = Mock()
        api.CredReadW.return_value = False
        with patch.object(credentials, "_api", return_value=api):
            with self.assertRaises(credentials.EditorialCredentialUnavailable):
                credentials.read_token()
            with self.assertRaises(credentials.EditorialCredentialUnavailable):
                credentials.enroll_token("invalid")
        with patch("sys.argv", ["credentials", "enroll"]), patch.object(credentials.sys.stdin, "isatty", return_value=True), \
                patch.object(credentials.sys.stderr, "isatty", return_value=True), \
                patch.object(credentials.getpass, "getpass", return_value=TOKEN), \
                patch.object(credentials, "enroll_token") as enroll, patch("sys.stdout", new_callable=StringIO) as out:
            before = dict(os.environ)
            self.assertEqual(credentials.main(), 0)
            enroll.assert_called_once_with(TOKEN)
            self.assertNotIn(TOKEN, out.getvalue())
            self.assertEqual(dict(os.environ), before)

    def test_local_config_survives_sessions_environment_can_disable_and_tokens_rejected(self):
        config = self.root / "settings.json"
        config.write_text(json.dumps({"enabled": True, "database_url": self.url, "chat_id": -456}))
        with patch.dict(os.environ, {"ATLAS_EDITORIAL_CONFIG_FILE": str(config), "ATLAS_EDITORIAL_ENABLED": "false"}):
            self.assertFalse(load_settings().enabled)
        with patch.dict(os.environ, {"ATLAS_EDITORIAL_CONFIG_FILE": str(config)}, clear=True):
            self.assertTrue(load_settings().enabled)
            self.assertTrue(load_settings().enabled)
            config.write_text(json.dumps({"bot_token": TOKEN}))
            with self.assertRaises(ValueError) as error:
                load_settings()
            self.assertNotIn(TOKEN, str(error.exception))
        with self.assertRaises(ValueError):
            dedicated_database("sqlite:///" + (self.root / "atlas.db").as_posix())

    def test_enabled_worker_loads_credential_inside_child_without_environment_token(self):
        provider = Mock(return_value=SecretStr(TOKEN))
        transport = Mock()
        before = dict(os.environ)
        with patch("sys.argv", ["editorial", "--once"]), patch.object(worker, "load_settings", return_value=self.settings), \
                patch.object(worker, "TelegramTransport", return_value=transport) as factory, \
                patch.object(worker, "run", return_value=0) as run:
            self.assertEqual(worker.main(credentials=provider), 0)
            provider.assert_called_once()
            factory.assert_called_once_with(provider.return_value)
            run.assert_called_once()
        self.assertEqual(dict(os.environ), before)

    def test_missing_or_invalid_worker_credential_does_not_contact_telegram(self):
        for provider in [Mock(side_effect=credentials.EditorialCredentialUnavailable()), Mock(return_value=SecretStr("bad"))]:
            with patch("sys.argv", ["editorial"]), patch.object(worker, "load_settings", return_value=self.settings), \
                    patch.object(worker, "TelegramTransport") as transport:
                self.assertEqual(worker.main(credentials=provider), 2)
                transport.assert_not_called()

    def test_disabled_worker_never_accesses_credential_or_database(self):
        with patch("sys.argv", ["editorial"]), patch.object(worker, "load_settings", return_value=SimpleNamespace(enabled=False)), \
                patch.object(worker, "create_engine") as engine:
            provider = Mock()
            self.assertEqual(worker.main(credentials=provider), 0)
            provider.assert_not_called()
            engine.assert_not_called()

    def test_credential_api_exception_never_exposes_token(self):
        api = Mock()
        api.CredReadW.side_effect = RuntimeError(TOKEN)
        with patch.object(credentials, "_api", return_value=api):
            with self.assertRaises(credentials.EditorialCredentialUnavailable) as error:
                credentials.read_token()
        self.assertNotIn(TOKEN, str(error.exception))

    def test_duplicate_worker_refused_before_credential_lookup(self):
        with worker.EditorialInstance(self.url), patch("sys.argv", ["editorial"]), \
                patch.object(worker, "load_settings", return_value=self.settings):
            provider = Mock()
            self.assertEqual(worker.main(credentials=provider), 3)
            provider.assert_not_called()

    def seed_artwork(self):
        prepared = self.media.prepare(png())
        with Session(self.engine) as db:
            db.add(Asset(id="a" * 32, **prepared))
            db.add(Draft(id="b" * 32, chat_id=-456, user_id=17, state="classified", revision=1, prompt_message_id=100))
            db.add(Version(draft_id="b" * 32, revision=1, asset_id="a" * 32, compressed_photo=False,
                           operation="board", created_at="2026-11-03T00:00:00Z"))
            db.add(Update(id=8, payload={"ignore": True}, state="done"))
            db.add(Reply(update_id=8, draft_id="b" * 32, chat_id=-456, text="Private draft", state="sending"))
            db.get(Cursor, 1).next_offset = 9
            db.commit()

    def test_copy_preserves_every_table_original_and_preview_and_source(self):
        import sqlite3
        self.seed_artwork()
        destination = self.root / "durable"
        before = {p.name: p.read_bytes() for p in self.media.root.iterdir()}
        receipt = copy_storage(self.path, self.media.root, destination)
        self.assertTrue(receipt["source_retained"])
        self.assertEqual(receipt["asset_count"], 1)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (destination / "media").iterdir()})
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(destination / "editorial.sqlite3")) as target:
            self.assertEqual(snapshot(source), snapshot(target))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.media.root.iterdir()})
        self.assertTrue(self.path.is_file())
        self.assertEqual(receipt["database_sha256"], sha256((destination / "editorial.sqlite3").read_bytes()).hexdigest())

    def test_copy_refuses_running_source_existing_destination_and_missing_asset(self):
        self.seed_artwork()
        with worker.EditorialInstance(self.url):
            with self.assertRaises(Exception):
                copy_storage(self.path, self.media.root, self.root / "durable")
        with self.assertRaises(ValueError):
            copy_storage(self.path, self.media.root, self.source)
        next(self.media.root.glob("*.preview.jpg")).unlink()
        with self.assertRaises(FileNotFoundError):
            copy_storage(self.path, self.media.root, self.root / "durable")
        self.assertFalse((self.root / "durable").exists())
        self.assertTrue(self.path.is_file())

    def test_durable_draft_recovered_across_two_restarts_no_publication(self):
        import threading
        self.seed_artwork()
        transport = FakeTelegram()
        for _ in range(2):
            worker.run(self.engine, self.settings, transport, threading.Event(), once=True)
        with Session(self.engine) as db:
            self.assertEqual(db.get(Draft, "b" * 32).state, "classified")
            self.assertEqual(db.get(Cursor, 1).next_offset, 9)
            self.assertEqual(db.scalar(select(Reply)).state, "uncertain")
            self.assertEqual(db.scalar(select(Version)).operation, "board")
        self.assertEqual(transport.sent, [])


class BothChildren(FakeChildren):
    def __init__(self, editorial_exit=None, **kwargs):
        super().__init__(**kwargs)
        self.editorial_exit, self.editorials = editorial_exit, []
        self.editorial_times = []

    def spawn(self, command, environment, cwd):
        if "app.workers.editorial" in command:
            self.calls.append((list(command), dict(environment), cwd))
            child = FakeChild(self.editorial_exit)
            self.editorials.append(child)
            self.editorial_times.append(self.clock())
            return child
        return super().spawn(command, environment, cwd)


class EditorialSupervisorTests(unittest.TestCase):
    def run_supervisor(self, children, enabled=True, limit=200, callback=None, incidents=True):
        clock = Clock()
        children.clock = clock
        stop = Stop(clock, limit, callback)
        config = SimpleNamespace(enabled=enabled, database_url="sqlite:///isolated-editorial.sqlite3",
            media_root="private", permissions_file="permissions.json", chat_id=-456, download_limit_bytes=15728640)
        provider = Mock(return_value=SecretStr(TOKEN))
        supervisor = BackendSupervisor(incident_settings(incidents), editorial_settings=config,
            children_factory=lambda: children, available=lambda _: True, credentials=provider,
            clock=clock, stop=stop, environment={"ATLAS_EDITORIAL_BOT_TOKEN": "FORBIDDEN_PARENT_TOKEN"})
        result = supervisor.run()
        return result, children, provider

    def test_disabled_editorial_starts_no_child_or_editorial_credential_access(self):
        result, children, _ = self.run_supervisor(BothChildren(), enabled=False, limit=5)
        self.assertEqual(result, 0)
        self.assertEqual(children.editorials, [])
        self.assertEqual(len(children.workers), 1)

    def test_independent_restart_budget_does_not_restart_incidents_or_backend(self):
        result, children, provider = self.run_supervisor(BothChildren(editorial_exit=1))
        self.assertEqual(result, 0)
        self.assertEqual(len(children.editorials), 4)
        self.assertEqual(len(children.workers), 1)
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(sum("uvicorn" in call[0] for call in children.calls), 1)
        for previous, current, delay in zip(children.editorial_times, children.editorial_times[1:], [5, 30, 120]):
            self.assertGreaterEqual(current - previous, delay)
            self.assertLessEqual(current - previous, delay + 2)
        for command, environment, _ in children.calls:
            self.assertNotIn("ATLAS_EDITORIAL_BOT_TOKEN", environment)
            if "app.workers.editorial" in command:
                self.assertEqual(environment["TELEGRAM_INCIDENTS_BOT_TOKEN"], "")
                self.assertEqual(environment["ATLAS_EDITORIAL_ENABLED"], "true")
            else:
                self.assertEqual(environment["ATLAS_EDITORIAL_ENABLED"], "false")

    def test_permanent_exit_not_restarted_and_shutdown_signals_all_owned_children(self):
        for exit_code in [0, 2, 3, 4]:
            _, children, _ = self.run_supervisor(BothChildren(editorial_exit=exit_code), limit=10)
            self.assertEqual(len(children.editorials), 1)
            self.assertEqual(children.backend.interrupts, 1)
            self.assertEqual(children.workers[0].interrupts, 1)
        _, children, _ = self.run_supervisor(BothChildren(), limit=5)
        self.assertEqual(children.editorials[0].interrupts, 1)
        self.assertTrue(children.closed)

    def test_backend_exit_stops_editorial_and_incidents(self):
        children = BothChildren()
        def crash_backend():
            children.backend.exit_code = 1
        result, children, _ = self.run_supervisor(children, callback=crash_backend)
        self.assertEqual(result, 1)
        self.assertEqual(children.editorials[0].interrupts, 1)
        self.assertEqual(children.workers[0].interrupts, 1)
        self.assertTrue(children.closed)


if __name__ == "__main__":
    unittest.main()
