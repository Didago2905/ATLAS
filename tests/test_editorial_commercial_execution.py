"""Post-commit execution and crash recovery; exact allowlisted temporary SQLite only."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha256
import shutil
import sqlite3
from contextlib import closing
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text, update
from sqlalchemy.orm import Session

from app.editorial import commercial_execution as execution
from app.editorial.application_receipts import receipts
from app.editorial.service import EditorialService
from app.editorial.commercial_applicator import PERMISSION
from tests import test_editorial_approval_flow as fixtures
from tests.test_editorial import USER


class ExecutionTests(unittest.TestCase):
    setUp = fixtures.ApprovalFlowTests.setUp
    close_logs = fixtures.ApprovalFlowTests.close_logs
    message = fixtures.ApprovalFlowTests.message
    dispatch = fixtures.ApprovalFlowTests.dispatch
    draft = fixtures.ApprovalFlowTests.draft
    count = fixtures.ApprovalFlowTests.count
    send = fixtures.ApprovalFlowTests.send
    answer = fixtures.ApprovalFlowTests.answer
    click = fixtures.ApprovalFlowTests.click
    token = fixtures.ApprovalFlowTests.token
    proposal = fixtures.ApprovalFlowTests.proposal
    action = fixtures.ApprovalFlowTests.action
    enter = fixtures.ApprovalFlowTests.enter
    field = fixtures.ApprovalFlowTests.field
    state = fixtures.ApprovalFlowTests.state
    edit = fixtures.ApprovalFlowTests.edit
    setup_application = fixtures.ApprovalFlowTests.setup_application
    receipt_rows = fixtures.ApprovalFlowTests.receipt_rows
    beer = fixtures.ApprovalFlowTests.beer
    ready = fixtures.ApprovalFlowTests.ready
    review = fixtures.ApprovalFlowTests.review

    def prepare_request(self):
        self.ready()
        self.scope = execution.allow_isolated_execution(self.engine,self.target,temporary_directory=self.temporary)
        self.click(self.review())  # Default UI: queued, still disabled, no catalog write.
        self.request_id = self.state()['application_review']['request_id']
        self.draft_id = self.draft()['id']
        return self.request()

    def request(self):
        return self.state()['execution_requests'][self.request_id]

    def execute(self, **kwargs):
        return execution.execute_request(self.scope,draft_id=self.draft_id,request_id=self.request_id,
                                         authorization_loader=kwargs.pop('authorization_loader',lambda:self.auth),**kwargs)

    def test_isolated_ui_executes_only_after_source_session_closes_and_displays_receipt(self):
        self.ready()
        self.scope = execution.allow_isolated_execution(self.engine,self.target,temporary_directory=self.temporary)
        self.service = EditorialService(self.engine,self.auth,self.media,self.transport,1000,
            catalog_database_url='sqlite:///'+self.catalog.as_posix(),isolated_execution_scope=self.scope,
            execution_authorization_loader=lambda:self.auth)
        token = self.review()
        self.assertEqual(self.state().get('execution_requests',{}),{})
        real = execution.apply_commercial_update
        def checked(*args,**kwargs):
            self.assertEqual(self.engine.pool.checkedout(),0)
            return real(*args,**kwargs)
        with patch.object(execution,'apply_commercial_update',side_effect=checked):
            self.click(token)
        self.request_id=self.state()['application_review']['request_id']
        self.assertEqual(self.request()['state'],'applied')
        self.assertEqual(self.request()['attempts'],1)
        self.assertEqual(self.beer()['prices']['taster'],40)
        self.assertEqual(len(self.receipt_rows()),1)
        self.assertIn('Aplicación verificada',self.transport.sent[-1]['text'])
        self.assertIn(self.receipt_rows()[0]['application_id'],self.transport.sent[-1]['text'])

    def test_expiration_does_not_apply(self):
        request=self.prepare_request()
        now=datetime.fromisoformat(request['expires_at'])+timedelta(seconds=1)
        self.assertEqual(self.execute(clock=lambda:now),'expired')
        self.assertEqual(self.receipt_rows(),[])
        self.assertEqual(self.beer()['prices']['taster'],0)

    def test_revoked_permission_is_terminal(self):
        self.prepare_request()
        self.auth.grants[USER]-={PERMISSION}
        self.assertEqual(self.execute(),'failed')
        self.assertFalse(self.request()['retryable'])
        self.assertEqual(self.request()['error_code'],'unauthorized')
        self.assertEqual(self.receipt_rows(),[])

    def test_permission_reload_inside_application_transaction(self):
        self.prepare_request()
        from app.editorial.config import Authorization
        calls=[]
        def loader():
            calls.append(True)
            return self.auth if len(calls)==1 else Authorization(self.auth.chat_id,{str(USER):['beer.edit']})
        self.assertEqual(self.execute(authorization_loader=loader),'failed')
        self.assertGreaterEqual(len(calls),2)
        self.assertEqual(self.receipt_rows(),[])

    def test_conflict_after_approval(self):
        self.prepare_request()
        with closing(sqlite3.connect(self.catalog)) as db,db:
            db.execute('UPDATE beers SET description=? WHERE id=1',('External update',))
        self.assertEqual(self.execute(),'conflict')
        self.assertFalse(self.request()['retryable'])
        self.assertEqual(self.receipt_rows(),[])

    def test_duplicate_delivery_verifies_original_receipt_without_reapply(self):
        self.prepare_request()
        self.assertEqual(self.execute(),'applied')
        with patch.object(execution,'apply_commercial_update',side_effect=AssertionError('Must reconcile only')):
            self.assertEqual(self.execute(),'applied')
        self.assertEqual(self.request()['attempts'],1)
        self.assertEqual(len(self.receipt_rows()),1)
        self.send('/recibo22')
        self.assertIn('Recibo persistido',self.transport.sent[-1]['text'])

    def test_interruption_before_application_recovers_after_lease(self):
        request=self.prepare_request()
        with patch.object(execution,'apply_commercial_update',side_effect=SystemExit('simulated process death')):
            with self.assertRaises(SystemExit):
                self.execute()
        self.assertEqual(self.request()['state'],'executing')
        self.assertEqual(self.execute(),'executing')
        later=datetime.fromisoformat(request['approved_at'])+timedelta(seconds=65)
        self.assertEqual(self.execute(clock=lambda:later),'applied')
        self.assertEqual(self.request()['attempts'],2)
        self.assertEqual(len(self.receipt_rows()),1)

    def test_interruption_after_commit_reconciles_even_after_expiration(self):
        request=self.prepare_request()
        with patch.object(execution,'_finish',side_effect=SystemExit('crash before reconciliation')):
            with self.assertRaises(SystemExit):
                self.execute()
        self.assertEqual(self.request()['state'],'executing')
        self.assertEqual(len(self.receipt_rows()),1)
        later=datetime.fromisoformat(request['expires_at'])+timedelta(minutes=1)
        self.auth.grants[USER]-={PERMISSION}
        with patch.object(execution,'apply_commercial_update',side_effect=AssertionError('No retry write')):
            self.assertEqual(self.execute(clock=lambda:later),'applied')
        self.assertEqual(self.request()['attempts'],1)

    def test_retryable_failure_before_application_uses_backoff(self):
        self.prepare_request()
        with patch.object(execution,'apply_commercial_update',side_effect=RuntimeError('private details must not persist')):
            self.assertEqual(self.execute(),'failed')
        self.assertTrue(self.request()['retryable'])
        self.assertEqual(self.request()['error_code'],'execution_unavailable')
        self.assertEqual(self.execute(),'failed')
        later=datetime.fromisoformat(self.request()['next_attempt_at'])+timedelta(seconds=1)
        self.assertEqual(self.execute(clock=lambda:later),'applied')
        self.assertEqual(self.request()['attempts'],2)

    def test_inconsistent_receipt_never_reports_success_or_reapplies(self):
        self.prepare_request()
        self.execute()
        with self.target.begin() as connection:
            connection.execute(update(receipts).values(action_id='wrong'))
        with patch.object(execution,'apply_commercial_update',side_effect=AssertionError('Cannot reapply')):
            self.assertEqual(self.execute(),'failed')
        self.assertEqual(self.request()['error_code'],'receipt_inconsistent')
        self.send('/recibo22')
        self.assertNotIn('Recibo persistido',self.transport.sent[-1]['text'])
        self.assertIn('No se afirma ninguna aplicación',self.transport.sent[-1]['text'])

    def test_exact_allowlist_and_nonserialized_capability_reject_other_targets(self):
        self.prepare_request()
        with self.assertRaises(ValueError):
            execution.execute_request(None,draft_id=self.draft_id,request_id=self.request_id,authorization_loader=lambda:self.auth)
        other=self.root/'other.sqlite3'
        shutil.copyfile(self.catalog,other)
        other_engine=create_engine('sqlite:///'+other.as_posix())
        self.addCleanup(other_engine.dispose)
        changed=replace(self.scope,catalog_engine=other_engine)
        with self.assertRaises(ValueError):
            execution.execute_request(changed,draft_id=self.draft_id,request_id=self.request_id,authorization_loader=lambda:self.auth)
        self.assertEqual(self.request()['attempts'],0)
        with self.assertRaises(ValueError):
            execution.allow_isolated_execution(self.engine,self.target,temporary_directory=self.root)

    def test_open_editorial_session_blocks_boundary(self):
        self.prepare_request()
        with Session(self.engine) as db:
            db.execute(text('SELECT 1'))
            with self.assertRaisesRegex(ValueError,'editorial_session_must_be_closed'):
                self.execute()
        self.assertEqual(self.request()['attempts'],0)
        self.assertEqual(self.execute(),'applied')

    def test_old_executor_cannot_overwrite_new_lease(self):
        self.prepare_request()
        with patch.object(execution,'apply_commercial_update',side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                self.execute()
        lease=self.request()['lease_token']
        self.assertEqual(execution._finish(self.scope,self.draft_id,self.request_id,'failed',
                                          error='execution_unavailable',expected_lease='obsolete'),'executing')
        self.assertEqual(self.request()['lease_token'],lease)

    def test_retry_budget_is_bounded(self):
        request=self.prepare_request()
        now=datetime.fromisoformat(request['approved_at'])
        with patch.object(execution,'apply_commercial_update',side_effect=RuntimeError):
            for attempt in range(3):
                self.assertEqual(self.execute(clock=lambda:now),'failed')
                self.assertEqual(self.request()['attempts'],attempt+1)
                now+=timedelta(seconds=31)
            self.assertFalse(self.request()['retryable'])
            self.execute(clock=lambda:now)
        self.assertEqual(self.request()['attempts'],3)
        self.assertEqual(self.receipt_rows(),[])

    def test_requests_survive_new_cases_and_legacy_navigation(self):
        self.prepare_request()
        original=deepcopy(self.request())
        self.send('/nueva22')
        self.send('/cancelar')
        self.send('/entrevista')
        self.assertEqual(self.request(),original)
        self.assertEqual(self.execute(),'applied')


if __name__=='__main__':
    unittest.main()
