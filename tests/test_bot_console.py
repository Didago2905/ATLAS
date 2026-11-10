"""Offline observability: temp logs, fake transports/config, no worker processes."""
import ast
import importlib.util
import io
import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.core import bot_observability as logs
from app.bot_console import read_available

REPO = Path(__file__).resolve().parents[1]


def close_handlers():
    for channel in logs.CHANNELS:
        logger = logging.getLogger('atlas.bot_console.' + channel)
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)


class BotConsoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patch = patch.object(logs, 'LOG_ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(close_handlers)

    def test_fixed_events_only_and_no_exception_or_payload_leakage(self):
        logs.event('editorial', 'operation_ok')
        logs.event('editorial', 'TOKEN PRIVATE MESSAGE')
        logs.event('unknown', 'started')
        logger = logging.getLogger('atlas.bot_console.editorial')
        logger.error('TOKEN PRIVATE MESSAGE')
        try:
            raise ValueError('SECRET_EXCEPTION')
        except ValueError:
            logger.info('%s | %s', 'editorial', 'operation_failed', exc_info=True, stack_info=True)
        raw = (self.root / 'editorial.log').read_text()
        self.assertIn('operation_ok', raw)
        self.assertIn('operation_failed', raw)
        self.assertNotIn('TOKEN', raw)
        self.assertNotIn('PRIVATE', raw)
        self.assertNotIn('SECRET', raw)
        self.assertNotIn('Traceback', raw)

    def test_rotation_is_bounded_and_configuration_not_duplicated(self):
        with patch.object(logs, 'MAX_BYTES', 160):
            for _ in range(40):
                logs.event('incidents', 'operation_ok')
        files = list(self.root.glob('incidents.log*'))
        self.assertEqual(len(files), 4)
        self.assertTrue(all(p.stat().st_size <= 160 for p in files))
        self.assertEqual(len(logging.getLogger('atlas.bot_console.incidents').handlers), 1)
        self.assertEqual(logs.MAX_BYTES, 512 * 1024)
        self.assertEqual(logs.BACKUPS, 3)

    def test_disk_failure_never_raises_or_echoes_exception(self):
        with patch.object(Path, 'mkdir', side_effect=PermissionError('SECRET')), patch('sys.stderr', new_callable=io.StringIO) as stderr:
            logs.event('editorial', 'started')
        self.assertEqual(stderr.getvalue(), '')

    def test_reader_missing_append_partial_rotation_and_close(self):
        path = self.root / 'editorial.log'
        lines, position = read_available(path)
        self.assertEqual(lines, [])
        logs.event('editorial', 'started')
        lines, position = read_available(path, position)
        self.assertEqual(len(lines), 1)
        self.assertEqual(read_available(path, position)[0], [])
        close_handlers()
        path.rename(self.root / 'editorial.log.1')  # Windows reader must not hold the file open.
        logs.event('editorial', 'stopped')
        lines, position = read_available(path, position)
        self.assertEqual(len(lines), 1)
        self.assertIn('stopped', lines[0])
        close_handlers()
        with path.open('ab') as output:
            output.write(b'2026-11-09T12:00:00Z | editorial | started')
        self.assertEqual(read_available(path, position)[0], [])
        with path.open('ab') as output:
            output.write(b'\nTOKEN FULL PAYLOAD\n')
        lines, _ = read_available(path, position)
        self.assertEqual(len(lines), 1)
        self.assertNotIn('TOKEN', ''.join(lines))

    def test_notifications_uses_fake_config_and_mocked_transport(self):
        spec = importlib.util.spec_from_file_location('isolated_notifications', REPO / 'devtools/telegram/bot.py')
        bot = importlib.util.module_from_spec(spec)
        fake = json.dumps({'telegram': {'bot_token': 'FAKE_SECRET', 'chat_id': -1}})
        with patch('builtins.open', return_value=io.StringIO(fake)):
            spec.loader.exec_module(bot)
        with patch.object(bot.requests, 'post', return_value=Mock()) as post:
            bot.send_message('PRIVATE MESSAGE')
            self.assertEqual(post.call_count, 1)
        with patch.object(bot.requests, 'post', side_effect=RuntimeError('FAKE_SECRET')):
            with self.assertRaises(RuntimeError):
                bot.send_message('PRIVATE MESSAGE')
        with patch('builtins.open', return_value=io.BytesIO(b'PRIVATE IMAGE')), patch.object(bot.requests, 'post', return_value=Mock()):
            bot.send_photo('unused', 'PRIVATE CAPTION')
        text = (self.root / 'notifications.log').read_text()
        self.assertIn('operation_ok', text)
        self.assertIn('operation_failed', text)
        self.assertNotIn('PRIVATE', text)
        self.assertNotIn('FAKE_SECRET', text)

    def test_launcher_preserves_owners_and_only_adds_readers(self):
        bat = (REPO / 'devtools/launcher/terminal.bat').read_text(encoding='utf-8')
        self.assertEqual(bat.count('new-tab '), 2)
        self.assertEqual(bat.count('split-pane '), 4)
        self.assertEqual(bat.count('app.dev_launcher'), 1)
        self.assertEqual(bat.count('devtools.launcher.launcher'), 1)
        self.assertEqual(bat.count('npm run dev -- --host'), 1)
        self.assertNotIn('app.workers.', bat)
        for channel in logs.CHANNELS:
            self.assertEqual(bat.count('-m app.bot_console ' + channel), 1)
        for line in bat.splitlines():
            if line.rstrip().endswith('^'):
                self.assertEqual(line, line.rstrip())
        self.assertTrue(bat.splitlines()[bat.splitlines().index('wt ^') + 1].startswith('new-tab '))
        viewer = ast.parse((REPO / 'app/bot_console.py').read_text())
        imports = [n.module or '' for n in ast.walk(viewer) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any('workers' in name or 'telegram' in name or 'database' in name for name in imports))
        for name in ('app/bot_console.py', 'app/core/bot_observability.py', 'devtools/launcher/launcher.py',
                     'app/workers/editorial.py', 'app/workers/incident_notifications.py'):
            ast.parse((REPO / name).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
