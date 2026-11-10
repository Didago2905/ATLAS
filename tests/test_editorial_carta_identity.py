"""Real isolated SQLite candidate reads; fake Telegram, no operational storage."""
from hashlib import sha256
from contextlib import closing
import sqlite3
import unittest

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.editorial.models import Interview, ProposalRevision, Asset, Version, Draft
from app.editorial.proposal_v22 import Proposal22, ExistingBeer
from app.editorial.service import EditorialService
from tests import test_editorial as foundation

CHAT, USER = foundation.CHAT, foundation.USER


class CartaIdentityTests(unittest.TestCase):
    setUp = foundation.EditorialTests.setUp
    message = foundation.EditorialTests.message
    dispatch = foundation.EditorialTests.dispatch
    draft = foundation.EditorialTests.draft
    start_image = foundation.EditorialTests.start_image
    attachment = foundation.EditorialTests.attachment
    count = foundation.EditorialTests.count

    def setUp(self):
        foundation.EditorialTests.setUp(self)
        self.catalog = self.root / "catalog.sqlite3"
        with closing(sqlite3.connect(self.catalog)) as db, db:
            db.execute("CREATE TABLE beers(id INTEGER PRIMARY KEY, name TEXT, brewery TEXT, style TEXT, is_available INTEGER, is_deleted INTEGER)")
            db.executemany("INSERT INTO beers VALUES (?,?,?,?,?,?)", [
                (1, "Leviatán", "Cyprez", "IPA", 1, 0),
                (2, "Leviatán", "Otra", "Double IPA", 0, 0),
                (3, "Leviatán", "Archivada", "IPA", 1, 1),
                (4, "Leviatán", "Tercera", "Stout", 0, 0),
                (5, "Leviatán", "Cuarta", "IPA", 1, 0)])
        self.before = sha256(self.catalog.read_bytes()).hexdigest()
        self.service.catalog_database_url = "sqlite:///" + self.catalog.as_posix()
        self.uid = 10

    def send(self, text, **extra):
        self.uid += 1
        self.dispatch(self.message(self.uid, text, **extra))

    def answer(self, name="leviatan"):
        self.send(name, reply_to_message={"message_id": self.draft()["prompt"]})

    def token(self, index=0):
        return self.transport.sent[-1]["markup"]["inline_keyboard"][index][0]["callback_data"]

    def click(self, token, user=USER):
        self.uid += 1
        self.dispatch({"update_id": self.uid, "callback_query": {
            "id": "fake", "from": {"id": user, "is_bot": False},
            "message": {"chat": {"id": CHAT, "type": "group"}}, "data": token}})

    def proposal(self):
        with Session(self.engine) as db:
            return Proposal22.model_validate(db.scalar(select(ProposalRevision).order_by(ProposalRevision.revision.desc())).payload)

    def test_success_real_lookup_and_explicit_confirmation_no_publication(self):
        self.send("/carta22")
        self.assertTrue(self.transport.sent[-1]["markup"]["force_reply"])
        self.answer()
        text = self.transport.sent[-1]["text"]
        self.assertIn("Cyprez · IPA · disponible", text)
        self.assertIn("Otra · Double IPA · no disponible", text)
        self.assertNotIn("Archivada", text)
        self.assertNotIn("Cuarta", text)
        self.assertEqual(self.proposal().beers[0].kind, "unresolved")
        self.assertTrue(all(len(row[0]["callback_data"].encode()) <= 64 for row in self.transport.sent[-1]["markup"]["inline_keyboard"]))
        self.click(self.token())
        proposal = self.proposal()
        self.assertIsInstance(proposal.beers[0], ExistingBeer)
        self.assertEqual(proposal.beers[0].beer_id, 1)
        self.assertEqual(proposal.beers[0].snapshot.name, "Leviatán")
        self.assertEqual(proposal.readiness, "incomplete")
        self.assertEqual(proposal.actions, ())
        self.assertEqual(self.count(Asset), 0)
        self.assertEqual(self.count(Version), 0)
        self.assertEqual(self.transport.downloads, [])
        self.assertIn("No se aprobó ni publicó", self.transport.sent[-1]["text"])
        self.assertEqual(sha256(self.catalog.read_bytes()).hexdigest(), self.before)

    def test_no_matches_retry_and_cancel(self):
        self.send("/carta22")
        self.answer("Nada")
        self.assertIn("No encontré", self.transport.sent[-1]["text"])
        self.answer()
        self.click(self.token(-1))
        self.assertEqual(self.draft()["state"], "cancelled")
        self.assertEqual(self.proposal().beers[0].kind, "unresolved")

    def test_cancel_at_name_and_reenter_preserves_revisions(self):
        self.send("/carta22")
        old_case = self.proposal().case_id
        self.send("/cancelar")
        self.send("/carta22")
        self.assertNotEqual(self.proposal().case_id, old_case)
        self.assertEqual(self.count(Draft), 1)
        self.assertEqual(self.count(ProposalRevision), 2)

    def test_stale_callbacks_after_search_retry_and_confirmation(self):
        self.send("/carta22")
        self.answer()
        old = self.token()
        self.click(self.token(-2))  # Explicit retry invalidates old candidate buttons.
        self.click(old)
        self.assertIn("no está vigente", self.transport.sent[-1]["text"])
        self.send("/continuar")
        self.answer()
        token = self.token()
        self.click(token)
        count = self.count(ProposalRevision)
        self.click(token)
        self.assertIn("no está vigente", self.transport.sent[-1]["text"])
        self.assertEqual(self.count(ProposalRevision), count)

    def test_revalidate_changed_deleted_or_missing_id(self):
        for sql in ("UPDATE beers SET brewery='Cambiada' WHERE id=1",
                    "UPDATE beers SET is_deleted=1 WHERE id=1", "DELETE FROM beers WHERE id=1"):
            with self.subTest(sql=sql):
                with closing(sqlite3.connect(self.catalog)) as db, db:
                    db.execute("INSERT OR REPLACE INTO beers VALUES(1,'Leviatán','Cyprez','IPA',1,0)")
                if self.count(Draft):
                    self.send("/cancelar")
                self.send("/carta22")
                self.answer()
                token = self.token()
                with closing(sqlite3.connect(self.catalog)) as db, db:
                    db.execute(sql)
                self.click(token)
                self.assertIn("no se pudo verificar", self.transport.sent[-1]["text"])
                self.assertEqual(self.proposal().beers[0].kind, "unresolved")

    def test_unauthorized_user_and_revoked_grant(self):
        self.send("/carta22", user=999)
        self.assertEqual(self.count(Draft), 0)
        self.send("/carta22")
        self.answer()
        token = self.token()
        self.click(token, user=999)
        self.assertEqual(self.proposal().beers[0].kind, "unresolved")
        self.auth.grants.clear()
        self.click(token)
        self.assertEqual(self.proposal().beers[0].kind, "unresolved")

    def test_other_authorized_operator_cannot_confirm_owner_case(self):
        self.auth.grants[99] = frozenset({"artwork.submit"})
        self.send("/carta22")
        self.answer()
        self.click(self.token(), user=99)
        self.assertEqual(self.count(Draft), 1)
        self.assertEqual(self.proposal().beers[0].kind, "unresolved")

    def test_only_matching_reply_is_accepted_and_no_image_download(self):
        self.send("/carta22")
        self.send("Leviatán")
        self.send("Leviatán", reply_to_message={"message_id": 9999})
        self.dispatch(self.attachment(uid=50))
        self.assertEqual(self.transport.downloads, [])
        self.assertEqual(self.proposal().beers[0].kind, "unresolved")
        with Session(self.engine) as db:
            self.assertEqual(db.get(Interview, self.draft()["id"]).history["phase"], "name")

    def test_restart_recovers_candidates_and_confirmation(self):
        self.send("/carta22")
        self.answer()
        token = self.token()
        self.service = EditorialService(self.engine, self.auth, self.media, self.transport, 1000,
                                       catalog_database_url="sqlite:///" + self.catalog.as_posix())
        self.click(token)
        self.assertEqual(self.proposal().beers[0].beer_id, 1)
        before = self.count(ProposalRevision)
        self.send("/resumen")
        self.assertIn("identidad confirmada", self.transport.sent[-1]["text"])
        self.assertEqual(self.count(ProposalRevision), before)

    def test_v21_active_draft_is_not_replaced(self):
        self.start_image()
        before = self.draft()
        self.send("/carta22")
        self.assertIn("borrador activo", self.transport.sent[-1]["text"])
        self.assertEqual(self.draft(), before)
        self.assertEqual(self.count(ProposalRevision), 0)
        self.send("/vista")
        self.assertIn("image", self.transport.sent[-1])

    def test_missing_catalog_fails_closed_without_creating_case(self):
        self.service.catalog_database_url = None
        self.send("/carta22")
        self.assertEqual(self.count(Draft), 0)
        self.assertIn("no está configurada", self.transport.sent[-1]["text"])

    def test_catalog_failure_does_not_lose_case_or_expose_paths(self):
        self.send("/carta22")
        self.service.catalog_database_url = "sqlite:///" + (self.root / "missing.sqlite3").as_posix()
        self.answer()
        self.assertIn("No se pudo consultar", self.transport.sent[-1]["text"])
        self.assertNotIn(str(self.root), self.transport.sent[-1]["text"])
        self.assertEqual(self.count(ProposalRevision), 1)
        self.assertFalse((self.root / "missing.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
