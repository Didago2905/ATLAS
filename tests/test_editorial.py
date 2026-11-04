"""Offline Editorial foundation: temporary SQLite/media and fake Telegram only."""
from contextlib import contextmanager
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.editorial.config import Authorization, EditorialSettings, private_root, REPO
from app.editorial.media import MediaStore
from app.editorial.models import Asset, Cursor, Draft, Update, Version, Reply
from app.editorial.service import EditorialService
from app.editorial.telegram import TelegramTransport, TransportError, DownloadLimit
from app.migrations.editorial import migrate, check_schema
from app.workers import editorial as worker
from app.core.incidents_instance import WorkerInstance

CHAT, USER = -456, 17


def png(color="red", size=(40, 60)):
    output = BytesIO()
    with Image.new("RGB", size, color) as image:
        image.save(output, "PNG")
    return output.getvalue()


class FakeTelegram:
    def __init__(self):
        self.image = png()
        self.mid = 100
        self.sent, self.downloads, self.polls = [], [], []
        self.fail_download = self.fail_send = False
        self.batch = []

    def send_message(self, chat, text, markup=None):
        if self.fail_send:
            raise TransportError()
        self.mid += 1
        self.sent.append(dict(chat=chat, text=text, markup=markup))
        return self.mid

    def send_photo(self, chat, text, image, markup=None):
        mid = self.send_message(chat, text, markup)
        self.sent[-1]["image"] = image
        return mid

    def answer_callback(self, callback_id):
        pass

    def get_updates(self, offset):
        self.polls.append(offset)
        return self.batch

    def download(self, file_id, limit):
        self.downloads.append((file_id, limit))
        if self.fail_download:
            raise TransportError()
        return self.image


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "editorial.sqlite3"
        self.engine = create_engine("sqlite:///" + self.path.as_posix())
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as c:
            c.exec_driver_sql("CREATE TABLE beers(id INTEGER PRIMARY KEY, tap_position INTEGER, name TEXT)")
            c.exec_driver_sql("INSERT INTO beers VALUES (1,7,'unchanged')")
        migrate(self.engine)
        self.transport = FakeTelegram()
        self.auth = Authorization(CHAT, {str(USER): ["artwork.submit", "beer.create", "beer.edit", "event.prepare"]})
        self.media = MediaStore(self.root / "private")
        self.service = EditorialService(self.engine, self.auth, self.media, self.transport, 15 * 1024 * 1024)
        self.no_network = patch.object(socket.socket, "connect", side_effect=AssertionError("Real network forbidden"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)

    def message(self, uid, text=None, user=USER, chat=CHAT, **extra):
        msg = {"message_id": uid, "chat": {"id": chat, "type": "group"},
               "from": {"id": user, "is_bot": False}, **extra}
        if text is not None:
            msg["text"] = text
        return {"update_id": uid, "message": msg}

    def dispatch(self, raw):
        self.service.ingest([raw])
        for _ in range(10):
            if not self.service.process_one():
                break
        for _ in range(10):
            if not self.service.flush_one():
                break

    def draft(self):
        with Session(self.engine) as db:
            d = db.scalar(select(Draft))
            return dict(id=d.id, revision=d.revision, prompt=d.prompt_message_id, state=d.state)

    def attachment(self, uid=2, **extra):
        return self.message(uid, reply_to_message={"message_id": self.draft()["prompt"]},
                            document={"file_id": "fake-file", "file_size": len(self.transport.image)}, **extra)

    def start_image(self):
        self.dispatch(self.message(1, "/obra@ATLAS_Editorial_Bot"))
        self.dispatch(self.attachment())

    def callback(self, uid=3, operation="board", revision=None, user=USER):
        draft = self.draft()
        revision = draft["revision"] if revision is None else revision
        return {"update_id": uid, "callback_query": {"id": "fake-callback", "from": {"id": user, "is_bot": False},
                "message": {"chat": {"id": CHAT, "type": "group"}},
                "data": f'op:{draft["id"]}:{revision}:{operation}'}}

    def count(self, model):
        with Session(self.engine) as db:
            return len(db.scalars(select(model)).all())

    def assert_catalog_unchanged(self):
        with self.engine.connect() as c:
            self.assertEqual(c.exec_driver_sql("SELECT * FROM beers").all(), [(1, 7, "unchanged")])
        self.assertFalse((self.root / "static").exists())
        self.assertNotIn("issue_reports", inspect(self.engine).get_table_names())

    def test_migration_is_explicit_repeatable_and_preserves_existing_tables(self):
        migrate(self.engine)
        with self.engine.connect() as c:
            check_schema(c)
        self.assert_catalog_unchanged()
        with self.engine.begin() as c:
            c.exec_driver_sql("ALTER TABLE editorial_assets ADD COLUMN unexpected TEXT")
        with self.assertRaises(ValueError):
            migrate(self.engine)
        self.assert_catalog_unchanged()

    def test_partial_schema_rejected_without_creating_other_tables(self):
        other = create_engine("sqlite:///" + (self.root / "partial.sqlite3").as_posix())
        try:
            with other.begin() as c:
                c.exec_driver_sql("CREATE TABLE editorial_cursor(id INTEGER PRIMARY KEY)")
            with self.assertRaises(ValueError):
                migrate(other)
            self.assertEqual(inspect(other).get_table_names(), ["editorial_cursor"])
        finally:
            other.dispose()

    def test_command_accepts_authorized_staff_and_requests_reply(self):
        self.dispatch(self.message(1, "/obra"))
        self.assertIn("Responde a este mensaje", self.transport.sent[-1]["text"])
        self.assertTrue(self.transport.sent[-1]["markup"]["force_reply"])
        self.assertEqual(self.draft()["prompt"], 101)
        self.assertEqual(self.count(Asset), 0)

    def test_group_user_anonymous_and_bot_inputs_fail_closed(self):
        cases = [self.message(1, "/obra", user=99), self.message(2, "/obra", chat=-789),
                 self.message(3, "/obra", sender_chat={"id": CHAT}),
                 self.message(4, "/obra", **{"from": {"id": USER, "is_bot": True}})]
        for raw in cases:
            self.dispatch(raw)
        self.assertEqual(self.count(Draft), 0)
        self.assertEqual(self.transport.sent, [])
        with Session(self.engine) as db:
            self.assertTrue(all(u.payload == {"ignore": True} for u in db.scalars(select(Update))))

    def test_inbox_and_cursor_commit_before_processing_and_deduplicate(self):
        raw = self.message(5, "/obra")
        self.service.ingest([raw, raw])
        self.service.ingest([raw])
        with Session(self.engine) as db:
            self.assertEqual(db.get(Cursor, 1).next_offset, 6)
            self.assertEqual(db.get(Update, 5).state, "pending")
        self.assertEqual(self.count(Update), 1)
        replacement = EditorialService(self.engine, self.auth, self.media, self.transport, self.service.download_limit)
        replacement.process_one()
        replacement.flush_one()
        self.dispatch(raw)
        self.assertEqual(self.count(Draft), 1)
        self.assertEqual(len(self.transport.sent), 1)

    def test_failed_inbox_insert_does_not_advance_cursor(self):
        with self.engine.begin() as c:
            c.exec_driver_sql("CREATE TRIGGER fail_update BEFORE INSERT ON editorial_updates BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        with self.assertRaises(Exception):
            self.service.ingest([self.message(3, "/obra")])
        with Session(self.engine) as db:
            self.assertEqual(db.get(Cursor, 1).next_offset, 0)

    def test_private_image_uses_shared_pipeline_and_actual_preview(self):
        with patch("app.services.museum_upload_service.upload_artwork", side_effect=AssertionError("Publication forbidden")), \
                patch("app.editorial.media.prepare_artwork", wraps=__import__("app.services.museum_upload_service", fromlist=["prepare_artwork"]).prepare_artwork) as prepare:
            self.start_image()
            prepare.assert_called_once()
        with Session(self.engine) as db:
            asset = db.scalar(select(Asset))
            self.assertEqual(self.media.path(asset.digest, ".png").read_bytes(), self.transport.image)
            self.assertEqual(self.media.path(asset.digest, ".preview.jpg").read_bytes(), self.transport.sent[-1]["image"])
        with Image.open(BytesIO(self.transport.sent[-1]["image"])) as image:
            self.assertEqual(image.format, "JPEG")
        self.assertIn("Sin elegir", self.transport.sent[-1]["text"])
        self.assertIn("Documento recibido", self.transport.sent[-1]["text"])
        self.assert_catalog_unchanged()

    def test_human_operation_persists_and_callbacks_are_idempotent_and_stale_safe(self):
        self.start_image()
        callback = self.callback()
        self.dispatch(callback)
        self.dispatch(callback)
        self.dispatch(self.callback(uid=4, revision=1))
        self.assertIn("ya no está vigente", self.transport.sent[-1]["text"])
        with Session(self.engine) as db:
            versions = db.scalars(select(Version).order_by(Version.revision)).all()
            self.assertEqual([v.operation for v in versions], [None, "board"])
        self.dispatch(self.message(5, "/vista"))
        self.assertIn("Tabla del Tap List", self.transport.sent[-1]["text"])
        self.assertEqual(self.draft()["state"], "classified")
        self.assert_catalog_unchanged()

    def test_accumulated_permissions_and_operation_permission_enforced(self):
        self.start_image()
        self.assertEqual(len(self.transport.sent[-1]["markup"]["inline_keyboard"]), 5)
        self.auth.grants[USER] = frozenset({"artwork.submit"})
        self.dispatch(self.callback(operation="new"))
        self.assertIn("No tienes permiso", self.transport.sent[-1]["text"])
        self.assertEqual(self.draft()["revision"], 1)

    def test_replacement_and_transport_limit_keep_previous_draft(self):
        self.start_image()
        self.dispatch(self.callback())
        before = self.draft()
        raw = self.attachment(uid=4)
        raw["message"]["document"]["file_size"] = self.service.download_limit + 1
        self.dispatch(raw)
        self.assertIn("15 MiB", self.transport.sent[-1]["text"])
        self.assertIn("No es el límite general", self.transport.sent[-1]["text"])
        self.assertEqual(self.draft(), before)
        self.assertEqual(len(self.transport.downloads), 1)
        self.transport.image = png("blue")
        self.dispatch(self.attachment(uid=5))
        self.assertEqual(self.draft()["revision"], 3)
        self.assertEqual(self.draft()["state"], "draft")
        self.assertEqual(self.count(Asset), 2)

    def test_actual_download_size_and_invalid_image_keep_draft(self):
        self.dispatch(self.message(1, "/obra"))
        self.service.download_limit = 10
        raw = self.attachment()
        raw["message"]["document"].pop("file_size")
        self.dispatch(raw)
        self.assertIn("descarga de Telegram", self.transport.sent[-1]["text"])
        self.service.download_limit = 1000
        self.transport.image = b"not an image"
        self.dispatch(self.attachment(uid=3))
        self.assertIn("ATLAS no pudo validar", self.transport.sent[-1]["text"])
        self.assertEqual(self.count(Asset), 0)
        self.assertEqual(self.draft()["revision"], 0)

    def test_photos_are_explicitly_marked_compressed(self):
        self.dispatch(self.message(1, "/obra"))
        raw = self.message(2, reply_to_message={"message_id": 101}, photo=[
            {"file_id": "small", "width": 10, "height": 10}, {"file_id": "large", "width": 40, "height": 60}])
        self.dispatch(raw)
        self.assertEqual(self.transport.downloads[0][0], "large")
        self.assertIn("Foto comprimida por Telegram", self.transport.sent[-1]["text"])

    def test_albums_forwards_wrong_reply_and_other_user_cannot_replace(self):
        self.dispatch(self.message(1, "/obra"))
        album = self.attachment()
        album["message"]["media_group_id"] = "album"
        self.dispatch(album)
        self.assertIn("álbum", self.transport.sent[-1]["text"])
        forwarded = self.attachment(uid=3, forward_origin={"type": "user"})
        self.dispatch(forwarded)
        wrong = self.attachment(uid=4)
        wrong["message"]["reply_to_message"]["message_id"] = 999
        self.dispatch(wrong)
        other = self.attachment(uid=5)
        other["message"]["from"]["id"] = 99
        self.dispatch(other)
        self.assertEqual(self.transport.downloads, [])
        self.assertEqual(self.count(Asset), 0)

    def test_download_retries_bounded_and_draft_remains(self):
        self.dispatch(self.message(1, "/obra"))
        self.transport.fail_download = True
        self.service.ingest([self.attachment()])
        for _ in range(3):
            self.service.process_one()
        self.service.flush_one()
        self.assertEqual(len(self.transport.downloads), 3)
        self.assertIn("Responde de nuevo", self.transport.sent[-1]["text"])
        self.assertEqual(self.draft()["revision"], 0)

    def test_restart_does_not_resend_uncertain_replies(self):
        self.service.ingest([self.message(1, "/obra")])
        self.service.process_one()
        with Session(self.engine) as db:
            db.scalar(select(Reply)).state = "sending"
            db.commit()
        self.service.recover_replies()
        self.assertFalse(self.service.flush_one())
        self.assertEqual(self.transport.sent, [])
        self.dispatch(self.message(2, "/obra"))
        self.assertIsNotNone(self.draft()["prompt"])

    def test_send_failure_and_revocation_do_not_lose_or_expose_draft(self):
        self.transport.fail_send = True
        self.dispatch(self.message(1, "/obra"))
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(Reply)).state, "uncertain")
        self.transport.fail_send = False
        self.service.ingest([self.message(2, "/obra")])
        self.service.process_one()
        self.auth.grants.clear()
        self.service.flush_one()
        self.assertEqual(self.transport.sent, [])
        self.assertEqual(self.count(Draft), 1)

    def test_cancel_and_restart_resume_draft_without_publication(self):
        self.start_image()
        self.dispatch(self.message(3, "/cancelar"))
        self.assertEqual(self.draft()["state"], "cancelled")
        self.dispatch(self.message(4, "/obra"))
        self.dispatch(self.message(5, "/vista"))
        self.assertIn("image", self.transport.sent[-1])
        self.assertEqual(self.count(Asset), 1)
        self.assert_catalog_unchanged()

    def test_same_bytes_deduplicate_assets_not_human_operation(self):
        self.start_image()
        self.dispatch(self.attachment(uid=3))
        self.assertEqual(self.count(Asset), 1)
        self.assertEqual(self.count(Version), 2)

    def test_public_media_roots_rejected(self):
        for root in [REPO / "static/editorial", REPO / "frontend/public/editorial", REPO / "frontend/src/editorial", REPO]:
            with self.assertRaises(ValueError):
                private_root(root)

    def test_invalid_or_ambiguous_permission_files_fail_closed(self):
        for grants in [{"017": ["artwork.submit"]}, {"17": ["administrator"]}, {"17": "artwork.submit"}]:
            with self.assertRaises(ValueError):
                Authorization(CHAT, grants)
        path = self.root / "permissions.json"
        path.write_text('{"17":["artwork.submit"],"17":["beer.create"]}')
        with self.assertRaises(ValueError):
            Authorization.load(SimpleNamespace(permissions_file=path, chat_id=CHAT))

    def test_singleton_separate_from_incidents_and_duplicate_editorial_rejected(self):
        url = "sqlite:///" + self.path.as_posix()
        with WorkerInstance(url):
            with worker.EditorialInstance(url):
                with self.assertRaises(Exception):
                    with worker.EditorialInstance(url):
                        pass

    def test_disabled_worker_does_not_touch_credentials_database_or_transport(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(EditorialSettings().enabled)
        with patch.object(worker, "load_settings", return_value=SimpleNamespace(enabled=False)), \
                patch.object(worker, "create_engine") as engine, patch.object(worker, "TelegramTransport") as transport, \
                patch.object(worker.Authorization, "load") as auth, patch("sys.argv", ["editorial", "--once"]):
            self.assertEqual(worker.main(), 0)
            engine.assert_not_called()
            transport.assert_not_called()
            auth.assert_not_called()

    def test_worker_restarts_with_durable_cursor_and_mocked_transport(self):
        permissions = self.root / "permissions.json"
        permissions.write_text(json.dumps({str(USER): ["artwork.submit"]}))
        settings = SimpleNamespace(permissions_file=permissions, chat_id=CHAT,
                                   media_root=self.media.root, download_limit_bytes=1000)
        self.transport.batch = [self.message(10, "/obra")]
        worker.run(self.engine, settings, self.transport, threading.Event(), once=True)
        self.transport.batch = []
        worker.run(self.engine, settings, self.transport, threading.Event(), once=True)
        self.assertEqual(self.transport.polls, [0, 11])
        self.assertEqual(self.count(Draft), 1)
        self.assert_catalog_unchanged()


class TransportTests(unittest.TestCase):
    def transport(self, result=None, raw=b"", declared=None, status=200):
        response = Mock(status=status)
        response.getheader.return_value = declared
        response.read.side_effect = BytesIO(json.dumps(result).encode() if result else raw).read
        connection = Mock()
        connection.getresponse.return_value = response
        factory = Mock(return_value=connection)
        token = SecretStr("123456:" + "x" * 35)
        return TelegramTransport(token, connection_factory=factory), connection, factory

    def test_mocked_poll_and_prompt_use_fixed_https_host(self):
        transport, connection, factory = self.transport({"ok": True, "result": []})
        self.assertEqual(transport.get_updates(14), [])
        factory.assert_called_once()
        self.assertEqual(factory.call_args.args, ("api.telegram.org",))
        payload = json.loads(connection.request.call_args.kwargs["body"])
        self.assertEqual(payload["offset"], 14)
        self.assertEqual(payload["allowed_updates"], ["message", "callback_query"])

    def test_download_content_and_declared_limits_and_safe_path(self):
        transport, _, _ = self.transport(raw=b"abcdef")
        with patch.object(transport, "_request", return_value={"file_path": "documents/file.png"}):
            with self.assertRaises(DownloadLimit):
                transport.download("fake", 5)
        transport, _, _ = self.transport(raw=b"abc", declared="999")
        with patch.object(transport, "_request", return_value={"file_path": "documents/file.png"}):
            with self.assertRaises(DownloadLimit):
                transport.download("fake", 5)
        for path in ["https://elsewhere/image", "../secret", "/absolute"]:
            with patch.object(transport, "_request", return_value={"file_path": path}):
                with self.assertRaises(TransportError):
                    transport.download("fake", 5)

    def test_transport_errors_never_include_secret_or_raw_response(self):
        transport, connection, _ = self.transport(raw=b"PRIVATE RESPONSE", status=500)
        with self.assertRaises(TransportError) as raised:
            transport.get_updates(0)
        self.assertEqual(str(raised.exception), "Editorial Telegram transport unavailable")
        self.assertNotIn("PRIVATE", str(raised.exception))

    def test_photo_preview_uses_bytes_not_public_url(self):
        transport, connection, _ = self.transport({"ok": True, "result": {"message_id": 19}})
        self.assertEqual(transport.send_photo(CHAT, "Borrador", b"fake-jpeg"), 19)
        body = connection.request.call_args.kwargs["body"]
        self.assertIn(b"fake-jpeg", body)
        self.assertNotIn(b"http", body)


if __name__ == "__main__":
    unittest.main()
