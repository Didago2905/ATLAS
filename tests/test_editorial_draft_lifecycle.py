"""Saved commercial lifecycle on isolated Editorial/catalog SQLite and fake Telegram."""
from copy import deepcopy
from hashlib import sha256
import unittest
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.editorial.models import ProposalRevision, Interview
from app.editorial.service import EditorialService
from tests import test_editorial_commercial as fixtures
from tests.test_editorial import USER


class LifecycleTests(unittest.TestCase):
    setUp = fixtures.CommercialTests.setUp
    close_logs = fixtures.CommercialTests.close_logs
    message = fixtures.CommercialTests.message
    dispatch = fixtures.CommercialTests.dispatch
    draft = fixtures.CommercialTests.draft
    count = fixtures.CommercialTests.count
    send = fixtures.CommercialTests.send
    answer = fixtures.CommercialTests.answer
    click = fixtures.CommercialTests.click
    token = fixtures.CommercialTests.token
    proposal = fixtures.CommercialTests.proposal
    action = fixtures.CommercialTests.action
    enter = fixtures.CommercialTests.enter
    field = fixtures.CommercialTests.field
    state = fixtures.CommercialTests.state
    start_image = fixtures.CommercialTests.start_image
    attachment = fixtures.CommercialTests.attachment

    def rows(self):
        with Session(self.engine) as db:
            return deepcopy([dict(r) for r in db.execute(select(ProposalRevision.__table__).order_by(ProposalRevision.id)).mappings()])

    def current(self):
        from app.editorial import interview
        with Session(self.engine) as db:
            from app.editorial.models import Draft
            return deepcopy(interview.latest(db, db.get(Draft, self.draft()['id'])).payload)

    def create(self, name):
        self.send('/nueva22')
        self.enter(name)
        self.send('/corregir')

    def saved_token(self, name):
        self.send('/borradores22')
        return next(row[0]['callback_data'] for row in self.transport.sent[-1]['markup']['inline_keyboard']
                    if name in row[0]['text'])

    def test_finish_keeps_exact_revisions_full_values_and_unapproved_state(self):
        self.create('Dark Blend')
        self.field('description')
        self.enter('Descripción ' * 25)
        self.send('/corregir')
        before = self.rows()
        self.action('f')
        self.assertEqual(self.draft()['state'], 'saved')
        self.assertIsNone(self.draft()['prompt'])
        self.assertEqual(self.rows(), before)
        self.assertIsNone(self.current()['preparation'])
        self.assertEqual(self.current()['actions'][0]['is_available'], False)
        self.assertIn('sin aprobación', self.transport.sent[-1]['text'])
        self.assertEqual(sha256(self.catalog.read_bytes()).hexdigest(), self.before)
        self.send('/resumen')
        self.assertEqual(self.rows(), before)

    def test_two_cases_reopen_old_case_and_append_above_global_revision(self):
        self.create('Primera')
        original = self.current()
        self.action('f')
        self.create('Segunda')
        self.action('f')
        old_rows = self.rows()
        maximum = max(row['revision'] for row in old_rows)
        token = self.saved_token('Primera')
        self.click(token)
        self.assertEqual(self.current(), original)
        self.assertEqual(self.count(ProposalRevision), len(old_rows))
        self.field('description')
        self.enter('Cambiar solo primera')
        self.assertGreater(self.current()['revision'], maximum)
        self.assertEqual(self.current()['case_id'], original['case_id'])
        self.assertEqual(self.rows()[:len(old_rows)], old_rows)
        self.send('/corregir')
        self.action('f')
        self.click(token)
        self.assertIn('lista ya no está vigente', self.transport.sent[-1]['text'])

    def test_reopen_after_restart_preserves_snapshot_and_rejects_old_buttons(self):
        self.create('Recuperable')
        old_button = self.token()
        context = deepcopy(self.state()['commercial'])
        self.action('f')
        token = self.saved_token('Recuperable')
        before = self.rows()
        self.service = EditorialService(self.engine, self.auth, self.media, self.transport, 1000,
                                       catalog_database_url='sqlite:///' + self.catalog.as_posix())
        self.click(token)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.state()['commercial'], context)
        self.click(old_button)
        self.assertIn('no está vigente', self.transport.sent[-1]['text'])
        self.assertEqual(self.rows(), before)

    def test_other_operator_forgery_and_revocation_fail_closed(self):
        self.create('Privada')
        self.action('f')
        token = self.saved_token('Privada')
        before = self.rows()
        self.auth.grants[99] = frozenset({'artwork.submit','beer.create'})
        self.click(token, user=99)
        self.assertNotIn('Privada', self.transport.sent[-1]['text'])
        self.assertIn('no está disponible', self.transport.sent[-1]['text'])
        self.click('r22:' + uuid4().hex + ':1')
        self.assertIn('no está disponible', self.transport.sent[-1]['text'])
        self.auth.grants[USER] = frozenset({'artwork.submit'})
        self.click(token)
        self.assertIn('No tienes permiso', self.transport.sent[-1]['text'])
        self.send('/borradores22')
        self.assertNotIn('Privada', self.transport.sent[-1]['text'])
        self.assertEqual(self.rows(), before)

    def test_reopen_cannot_replace_active_commercial_or_legacy(self):
        self.create('Guardada')
        self.action('f')
        token = self.saved_token('Guardada')
        self.create('Activa')
        state = self.state()
        self.click(token)
        self.assertIn('borrador activo', self.transport.sent[-1]['text'])
        self.assertEqual(self.state(), state)
        self.send('/cancelar')
        self.send('/entrevista')
        state = self.state()
        self.click(token)
        self.assertIn('borrador activo', self.transport.sent[-1]['text'])
        self.assertEqual(self.state(), state)

    def test_legacy_navigation_retains_saved_contexts(self):
        self.create('Conservada')
        proposal = self.current()
        self.action('f')
        self.send('/entrevista')
        self.click(next(row[0]['callback_data'] for row in self.transport.sent[-1]['markup']['inline_keyboard'] if row[0]['callback_data'].endswith(':board')))
        def legacy(action):
            with Session(self.engine) as db:
                rev = db.get(Interview, self.draft()['id']).revision
            self.click(f'i:{self.draft()["id"]}:{rev}:{action}')
        legacy('0')
        legacy('back')
        self.send('/corregir')
        self.send('/cancelar')
        self.click(self.saved_token('Conservada'))
        self.assertEqual(self.current(), proposal)
        self.assertEqual(self.draft()['state'], 'draft')

    def test_cancelled_commercial_remains_recoverable_with_values(self):
        self.create('Cancelada')
        original = self.current()
        self.send('/cancelar')
        self.assertEqual(self.draft()['state'], 'cancelled')
        self.click(self.saved_token('Cancelada'))
        self.assertEqual(self.current(), original)

    def test_finish_only_accepted_from_review_and_deduplicated(self):
        self.send('/nueva22')
        forged = self.token().rsplit(':',1)[0] + ':f'
        self.click(forged)
        self.assertEqual(self.draft()['state'], 'draft')
        self.send('/corregir')
        token = next(row[0]['callback_data'] for row in self.transport.sent[-1]['markup']['inline_keyboard'] if row[0]['callback_data'].endswith(':f'))
        before = self.rows()
        self.click(token)
        self.click(token)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.draft()['state'], 'saved')

    def test_empty_list_and_pagination_are_bounded(self):
        self.send('/borradores22')
        self.assertIn('No hay borradores', self.transport.sent[-1]['text'])
        for index in range(11):
            self.create('Caso ' + str(index))
            self.action('f')
        self.send('/borradores22')
        buttons = self.transport.sent[-1]['markup']['inline_keyboard']
        self.assertEqual(sum(row[0]['callback_data'].startswith('r22:') and ':list:' not in row[0]['callback_data'] for row in buttons), 10)
        self.click(buttons[-1][0]['callback_data'])
        self.assertIn('Caso 0', self.transport.sent[-1]['text'])


if __name__ == '__main__':
    unittest.main()
