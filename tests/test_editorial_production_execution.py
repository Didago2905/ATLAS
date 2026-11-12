"""Production capability paths exercised exclusively on disposable SQLite fixtures."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from dataclasses import replace
import shutil
import sqlite3
import json
from contextlib import closing
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine

from app.editorial import commercial_execution as execution
from app.editorial.config import EditorialSettings
from app.editorial.production_execution import (
    allow_production_execution, validate_production_scope, ProductionExecutionConfig,
)
from app.editorial.service import EditorialService
from app.workers import editorial as worker
from tests import test_editorial_commercial_execution as fixtures
from tests.test_editorial import USER


class ProductionTests(unittest.TestCase):
    # Reuse only isolated fixture helpers, not inherited tests.
    for helper in ('setUp','close_logs','message','dispatch','draft','count','send','answer','click',
                   'token','proposal','action','enter','field','state','edit','setup_application',
                   'receipt_rows','beer','ready','review','request','execute'):
        locals()[helper] = getattr(fixtures.ExecutionTests,helper)

    def config(self):
        def target(path):
            stat=path.stat()
            return dict(path=str(path.resolve()),device=stat.st_dev,inode=stat.st_ino)
        return dict(enabled=True,activation_id=str(uuid4()),not_before=datetime.now(timezone.utc)-timedelta(seconds=1),
                    editorial=target(self.path),catalog=target(self.catalog))

    def production(self, *, execute=False):
        self.ready()
        self.settings=self.config()
        self.scope=allow_production_execution(self.engine,self.target,config=self.settings)
        self.service=EditorialService(self.engine,self.auth,self.media,self.transport,1000,
            catalog_database_url='sqlite:///'+self.catalog.as_posix(),production_execution_scope=self.scope,
            execution_authorization_loader=lambda:self.auth)
        token=self.review()
        if execute:
            self.click(token)
        else:
            # Simulate interruption of post-commit entry, before any attempt is claimed.
            with patch.object(execution,'execute_request',side_effect=SystemExit):
                with self.assertRaises(SystemExit):
                    self.click(token)
        self.request_id=self.state()['application_review']['request_id']
        self.draft_id=self.draft()['id']

    def test_default_denial_and_disabled_worker_never_opens_catalog(self):
        self.assertFalse(EditorialSettings().commercial_execution.enabled)
        with self.assertRaisesRegex(ValueError,'production_execution_disabled'):
            allow_production_execution(None,None,config={})
        with patch.object(worker,'create_engine',side_effect=AssertionError('disabled must not open catalog')), \
                patch.object(worker,'_run',return_value=0) as run:
            self.assertEqual(worker.run(None,EditorialSettings(),None,None),0)
            self.assertIsNone(run.call_args.kwargs['scope'])

    def test_explicit_configuration_and_wrong_physical_targets(self):
        self.ready()
        config=self.config()
        bad=deepcopy(config)
        bad['catalog']['inode']+=1
        with self.assertRaises(ValueError):
            allow_production_execution(self.engine,self.target,config=bad)
        with self.assertRaises(ValueError):
            allow_production_execution(self.engine,self.target,config={'enabled':True})
        scope=allow_production_execution(self.engine,self.target,config=config)
        validate_production_scope(scope)
        other=self.root/'other.sqlite3'
        shutil.copyfile(self.catalog,other)
        engine=create_engine('sqlite:///'+other.as_posix())
        self.addCleanup(engine.dispose)
        with self.assertRaises(ValueError):
            validate_production_scope(replace(scope,catalog_engine=engine))
        self.assertEqual(self.receipt_rows(),[])

    def test_worker_reuses_scope_without_schema_creation(self):
        self.ready()
        settings=EditorialSettings(database_url=str(self.engine.url),catalog_database_url=str(self.target.url),
                                  commercial_execution=self.config())
        with patch.object(worker,'_run',return_value=0) as run:
            self.assertEqual(worker.run(self.engine,settings,None,None),0)
            validate_production_scope(run.call_args.kwargs['scope'])
        self.assertEqual(self.receipt_rows(),[])

    def test_success_and_explicit_duplicate_recovery_no_second_write(self):
        self.production(execute=True)
        self.assertEqual(self.request()['state'],'applied')
        self.assertEqual(self.beer()['prices']['taster'],40)
        with patch.object(execution,'apply_commercial_update',side_effect=AssertionError('no reapply')):
            self.send('/recuperar22 '+self.request_id)
        self.assertIn('Aplicación verificada',self.transport.sent[-1]['text'])
        self.assertEqual(len(self.receipt_rows()),1)
        self.assertEqual(self.request()['attempts'],1)

    def test_recovery_after_post_commit_entry_interruption(self):
        self.production()
        self.assertEqual(self.request()['state'],'pending')
        self.send('/recuperar22 '+self.request_id)
        self.assertEqual(self.request()['state'],'applied')
        self.assertIn('Aplicación verificada',self.transport.sent[-1]['text'])
        self.assertEqual(len(self.receipt_rows()),1)

    def test_recovery_after_sql_commit_reconciles_receipt(self):
        self.production()
        with patch.object(execution,'_finish',side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                self.execute()
        self.assertEqual(self.request()['state'],'executing')
        with patch.object(execution,'apply_commercial_update',side_effect=AssertionError('no reapply')):
            self.send('/recuperar22 '+self.request_id)
        self.assertEqual(self.request()['state'],'applied')
        self.assertEqual(len(self.receipt_rows()),1)

    def test_revoked_permission_rejects_recovery(self):
        self.production()
        self.auth.grants[USER]-={execution.PERMISSION}
        self.send('/recuperar22 '+self.request_id)
        self.assertIn('No se puede recuperar',self.transport.sent[-1]['text'])
        self.assertEqual(self.request()['attempts'],0)
        with self.assertRaisesRegex(ValueError,'unauthorized'):
            self.execute()
        self.assertEqual(self.receipt_rows(),[])

    def test_expired_approval_cannot_apply(self):
        self.production()
        later=datetime.fromisoformat(self.request()['expires_at'])+timedelta(seconds=1)
        self.assertEqual(self.execute(clock=lambda:later),'expired')
        self.assertEqual(self.receipt_rows(),[])

    def test_revoked_base_bot_access_blocks_direct_execution(self):
        self.production()
        self.auth.grants[USER]-={'artwork.submit'}
        with self.assertRaisesRegex(ValueError,'unauthorized'):
            self.execute()
        self.assertEqual(self.receipt_rows(),[])

    def test_historical_request_without_activation_rejected(self):
        fixtures.ExecutionTests.prepare_request(self)
        config=self.config()
        self.scope=allow_production_execution(self.engine,self.target,config=config)
        with self.assertRaisesRegex(ValueError,'historical_execution_request_rejected'):
            self.execute()
        self.assertEqual(self.request()['attempts'],0)
        self.assertEqual(self.receipt_rows(),[])

    def test_old_activation_cannot_replay_request(self):
        self.production()
        new=deepcopy(self.settings)
        new['activation_id']=str(uuid4())
        self.scope=allow_production_execution(self.engine,self.target,config=new)
        with self.assertRaisesRegex(ValueError,'historical_execution_request_rejected'):
            self.execute()
        self.assertEqual(self.receipt_rows(),[])

    def test_sql_conflict_after_approval(self):
        self.production()
        with closing(sqlite3.connect(self.catalog)) as db,db:
            db.execute('UPDATE beers SET description=? WHERE id=1',('External update',))
        self.assertEqual(self.execute(),'conflict')
        self.assertEqual(self.receipt_rows(),[])

    def test_superseded_revision_rejected(self):
        self.production()
        raw=self.proposal().model_dump(mode='json')
        raw['revision']+=1
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('INSERT INTO editorial_proposals(draft_id,revision,payload) VALUES(?,?,?)',
                       (self.draft_id,raw['revision'],json.dumps(raw)))
        self.assertEqual(self.execute(),'failed')
        self.assertEqual(self.request()['error_code'],'superseded_proposal')
        self.assertEqual(self.receipt_rows(),[])

    def test_old_review_cannot_be_confirmed_after_enabling(self):
        self.ready()
        token=self.review()
        scope=allow_production_execution(self.engine,self.target,config=self.config())
        self.service=EditorialService(self.engine,self.auth,self.media,self.transport,1000,
            catalog_database_url=str(self.target.url),production_execution_scope=scope,
            execution_authorization_loader=lambda:self.auth)
        self.click(token)
        self.assertIn('ya no está vigente',self.transport.sent[-1]['text'])
        self.assertEqual(self.state().get('execution_requests',{}),{})
        self.assertEqual(self.receipt_rows(),[])

    def test_worker_restart_does_not_scan_pending_requests(self):
        self.production()
        from threading import Event
        from types import SimpleNamespace
        settings=SimpleNamespace(commercial_execution=ProductionExecutionConfig.model_validate(self.settings),
            catalog_database_url=str(self.target.url),media_root=self.media.root if hasattr(self.media,'root') else self.root/'media',
            download_limit_bytes=1000)
        stop=Event()
        stop.set()
        with patch.object(worker,'MediaStore',return_value=self.media), \
                patch.object(worker.Authorization,'load',return_value=self.auth), \
                patch.object(execution,'apply_commercial_update',side_effect=AssertionError('no historical replay')):
            worker.run(self.engine,settings,self.transport,stop)
        self.assertEqual(self.request()['state'],'pending')
        self.assertEqual(self.receipt_rows(),[])


if __name__=='__main__':
    unittest.main()
