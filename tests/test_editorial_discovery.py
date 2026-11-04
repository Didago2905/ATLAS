"""Offline ID discovery: fake responses only; no real credentials or SQLite."""
from contextlib import redirect_stdout, redirect_stderr
import getpass
from io import StringIO
import os
import socket
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
import warnings

from app.editorial import discover_ids as discovery

USERNAME = "ATLAS_TestEditorialBot"
CODE = "DISCOVERY_TEST_8472"
TOKEN = "123456:" + "x" * 35


def message():
    command = "/identificar@" + USERNAME
    return {"update_id": 1, "message": {
        "message_id": 12, "text": command + " " + CODE,
        "entities": [{"type": "bot_command", "offset": 0, "length": len(command)}],
        "chat": {"id": -123456, "type": "group", "title": "PRIVATE GROUP TITLE"},
        "from": {"id": 789, "is_bot": False, "first_name": "PRIVATE PERSONAL NAME"},
    }}


def transport(updates=None, webhook=None, bot=None):
    fake = Mock()
    responses = {
        "getMe": bot if bot is not None else {"id": 222, "is_bot": True, "username": USERNAME},
        "getWebhookInfo": webhook if webhook is not None else {"url": ""},
        "getUpdates": [message()] if updates is None else updates,
    }
    def request(method, payload):
        if method not in responses:
            raise AssertionError("Mutation or unsupported Telegram call")
        return responses[method]
    fake._request.side_effect = request
    return fake


class Terminal(StringIO):
    def isatty(self):
        return True


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(socket.socket, "connect", side_effect=AssertionError("Real network forbidden"))
        guard.start()
        self.addCleanup(guard.stop)

    def run_cli(self, client=None, inputs=None, argv=None):
        stdout, stderr = Terminal(), Terminal()
        factory = Mock(return_value=client or transport())
        with patch.object(sys, "argv", argv or ["discover_ids"]), patch.object(sys, "stdin", Terminal()), \
                redirect_stdout(stdout), redirect_stderr(stderr), \
                patch.object(getpass, "getpass", return_value=TOKEN), \
                patch("builtins.input", side_effect=inputs if inputs is not None else [CODE, ""]):
            status = discovery.main(transport_factory=factory)
        return status, stdout.getvalue(), stderr.getvalue(), factory

    def assert_reason(self, updates, reason):
        with self.assertRaises(discovery.DiscoveryError) as raised:
            discovery.discover_ids(transport(updates), USERNAME, CODE)
        self.assertEqual(raised.exception.reason, reason)

    def test_valid_identification_prints_exactly_four_sanitized_fields(self):
        status, out, err, factory = self.run_cli()
        self.assertEqual(status, 0)
        self.assertEqual(err, "")
        self.assertEqual(out, f"bot_username: @{USERNAME}\nchat_id: -123456\nchat_type: group\nuser_id: 789\n")
        self.assertNotIn(TOKEN, repr(factory.call_args))
        for sensitive in [TOKEN, CODE, "PRIVATE", "/identificar", "https://"]:
            self.assertNotIn(sensitive, out + err)

    def test_only_fixed_read_methods_and_no_offset_or_subscription_changes(self):
        client = transport()
        self.assertEqual(self.run_cli(client)[0], 0)
        self.assertEqual(client._request.call_args_list, [
            unittest.mock.call("getMe", {}), unittest.mock.call("getWebhookInfo", {}),
            unittest.mock.call("getUpdates", {"timeout": 0, "limit": 100}),
        ])
        client.send_message.assert_not_called()
        client.send_photo.assert_not_called()
        client.download.assert_not_called()
        client.get_updates.assert_not_called()  # Worker method requires an offset; intentionally not used.

    def test_supergroup_identification(self):
        raw = message()
        raw["message"]["chat"]["type"] = "supergroup"
        result = discovery.discover_ids(transport([raw]), USERNAME, CODE)
        self.assertEqual(result.chat_type, "supergroup")

    def test_missing_identification_offers_safe_retry_without_raw_content(self):
        status, out, err, _ = self.run_cli(transport([]))
        self.assertEqual(status, 1)
        self.assertIn("No hay una identificación", err)
        self.assertIn("worker detenido", err)
        self.assertIn("No descartes", err)
        self.assertNotIn("chat_id:", out)

    def test_wrong_command_bot_code_whitespace_or_caption_do_not_match(self):
        for text in [f"/obra@{USERNAME} {CODE}", f"/identificar@AnotherEditorialBot {CODE}",
                     f"/identificar@{USERNAME} DIFFERENT_CODE", f"/identificar {CODE}",
                     f"/identificar@{USERNAME}  {CODE}", f" /identificar@{USERNAME} {CODE}"]:
            with self.subTest(text=text):
                raw = message()
                raw["message"]["text"] = text
                self.assert_reason([raw], "missing")
        raw = message()
        raw["message"]["caption"] = raw["message"].pop("text")
        self.assert_reason([raw], "missing")

    def test_forwarded_message_variants_rejected(self):
        for key in ["forward_origin", "forward_from", "forward_from_chat", "forward_sender_name", "forward_date"]:
            with self.subTest(key=key):
                raw = message()
                raw["message"][key] = "PRIVATE FORWARD METADATA"
                self.assert_reason([raw], "sender")

    def test_anonymous_administrator_channel_identity_and_bot_rejected(self):
        for change in [{"sender_chat": {"id": -123456}}, {"author_signature": "PRIVATE"},
                       {"from": {"id": 789, "is_bot": True}}, {"via_bot": {"id": 999}}]:
            with self.subTest(change=change):
                raw = message()
                raw["message"].update(change)
                self.assert_reason([raw], "sender")

    def test_channel_posts_and_edits_cannot_identify_operator(self):
        for kind in ["channel_post", "edited_message", "edited_channel_post"]:
            raw = message()
            raw[kind] = raw.pop("message")
            self.assert_reason([raw], "sender")
        raw = message()
        raw["message"]["chat"]["type"] = "channel"
        self.assert_reason([raw], "sender")

    def test_numeric_ids_and_bot_command_entity_required(self):
        for field, value in [("chat", {"id": "-123456", "type": "group"}),
                             ("chat", {"id": 123456, "type": "group"}),
                             ("from", {"id": True, "is_bot": False}),
                             ("from", {"id": 0, "is_bot": False}), ("entities", [])]:
            raw = message()
            raw["message"][field] = value
            self.assert_reason([raw], "sender")

    def test_multiple_matching_messages_rejected_even_with_same_ids(self):
        first, second = message(), message()
        second["update_id"] = 2
        second["message"]["message_id"] = 13
        self.assert_reason([first, second], "ambiguous")
        second["message"]["from"]["id"] = 987
        self.assert_reason([first, second], "ambiguous")

    def test_valid_and_forwarded_match_are_also_ambiguous(self):
        second = message()
        second["message"]["forward_origin"] = {"type": "user"}
        self.assert_reason([message(), second], "ambiguous")

    def test_full_window_refused_without_advancing_cursor(self):
        client = transport([message()] + [{"update_id": uid} for uid in range(2, 101)])
        with self.assertRaises(discovery.DiscoveryError) as raised:
            discovery.discover_ids(client, USERNAME, CODE)
        self.assertEqual(raised.exception.reason, "backlog")
        client._request.assert_called_once_with("getUpdates", {"timeout": 0, "limit": 100})

    def test_active_webhook_stops_before_discovery_and_does_not_print_url(self):
        client = transport(webhook={"url": "https://PRIVATE-WEBHOOK/secret"})
        status, out, err, _ = self.run_cli(client)
        self.assertEqual(status, 1)
        self.assertIn("webhook activo", err)
        self.assertNotIn("PRIVATE", out + err)
        self.assertEqual([call.args[0] for call in client._request.call_args_list], ["getMe", "getWebhookInfo"])

    def test_malformed_identity_or_webhook_fails_closed(self):
        for bot in [{}, {"id": 222, "is_bot": False, "username": USERNAME},
                    {"id": 222, "is_bot": True, "username": "PRIVATE\nTEXT"}]:
            status, out, err, _ = self.run_cli(transport(bot=bot))
            self.assertEqual(status, 1)
            self.assertNotIn("PRIVATE", out + err)
        self.assertEqual(self.run_cli(transport(webhook={}))[0], 1)

    def test_api_errors_and_factory_errors_do_not_leak_token_or_response(self):
        client = transport()
        client._request.side_effect = RuntimeError(TOKEN + " https://private/token PRIVATE RESPONSE")
        status, out, err, _ = self.run_cli(client)
        self.assertEqual(status, 2)
        self.assertNotIn(TOKEN, out + err)
        self.assertNotIn("PRIVATE RESPONSE", out + err)
        self.assertNotIn("https://", out + err)
        client = transport()
        original = client._request.side_effect
        def fail_updates(method, payload):
            if method == "getUpdates":
                raise RuntimeError(TOKEN)
            return original(method, payload)
        client._request.side_effect = fail_updates
        self.assertNotIn(TOKEN, "".join(self.run_cli(client)[1:3]))

    def test_http_api_error_body_is_never_displayed(self):
        from pydantic import SecretStr
        from app.editorial.telegram import TelegramTransport
        response = Mock(status=401)
        response.read.return_value = (TOKEN + " PRIVATE API RESPONSE").encode()
        connection = Mock()
        connection.getresponse.return_value = response
        client = TelegramTransport(SecretStr(TOKEN), connection_factory=Mock(return_value=connection))
        status, out, err, _ = self.run_cli(client)
        self.assertEqual(status, 2)
        self.assertNotIn(TOKEN, out + err)
        self.assertNotIn("PRIVATE API RESPONSE", out + err)

    def test_diagnostic_connections_disable_wire_debugging(self):
        connection = Mock()
        with patch.object(discovery.http.client, "HTTPSConnection", return_value=connection):
            self.assertIs(discovery.quiet_connection("api.telegram.org", timeout=35), connection)
        connection.set_debuglevel.assert_called_once_with(0)

    def test_invalid_code_does_not_poll_or_echo_the_value(self):
        client = transport()
        status, out, err, _ = self.run_cli(client, inputs=["PRIVATE INVALID CODE"])
        self.assertEqual(status, 1)
        self.assertNotIn("PRIVATE INVALID CODE", out + err)
        self.assertEqual(client._request.call_count, 2)

    def test_noninteractive_input_and_getpass_echo_fallback_refused(self):
        with patch.object(sys, "argv", ["discover_ids"]), patch.object(sys, "stdin", StringIO()), \
                redirect_stderr(Terminal()), patch.object(getpass, "getpass") as prompt:
            self.assertEqual(discovery.main(), 2)
            prompt.assert_not_called()
        stdout, stderr = Terminal(), Terminal()
        def fallback(*args):
            warnings.warn("PRIVATE FALLBACK", getpass.GetPassWarning)
            raise AssertionError("Echoing fallback must not proceed")
        with patch.object(sys, "argv", ["discover_ids"]), patch.object(sys, "stdin", Terminal()), \
                redirect_stdout(stdout), redirect_stderr(stderr), patch.object(getpass, "getpass", side_effect=fallback):
            self.assertEqual(discovery.main(), 2)
        self.assertNotIn("PRIVATE FALLBACK", stdout.getvalue() + stderr.getvalue())

    def test_secret_in_accidental_arguments_is_not_echoed(self):
        status, out, err, factory = self.run_cli(argv=["discover_ids", "--token", TOKEN])
        self.assertEqual(status, 2)
        factory.assert_not_called()
        self.assertNotIn(TOKEN, out + err)

    def test_invalid_token_and_interruption_do_not_leak(self):
        stdout, stderr = Terminal(), Terminal()
        with patch.object(sys, "argv", ["discover_ids"]), patch.object(sys, "stdin", Terminal()), \
                redirect_stdout(stdout), redirect_stderr(stderr), patch.object(getpass, "getpass", return_value="PRIVATE_INVALID_TOKEN"):
            self.assertEqual(discovery.main(), 2)
        self.assertNotIn("PRIVATE_INVALID_TOKEN", stdout.getvalue() + stderr.getvalue())

    def test_no_environment_token_child_process_files_or_database_access(self):
        before = dict(os.environ)
        with patch("builtins.open", side_effect=AssertionError("File access forbidden")), \
                patch.object(sqlite3, "connect", side_effect=AssertionError("SQLite forbidden")) as connect, \
                patch.object(subprocess, "Popen", side_effect=AssertionError("Child process forbidden")) as popen:
            self.assertEqual(self.run_cli()[0], 0)
            connect.assert_not_called()
            popen.assert_not_called()
        self.assertEqual(dict(os.environ), before)


if __name__ == "__main__":
    unittest.main()
