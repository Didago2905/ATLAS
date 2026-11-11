"""Quick editing: isolated catalog/Editorial SQLite; no live Telegram or SQL writes."""
from copy import deepcopy
from hashlib import sha256
import unittest

from app.editorial.models import ProposalRevision
from app.editorial.service import EditorialService
from tests import test_editorial_commercial as fixtures
from tests.test_editorial import USER


class QuickEditTests(unittest.TestCase):
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
    projected = fixtures.CommercialTests.projected
    edit = fixtures.CommercialTests.edit

    def quick(self):
        self.send('/carta22')
        self.answer()
        self.click(self.token())
        self.identity = deepcopy(self.proposal().beers[0].model_dump(mode='json'))
        self.send('/rapido22')

    def choose(self, index):
        self.action('e' + str(index))

    def test_entry_starts_direct_selector_for_all_fields(self):
        self.quick()
        self.assertTrue(self.state()['commercial']['quick'])
        self.assertTrue(self.state()['commercial']['review'])
        buttons = self.transport.sent[-1]['markup']['inline_keyboard']
        self.assertEqual(sum(':e' in row[0]['callback_data'] for row in buttons), 13)
        self.assertIn('No hay cambios efectivos', self.transport.sent[-1]['text'])
        self.assertNotIn('conservar Cyprez', self.transport.sent[-1]['text'])
        self.assertTrue(all(len(row[0]['callback_data'].encode()) <= 64 for row in buttons))

    def test_multiple_fields_return_to_selector_and_preserve_all_other_values(self):
        self.quick()
        baseline = deepcopy(self.state()['commercial']['baseline'])
        self.choose(8)  # taster
        self.enter('35')
        self.assertTrue(self.state()['commercial']['review'])
        self.choose(5)  # description directly, not thirteen sequential steps
        self.enter('Solo descripción nueva')
        text = self.transport.sent[-1]['text']
        self.assertIn('Taster: 0 → 35.0', text)
        self.assertIn('Descripción: Original → Solo descripción nueva', text)
        self.assertNotIn('Nombre:', text)
        self.assertNotIn('Cervecería:', text)
        self.assertNotIn('Pinta chica:', text)
        actual = self.projected()
        baseline['prices']['taster'] = 35
        baseline['description'] = 'Solo descripción nueva'
        self.assertEqual(actual, baseline)
        self.assertEqual(self.proposal().beers[0].model_dump(mode='json'), self.identity)
        self.assertEqual(sha256(self.catalog.read_bytes()).hexdigest(), self.before)

    def test_identical_sets_clear_absent_and_unknown_are_not_actual_changes(self):
        self.quick()
        self.choose(9)
        self.enter('60')  # Original is 60.
        self.choose(10)
        self.action('c')  # Price was absent.
        self.choose(1)
        self.action('u')
        text = self.transport.sent[-1]['text']
        self.assertIn('No hay cambios efectivos', text)
        self.assertNotIn('Pinta chica:', text)
        self.assertNotIn('Pinta grande:', text)
        self.assertNotIn('Cervecería:', text)

    def test_full_summary_toggle_readonly_command_and_stale_selector(self):
        self.quick()
        old = next(row[0]['callback_data'] for row in self.transport.sent[-1]['markup']['inline_keyboard'] if row[0]['callback_data'].endswith(':e0'))
        count = self.count(ProposalRevision)
        self.action('h')
        self.assertIn('Nombre: conservar Leviatán', self.transport.sent[-1]['text'])
        self.assertEqual(self.count(ProposalRevision), count)
        self.click(old)
        self.assertIn('no está vigente', self.transport.sent[-1]['text'])
        self.send('/continuar')
        self.action('h')
        self.assertNotIn('Nombre:', self.transport.sent[-1]['text'])
        before = deepcopy(self.state())
        self.send('/resumen')
        self.assertIn('Nombre:', self.transport.sent[-1]['text'])
        self.assertEqual(self.state(), before)
        self.assertEqual(self.count(ProposalRevision), count)

    def test_clear_discard_and_zero_remain_explicit(self):
        self.quick()
        self.choose(3)
        self.action('c')
        self.assertIn('Origen: México → borrar', self.transport.sent[-1]['text'])
        self.choose(3)
        self.action('d')
        self.assertTrue(self.state()['commercial']['review'])
        self.assertNotIn('Origen:', self.transport.sent[-1]['text'])
        self.assertEqual(self.projected()['origin'], 'México')
        self.choose(9)
        self.enter('0')
        self.assertIn('Pinta chica: 60 → 0.0', self.transport.sent[-1]['text'])

    def test_quick_draft_finish_restart_and_reopen_preserves_mode(self):
        self.quick()
        self.choose(8)
        self.enter('41')
        original = self.proposal().model_dump(mode='json')
        self.action('f')
        self.service = EditorialService(self.engine, self.auth, self.media, self.transport, 1000,
                                       catalog_database_url='sqlite:///' + self.catalog.as_posix())
        self.send('/borradores22')
        self.click(self.token())
        self.assertTrue(self.state()['commercial']['quick'])
        self.assertEqual(self.proposal().model_dump(mode='json'), original)
        self.assertIn('Taster:', self.transport.sent[-1]['text'])
        self.assertNotIn('Nombre:', self.transport.sent[-1]['text'])

    def test_full_interview_remains_sequential_and_cannot_be_silently_replaced(self):
        self.edit()
        self.assertFalse(self.state()['commercial']['quick'])
        self.assertFalse(self.state()['commercial']['review'])
        self.enter('Otro nombre propuesto')
        self.assertEqual(self.state()['commercial']['index'], 1)
        self.assertFalse(self.state()['commercial']['review'])
        before = deepcopy(self.state())
        self.send('/rapido22')
        self.assertEqual(self.state(), before)

    def test_requires_confirmed_sql_identity_and_edit_permission(self):
        self.send('/rapido22')
        self.assertEqual(self.count(ProposalRevision), 0)
        self.send('/carta22')
        self.answer()
        self.click(self.token())
        before = self.count(ProposalRevision)
        self.auth.grants[USER] = frozenset({'artwork.submit'})
        self.send('/rapido22')
        self.assertIn('No tienes permiso', self.transport.sent[-1]['text'])
        self.assertEqual(self.count(ProposalRevision), before)

    def test_wrong_reply_validation_and_back_to_selector(self):
        self.quick()
        self.choose(6)
        self.action('s')
        before = self.count(ProposalRevision)
        self.send('99', reply_to_message={'message_id': 9999})
        self.answer('NaN')
        self.assertEqual(self.count(ProposalRevision), before)
        self.answer('7,2')
        self.assertTrue(self.state()['commercial']['review'])
        self.assertIn('ABV (%):', self.transport.sent[-1]['text'])
        self.choose(7)
        self.action('b')
        self.assertTrue(self.state()['commercial']['review'])


if __name__ == '__main__':
    unittest.main()
