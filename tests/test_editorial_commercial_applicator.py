"""Temporary SQLite files ONLY; no runtime settings, credentials or Telegram calls."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
import sqlite3
import threading
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, event, select

from app.editorial.application_receipts import receipts
from app.editorial.commercial_applicator import (
    apply_commercial_update, initialize_receipts_for_isolated_tests, CommercialApproval,
    ApplicationError, approval_digest, PERMISSION,
)
from app.editorial.config import Authorization
from tests import test_editorial_commercial as fixtures
from tests.test_editorial import CHAT, USER


class ApplicatorTests(unittest.TestCase):
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

    def setup_application(self, *, initialize=True):
        with closing(sqlite3.connect(self.catalog)) as db, db:
            db.execute('ALTER TABLE beers ADD COLUMN tap_position INTEGER')
            db.execute('ALTER TABLE beers ADD COLUMN is_featured BOOLEAN')
            db.execute('ALTER TABLE beers ADD COLUMN image_url TEXT')
            db.execute("UPDATE beers SET tap_position=7,is_featured=1,image_url='unchanged' WHERE id=1")
        self.target = create_engine('sqlite:///' + self.catalog.as_posix(), connect_args={'timeout':10,'check_same_thread':False})
        self.addCleanup(self.target.dispose)
        if initialize:
            initialize_receipts_for_isolated_tests(self.target, isolated_root=self.root)
        self.edit()
        self.field('prices.taster')
        self.enter('40')
        self.send('/corregir')
        self.action('f')
        self.approval = CommercialApproval(reference=uuid4(), case_id=self.proposal().case_id,
            revision=self.proposal().revision, request_sha256=approval_digest(self.proposal(), self.state()), confirmed=True)
        self.authority = Authorization(CHAT, {str(USER):['beer.edit',PERMISSION]})

    def apply(self, **overrides):
        args = dict(editorial_database=self.path, isolated_root=self.root, draft_id=self.draft()['id'],
                    case_id=self.approval.case_id, revision=self.approval.revision, approval=self.approval,
                    authorization=self.authority, chat_id=CHAT, user_id=USER)
        args.update(overrides)
        return apply_commercial_update(self.target, **args)

    def beer(self):
        with closing(sqlite3.connect(self.catalog)) as db:
            db.row_factory = sqlite3.Row
            result = dict(db.execute('SELECT * FROM beers WHERE id=1').fetchone())
            result['prices'] = json.loads(result['prices'])
            return result

    def receipt_rows(self):
        with self.target.connect() as db:
            return [dict(row) for row in db.execute(select(receipts)).mappings()]

    def test_single_price_atomic_receipt_and_preserved_source_and_operational_fields(self):
        self.setup_application()
        before = self.beer()
        source_hash = sha256(self.path.read_bytes()).hexdigest()
        result = self.apply()
        after = self.beer()
        before['prices']['taster'] = 40
        self.assertEqual(after, before)
        self.assertFalse(result.replayed)
        self.assertEqual(result.receipt['status'], 'applied')
        self.assertEqual(result.receipt['beer_id'], 1)
        self.assertEqual(result.receipt['proposal_revision'], self.approval.revision)
        self.assertEqual(result.receipt['authorization_ref'], str(self.approval.reference))
        self.assertTrue(result.receipt['applied_at'].endswith('+00:00'))
        self.assertEqual(result.receipt['changes'][0]['path'], ['prices','taster'])
        self.assertEqual(self.receipt_rows(), [result.receipt])
        self.assertEqual(sha256(self.path.read_bytes()).hexdigest(), source_hash)

    def test_multiple_fields_and_single_price_clear(self):
        self.setup_application()
        self.send('/borradores22')
        self.click(self.token())
        self.field('description')
        self.enter('Cambio aprobado')
        self.field('origin')
        self.action('c')
        self.field('prices.pinta_chica')
        self.action('c')
        self.send('/corregir')
        self.action('f')
        self.approval = CommercialApproval(reference=uuid4(), case_id=self.proposal().case_id, revision=self.proposal().revision,
                                           request_sha256=approval_digest(self.proposal(), self.state()), confirmed=True)
        result = self.apply()
        self.assertEqual(self.beer()['description'], 'Cambio aprobado')
        self.assertIsNone(self.beer()['origin'])
        self.assertEqual(self.beer()['prices'], {'taster':40,'legacy_price':99})
        self.assertEqual({tuple(c['path']) for c in result.receipt['changes']},
                         {('prices','taster'),('prices','pinta_chica'),('description',),('origin',)})

    def test_stale_baseline_and_changed_identity_rollback_without_receipt(self):
        self.setup_application()
        for field, value in [('description','Externo'),('name','Otra identidad')]:
            with closing(sqlite3.connect(self.catalog)) as db, db:
                db.execute(f'UPDATE beers SET {field}=? WHERE id=1',(value,))
            before = self.beer()
            with self.assertRaisesRegex(ApplicationError, 'conflict'):
                self.apply()
            self.assertEqual(self.beer(), before)
            self.assertEqual(self.receipt_rows(), [])

    def test_edit_alone_wrong_owner_and_wrong_approval_never_apply(self):
        self.setup_application()
        before = self.beer()
        with self.assertRaisesRegex(ApplicationError,'unauthorized'):
            self.apply(authorization=Authorization(CHAT,{str(USER):['beer.edit']}))
        with self.assertRaisesRegex(ApplicationError,'proposal_owner_mismatch'):
            self.apply(user_id=99, authorization=Authorization(CHAT,{'99':['beer.edit',PERMISSION]}))
        bad = self.approval.model_copy(update={'request_sha256':'0'*64})
        with self.assertRaisesRegex(ApplicationError,'approval_content_mismatch'):
            self.apply(approval=bad)
        with self.assertRaisesRegex(ApplicationError,'approval_revision_mismatch'):
            self.apply(revision=self.approval.revision+1)
        self.assertEqual(self.beer(), before)
        self.assertEqual(self.receipt_rows(), [])

    def test_idempotent_retry_returns_original_receipt(self):
        self.setup_application()
        first = self.apply()
        second = self.apply()
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(first.receipt, second.receipt)
        self.assertEqual(len(self.receipt_rows()), 1)

    def test_commercial_application_preserves_tap_entry_timestamp(self):
        self.setup_application()
        with self.target.begin() as db:
            db.exec_driver_sql('ALTER TABLE beers ADD COLUMN tap_entered_at DATETIME')
            db.exec_driver_sql("UPDATE beers SET tap_entered_at='2026-01-01 00:00:00' WHERE id=1")
        self.apply()
        self.assertEqual(self.beer()['tap_entered_at'],'2026-01-01 00:00:00')

    def test_concurrent_same_application_is_applied_once(self):
        self.setup_application()
        # Precompute all source arguments: test helpers must not share ORM sessions across threads.
        args = dict(editorial_database=self.path, isolated_root=self.root, draft_id=self.draft()['id'],
                    case_id=self.approval.case_id, revision=self.approval.revision, approval=self.approval,
                    authorization=self.authority, chat_id=CHAT, user_id=USER)
        barrier = threading.Barrier(2)
        def apply_one():
            barrier.wait()
            return apply_commercial_update(self.target, **args)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(apply_one) for _ in range(2)]
            results = [f.result() for f in futures]
        self.assertEqual(sorted(r.replayed for r in results), [False,True])
        self.assertEqual(results[0].application_id, results[1].application_id)
        self.assertEqual(len(self.receipt_rows()), 1)

    def test_failure_after_receipt_insert_rolls_back_update_and_receipt(self):
        self.setup_application()
        before = self.beer()
        def fail(conn, cursor, statement, params, context, many):
            if statement.lstrip().upper().startswith('INSERT INTO EDITORIAL_COMMERCIAL_APPLICATIONS'):
                raise RuntimeError('SYNTHETIC_PRIVATE_EXCEPTION')
        event.listen(self.target, 'after_cursor_execute', fail)
        try:
            with self.assertRaisesRegex(ApplicationError,'application_failed_rolled_back') as error:
                self.apply()
            self.assertNotIn('SYNTHETIC_PRIVATE', str(error.exception))
        finally:
            event.remove(self.target,'after_cursor_execute',fail)
        self.assertEqual(self.beer(),before)
        self.assertEqual(self.receipt_rows(),[])
        self.assertFalse(self.apply().replayed)  # A deliberate later retry can apply after rollback.

    def test_superseded_or_tampered_source_rejected(self):
        self.setup_application()
        raw = self.proposal().model_dump(mode='json')
        original_revision = raw['revision']
        raw['revision'] += 1
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO editorial_proposals(draft_id,revision,payload) VALUES(?,?,?)',
                       (self.draft()['id'],raw['revision'],json.dumps(raw)))
        with self.assertRaisesRegex(ApplicationError,'superseded_proposal'):
            self.apply()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DELETE FROM editorial_proposals WHERE revision=?',(raw['revision'],))
            raw['revision'] = original_revision
            raw['actions'][0]['patch']['prices']['taster']['value'] = 999
            db.execute('UPDATE editorial_proposals SET payload=? WHERE revision=?',(json.dumps(raw),original_revision))
        with self.assertRaisesRegex(ApplicationError,'approval_content_mismatch'):
            self.apply()
        self.assertEqual(self.receipt_rows(),[])

    def test_explicit_setup_and_isolated_storage_guards(self):
        self.setup_application(initialize=False)
        with self.assertRaisesRegex(ApplicationError,'explicit_isolated_receipt_setup_required'):
            self.apply()
        initialize_receipts_for_isolated_tests(self.target, isolated_root=self.root)
        initialize_receipts_for_isolated_tests(self.target, isolated_root=self.root)
        with self.assertRaises(ApplicationError):
            self.apply(isolated_root=self.root / 'logs')
        self.assertEqual(self.receipt_rows(),[])

    def test_invalid_numeric_and_noop_proposals_do_not_write(self):
        self.setup_application()
        raw = self.proposal().model_dump(mode='json')
        for value in (float('nan'), 0):
            raw['actions'][0]['patch']['prices']['taster']['value'] = value
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute('UPDATE editorial_proposals SET payload=? WHERE revision=?',(json.dumps(raw),raw['revision']))
            if value == 0:
                self.approval = CommercialApproval(reference=uuid4(),case_id=raw['case_id'],revision=raw['revision'],
                    request_sha256=approval_digest(raw,self.state()),confirmed=True)
            before = self.beer()
            with self.assertRaises(ApplicationError):
                self.apply()
            self.assertEqual(self.beer(),before)
            self.assertEqual(self.receipt_rows(),[])

    def test_editorial_writes_are_locked_until_update_receipt_transaction_ends(self):
        self.setup_application()
        observed = []
        source_hash = sha256(self.path.read_bytes()).hexdigest()
        def try_source_write(conn, cursor, statement, params, context, many):
            if statement.lstrip().upper().startswith('UPDATE BEERS'):
                with closing(sqlite3.connect(self.path,timeout=0.01)) as source:
                    try:
                        source.execute('UPDATE editorial_cursor SET next_offset=next_offset+1 WHERE id=1')
                    except sqlite3.OperationalError:
                        observed.append('locked')
                    else:
                        source.rollback()
                        observed.append('unexpected_write_access')
        event.listen(self.target,'after_cursor_execute',try_source_write)
        try:
            self.apply()
        finally:
            event.remove(self.target,'after_cursor_execute',try_source_write)
        self.assertEqual(observed,['locked'])
        self.assertEqual(sha256(self.path.read_bytes()).hexdigest(),source_hash)

    def test_competing_different_proposals_cannot_both_apply_same_baseline(self):
        self.setup_application()
        a = self.proposal().model_dump(mode='json')
        b = deepcopy(a)
        b['case_id'], b['revision'] = str(uuid4()), a['revision']+1
        b['actions'][0]['id'] = str(uuid4())
        b['actions'][0]['patch']['prices']['taster']['value'] = 50
        history = self.state()
        context = deepcopy(history)
        context.pop('saved_cases',None)
        context['navigation'].update(case_id=b['case_id'],content_revision=b['revision'])
        history['saved_cases'][b['case_id']] = {'context':context,'revision':b['revision'],'status':'saved'}
        with closing(sqlite3.connect(self.path)) as source, source:
            source.execute('INSERT INTO editorial_proposals(draft_id,revision,payload) VALUES(?,?,?)',
                           (self.draft()['id'],b['revision'],json.dumps(b)))
            source.execute('UPDATE editorial_interviews SET history=? WHERE id=?',(json.dumps(history),self.draft()['id']))
        second = CommercialApproval(reference=uuid4(),case_id=b['case_id'],revision=b['revision'],
                                    request_sha256=approval_digest(b,context),confirmed=True)
        common = dict(editorial_database=self.path, isolated_root=self.root, draft_id=self.draft()['id'],
                      authorization=self.authority, chat_id=CHAT, user_id=USER)
        barrier = threading.Barrier(2)
        def run(approval):
            barrier.wait()
            try:
                return apply_commercial_update(self.target,case_id=approval.case_id,revision=approval.revision,
                                               approval=approval,**common)
            except ApplicationError as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(run,approval) for approval in (self.approval,second)]
            results = [f.result() for f in pending]
        self.assertEqual(sum(not isinstance(r,str) for r in results),1)
        self.assertIn('conflict',results)
        self.assertEqual(len(self.receipt_rows()),1)

    def test_real_json_column_and_explicit_true_approval(self):
        with closing(sqlite3.connect(self.catalog)) as db, db:
            db.execute('CREATE TABLE replacement(id INTEGER PRIMARY KEY,name TEXT,brewery TEXT,style TEXT,is_available INTEGER,is_deleted INTEGER,origin TEXT,color TEXT,description TEXT,abv REAL,ibu REAL,prices JSON)')
            db.execute('INSERT INTO replacement SELECT * FROM beers')
            db.execute('DROP TABLE beers')
            db.execute('ALTER TABLE replacement RENAME TO beers')
        self.setup_application()
        for flag in (False,1):
            with self.assertRaises(ValueError):
                CommercialApproval(reference=uuid4(),case_id=self.approval.case_id,revision=self.approval.revision,
                                   request_sha256=self.approval.request_sha256,confirmed=flag)
        self.apply()
        self.assertEqual(self.beer()['prices'],{'taster':40,'pinta_chica':60,'legacy_price':99})

    def test_authorization_is_checked_again_after_acquiring_transaction_lock(self):
        self.setup_application()
        before = self.beer()
        def revoke(conn,cursor,statement,params,context,many):
            if statement == 'BEGIN IMMEDIATE':
                self.authority.grants[USER] = frozenset({'beer.edit'})
        event.listen(self.target,'after_cursor_execute',revoke)
        try:
            with self.assertRaisesRegex(ApplicationError,'unauthorized'):
                self.apply()
        finally:
            event.remove(self.target,'after_cursor_execute',revoke)
        self.assertEqual(self.beer(),before)
        self.assertEqual(self.receipt_rows(),[])


if __name__ == '__main__':
    unittest.main()
