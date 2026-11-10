"""V2.1 offline interview tests: temporary DB/media, no credentials or network."""
import json
import unittest
from unittest.mock import patch
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import ValidationError
from app.editorial.models import Interview, ProposalRevision, Version, Asset, Cursor
from app.editorial.proposal import Proposal, Prices
from app.editorial.service import EditorialService
from app.migrations.editorial import migrate, check_schema, LEGACY_TABLES
from tests import test_editorial as foundation
CHAT, USER = foundation.CHAT, foundation.USER


class InterviewTests(unittest.TestCase):
    setUp = foundation.EditorialTests.setUp
    message = foundation.EditorialTests.message
    dispatch = foundation.EditorialTests.dispatch
    draft = foundation.EditorialTests.draft
    attachment = foundation.EditorialTests.attachment
    start_image = foundation.EditorialTests.start_image
    callback = foundation.EditorialTests.callback
    count = foundation.EditorialTests.count
    assert_catalog_unchanged = foundation.EditorialTests.assert_catalog_unchanged

    def send(self, text):
        self.uid += 1
        self.dispatch(self.message(self.uid, text))

    def state(self):
        with Session(self.engine) as db:
            row = db.get(Interview, self.draft()['id'])
            p = db.scalar(select(ProposalRevision).order_by(ProposalRevision.revision.desc()))
            return row.step, row.revision, p.payload

    def action(self, action, revision=None, user=USER):
        self.uid += 1
        draft = self.draft()
        rev = self.state()[1] if revision is None else revision
        self.dispatch({'update_id': self.uid, 'callback_query': {
            'id': 'cb', 'from': {'id': user, 'is_bot': False},
            'message': {'chat': {'id': CHAT, 'type': 'group'}},
            'data': f'i:{draft["id"]}:{rev}:{action}'}})

    def answer(self, value):
        self.uid += 1
        self.dispatch(self.message(self.uid, value, reply_to_message={'message_id': self.draft()['prompt']}))

    def begin(self, operation='new'):
        self.uid = 10
        self.send('/entrevista')
        self.uid += 1
        self.dispatch(self.callback(uid=self.uid, operation=operation))
        self.assertEqual(self.state()[0], 'targets')

    def to_summary(self):
        for _ in range(35):
            if self.state()[0] == 'summary':
                return
            self.action('skip')
        self.fail('Interview failed to finish')

    def test_new_beer_interview_and_optional_fields(self):
        with patch('app.services.museum_upload_service.upload_artwork', side_effect=AssertionError('No publication')):
            self.begin()
            self.action('0')
            for value in ('Leviatán', 'Cervecería de prueba', 'IPA'):
                self.answer(value)
            for _ in range(3):
                self.action('skip')  # origin, color, description
            self.answer('6,5')
            self.action('skip')  # IBU
            self.answer('0')
            for _ in range(4):
                self.action('skip')
            self.action('1')  # future intent only
            self.action('skip')  # image optional for beer record preparation
            step, _, p = self.state()
            self.assertEqual(step, 'summary')
            self.assertEqual(p['beer']['abv'], 6.5)
            self.assertEqual(p['beer']['prices']['taster'], 0)
            self.assertIsNone(p['beer']['prices']['pinta_chica'])
            self.assertEqual(p['tap_activation_intent'], 'later')
            self.assertEqual(p['validation_status'], 'valid')
            self.assertEqual(p['targets'], ['beer_create'])
            self.assert_catalog_unchanged()

    def test_brewery_board_does_not_create_or_identify_beer(self):
        self.start_image()
        self.uid = 10
        self.send('/entrevista')
        self.uid += 1
        raw = self.callback(uid=self.uid, operation='board')
        raw['callback_query']['data'] = raw['callback_query']['data'].replace('op:', 'start:', 1)
        self.dispatch(raw)
        self.action('0')  # Museum target
        self.action('0')  # tap_list
        self.answer('Tabla de la cervecería')
        self.action('skip')  # year
        self.action('0')  # no semantics
        self.action('1')  # explicit board role
        self.action('1')  # brewery subject
        self.answer('Cervecería de prueba')
        _, _, p = self.state()
        self.assertEqual(p['artworks']['tap_board']['subject'], 'brewery')
        self.assertEqual(p['artworks']['tap_board']['subject_name'], 'Cervecería de prueba')
        self.assertIsNone(p['beer']['name'])
        self.assertEqual(p['museum']['semantic_products'], [])
        self.assertEqual(p['targets'], ['museum'])
        self.assertEqual(p['validation_status'], 'valid')
        self.assert_catalog_unchanged()

    def test_missing_required_fields_remain_missing(self):
        self.begin()
        self.action('0')
        self.to_summary()
        p = self.state()[2]
        self.assertIsNone(p['beer']['name'])
        self.assertEqual(p['validation_status'], 'incomplete')
        self.assertIn('Falta cerveza: name', p['validation_issues'])
        self.assertTrue(all(value is None for value in p['beer']['prices'].values()))

    def test_price_and_abv_contract_reject_invalid_values(self):
        for value in ('NaN', 'Infinity', '-Infinity', -1, True, 1000001):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                Prices(taster=value)
        for value in ('NaN', 'Infinity', -1, 101, True):
            with self.subTest(abv=value), self.assertRaises(ValidationError):
                Proposal(revision=1, operation='new', beer={'abv': value})
        self.assertEqual(Prices(taster=0).taster, 0)
        with self.assertRaises(ValidationError):
            Prices(unknown=1)

    def test_invalid_answer_keeps_question_and_revision(self):
        self.begin()
        self.action('0')
        for _ in range(6):
            self.action('skip')
        self.assertEqual(self.state()[0], 'beer.abv')
        before = self.state()
        for value in ('NaN', '101', '-2', 'infinito'):
            self.answer(value)
            self.assertEqual(self.state(), before)
        self.answer('5')
        self.assertEqual(self.state()[2]['beer']['abv'], 5)

    def test_correction_back_stale_reply_restart_cancel_resume(self):
        self.begin()
        self.action('0')
        self.answer('Original')
        self.action('back')
        self.assertEqual(self.state()[0], 'beer.name')
        self.answer('Corregido')
        before = self.state()
        self.service = EditorialService(self.engine, self.auth, self.media, self.transport, self.service.download_limit)
        self.send('/cancelar')
        self.send('/continuar')
        self.assertEqual(self.state(), before)
        self.assertIn('Cervecería', self.transport.sent[-1]['text'])
        old_revision = before[1] - 1
        self.action('skip', revision=old_revision)
        self.assertEqual(self.state(), before)
        self.send('/corregir')
        self.action('1')  # name
        self.answer('Edición final')
        with Session(self.engine) as db:
            snapshots = db.scalars(select(ProposalRevision).order_by(ProposalRevision.revision)).all()
            names = [row.payload['beer']['name'] for row in snapshots]
            self.assertIn('Original', names)
            self.assertIn('Corregido', names)
            self.assertEqual(names[-1], 'Edición final')
        self.assert_catalog_unchanged()

    def test_unrelated_text_not_persisted_and_stale_prompt_not_applied(self):
        self.begin()
        self.action('0')
        old_prompt = self.draft()['prompt']
        self.answer('Nombre')
        before = self.state()
        self.uid += 1
        self.dispatch(self.message(self.uid, 'No debe cambiar', reply_to_message={'message_id': old_prompt}))
        self.assertEqual(self.state(), before)
        self.send('Conversación ajena')
        from app.editorial.models import Update
        with Session(self.engine) as db:
            self.assertNotIn('Conversación ajena', json.dumps(db.get(Update, self.uid).payload))

    def test_independent_artwork_roles_and_legacy_preview(self):
        self.start_image()
        with Session(self.engine) as db:
            old = db.scalar(select(Version))
            old_values = (old.id, old.asset_id, old.operation)
        self.uid = 10
        self.send('/entrevista')
        self.uid += 1
        raw = self.callback(uid=self.uid, operation='board')
        raw['callback_query']['data'] = raw['callback_query']['data'].replace('op:', 'start:', 1)
        self.dispatch(raw)
        self.to_summary()
        self.send('/obra')
        self.uid += 1
        self.dispatch(self.attachment(uid=self.uid))
        self.assertIn('image', self.transport.sent[-1])
        self.action('2')  # label
        self.action('3')  # unknown subject
        p = self.state()[2]
        self.assertIsNone(p['artworks']['beer_card'])
        self.assertIsNone(p['artworks']['tap_board'])
        self.assertEqual(p['artworks']['label']['subject'], 'unknown')
        with Session(self.engine) as db:
            old = db.get(Version, old_values[0])
            self.assertEqual((old.id, old.asset_id, old.operation), old_values)
        self.assertEqual(self.count(Asset), 1)

    def test_legacy_schema_migration_preserves_all_old_rows(self):
        self.start_image()
        with self.engine.begin() as c:
            c.exec_driver_sql('DROP TABLE editorial_interviews')
            c.exec_driver_sql('DROP TABLE editorial_proposals')
            c.exec_driver_sql('UPDATE editorial_cursor SET schema_version=1')
            before = {name: c.exec_driver_sql(f'SELECT * FROM {name}').all() for name in LEGACY_TABLES if name != 'editorial_cursor'}
        migrate(self.engine)
        migrate(self.engine)
        with self.engine.connect() as c:
            check_schema(c)
            after = {name: c.exec_driver_sql(f'SELECT * FROM {name}').all() for name in before}
            self.assertEqual(before, after)
            self.assertEqual(c.exec_driver_sql('SELECT schema_version FROM editorial_cursor').scalar(), 2)
        self.uid = 10
        self.send('/vista')
        self.assertIn('image', self.transport.sent[-1])
        self.assertEqual(self.count(ProposalRevision), 0)

    def test_semantic_product_is_explicit_and_separate(self):
        self.begin('board')
        self.action('0')
        self.action('0')
        self.answer('Tabla')
        self.action('skip')
        self.action('1')
        for value in ('Cerveza semántica', 'Pale Ale', 'Otra cervecería', 'Otro origen'):
            self.answer(value)
        p = self.state()[2]
        self.assertEqual(p['museum']['semantic_products'][0]['beer_name']['value'], 'Cerveza semántica')
        self.assertEqual(p['museum']['semantic_products'][0]['beer_name']['confidence'], 'unknown')
        self.assertIsNone(p['beer']['name'])
        self.assertIsNone(p['beer']['brewery'])

    def test_revoked_operation_permission_blocks_text_and_callbacks(self):
        self.begin()
        self.action('0')
        before = self.state()
        self.auth.grants[USER] = frozenset({'artwork.submit'})
        self.answer('No autorizado')
        self.action('skip')
        self.assertEqual(self.state(), before)


    def test_three_assets_are_independent_and_replacements_are_versioned(self):
        self.begin('board')
        self.to_summary()
        from tests.test_editorial import png
        assigned = {}
        for color, role, choice in [('red', 'beer_card', '0'), ('blue', 'tap_board', '1'), ('green', 'label', '2')]:
            self.send('/obra')
            self.transport.image = png(color)
            self.uid += 1
            self.dispatch(self.attachment(uid=self.uid))
            self.action(choice)
            self.action('3')
            assigned[role] = self.state()[2]['artworks'][role]['asset_id']
        self.assertEqual(len(set(assigned.values())), 3)
        self.assertEqual({role: art['asset_id'] for role, art in self.state()[2]['artworks'].items()}, assigned)
        self.assertEqual(self.count(Asset), 3)
        self.assert_catalog_unchanged()

    def test_summary_is_read_only_and_duplicate_answer_is_idempotent(self):
        self.begin()
        self.action('0')
        self.uid += 1
        raw = self.message(self.uid, 'Persistente', reply_to_message={'message_id': self.draft()['prompt']})
        self.dispatch(raw)
        before = self.state()
        count = self.count(ProposalRevision)
        self.dispatch(raw)
        self.send('/resumen')
        self.assertEqual(self.state(), before)
        self.assertEqual(self.count(ProposalRevision), count)
        self.send('/cancelar')
        self.send('/resumen')
        self.assertEqual(self.draft()['state'], 'cancelled')

    def test_failed_outbox_insert_rolls_back_answer_and_proposal(self):
        self.begin()
        self.action('0')
        before = self.state()
        with self.engine.begin() as c:
            c.exec_driver_sql("CREATE TRIGGER fail_reply BEFORE INSERT ON editorial_replies BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        self.uid += 1
        raw = self.message(self.uid, 'No parcial', reply_to_message={'message_id': self.draft()['prompt']})
        self.service.ingest([raw])
        with self.assertRaises(Exception):
            self.service.process_one()
        self.assertEqual(self.state(), before)
        with self.engine.begin() as c:
            c.exec_driver_sql('DROP TRIGGER fail_reply')
        self.service.process_one()
        self.service.flush_one()
        self.assertEqual(self.state()[2]['beer']['name'], 'No parcial')

    def test_partial_upgrade_is_not_repaired(self):
        with self.engine.begin() as c:
            c.exec_driver_sql('DROP TABLE editorial_interviews')
        with self.assertRaises(ValueError):
            migrate(self.engine)
        from sqlalchemy import inspect
        self.assertNotIn('editorial_interviews', inspect(self.engine).get_table_names())

    def test_contract_rejects_operational_flags_and_incompatible_targets(self):
        for field in ('is_available', 'tap_position', 'is_featured'):
            with self.assertRaises(ValidationError):
                Proposal(revision=1, operation='new', **{field: True})
        p = Proposal(revision=1, operation='board', targets=['beer_create']).validated_snapshot()
        self.assertEqual(p.validation_status, 'incomplete')



    def assert_summary_has_no_writes(self):
        from sqlalchemy import event, inspect
        from hashlib import sha256
        def snapshot():
            with self.engine.connect() as c:
                return {name: c.exec_driver_sql(f'SELECT * FROM "{name}" ORDER BY 1').all()
                        for name in inspect(c).get_table_names()}
        before = snapshot()
        media = {path.name: path.read_bytes() for path in self.media.root.glob('*') if path.is_file()}
        database_hash = sha256(self.path.read_bytes()).hexdigest()
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.strip().split()[0].upper())
        event.listen(self.engine, 'before_cursor_execute', capture)
        try:
            self.send('/resumen')
        finally:
            event.remove(self.engine, 'before_cursor_execute', capture)
        self.assertFalse(set(statements) & {'INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'CREATE', 'ALTER', 'DROP'})
        self.assertEqual(snapshot(), before)
        self.assertEqual(sha256(self.path.read_bytes()).hexdigest(), database_hash)
        self.assertEqual(media, {path.name: path.read_bytes() for path in self.media.root.glob('*') if path.is_file()})

    def test_legacy_classified_summary_is_strictly_read_only(self):
        self.start_image()
        self.dispatch(self.callback())
        self.uid = 10
        self.assert_summary_has_no_writes()
        self.assertIn('/entrevista', self.transport.sent[-1]['text'])
        self.assertIn('Tabla del Tap List', self.transport.sent[-1]['text'])
        self.assertEqual(self.count(Interview), 0)
        self.assertEqual(self.count(ProposalRevision), 0)

    def test_existing_proposal_summary_is_strictly_read_only(self):
        self.begin()
        self.action('0')
        self.answer('Conservar')
        self.assert_summary_has_no_writes()
        self.assertIn('Conservar', self.transport.sent[-1]['text'])

    def test_summary_without_draft_does_not_create_any_records(self):
        self.uid = 10
        self.assert_summary_has_no_writes()
        from app.editorial.models import Draft, Update, Reply
        for model in (Draft, Update, Reply, Interview, ProposalRevision):
            self.assertEqual(self.count(model), 0)

    def test_summary_failure_and_duplicate_leave_database_unchanged(self):
        self.begin()
        self.transport.fail_send = True
        self.assert_summary_has_no_writes()
        self.transport.fail_send = False
        raw = self.message(self.uid, '/resumen')
        sent = len(self.transport.sent)
        self.dispatch(raw)
        self.assertEqual(len(self.transport.sent), sent)
        with Session(self.engine) as db:
            self.assertGreater(self.service.readonly_offset, db.get(Cursor, 1).next_offset)

    def test_old_operation_callbacks_cannot_change_interview_even_with_current_image_revision(self):
        self.start_image()
        self.uid = 10
        self.send('/entrevista')
        raw = self.callback(uid=12, operation='board')
        raw['callback_query']['data'] = raw['callback_query']['data'].replace('op:', 'start:', 1)
        self.dispatch(raw)
        self.uid = 12
        self.action('0')
        before = self.state()
        image_before = self.draft()
        for prefix in ('op:', 'start:'):
            self.uid += 1
            raw = self.callback(uid=self.uid, operation='new')
            raw['callback_query']['data'] = raw['callback_query']['data'].replace('op:', prefix, 1)
            self.dispatch(raw)
            self.assertEqual(self.state(), before)
            self.assertEqual(self.draft(), image_before)
            self.assertIn('/corregir', self.transport.sent[-1]['text'])

    def test_controlled_operation_correction_requires_current_revision_and_confirmation(self):
        self.begin()
        self.action('0')
        self.answer('Nombre preservado')
        self.send('/corregir')
        from app.editorial.interview import options
        edit_options = options('edit', Proposal.model_validate(self.state()[2]))
        self.action(str(len(edit_options) - 1))
        self.assertEqual(self.state()[0], 'operation')
        rev = self.state()[1]
        self.action('3')  # board
        self.assertEqual(self.state()[0], 'confirm_operation:board')
        self.assertEqual(self.state()[2]['operation'], 'new')
        before = self.state()
        self.action('0', revision=rev)
        self.assertEqual(self.state(), before)
        self.action('0')
        self.assertEqual(self.state()[2]['operation'], 'board')
        self.assertEqual(self.state()[2]['beer']['name'], 'Nombre preservado')
        self.assertEqual(self.state()[2]['targets'], [])
        self.assertEqual(self.state()[0], 'targets')
        self.assert_catalog_unchanged()

    def test_operation_correction_checks_permission_again_on_confirmation(self):
        self.begin('board')
        self.send('/corregir')
        from app.editorial.interview import options
        self.action(str(len(options('edit', Proposal.model_validate(self.state()[2]))) - 1))
        self.action('0')  # new
        before = self.state()
        self.auth.grants[USER] = frozenset({'artwork.submit'})
        self.action('0')
        self.assertEqual(self.state(), before)
        self.assertIn('permiso', self.transport.sent[-1]['text'])



    def test_worker_advances_read_only_polling_without_persisting_summary(self):
        from app.workers.editorial import run
        from types import SimpleNamespace
        permissions = self.root / 'permissions.json'
        permissions.write_text(json.dumps({str(USER): ['artwork.submit']}), encoding='utf-8')
        settings = SimpleNamespace(permissions_file=permissions, chat_id=CHAT,
                                   media_root=self.media.root, download_limit_bytes=self.service.download_limit)
        class Stop:
            stopped = False
            def is_set(self):
                return self.stopped
            def wait(self, seconds):
                pass
        stop = Stop()
        offsets = []
        def poll(offset):
            offsets.append(offset)
            if len(offsets) == 1:
                return [self.message(100, '/resumen')]
            if len(offsets) == 2:
                with Session(self.engine) as db:
                    self.assertEqual(db.get(Cursor, 1).next_offset, 0)
                return [self.message(101, '/obra')]
            stop.stopped = True
            return []
        self.transport.get_updates = poll
        run(self.engine, settings, self.transport, stop)
        self.assertEqual(offsets, [0, 101, 102])
        from app.editorial.models import Update, Reply
        with Session(self.engine) as db:
            self.assertIsNone(db.get(Update, 100))
            self.assertEqual([r.update_id for r in db.scalars(select(Reply))], [101])

    def test_operation_confirmation_rejects_inconsistent_proposal_revision(self):
        self.begin('board')
        self.send('/corregir')
        from app.editorial.interview import options
        self.action(str(len(options('edit', Proposal.model_validate(self.state()[2]))) - 1))
        self.action('0')
        with Session(self.engine) as db:
            row = db.get(Interview, self.draft()['id'])
            row.revision += 1
            db.commit()
        before = self.state()
        self.action('0')
        self.assertEqual(self.state(), before)
        self.assertIn('ya no está vigente', self.transport.sent[-1]['text'])



    def test_cancelled_interview_rejects_operation_callbacks(self):
        self.begin('board')
        self.send('/cancelar')
        before = self.state()
        self.uid += 1
        self.dispatch(self.callback(uid=self.uid, operation='new'))
        self.assertEqual(self.state(), before)
        self.assertEqual(self.draft()['state'], 'cancelled')
        self.assertIn('ya no está vigente', self.transport.sent[-1]['text'])


if __name__ == '__main__':
    unittest.main()
