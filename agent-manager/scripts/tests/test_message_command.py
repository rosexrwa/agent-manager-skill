from __future__ import annotations

import argparse
import io
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from commands.message import build_envelope, cmd_message  # noqa: E402


class _FixedUuid:
    hex = 'abcdef1234567890'


class _UuidModule:
    @staticmethod
    def uuid4():
        return _FixedUuid()


class _DatetimeModule:
    @staticmethod
    def now():
        return datetime(2026, 7, 24, 15, 30, 12)


def _deps(**overrides):
    target = {'name': 'qa', 'file_id': 'EMP_0017', 'launcher': 'codex'}
    values = {
        'datetime': _DatetimeModule,
        'uuid': _UuidModule,
        'resolve_agent': lambda value: target if value in {'qa', 'EMP_0017'} else None,
        'get_agent_id': lambda config: config.get('file_id', '').lower().replace('_', '-'),
        'check_tmux': lambda: True,
        'session_exists': lambda _agent_id: True,
        'resolve_launcher_command': lambda launcher: launcher,
        'send_keys': lambda *_args, **_kwargs: True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class MessageCommandTests(unittest.TestCase):
    def test_build_message_envelope_with_footer(self):
        envelope, message_id, error = build_envelope(
            deps=_deps(),
            message_type='message',
            from_agent='EMP_0001',
            to_agent='EMP_0017',
            body='Review PR #123.',
            footer='Reply with QA Verdict.',
        )

        self.assertEqual(error, '')
        self.assertEqual(message_id, 'msg_20260724_153012_abcdef12')
        self.assertEqual(
            envelope,
            '\n'.join(
                [
                    '--- Meta ---',
                    'id: msg_20260724_153012_abcdef12',
                    'type: message',
                    'from: EMP_0001',
                    'to: EMP_0017',
                    '',
                    '--- Body ---',
                    'Review PR #123.',
                    '',
                    '--- Footer ---',
                    'Reply with QA Verdict.',
                ]
            ),
        )

    def test_empty_footer_is_omitted(self):
        envelope, _message_id, error = build_envelope(
            deps=_deps(),
            message_type='message',
            from_agent='EMP_0001',
            to_agent='EMP_0017',
            body='Ping.',
            footer='   ',
            message_id='msg_fixed',
        )

        self.assertEqual(error, '')
        self.assertNotIn('--- Footer ---', envelope)

    def test_reply_includes_reply_to(self):
        envelope, _message_id, error = build_envelope(
            deps=_deps(),
            message_type='reply',
            from_agent='EMP_0017',
            to_agent='EMP_0001',
            reply_to='msg_parent',
            body='QA Verdict: PASS',
            message_id='msg_reply',
        )

        self.assertEqual(error, '')
        self.assertIn('type: reply', envelope)
        self.assertIn('reply_to: msg_parent', envelope)

    def test_reply_requires_reply_to(self):
        envelope, message_id, error = build_envelope(
            deps=_deps(),
            message_type='reply',
            from_agent='EMP_0017',
            to_agent='EMP_0001',
            body='ok',
        )

        self.assertIsNone(envelope)
        self.assertIsNone(message_id)
        self.assertEqual(error, "Meta field 'reply_to' is required for replies")

    def test_meta_fields_reject_multiline_values(self):
        envelope, message_id, error = build_envelope(
            deps=_deps(),
            message_type='message',
            from_agent='EMP_0001\nbad',
            to_agent='EMP_0017',
            body='ok',
        )

        self.assertIsNone(envelope)
        self.assertIsNone(message_id)
        self.assertEqual(error, "Meta field 'from' must be a single line")

    def test_send_delivers_rendered_envelope_without_queue_dependency(self):
        calls = []

        def send_keys(*args, **kwargs):
            calls.append((args, kwargs))
            return True

        deps = _deps(send_keys=send_keys)
        args = argparse.Namespace(
            message_command='send',
            agent='qa',
            from_agent='EMP_0001',
            body='Please test.',
            footer='Reply PASS or FAIL.',
            id='msg_fixed',
        )

        output = io.StringIO()
        with redirect_stdout(output):
            rc = cmd_message(args, deps=deps)

        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1)
        send_args, send_kwargs = calls[0]
        self.assertEqual(send_args[0], 'emp-0017')
        self.assertIn('id: msg_fixed', send_args[1])
        self.assertIn('to: EMP_0017', send_args[1])
        self.assertIn('Please test.', send_args[1])
        self.assertTrue(send_kwargs['send_enter'])
        self.assertTrue(send_kwargs['clear_input'])
        self.assertIn('tmux accepted', output.getvalue())

    def test_send_returns_nonzero_when_tmux_send_fails(self):
        args = argparse.Namespace(
            message_command='send',
            agent='qa',
            from_agent='EMP_0001',
            body='Please test.',
            footer=None,
            id='msg_fixed',
        )

        output = io.StringIO()
        with redirect_stdout(output):
            rc = cmd_message(args, deps=_deps(send_keys=lambda *_args, **_kwargs: False))

        self.assertEqual(rc, 1)
        self.assertIn('Failed to send protocol message', output.getvalue())


if __name__ == '__main__':
    unittest.main()
