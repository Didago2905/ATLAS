"""Tap transitions and explicit migration on temporary SQLite only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch, mock_open

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.core.database import Base
from app.models.beer import Beer
from app.schemas.beer import BeerCreate, BeerUpdate, BeerAvailabilityUpdate, BeerResponse
from app.services import beer_service as service
from app.migrations.tap_entry import migrate


class TapEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'catalog.sqlite3'
        self.engine=create_engine('sqlite:///'+self.path.as_posix(),connect_args={'timeout':15})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        self.addCleanup(self.db.close)

    def seed(self,n=1,**overrides):
        rows=[]
        for i in range(n):
            values=dict(name=f'Beer {i}',brewery='Fixture',style='IPA',is_available=True,
                        is_deleted=False,tap_position=i+1)
            values.update(overrides)
            beer=Beer(**values);self.db.add(beer);rows.append(beer)
        self.db.commit()
        return rows

    def test_legacy_fifteen_no_backfill_and_public_field(self):
        self.seed(15)
        self.assertFalse(migrate(self.engine))
        self.assertTrue(all(b.tap_entered_at is None for b in service.get_tap_beers(self.db)))
        self.assertEqual([b.tap_position for b in service.get_tap_beers(self.db)],list(range(1,16)))
        self.assertIsNone(BeerResponse.model_validate(service.get_tap_beers(self.db)[0]).tap_entered_at)

    def test_put_entry_reentry_and_repeated_activation(self):
        beer=self.seed(is_available=False,tap_position=None)[0]
        first=service.update_beer(self.db,beer.id,BeerUpdate(is_available=True))
        timestamp=first.tap_entered_at
        self.assertIsNotNone(timestamp)
        self.assertEqual(first.tap_position,1)
        self.assertEqual(service.update_beer(self.db,beer.id,BeerUpdate(is_available=True)).tap_entered_at,timestamp)
        service.update_beer(self.db,beer.id,BeerUpdate(is_available=False))
        previous_entry=timestamp-timedelta(days=1)
        first.tap_entered_at=previous_entry;self.db.commit()
        self.assertGreater(service.update_beer(self.db,beer.id,BeerUpdate(is_available=True)).tap_entered_at,previous_entry)

    def test_patch_reactivation_retains_position_and_records_entry(self):
        old=datetime(2020,1,1)
        beer=self.seed(tap_entered_at=old)[0]
        service.update_availability(self.db,beer.id,BeerAvailabilityUpdate(is_available=False))
        self.assertEqual(beer.tap_position,1)
        self.assertEqual(beer.tap_entered_at,old)
        service.update_availability(self.db,beer.id,BeerAvailabilityUpdate(is_available=True))
        self.assertGreater(beer.tap_entered_at,old)
        timestamp=beer.tap_entered_at
        service.update_availability(self.db,beer.id,BeerAvailabilityUpdate(is_available=True))
        self.assertEqual(beer.tap_entered_at,timestamp)

    def test_available_without_position_is_not_an_entry(self):
        beer=self.seed(is_available=False,tap_position=None)[0]
        service.update_availability(self.db,beer.id,BeerAvailabilityUpdate(is_available=True))
        self.assertIsNone(beer.tap_entered_at)
        self.assertEqual(service.get_tap_beers(self.db),[])

    def test_create_with_position_records_entry_without_position_does_not(self):
        inside=service.create_beer(self.db,BeerCreate(name='Inside',brewery='Fixture',style='IPA',tap_position=1))
        outside=service.create_beer(self.db,BeerCreate(name='Outside',brewery='Fixture',style='IPA'))
        self.assertIsNotNone(inside.tap_entered_at)
        self.assertIsNone(outside.tap_entered_at)

    def test_price_metadata_and_featured_edits_do_not_stamp(self):
        for timestamp in (None,datetime(2020,1,1)):
            beer=self.seed(tap_entered_at=timestamp)[0]
            service.update_beer(self.db,beer.id,BeerUpdate(prices={'taster':45},description='Updated'))
            with patch('builtins.open',mock_open()):
                service.update_beer(self.db,beer.id,BeerUpdate(is_featured=True))
            self.assertEqual(beer.tap_entered_at,timestamp)
        outside=self.seed(is_available=False,tap_position=None)[0]
        service.update_beer(self.db,outside.id,BeerUpdate(prices={'taster':40}))
        self.assertIsNone(outside.tap_entered_at)

    def test_capacity_sixteenth_allowed_seventeenth_rejected_all_paths(self):
        self.seed(15)
        service.create_beer(self.db,BeerCreate(name='Sixteenth',brewery='Fixture',style='IPA',tap_position=16))
        for mode in ('put','patch','create'):
            beer=self.seed(is_available=False,tap_position=1 if mode=='patch' else None)[0]
            with self.assertRaises(HTTPException) as raised:
                if mode=='put':service.update_beer(self.db,beer.id,BeerUpdate(is_available=True))
                elif mode=='patch':service.update_availability(self.db,beer.id,BeerAvailabilityUpdate(is_available=True))
                else:service.create_beer(self.db,BeerCreate(name='Overflow',brewery='Fixture',style='IPA',tap_position=1))
            self.assertEqual(raised.exception.status_code,400)
            self.db.rollback()
            self.assertEqual(len(service.get_tap_beers(self.db)),16)
            self.assertIsNone(self.db.get(Beer,beer.id).tap_entered_at)

    def test_concurrent_last_slot_only_one_entry(self):
        self.seed(15)
        candidates=[self.seed(is_available=False,tap_position=16)[0].id for _ in range(2)]
        barrier=threading.Barrier(2)
        def activate(beer_id):
            with Session(self.engine) as db:
                barrier.wait()
                try:
                    service.update_availability(db,beer_id,BeerAvailabilityUpdate(is_available=True))
                    return True
                except HTTPException:
                    return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(activate,candidates))
        self.assertEqual(sorted(results),[False,True])
        self.db.expire_all()
        self.assertEqual(len(service.get_tap_beers(self.db)),16)

    def test_deleted_beer_is_not_a_tap_entry(self):
        beer=self.seed(is_deleted=True,is_available=False)[0]
        service.update_availability(self.db,beer.id,BeerAvailabilityUpdate(is_available=True))
        self.assertIsNone(beer.tap_entered_at)
        self.assertEqual(service.get_tap_beers(self.db),[])


class MigrationTests(unittest.TestCase):
    def test_failure_after_add_column_rolls_back_and_can_retry(self):
        engine=create_engine('sqlite://')
        try:
            with engine.begin() as db:
                db.exec_driver_sql('CREATE TABLE beers(id INTEGER PRIMARY KEY,is_available BOOLEAN,is_deleted BOOLEAN,tap_position INTEGER)')
                db.exec_driver_sql('INSERT INTO beers VALUES(1,1,0,2)')
            def fail(conn,cursor,statement,parameters,context,many):
                if statement.startswith('ALTER TABLE'):
                    raise RuntimeError('Injected migration failure')
            event.listen(engine,'after_cursor_execute',fail)
            try:
                with self.assertRaises(RuntimeError):migrate(engine)
            finally:event.remove(engine,'after_cursor_execute',fail)
            with engine.connect() as db:
                self.assertNotIn('tap_entered_at',[r[1] for r in db.exec_driver_sql('PRAGMA table_info(beers)')])
                self.assertEqual(db.exec_driver_sql('SELECT * FROM beers').fetchall(),[(1,1,0,2)])
            self.assertTrue(migrate(engine))
        finally:engine.dispose()

    def test_legacy_schema_additive_repeatable_preserves_rows_and_other_tables(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'legacy.sqlite3'
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('CREATE TABLE beers(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,is_available BOOLEAN,is_deleted BOOLEAN,tap_position INTEGER,prices JSON)')
                db.execute("INSERT INTO beers(name,is_available,is_deleted,tap_position,prices) VALUES('Legacy',1,0,2,'{}')")
                db.execute('CREATE TABLE unrelated(id INTEGER PRIMARY KEY)')
                before=db.execute('SELECT * FROM beers').fetchall()
            engine=create_engine('sqlite:///'+path.as_posix())
            try:
                self.assertTrue(migrate(engine));self.assertFalse(migrate(engine))
                with closing(sqlite3.connect(path)) as db:
                    self.assertEqual(db.execute('SELECT id,name,is_available,is_deleted,tap_position,prices FROM beers').fetchall(),before)
                    self.assertEqual(db.execute('SELECT tap_entered_at FROM beers').fetchall(),[(None,)])
                    self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
                    self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                    self.assertEqual(db.execute('SELECT count(*) FROM unrelated').fetchone(),(0,))
            finally:engine.dispose()

    def test_incompatible_existing_column_rejected_without_changes(self):
        engine=create_engine('sqlite://')
        try:
            with engine.begin() as db:
                db.exec_driver_sql('CREATE TABLE beers(id INTEGER PRIMARY KEY,is_available BOOLEAN,is_deleted BOOLEAN,tap_position INTEGER,tap_entered_at TEXT)')
            with self.assertRaises(ValueError):migrate(engine)
        finally:engine.dispose()


if __name__=='__main__':unittest.main()
