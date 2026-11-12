"""Authenticated Telegram simulation; actual application only as separate isolated fixture step."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
import shutil
import sqlite3
import unittest
from unittest.mock import patch

from app.editorial.models import ProposalRevision
from app.editorial.commercial_applicator import CommercialApproval, PERMISSION
from tests import test_editorial_commercial_applicator as fixtures
from tests.test_editorial import USER


class ApprovalFlowTests(unittest.TestCase):
    setUp = fixtures.ApplicatorTests.setUp
    close_logs = fixtures.ApplicatorTests.close_logs
    message = fixtures.ApplicatorTests.message
    dispatch = fixtures.ApplicatorTests.dispatch
    draft = fixtures.ApplicatorTests.draft
    count = fixtures.ApplicatorTests.count
    send = fixtures.ApplicatorTests.send
    answer = fixtures.ApplicatorTests.answer
    click = fixtures.ApplicatorTests.click
    token = fixtures.ApplicatorTests.token
    proposal = fixtures.ApplicatorTests.proposal
    action = fixtures.ApplicatorTests.action
    enter = fixtures.ApplicatorTests.enter
    field = fixtures.ApplicatorTests.field
    state = fixtures.ApplicatorTests.state
    edit = fixtures.ApplicatorTests.edit
    setup_application = fixtures.ApplicatorTests.setup_application
    apply = fixtures.ApplicatorTests.apply
    receipt_rows = fixtures.ApplicatorTests.receipt_rows
    beer = fixtures.ApplicatorTests.beer

    def ready(self):
        self.setup_application()
        self.auth.grants[USER] |= {PERMISSION}

    def review(self):
        self.send('/aplicar22')
        self.click(self.token())
        return 'a22:' + self.state()['application_review']['nonce'] + ':confirm'

    def test_unauthorized_operator_and_cross_operator_callbacks(self):
        self.setup_application()
        self.send('/aplicar22')
        self.assertIn('No tienes permiso',self.transport.sent[-1]['text'])
        self.assertNotIn('application_review',self.state())
        self.auth.grants[USER] |= {PERMISSION}
        token = self.review()
        self.auth.grants[99] = frozenset({'artwork.submit','beer.edit',PERMISSION})
        self.click(token,user=99)
        self.assertIn('No hay propuestas propias',self.transport.sent[-1]['text'])
        self.assertNotIn('approval',self.state()['application_review'])
        self.auth.grants[USER] -= {PERMISSION}
        self.click(token)
        self.assertIn('No tienes permiso',self.transport.sent[-1]['text'])

    def test_review_then_valid_confirmation_is_bound_and_never_executes(self):
        self.ready()
        before = self.proposal().model_dump(mode='json')
        count = self.count(ProposalRevision)
        catalog_hash = sha256(self.catalog.read_bytes()).hexdigest()
        with patch('app.editorial.commercial_applicator.apply_commercial_update',side_effect=AssertionError('UI cannot execute')) as execute:
            token = self.review()
            self.assertIn('["prices", "taster"]',self.transport.sent[-1]['text'])
            self.assertIn('Antes: 0',self.transport.sent[-1]['text'])
            self.assertIn('Después: 40.0',self.transport.sent[-1]['text'])
            self.assertNotIn('approval',self.state()['application_review'])
            self.click(token)
            review = self.state()['application_review']
            self.assertEqual(review['status'],'confirmed_execution_disabled')
            self.assertEqual(review['operator'],USER)
            self.assertEqual(review['approval']['case_id'],before['case_id'])
            self.assertEqual(review['approval']['revision'],before['revision'])
            self.assertEqual(review['approval']['request_sha256'],review['request_sha256'])
            self.assertEqual(review['beer_id'],1)
            self.assertIn('ejecución SQL está deshabilitada',self.transport.sent[-1]['text'])
            execute.assert_not_called()
        self.assertEqual(self.proposal().model_dump(mode='json'),before)
        self.assertEqual(self.count(ProposalRevision),count)
        self.assertEqual(self.draft()['state'],'saved')
        self.assertEqual(self.receipt_rows(),[])
        self.assertEqual(sha256(self.catalog.read_bytes()).hexdigest(),catalog_hash)

    def test_stale_confirmation_after_another_review(self):
        self.ready()
        old = self.review()
        new = self.review()
        self.assertNotEqual(old,new)
        self.click(old)
        self.assertIn('ya no está vigente',self.transport.sent[-1]['text'])
        self.assertNotIn('approval',self.state()['application_review'])

    def test_changed_proposal_after_review_is_rejected(self):
        self.ready()
        token = self.review()
        raw = self.proposal().model_dump(mode='json')
        raw['actions'][0]['patch']['prices']['taster']['value'] = 41
        with closing(sqlite3.connect(self.path)) as source,source:
            source.execute('UPDATE editorial_proposals SET payload=? WHERE revision=?',(json.dumps(raw),raw['revision']))
        self.click(token)
        self.assertIn('ya no está vigente',self.transport.sent[-1]['text'])
        self.assertNotIn('approval',self.state()['application_review'])

    def test_sql_conflict_after_review_blocks_confirmation(self):
        self.ready()
        token = self.review()
        with closing(sqlite3.connect(self.catalog)) as target,target:
            target.execute('UPDATE beers SET prices=? WHERE id=1',(json.dumps({'taster':50,'pinta_chica':60,'legacy_price':99}),))
        self.click(token)
        self.assertIn('SQL cambió',self.transport.sent[-1]['text'])
        self.assertIn('Conflictos',self.transport.sent[-1]['text'])
        self.assertEqual(self.state()['application_review']['status'],'blocked')
        self.assertNotIn('approval',self.state()['application_review'])
        self.assertEqual(self.receipt_rows(),[])

    def test_duplicate_confirmation_keeps_one_authorization(self):
        self.ready()
        token = self.review()
        self.click(token)
        original = deepcopy(self.state()['application_review']['approval'])
        self.click(token)
        self.assertIn('ya registrada',self.transport.sent[-1]['text'])
        self.assertEqual(self.state()['application_review']['approval'],original)
        self.assertEqual(self.receipt_rows(),[])

    def test_receipt_display_uses_real_persisted_isolated_receipt(self):
        self.ready()
        token = self.review()
        self.click(token)
        self.send('/recibo22')
        self.assertIn('No hay recibo',self.transport.sent[-1]['text'])
        self.approval = CommercialApproval.model_validate(self.state()['application_review']['approval'])
        result = self.apply()  # Separate fixture invocation AFTER UI transaction, temporary DBs only.
        self.send('/recibo22')
        text = self.transport.sent[-1]['text']
        self.assertIn('Recibo persistido',text)
        self.assertIn(result.application_id,text)
        self.assertIn('Estado: applied',text)
        self.assertIn(result.receipt['applied_at'],text)

    def test_production_named_target_cannot_be_executed_by_ui(self):
        self.ready()
        blocked = self.root / 'atlas.db'
        shutil.copyfile(self.catalog,blocked)
        self.service.catalog_database_url = 'sqlite:///' + blocked.as_posix()
        before = sha256(blocked.read_bytes()).hexdigest()
        with patch('app.editorial.commercial_applicator.apply_commercial_update',side_effect=AssertionError('No production execution')) as execute:
            self.click(self.review())
            execute.assert_not_called()
        self.assertEqual(sha256(blocked.read_bytes()).hexdigest(),before)
        self.assertEqual(self.state()['application_review']['status'],'confirmed_execution_disabled')

    def test_exact_long_diff_requires_sequential_pages_before_confirmation(self):
        with closing(sqlite3.connect(self.catalog)) as target,target:
            target.execute('UPDATE beers SET description=? WHERE id=1',('X'*3000,))
        self.ready()
        self.send('/borradores22')
        self.click(self.token())
        self.field('description')
        self.enter('Corta')
        self.send('/corregir')
        self.action('f')
        token = self.review()
        review = self.state()['application_review']
        self.assertGreater(len(review['pages']),1)
        self.assertIn('X'*3000,''.join(review['pages']))
        self.click(token)
        self.assertNotIn('approval',self.state()['application_review'])
        while self.state()['application_review']['page'] < len(review['pages'])-1:
            page = self.state()['application_review']['page']+1
            self.click(f"a22:{review['nonce']}:p{page}")
            self.assertLess(len(self.transport.sent[-1]['text'].encode('utf-16-le'))//2,4096)
        self.click(token)
        self.assertIn('approval',self.state()['application_review'])


if __name__ == '__main__':
    unittest.main()
