"""Commercial Telegram interview: temporary SQLite only, fake Telegram and temp logs."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
import sqlite3
import unittest
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import bot_observability
from app.editorial import commercial_interview as flow
from app.editorial.models import Interview, ProposalRevision, Asset, Version
from app.editorial.patches import apply_commercial_patch
from app.editorial.proposal_v22 import Proposal22, CreateBeerAction
from app.editorial.service import EditorialService
from tests import test_editorial_carta_identity as foundation


class CommercialTests(unittest.TestCase):
    message = foundation.CartaIdentityTests.message
    dispatch = foundation.CartaIdentityTests.dispatch
    draft = foundation.CartaIdentityTests.draft
    count = foundation.CartaIdentityTests.count
    send = foundation.CartaIdentityTests.send
    answer = foundation.CartaIdentityTests.answer
    click = foundation.CartaIdentityTests.click
    token = foundation.CartaIdentityTests.token
    proposal = foundation.CartaIdentityTests.proposal
    start_image = foundation.CartaIdentityTests.start_image
    attachment = foundation.CartaIdentityTests.attachment

    def setUp(self):
        foundation.CartaIdentityTests.setUp(self)
        self.log_patch = patch.object(bot_observability, 'LOG_ROOT', self.root / 'logs')
        self.log_patch.start()
        self.addCleanup(self.log_patch.stop)
        self.addCleanup(self.close_logs)
        with closing(sqlite3.connect(self.catalog)) as db, db:
            for field, kind in [('origin','TEXT'),('color','TEXT'),('description','TEXT'),('abv','REAL'),('ibu','REAL'),('prices','TEXT')]:
                db.execute(f'ALTER TABLE beers ADD COLUMN {field} {kind}')
            db.execute('UPDATE beers SET origin=?,color=?,description=?,abv=?,ibu=?,prices=? WHERE id=1',
                       ('México','Ámbar','Original',6.5,40,json.dumps({'taster':0,'pinta_chica':60,'legacy_price':99})))
        self.before = sha256(self.catalog.read_bytes()).hexdigest()

    def close_logs(self):
        import logging
        logger = logging.getLogger('atlas.bot_console.editorial')
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

    def action(self, code):
        rows = self.transport.sent[-1]['markup']['inline_keyboard']
        token = next(row[0]['callback_data'] for row in rows if row[0]['callback_data'].endswith(':' + code))
        self.click(token)

    def enter(self, value):
        self.action('s')
        self.answer(value)

    def field(self, name):
        self.send('/corregir')
        self.action('e' + str(flow.FIELDS.index(name)))

    def edit(self):
        self.send('/carta22')
        self.answer()
        self.click(self.token())
        self.identity = deepcopy(self.proposal().beers[0].model_dump(mode='json'))
        self.send('/editar22')

    def state(self):
        with Session(self.engine) as db:
            return deepcopy(db.get(Interview, self.draft()['id']).history)

    def projected(self):
        return apply_commercial_patch(self.state()['commercial']['baseline'], self.proposal().actions[0].patch,
                                      allow_clear=flow.CLEARABLE)

    def test_create_all_fields_and_prices_unavailable_no_side_effects(self):
        self.send('/nueva22')
        values = ('Nueva','Cervecería','IPA','México','Ámbar','Descripción', '6,5','40','0','60','90','150','200')
        for value in values:
            self.enter(value)
        p = self.proposal()
        self.assertIsInstance(p.actions[0], CreateBeerAction)
        self.assertIs(p.actions[0].is_available, False)
        self.assertEqual(p.beers[0].candidate.name, 'Nueva')
        self.assertEqual(p.beers[0].candidate.abv, 6.5)
        self.assertEqual(p.beers[0].candidate.prices.taster, 0)
        self.assertEqual(len(p.actions[0].patch.prices.model_dump()), 5)
        self.assertEqual(p.readiness, 'technically_valid')
        self.assertIn('no disponible', self.transport.sent[-1]['text'])
        self.assertIn('No se publicó ni activó', self.transport.sent[-1]['text'])
        self.assertLess(len(self.transport.sent[-1]['text']), 4096)
        self.assertEqual(self.count(Asset), 0)
        self.assertEqual(self.count(Version), 0)
        self.assertEqual(sha256(self.catalog.read_bytes()).hexdigest(), self.before)

    def test_edit_sparse_values_unknown_keep_and_single_price_clear(self):
        self.edit()
        self.action('k')  # name
        self.action('u')  # brewery: unknown, not null/clear
        self.action('k')  # style
        self.action('c')  # origin: explicit null
        self.field('prices.pinta_chica')
        self.action('c')
        self.field('prices.pinta_grande')
        self.enter('0')
        result = self.projected()
        self.assertIsNone(result['origin'])
        self.assertEqual(result['brewery'], 'Cyprez')
        self.assertEqual(result['prices'], {'taster':0,'legacy_price':99,'pinta_grande':0})
        self.assertEqual(result['description'], 'Original')
        self.assertEqual(self.proposal().beers[0].model_dump(mode='json'), self.identity)
        self.send('/resumen')
        self.assertIn('sin información; conservar Cyprez', self.transport.sent[-1]['text'])
        self.assertEqual(sha256(self.catalog.read_bytes()).hexdigest(), self.before)

    def test_optional_unknown_does_not_invent_values_or_complete_missing_required(self):
        self.send('/nueva22')
        for _ in flow.FIELDS:
            self.action('u')
        self.assertEqual(self.proposal().readiness, 'incomplete')
        self.assertIsNone(self.proposal().beers[0].candidate.name)
        self.assertIn('Falta: Nombre, Cervecería, Estilo', self.transport.sent[-1]['text'])

    def test_invalid_numbers_and_required_clear_are_rejected_without_revisions(self):
        self.send('/nueva22')
        token = self.token().rsplit(':',1)[0] + ':c'
        before = self.count(ProposalRevision)
        self.click(token)
        self.assertEqual(self.count(ProposalRevision), before)
        self.field('abv')
        self.action('s')
        for value in ('NaN','Infinity','-1','101','true','1e999'):
            before = self.count(ProposalRevision)
            self.answer(value)
            self.assertEqual(self.count(ProposalRevision), before)
            self.assertIn('válido', self.transport.sent[-1]['text'])
        self.answer('6,5')
        self.assertEqual(self.proposal().beers[0].candidate.abv, 6.5)
        self.field('prices.taster')
        self.action('s')
        for value in ('-1','1000001','NaN'):
            before = self.count(ProposalRevision)
            self.answer(value)
            self.assertEqual(self.count(ProposalRevision), before)

    def test_correction_keep_preserves_prior_patch_explicit_discard_restores_source(self):
        self.edit()
        self.field('description')
        self.enter('Nueva descripción')
        self.field('description')
        self.action('k')
        self.assertEqual(self.projected()['description'], 'Nueva descripción')
        self.field('description')
        self.action('d')
        self.assertEqual(self.projected()['description'], 'Original')
        self.assertNotIn('description', self.proposal().actions[0].patch.model_dump())

    def test_stale_buttons_wrong_reply_and_restart_recovery(self):
        self.send('/nueva22')
        old = self.token()
        self.action('s')
        prompt = self.draft()['prompt']
        before = self.count(ProposalRevision)
        self.send('No capturar')
        self.send('No capturar', reply_to_message={'message_id':9999})
        self.assertEqual(self.count(ProposalRevision), before)
        self.service = EditorialService(self.engine, self.auth, self.media, self.transport,1000,
                                       catalog_database_url='sqlite:///' + self.catalog.as_posix())
        self.answer('Nueva')
        self.click(old)
        self.assertIn('no está vigente', self.transport.sent[-1]['text'])
        self.send('Vieja', reply_to_message={'message_id':prompt})
        self.assertEqual(self.proposal().beers[0].candidate.name, 'Nueva')
        self.send('/continuar')
        self.action('b')
        self.assertEqual(self.state()['commercial']['index'], 0)
        before = self.count(ProposalRevision)
        self.send('/resumen')
        self.assertEqual(self.count(ProposalRevision), before)

    def test_permissions_and_unrelated_active_draft_not_replaced(self):
        self.auth.grants[foundation.USER] = frozenset({'artwork.submit'})
        self.send('/nueva22')
        self.assertEqual(self.count(ProposalRevision), 0)
        self.auth.grants[foundation.USER] = frozenset({'artwork.submit','beer.create'})
        self.send('/nueva22')
        before = self.state()
        self.send('/nueva22')
        self.send('/carta22')
        self.assertEqual(self.state(), before)
        self.auth.grants[foundation.USER] = frozenset({'artwork.submit'})
        token = self.token() if self.transport.sent[-1].get('markup') else None
        self.send('/continuar')
        self.assertIn('No tienes permiso', self.transport.sent[-1]['text'])
        self.assertEqual(self.state(), before)
        self.send('/cancelar')
        self.assertEqual(self.draft()['state'], 'cancelled')

    def test_edit_requires_confirmed_current_identity(self):
        self.send('/editar22')
        self.assertEqual(self.count(ProposalRevision), 0)
        self.send('/carta22')
        self.answer()
        self.click(self.token())
        before = self.count(ProposalRevision)
        with closing(sqlite3.connect(self.catalog)) as db, db:
            db.execute("UPDATE beers SET brewery='Otra' WHERE id=1")
        self.send('/editar22')
        self.assertEqual(self.count(ProposalRevision), before)
        self.assertIn('No se pudo verificar', self.transport.sent[-1]['text'])

    def test_cancel_return_v21_preserves_all_proposal_rows(self):
        self.send('/nueva22')
        self.enter('Nueva')
        with Session(self.engine) as db:
            rows = deepcopy([p.payload for p in db.scalars(select(ProposalRevision).order_by(ProposalRevision.id))])
        old = self.token()
        self.send('/cancelar')
        self.send('/entrevista')
        self.click(old)
        self.assertIn('no está vigente', self.transport.sent[-1]['text'])
        self.send('/entrevista')
        self.click(next(row[0]['callback_data'] for row in self.transport.sent[-1]['markup']['inline_keyboard'] if row[0]['callback_data'].endswith(':board')))
        with Session(self.engine) as db:
            actual = [p.payload for p in db.scalars(select(ProposalRevision).order_by(ProposalRevision.id))]
        self.assertEqual(actual[:len(rows)], rows)
        self.assertEqual(actual[-1]['schema_version'], '2.1')

    def test_creation_contract_rejects_availability_or_operational_controls(self):
        self.send('/nueva22')
        raw = self.proposal().model_dump(mode='json')
        for value in (True, 0, 1):
            changed = deepcopy(raw)
            changed['actions'][0]['is_available'] = value
            with self.assertRaises(ValueError):
                Proposal22.model_validate(changed)
        raw['actions'][0]['tap_position'] = 1
        with self.assertRaises(ValueError):
            Proposal22.model_validate(raw)

    def test_creation_contract_rejects_candidate_patch_disagreement(self):
        self.send('/nueva22')
        raw = self.proposal().model_dump(mode='json')
        raw['beers'][0]['candidate']['name'] = 'No proviene del patch'
        with self.assertRaises(ValueError):
            Proposal22.model_validate(raw)

    def test_commercial_snapshot_is_allowlisted_and_reader_never_changes_source(self):
        from app.editorial.candidate_lookup import read_commercial_beer
        baseline = read_commercial_beer('sqlite:///' + self.catalog.as_posix(), 1)
        self.assertEqual(set(baseline), set(flow.FIELDS[:8]) | {'prices'})
        self.assertEqual(baseline['prices']['legacy_price'], 99)
        self.assertEqual(sha256(self.catalog.read_bytes()).hexdigest(), self.before)
        for bad_id in (True, -1, '1', 999):
            with self.assertRaises(ValueError):
                read_commercial_beer('sqlite:///' + self.catalog.as_posix(), bad_id)


if __name__ == '__main__':
    unittest.main()
