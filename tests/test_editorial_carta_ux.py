"""Carta-only UX checks: isolated SQLite and mocked transport, no Telegram calls."""
import unittest
from unittest.mock import Mock, patch
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.editorial import carta_identity
from app.editorial.models import Reply, ProposalRevision
from app.editorial.telegram import TelegramTransport, TransportError
from tests import test_editorial_carta_identity as fixtures


class CartaUXTests(unittest.TestCase):
    message = fixtures.CartaIdentityTests.message
    dispatch = fixtures.CartaIdentityTests.dispatch
    draft = fixtures.CartaIdentityTests.draft
    start_image = fixtures.CartaIdentityTests.start_image
    attachment = fixtures.CartaIdentityTests.attachment
    count = fixtures.CartaIdentityTests.count
    send = fixtures.CartaIdentityTests.send
    answer = fixtures.CartaIdentityTests.answer
    token = fixtures.CartaIdentityTests.token
    click = fixtures.CartaIdentityTests.click
    proposal = fixtures.CartaIdentityTests.proposal

    def setUp(self):
        fixtures.CartaIdentityTests.setUp(self)
        self.transport.send_typing = Mock()
        self.transport.remove_inline_keyboard = Mock()

    def keyboard_message_ids(self):
        with Session(self.engine) as db:
            return [r.message_id for r in db.scalars(select(Reply).order_by(Reply.id))
                    if r.state == 'sent' and r.markup and r.markup.get('inline_keyboard')]

    def test_typing_once_before_actual_name_search(self):
        self.send('/carta22')
        lookup = carta_identity.lookup_beers

        def checked(*args, **kwargs):
            self.transport.send_typing.assert_called_once_with(fixtures.CHAT)
            return lookup(*args, **kwargs)

        with patch.object(carta_identity, 'lookup_beers', side_effect=checked):
            self.answer()
        self.transport.send_typing.assert_called_once_with(fixtures.CHAT)

    def test_typing_failure_still_searches_and_no_results_can_retry(self):
        self.send('/carta22')
        self.transport.send_typing.side_effect = TransportError()
        self.answer('No existe')
        self.assertIn('No encontré', self.transport.sent[-1]['text'])
        self.answer()
        self.assertIn('confirma una cerveza', self.transport.sent[-1]['text'])
        self.assertEqual(self.transport.send_typing.call_count, 2)

    def test_no_typing_for_wrong_reply_unauthorized_or_v21(self):
        self.start_image()
        self.send('/vista')
        self.transport.send_typing.assert_not_called()
        self.send('/cancelar')
        self.send('/carta22')
        self.send('Leviatán', reply_to_message={'message_id': 99999})
        self.send('Leviatán', user=999, reply_to_message={'message_id': self.draft()['prompt']})
        self.transport.send_typing.assert_not_called()

    def test_confirmed_case_never_requests_name_again_and_cleans_keyboard(self):
        self.send('/carta22')
        self.answer()
        token = self.token()
        ids = self.keyboard_message_ids()
        self.click(token)
        self.transport.remove_inline_keyboard.assert_called_once_with(fixtures.CHAT, ids[0])
        self.assertEqual(self.keyboard_message_ids(), ids)  # History is not deleted or rewritten.
        revisions = self.count(ProposalRevision)
        for text in ('Otro nombre', '/obra', '/entrevista', '/continuar', '/vista', '/resumen'):
            self.send(text, reply_to_message={'message_id': 101})
            actual = self.transport.sent[-1]['text']
            self.assertIn('identidad confirmada', actual)
            self.assertIn('guardó la identidad', actual)
            self.assertIn('No se aprobó ni publicó', actual)
            self.assertNotIn('pide el nombre', actual)
        self.assertEqual(self.count(ProposalRevision), revisions)
        self.transport.send_typing.assert_called_once()
        self.click(token)
        self.assertIn('no está vigente', self.transport.sent[-1]['text'])
        self.transport.remove_inline_keyboard.assert_called_once()

    def test_candidate_state_guidance_does_not_ask_for_name(self):
        self.send('/carta22')
        self.answer()
        self.send('Otra respuesta', reply_to_message={'message_id': 101})
        self.assertIn('con los botones', self.transport.sent[-1]['text'])
        self.assertNotIn('pide el nombre', self.transport.sent[-1]['text'])

    def test_command_cancel_removes_all_current_case_keyboards_only(self):
        self.send('/carta22')
        self.answer()
        first_ids = self.keyboard_message_ids()
        self.send('/cancelar')
        self.transport.remove_inline_keyboard.assert_called_once_with(fixtures.CHAT, first_ids[0])
        self.send('/carta22')
        self.answer()
        token = self.token()
        self.send('/continuar')  # A second keyboard for the same current case.
        current_ids = self.keyboard_message_ids()[1:]
        self.transport.remove_inline_keyboard.reset_mock()
        self.send('/cancelar')
        self.assertEqual([call.args for call in self.transport.remove_inline_keyboard.call_args_list],
                         [(fixtures.CHAT, mid) for mid in current_ids])
        self.send('/resumen')
        self.assertIn('cerrado', self.transport.sent[-1]['text'])
        self.assertNotIn('llama la cerveza', self.transport.sent[-1]['text'])
        self.click(token)
        self.assertIn('no está vigente', self.transport.sent[-1]['text'])

    def test_button_cancel_and_cleanup_failure_preserve_cancelled_state(self):
        self.send('/carta22')
        self.answer()
        self.transport.remove_inline_keyboard.side_effect = TransportError()
        self.click(self.token(-1))
        self.assertEqual(self.draft()['state'], 'cancelled')
        self.assertIn('cerrado', self.transport.sent[-1]['text'])

    def test_cleanup_failure_does_not_undo_confirmation(self):
        self.send('/carta22')
        self.answer()
        self.transport.remove_inline_keyboard.side_effect = TransportError()
        self.click(self.token())
        self.assertEqual(self.proposal().beers[0].kind, 'existing')
        self.assertIn('identidad confirmada', self.transport.sent[-1]['text'])

    def test_native_transport_methods_only_send_expected_api_payloads(self):
        transport = TelegramTransport(SecretStr('fake-token-never-used'))
        with patch.object(transport, '_request', return_value=True) as request:
            transport.send_typing(fixtures.CHAT)
            request.assert_called_once_with('sendChatAction', {'chat_id': fixtures.CHAT, 'action': 'typing'})
            request.reset_mock()
            transport.remove_inline_keyboard(fixtures.CHAT, 42)
            request.assert_called_once_with('editMessageReplyMarkup', {
                'chat_id': fixtures.CHAT, 'message_id': 42, 'reply_markup': {'inline_keyboard': []}})


if __name__ == '__main__':
    unittest.main()
