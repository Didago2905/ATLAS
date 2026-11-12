"""Read-only preparation on temporary fixtures; no live SQLite or Telegram."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
import sqlite3
import unittest
import warnings
from unittest.mock import patch

from app.editorial.commercial_preparation import prepare_commercial_update, PreparationError
from app.editorial import commercial_preparation as preparation
from app.editorial.models import ProposalRevision
from tests import test_editorial_commercial as fixtures


class PreparationTests(unittest.TestCase):
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
    edit = fixtures.CommercialTests.edit

    def prepare(self, **overrides):
        return prepare_commercial_update('sqlite:///' + self.catalog.as_posix(),
                                         proposal=overrides.get('proposal', self.proposal()),
                                         interview_context=overrides.get('interview_context', self.state()))

    def update_fixture(self, sql, parameters=()):
        with closing(sqlite3.connect(self.catalog)) as db, db:
            db.execute(sql, parameters)

    def test_single_price_diff_preserves_other_keys_and_source_is_readonly(self):
        self.edit()
        self.field('prices.taster')
        self.enter('40')
        proposal, context = self.proposal(), self.state()
        before = deepcopy(proposal.model_dump(mode='json')), deepcopy(context)
        count = self.count(ProposalRevision)
        editorial_hash = sha256(self.path.read_bytes()).hexdigest()
        actual_connect = sqlite3.connect
        seen = []

        def readonly(*args, **kwargs):
            self.assertIn('?mode=ro', args[0])
            self.assertTrue(kwargs.get('uri'))
            seen.append(args[0])
            return actual_connect(*args, **kwargs)

        with patch.object(sqlite3, 'connect', side_effect=readonly):
            result = self.prepare(proposal=proposal, interview_context=context)
        self.assertEqual(len(seen), 1)
        self.assertEqual(result.status, 'prepared')
        self.assertTrue(result.approval_required)
        self.assertEqual([change.path for change in result.changes], [('prices','taster')])
        self.assertEqual((result.changes[0].before, result.changes[0].after), (0,40))
        self.assertEqual(result.proposed['prices'], {'taster':40,'pinta_chica':60,'legacy_price':99})
        self.assertEqual(result.case_id, proposal.case_id)
        self.assertEqual(result.proposal_revision, proposal.revision)
        self.assertEqual(result.identity_confirmation, proposal.beers[0].confirmation)
        self.assertEqual((proposal.model_dump(mode='json'), context), before)
        self.assertEqual(self.count(ProposalRevision), count)
        self.assertEqual(sha256(self.path.read_bytes()).hexdigest(), editorial_hash)
        self.assertEqual(sha256(self.catalog.read_bytes()).hexdigest(), self.before)

    def test_multiple_fields_and_optional_clear_generate_explicit_diff(self):
        self.edit()
        self.field('description')
        self.enter('Nueva descripción')
        self.field('origin')
        self.action('c')
        self.field('prices.pinta_chica')
        self.action('c')
        result = self.prepare()
        self.assertEqual({d.path for d in result.changes}, {('description',),('origin',),('prices','pinta_chica')})
        price = next(d for d in result.changes if d.path == ('prices','pinta_chica'))
        self.assertTrue(price.before_present)
        self.assertFalse(price.after_present)
        origin = next(d for d in result.changes if d.path == ('origin',))
        self.assertTrue(origin.after_present)
        self.assertIsNone(origin.after)
        self.assertEqual(result.proposed['abv'], 6.5)

    def test_stale_selected_and_unselected_fields_block_preparation(self):
        self.edit()
        self.field('prices.taster')
        self.enter('40')
        self.update_fixture('UPDATE beers SET description=?,prices=? WHERE id=1',
                            ('Cambio externo', json.dumps({'taster':40,'pinta_chica':60,'legacy_price':101})))
        result = self.prepare()
        self.assertEqual(result.status, 'conflict')
        self.assertTrue(result.identity_current)
        self.assertEqual({d.path for d in result.conflicts}, {('description',),('prices','taster'),('prices','legacy_price')})
        self.assertEqual(result.changes, ())  # Same price already in SQL still conflicts with old baseline.
        self.assertEqual(result.proposed['prices']['legacy_price'], 101)

    def test_missing_deleted_and_changed_identity(self):
        self.edit()
        self.field('prices.taster')
        self.enter('40')
        self.update_fixture("UPDATE beers SET name='Renombrada' WHERE id=1")
        result = self.prepare()
        self.assertEqual(result.status, 'conflict')
        self.assertFalse(result.identity_current)
        self.assertIn(('name',), {d.path for d in result.conflicts})
        self.update_fixture('UPDATE beers SET is_deleted=1 WHERE id=1')
        with self.assertRaises(PreparationError):
            self.prepare()
        self.update_fixture('DELETE FROM beers WHERE id=1')
        with self.assertRaises(PreparationError):
            self.prepare()

    def test_noop_keep_unknown_identical_set_or_clear_absent(self):
        self.edit()
        self.assertEqual(self.prepare().status, 'noop')
        self.action('u')
        self.field('prices.taster')
        self.enter('0')
        self.field('prices.pinta_grande')
        self.action('c')
        result = self.prepare()
        self.assertEqual(result.status, 'noop')
        self.assertEqual(result.changes, ())
        self.assertEqual(result.current, result.proposed)

    def test_invalid_numeric_patch_rejected_before_catalog_read_without_details(self):
        self.edit()
        raw = self.proposal().model_dump(mode='json')
        for value in (-1,float('nan'),float('inf'),True,'PRIVATE_SECRET'):
            bad = deepcopy(raw)
            bad['actions'][0]['patch'] = {'prices':{'taster':{'op':'set','value':value}}}
            with patch.object(preparation, 'read_commercial_beer', side_effect=AssertionError('Must validate first')):
                with self.assertRaises(PreparationError) as error:
                    self.prepare(proposal=bad)
            self.assertEqual(str(error.exception), 'invalid_or_ambiguous_proposal_context')

    def test_tampered_baseline_case_revision_and_ambiguous_actions_are_rejected(self):
        self.edit()
        for key in ('baseline','baseline_sha256','mode'):
            context = self.state()
            if key == 'baseline':
                context['commercial'][key]['abv'] = 7
            else:
                context['commercial'][key] = 'wrong'
            with self.assertRaises(PreparationError):
                self.prepare(interview_context=context)
        context = self.state()
        context['navigation']['content_revision'] += 1
        with self.assertRaises(PreparationError):
            self.prepare(interview_context=context)
        raw = self.proposal().model_dump(mode='json')
        raw['actions'].append(deepcopy(raw['actions'][0]))
        with self.assertRaises(PreparationError):
            self.prepare(proposal=raw)
        self.send('/cancelar')
        self.send('/nueva22')
        with self.assertRaises(PreparationError):
            self.prepare()

    def test_absence_null_and_zero_are_distinct(self):
        self.update_fixture('UPDATE beers SET prices=? WHERE id=1', (json.dumps({'taster':None,'pinta_chica':0}),))
        self.edit()
        self.field('prices.taster')
        self.action('c')
        result = self.prepare()
        self.assertEqual(result.status, 'prepared')
        self.assertTrue(result.changes[0].before_present)
        self.assertIsNone(result.changes[0].before)
        self.assertFalse(result.changes[0].after_present)
        self.assertEqual(result.proposed['prices']['pinta_chica'], 0)

    def test_output_is_isolated_and_technical_status_is_never_approval(self):
        self.edit()
        self.field('prices.taster')
        self.enter('40')
        self.assertEqual(self.proposal().readiness, 'technically_valid')
        original = self.state()
        result = self.prepare()
        result.proposed['prices']['legacy_price'] = -100
        self.assertEqual(self.state(), original)
        self.assertTrue(result.approval_required)
        self.assertNotIn('Nueva descripción', repr(result))

    def test_unchecked_model_copy_is_revalidated_without_serializer_warnings(self):
        self.edit()
        invalid = self.proposal().model_copy(update={'revision':False})
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always')
            with self.assertRaises(PreparationError):
                self.prepare(proposal=invalid)
        self.assertEqual(captured, [])


if __name__ == '__main__':
    unittest.main()
