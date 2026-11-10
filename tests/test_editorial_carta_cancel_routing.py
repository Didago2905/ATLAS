"""Cancelled Carta -> legacy regression checks on isolated Editorial/catalog fixtures."""
from copy import deepcopy
import unittest

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.editorial.models import Interview, ProposalRevision, Asset, Version, Draft
from tests import test_editorial_carta_identity as fixtures


class CancelledCartaRoutingTests(unittest.TestCase):
    setUp = fixtures.CartaIdentityTests.setUp
    message = fixtures.CartaIdentityTests.message
    dispatch = fixtures.CartaIdentityTests.dispatch
    draft = fixtures.CartaIdentityTests.draft
    start_image = fixtures.CartaIdentityTests.start_image
    attachment = fixtures.CartaIdentityTests.attachment
    count = fixtures.CartaIdentityTests.count
    send = fixtures.CartaIdentityTests.send
    answer = fixtures.CartaIdentityTests.answer
    token = fixtures.CartaIdentityTests.token
    click = fixtures.CartaIdentityTests.click
    proposal = fixtures.CartaIdentityTests.proposal

    def snapshots(self, model):
        with Session(self.engine) as db:
            return deepcopy([dict(row) for row in db.execute(select(model.__table__).order_by(model.id)).mappings()])

    def start_legacy_operation(self):
        buttons = self.transport.sent[-1]['markup']['inline_keyboard']
        token = next(row[0]['callback_data'] for row in buttons if row[0]['callback_data'].endswith(':board'))
        self.click(token)
        with Session(self.engine) as db:
            self.assertEqual(db.get(Interview, self.draft()['id']).step, 'targets')
            row = db.scalar(select(ProposalRevision).order_by(ProposalRevision.revision.desc()))
            self.assertEqual(row.payload['schema_version'], '2.1')

    def test_cancel_then_obra_image_and_entrevista(self):
        self.send('/carta22')
        self.send('/cancelar')
        saved = self.snapshots(ProposalRevision)
        self.send('/obra')
        self.assertTrue(self.transport.sent[-1]['markup']['force_reply'])
        self.uid += 1
        self.dispatch(self.attachment(uid=self.uid))
        self.assertEqual(self.count(Asset), 1)
        self.send('/entrevista')
        self.start_legacy_operation()
        self.assertEqual(self.snapshots(ProposalRevision)[:len(saved)], saved)
        self.assertEqual(self.count(Draft), 1)

    def test_cancel_then_entrevista_without_image(self):
        self.send('/carta22')
        self.send('/cancelar')
        self.send('/entrevista')
        self.assertIn('Elige la operación', self.transport.sent[-1]['text'])
        self.start_legacy_operation()
        self.assertEqual(self.count(Asset), 0)

    def test_active_carta_routing_and_active_draft_protection(self):
        self.send('/carta22')
        original = self.snapshots(Interview), self.snapshots(ProposalRevision)
        for command in ('/obra', '/entrevista', '/corregir', '/carta22'):
            self.send(command)
            self.assertEqual((self.snapshots(Interview), self.snapshots(ProposalRevision)), original)
        self.send('/continuar')
        self.assertTrue(self.transport.sent[-1]['markup']['force_reply'])
        self.answer()
        self.send('/continuar')
        self.assertIn('confirma una cerveza', self.transport.sent[-1]['text'])
        self.click(self.token())
        self.assertEqual(self.proposal().beers[0].kind, 'existing')

    def test_stale_carta_and_legacy_buttons_after_return(self):
        self.start_image()
        draft = self.draft()
        old_legacy = f'op:{draft["id"]}:{draft["revision"]}:board'
        self.send('/cancelar')
        self.send('/carta22')
        self.answer()
        old_carta = self.token()
        self.send('/cancelar')
        self.click(old_carta)
        self.assertIn('no está vigente', self.transport.sent[-1]['text'])
        self.send('/entrevista')
        menu = deepcopy(self.transport.sent[-1]['markup'])
        before = self.snapshots(ProposalRevision)
        self.click(old_carta)
        self.click(old_legacy)
        self.assertIn('no está vigente', self.transport.sent[-1]['text'])
        self.assertEqual(self.snapshots(ProposalRevision), before)
        self.click(next(row[0]['callback_data'] for row in menu['inline_keyboard'] if row[0]['callback_data'].endswith(':board')))
        self.assertEqual(self.snapshots(ProposalRevision)[-1]['payload']['schema_version'], '2.1')

    def test_saved_proposals_versions_and_media_survive(self):
        self.start_image()
        draft = self.draft()
        self.click(f'op:{draft["id"]}:{draft["revision"]}:board')
        self.send('/entrevista')
        self.send('/cancelar')
        self.send('/carta22')
        self.answer()
        self.click(self.token())
        self.send('/cancelar')
        proposals = self.snapshots(ProposalRevision)
        assets, versions = self.snapshots(Asset), self.snapshots(Version)
        media = {p.name: p.read_bytes() for p in self.media.root.iterdir() if p.is_file()}
        self.send('/entrevista')
        self.start_legacy_operation()
        self.assertEqual(self.snapshots(ProposalRevision)[:len(proposals)], proposals)
        self.assertEqual(self.snapshots(Asset), assets)
        self.assertEqual(self.snapshots(Version), versions)
        self.assertEqual({p.name: p.read_bytes() for p in self.media.root.iterdir() if p.is_file()}, media)

    def test_legacy_active_draft_not_replaced(self):
        self.start_image()
        before = self.snapshots(Draft), self.snapshots(Version)
        self.send('/carta22')
        self.assertIn('borrador activo', self.transport.sent[-1]['text'])
        self.assertEqual((self.snapshots(Draft), self.snapshots(Version)), before)

    def test_authorization_and_reply_rules_survive_return(self):
        self.send('/carta22')
        old_prompt = self.draft()['prompt']
        self.send('/cancelar')
        state = self.snapshots(Interview)
        self.send('/obra', user=999)
        self.assertEqual(self.snapshots(Interview), state)
        self.send('/obra')
        self.uid += 1
        raw = self.attachment(uid=self.uid)
        raw['message']['reply_to_message']['message_id'] = old_prompt
        self.dispatch(raw)
        self.assertEqual(self.transport.downloads, [])
        self.send('Solo texto', reply_to_message={'message_id': self.draft()['prompt']})
        self.assertEqual(self.count(Asset), 0)
        self.uid += 1
        self.dispatch(self.attachment(uid=self.uid))
        self.assertEqual(self.count(Asset), 1)

    def test_pending_legacy_can_cancel_and_start_another_carta(self):
        self.send('/carta22')
        self.send('/cancelar')
        self.send('/entrevista')
        self.send('/cancelar')
        self.send('/carta22')
        self.assertEqual(self.proposal().revision, 2)
        self.assertEqual(self.count(ProposalRevision), 2)


if __name__ == '__main__':
    unittest.main()
