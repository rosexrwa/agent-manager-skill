from __future__ import annotations
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import tmux_helper  # noqa: E402


class SendKeysTests(unittest.TestCase):
    @patch('tmux_helper._agent_pane_target', return_value='%1')
    @patch('tmux_helper.session_exists', return_value=True)
    @patch('tmux_helper.time.sleep', return_value=None)
    @patch('tmux_helper.subprocess.run')
    def test_enter_via_key_uses_native_enter_first(self, mock_run, _mock_sleep, _mock_session_exists, _mock_target):
        commands = []
        capture_index = {'count': 0}

        def fake_run(args, *pargs, **kwargs):
            commands.append(args)
            if args[:5] == ['tmux', 'capture-pane', '-p', '-t', '%1']:
                capture_index['count'] += 1
                stdout = 'before\n' if capture_index['count'] == 1 else 'after\n'
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout)
            return subprocess.CompletedProcess(args=args, returncode=0, stdout='')

        mock_run.side_effect = fake_run

        ok = tmux_helper.send_keys(
            'emp-0001',
            'hello from test',
            send_enter=True,
            enter_via_key=True,
        )

        self.assertTrue(ok)
        self.assertTrue(any(cmd[:4] == ['tmux', 'send-keys', '-t', '%1'] and cmd[-1] == 'C-m' for cmd in commands))
        self.assertFalse(any(cmd[:4] == ['tmux', 'load-buffer', '-b', 'enter-key'] for cmd in commands))

    @patch('tmux_helper._agent_pane_target', return_value='%1')
    @patch('tmux_helper.session_exists', return_value=True)
    @patch('tmux_helper.time.sleep', return_value=None)
    @patch('tmux_helper.subprocess.run')
    def test_enter_via_key_returns_false_when_native_and_fallback_do_not_change_pane(
        self,
        mock_run,
        _mock_sleep,
        _mock_session_exists,
        _mock_target,
    ):
        commands = []

        def fake_run(args, *pargs, **kwargs):
            commands.append(args)
            if args[:5] == ['tmux', 'capture-pane', '-p', '-t', '%1']:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout='unchanged\n')
            return subprocess.CompletedProcess(args=args, returncode=0, stdout='')

        mock_run.side_effect = fake_run

        ok = tmux_helper.send_keys(
            'emp-0001',
            'hello from test',
            send_enter=True,
            enter_via_key=True,
        )

        self.assertFalse(ok)
        self.assertTrue(any(cmd[:4] == ['tmux', 'send-keys', '-t', '%1'] and cmd[-1] == 'C-m' for cmd in commands))
        self.assertTrue(any(cmd[:4] == ['tmux', 'load-buffer', '-b', 'enter-key'] for cmd in commands))
        self.assertTrue(any(cmd[:5] == ['tmux', 'paste-buffer', '-d', '-b', 'enter-key'] for cmd in commands))

    @patch('tmux_helper._agent_pane_target', return_value='%1')
    @patch('tmux_helper.session_exists', return_value=True)
    @patch('tmux_helper.time.sleep', return_value=None)
    @patch('tmux_helper.subprocess.run')
    def test_enter_via_key_fallback_succeeds_when_pane_changes_after_newline(
        self,
        mock_run,
        _mock_sleep,
        _mock_session_exists,
        _mock_target,
    ):
        commands = []
        capture_outputs = iter([
            'unchanged\n',  # native before
            'unchanged\n',  # native probe-1
            'unchanged\n',  # native probe-2
            'unchanged\n',  # native probe-3
            'unchanged\n',  # fallback before
            'changed\n',    # fallback probe-1
        ])

        def fake_run(args, *pargs, **kwargs):
            commands.append(args)
            if args[:5] == ['tmux', 'capture-pane', '-p', '-t', '%1']:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=next(capture_outputs))
            return subprocess.CompletedProcess(args=args, returncode=0, stdout='')

        mock_run.side_effect = fake_run

        ok = tmux_helper.send_keys(
            'emp-0001',
            'hello from test',
            send_enter=True,
            enter_via_key=True,
        )

        self.assertTrue(ok)
        self.assertTrue(any(cmd[:4] == ['tmux', 'load-buffer', '-b', 'enter-key'] for cmd in commands))
        self.assertTrue(any(cmd[:5] == ['tmux', 'paste-buffer', '-d', '-b', 'enter-key'] for cmd in commands))


class EnterClosedLoopTests(unittest.TestCase):
    """Issue #158: Enter submissions must be verified and retried when lost.

    The fakes model the real failure: the task text sits in the input box and
    stays there until the Nth Enter actually lands."""

    def _run_send_keys(self, *, enters_needed, box_text, busy_text=None,
                       busy_always=False, keys='fix the bug in parser',
                       enter_via_key=True):
        """Drive send_keys against a fake pane.

        The pane shows `box_text` (input box with pending text) until
        `enters_needed` Enter events have occurred, after which it shows the
        cleared state (or `busy_text` if given). `busy_always` keeps a busy
        indicator on screen the whole time.
        """
        commands = []
        state = {'enters': 0}

        cleared = busy_text if busy_text is not None else '│ > │\n'
        if busy_always:
            box_text = box_text + 'Working (3m 12s • esc to interrupt)\n'
            cleared = cleared + 'Working (3m 12s • esc to interrupt)\n'

        def fake_run(args, *pargs, **kwargs):
            commands.append(args)
            if args[:2] == ['tmux', 'send-keys'] and args[-1] in ('C-m', 'Enter'):
                state['enters'] += 1
            if args[:3] == ['tmux', 'paste-buffer', '-d'] and '-b' in args and 'enter-key' in args:
                state['enters'] += 1
            if args[:2] == ['tmux', 'capture-pane']:
                stdout = cleared if state['enters'] >= enters_needed else box_text
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout)
            return subprocess.CompletedProcess(args=args, returncode=0, stdout='')

        with patch('tmux_helper._agent_pane_target', return_value='%1'), \
                patch('tmux_helper.session_exists', return_value=True), \
                patch('tmux_helper.time.sleep', return_value=None) as mock_sleep, \
                patch('tmux_helper.subprocess.run', side_effect=fake_run):
            ok = tmux_helper.send_keys(
                'emp-0001',
                keys,
                send_enter=True,
                enter_via_key=enter_via_key,
            )
        return ok, commands, state, mock_sleep

    def test_lost_enter_is_detected_and_retried(self):
        # Input box keeps the text through the first two Enter events (native
        # + newline fallback of attempt 0); the third Enter lands.
        ok, commands, state, mock_sleep = self._run_send_keys(
            enters_needed=3,
            box_text='│ > fix the bug in parser │\n',
        )

        self.assertTrue(ok)
        self.assertGreaterEqual(state['enters'], 3)
        # Exponential backoff kicked in for the retry round.
        sleep_values = [call.args[0] for call in mock_sleep.call_args_list]
        self.assertIn(tmux_helper._ENTER_RETRY_BASE_DELAY, sleep_values)

    def test_wrapped_input_box_text_is_still_recognized(self):
        # The pending text wraps across bordered box lines; normalization must
        # still recognize it as "text stuck in the input box" and retry.
        wrapped_box = (
            '╭──────────────────╮\n'
            '│ > fix the bug in │\n'
            '│ parser           │\n'
            '╰──────────────────╯\n'
        )
        ok, commands, state, _ = self._run_send_keys(
            enters_needed=2,
            box_text=wrapped_box,
        )

        self.assertTrue(ok)
        self.assertGreaterEqual(state['enters'], 2)

    def test_busy_transition_counts_as_submission(self):
        # Marker not visible (e.g. paste placeholder); the agent starting to
        # work (spinner appears) is accepted as submission evidence.
        ok, commands, state, _ = self._run_send_keys(
            enters_needed=1,
            box_text='│ > [Pasted text #1 +40 lines] │\n',
            busy_text='✻ Thinking…\n│ > │\n',
        )

        self.assertTrue(ok)
        self.assertEqual(state['enters'], 1)

    def test_busy_agent_swallowing_all_enters_reports_failure(self):
        # The issue's incident shape: agent busy the whole time, every Enter
        # swallowed, text stays in the box. send_keys must report failure
        # after bounded retries instead of a false success.
        ok, commands, state, mock_sleep = self._run_send_keys(
            enters_needed=10**9,
            box_text='│ > fix the bug in parser │\n',
            busy_always=True,
        )

        self.assertFalse(ok)
        # 1 initial + 3 retries, each trying native Enter and newline paste.
        self.assertEqual(state['enters'], 8)
        sleep_values = [call.args[0] for call in mock_sleep.call_args_list]
        for expected_delay in (0.2, 0.4, 0.8):
            self.assertIn(expected_delay, sleep_values)

    def test_default_path_without_native_enter_also_retries(self):
        # enter_via_key=False (Claude Code CLI default): only newline paste is
        # used, and it must still verify + retry.
        ok, commands, state, _ = self._run_send_keys(
            enters_needed=2,
            box_text='│ > fix the bug in parser │\n',
            enter_via_key=False,
        )

        self.assertTrue(ok)
        self.assertEqual(state['enters'], 2)
        self.assertFalse(
            any(cmd[:2] == ['tmux', 'send-keys'] and cmd[-1] in ('C-m', 'Enter') for cmd in commands)
        )


if __name__ == '__main__':
    unittest.main()
