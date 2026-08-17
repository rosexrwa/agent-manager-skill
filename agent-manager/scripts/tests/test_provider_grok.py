from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(SCRIPTS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))

import main  # noqa: E402
import tmux_helper  # noqa: E402
from providers import (  # noqa: E402
    get_agents_md_mode,
    get_mcp_config_mode,
    get_prompt_patterns,
    get_provider_key,
    get_runtime_config,
    get_session_restore_flag,
    get_session_restore_mode,
    get_system_prompt_flag,
    get_system_prompt_mode,
    launcher_binary_exists,
    missing_launcher_help,
    resolve_launcher_command,
)
from runtime_state import detect_first_pattern, evaluate_runtime_state  # noqa: E402


SECRET = 'xai-test-secret-should-never-leak'
SESSION_ID = '11111111-2222-4333-8444-555555555555'

# Live Grok Build 1.0.4 pane excerpts from isolated tmux capture.
LIVE_AUTH_PANE = """\
                              Clipboard may be unreachable.
                           Run /doctor for details and fixes.

                   New worktree                                 ctrl+w
                   Resume session                               ctrl+s
                   Changelog
                   Quit                                         ctrl+q

                   Grok 4.6 is here!
                   Select 'Grok 4.6' under /model.

  ╭───────────────────────────────────────────────────────────────────────────────────╮
  │ ❯                                                                                 │
  ╰─────────────────────────────────────────────── Grok 4.6 (xhigh) · always-approve ─╯

                                                                      Grok Build  1.0.4
"""

LIVE_UNAUTH_PANE = """\
                      Approve in your browser to finish signing in.

                                        AE48-P7CG

                         Make sure your browser shows this code.

                                 Waiting for approval...

                                      ctrl+q  quit
"""


def _wait_for_prompt_would_accept(output: str, pattern: str) -> bool:
    """Replica of tmux_helper.wait_for_prompt standard-line rule."""
    if pattern not in output:
        return False
    for line in output.split('\n'):
        stripped = line.strip()
        if stripped == pattern or (stripped.startswith(pattern) and len(stripped) <= 3):
            return True
    return False


def _grok_agent_config(working_dir: str) -> dict:
    return {
        'name': 'grok-dev',
        'file_id': 'EMP_GROK',
        'launcher': 'grok',
        'launcher_args': ['--model', 'grok-4', '--yolo'],
        'enabled': True,
        'working_directory': working_dir,
    }


class GrokProviderTests(unittest.TestCase):
    def test_grok_launcher_maps_to_grok_provider(self):
        self.assertEqual(get_provider_key('grok'), 'grok')
        self.assertEqual(get_provider_key('grok-cli'), 'grok')
        self.assertEqual(get_provider_key('grok-build'), 'grok')
        self.assertEqual(get_provider_key('/home/test/.local/bin/grok'), 'grok')
        self.assertEqual(get_provider_key('/opt/homebrew/bin/xai-grok-pager'), 'grok')

    def test_cursor_still_wins_when_model_name_mentions_grok(self):
        self.assertEqual(get_provider_key('cursor-agent'), 'cursor')
        self.assertEqual(get_provider_key('/home/test/.local/bin/cursor-agent'), 'cursor')
        self.assertEqual(get_provider_key('cursor-grok-4.6-xhigh'), 'cursor')
        self.assertNotEqual(get_provider_key('cursor-grok-4.6-xhigh'), 'grok')

    def test_grok_provider_capabilities(self):
        self.assertEqual(get_system_prompt_mode('grok'), 'cli_append')
        self.assertEqual(get_system_prompt_flag('grok'), '--append-system-prompt')
        self.assertEqual(get_agents_md_mode('grok'), 'cwd')
        self.assertEqual(get_mcp_config_mode('grok'), 'unsupported')
        self.assertEqual(get_session_restore_mode('grok'), 'cli_optional_arg')
        self.assertEqual(get_session_restore_flag('grok'), '--resume')
        self.assertEqual(get_prompt_patterns('grok'), [])

    def test_grok_busy_patterns_avoid_idle_false_positives(self):
        busy_patterns = get_runtime_config('grok').get('busy_patterns', [])
        self.assertNotIn('Working', busy_patterns)
        self.assertIn('esc to interrupt', busy_patterns)
        self.assertIn('Thinking…', busy_patterns)

    def test_grok_blocked_patterns_match_live_login_ui(self):
        blocked_patterns = get_runtime_config('grok').get('blocked_patterns', [])
        self.assertIn('grok login', blocked_patterns)
        self.assertIn('Paste your token here', blocked_patterns)
        self.assertIn('Not signed in', blocked_patterns)
        self.assertIn('You are not authenticated', blocked_patterns)
        self.assertIn('Waiting for approval', blocked_patterns)
        self.assertIn('Approve in your browser', blocked_patterns)

    def test_grok_resolves_installed_binary_without_exposing_credentials(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            grok_bin = home / '.local' / 'bin' / 'grok'
            grok_bin.parent.mkdir(parents=True)
            grok_bin.touch()
            with patch.dict(os.environ, {'HOME': str(home), 'XAI_API_KEY': SECRET}):
                resolved = resolve_launcher_command('grok')
                help_text = missing_launcher_help('grok')
            self.assertEqual(resolved, str(grok_bin))
            self.assertNotIn(SECRET, resolved)
            self.assertNotIn(SECRET, help_text)

    def test_grok_prefers_local_bin_over_generic_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            grok_bin = home / '.grok' / 'bin' / 'grok'
            grok_bin.parent.mkdir(parents=True)
            grok_bin.touch()
            with patch.dict(os.environ, {'HOME': str(home)}):
                resolved = resolve_launcher_command('grok-cli')
            self.assertEqual(resolved, str(grok_bin))

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            original_exists = Path.exists

            def exists_under_fake_home(self):
                try:
                    return original_exists(self) and str(self).startswith(str(home))
                except Exception:
                    return False

            with patch.dict(os.environ, {'HOME': str(home)}), \
                 patch.object(Path, 'exists', exists_under_fake_home):
                resolved = resolve_launcher_command('grok')
            self.assertEqual(resolved, 'grok')

    def test_grok_start_command_is_deterministic_and_secret_free(self):
        with patch.dict(os.environ, {'XAI_API_KEY': SECRET}):
            command = main.build_start_command(
                '/tmp/work',
                'grok',
                ['--model', 'grok-4', '--yolo'],
            )
        self.assertIn("cd /tmp/work", command)
        self.assertIn("grok", command)
        self.assertIn("--model", command)
        self.assertIn("grok-4", command)
        self.assertIn("--yolo", command)
        self.assertNotIn(SECRET, command)
        self.assertNotIn('XAI_API_KEY', command)

    def test_grok_restore_args_use_resume_flag(self):
        args = main._apply_session_restore_args(
            provider_key='grok',
            launcher='grok',
            launcher_args=['--model', 'grok-4', '--yolo'],
            restore_flag='--resume',
            session_id='11111111-2222-4333-8444-555555555555',
        )
        self.assertEqual(
            args,
            ['--resume', '11111111-2222-4333-8444-555555555555', '--model', 'grok-4', '--yolo'],
        )

    def test_launcher_binary_exists_for_path_and_missing_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            binary = Path(tmpdir) / 'grok'
            binary.touch()
            self.assertTrue(launcher_binary_exists(str(binary)))
        self.assertFalse(launcher_binary_exists(''))
        with patch('shutil.which', return_value=None):
            self.assertFalse(launcher_binary_exists('grok-not-installed-xyz'))

    def test_missing_grok_help_never_includes_secrets(self):
        with patch.dict(os.environ, {'XAI_API_KEY': SECRET}):
            help_text = missing_launcher_help('grok')
        self.assertIn('Grok CLI not found', help_text)
        self.assertIn('grok login', help_text)
        self.assertNotIn(SECRET, help_text)

    def test_start_fails_clearly_when_grok_cli_missing(self):
        args = argparse.Namespace(
            agent='EMP_GROK',
            working_dir='/tmp/grok-work',
            restore=True,
            tmux_layout='sessions',
        )
        agent_config = {
            'name': 'grok-dev',
            'file_id': 'EMP_GROK',
            'launcher': 'grok',
            'launcher_args': ['--model', 'grok-4', '--yolo'],
            'enabled': True,
            'working_directory': '/tmp/grok-work',
        }
        with patch.dict(os.environ, {'XAI_API_KEY': SECRET}), \
             patch('main.check_tmux', return_value=True), \
             patch('main.resolve_agent', return_value=agent_config), \
             patch('main.get_agent_id', return_value='emp-grok'), \
             patch('main.session_exists', return_value=False), \
             patch('main.get_repo_root', return_value=Path('/tmp')), \
             patch('main.resolve_launcher_command', return_value='grok'), \
             patch('main.get_provider_key', return_value='grok'), \
             patch('main.launcher_binary_exists', return_value=False), \
             patch('main.start_session') as start_session:
            output = io.StringIO()
            with redirect_stdout(output):
                rc = main.cmd_start(args)

        text = output.getvalue()
        self.assertEqual(rc, 1)
        start_session.assert_not_called()
        self.assertIn('Grok CLI not found', text)
        self.assertIn('grok login', text)
        self.assertNotIn(SECRET, text)

    def test_live_auth_pane_bare_prompt_matcher_rejects_boxed_prompt(self):
        self.assertIn('❯', LIVE_AUTH_PANE)
        self.assertFalse(_wait_for_prompt_would_accept(LIVE_AUTH_PANE, '❯'))
        self.assertEqual(get_prompt_patterns('grok'), [])

    def test_wait_for_prompt_treats_empty_patterns_as_ready(self):
        with patch.object(tmux_helper, '_agent_pane_target', return_value='agent-emp-grok:0.0'), \
             patch.object(tmux_helper.time, 'sleep'):
            self.assertTrue(tmux_helper.wait_for_prompt('emp-grok', 'grok', timeout=30))

    def test_agents_md_start_succeeds_with_process_readiness(self):
        args = argparse.Namespace(
            agent='EMP_GROK',
            working_dir=None,
            restore=True,
            tmux_layout='sessions',
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            work = Path(tmpdir) / 'work'
            work.mkdir()
            (work / 'AGENTS.md').write_text('# agents\n', encoding='utf-8')
            agent_config = _grok_agent_config(str(work))
            session_calls = {'n': 0}
            started = []

            def session_exists(_agent_id):
                session_calls['n'] += 1
                return session_calls['n'] > 1

            def start_session(agent_id, command, layout='sessions'):
                started.append(command)
                return True

            with patch('main.check_tmux', return_value=True), \
                 patch('main.resolve_agent', return_value=agent_config), \
                 patch('main.get_agent_id', return_value='emp-grok'), \
                 patch('main.session_exists', side_effect=session_exists), \
                 patch('main.get_repo_root', return_value=Path(tmpdir)), \
                 patch('main.resolve_launcher_command', return_value='grok'), \
                 patch('main.launcher_binary_exists', return_value=True), \
                 patch('main.start_session', side_effect=start_session), \
                 patch('main.get_session_info', return_value={'session': 'agent-emp-grok', 'mode': 'sessions'}), \
                 patch('main.wait_for_prompt', return_value=True), \
                 patch('main.wait_for_agent_ready', return_value=True), \
                 patch('main._load_provider_session_id', return_value=''), \
                 patch('main._find_new_provider_session_id_with_retry', return_value='') as find_new, \
                 patch('main._save_provider_session_id') as save_session:
                output = io.StringIO()
                with redirect_stdout(output):
                    rc = main.cmd_start(args)

            text = output.getvalue()
            self.assertEqual(rc, 0, text)
            self.assertTrue(started)
            self.assertNotIn('Timeout waiting for CLI prompt', text)
            self.assertNotIn('--resume', started[0])
            self.assertEqual(get_prompt_patterns('grok'), [])
            find_new.assert_called()
            save_session.assert_not_called()

    def test_live_unauth_device_code_is_blocked(self):
        cfg = get_runtime_config('grok')
        blocked = detect_first_pattern(LIVE_UNAUTH_PANE, cfg.get('blocked_patterns', []))
        state = evaluate_runtime_state(
            output=LIVE_UNAUTH_PANE,
            runtime_config=cfg,
            session_running=True,
            output_readable=True,
        )
        self.assertIsNotNone(blocked)
        self.assertIn(blocked, {'Waiting for approval', 'Approve in your browser', 'Approve in your browser to finish signing in'})
        self.assertEqual(state.get('state'), 'blocked')
        self.assertNotIn('Paste your token here', LIVE_UNAUTH_PANE)
        self.assertNotIn('grok login', LIVE_UNAUTH_PANE)

    def test_stored_grok_session_is_resumed(self):
        args = argparse.Namespace(
            agent='EMP_GROK',
            working_dir=None,
            restore=True,
            tmux_layout='sessions',
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            work = Path(tmpdir) / 'work'
            work.mkdir()
            sessions_root = Path(tmpdir) / 'sessions'
            encoded = quote(str(work.resolve()), safe='')
            (sessions_root / encoded / SESSION_ID).mkdir(parents=True)
            agent_config = _grok_agent_config(str(work))
            session_calls = {'n': 0}
            started = []

            def session_exists(_agent_id):
                session_calls['n'] += 1
                return session_calls['n'] > 1

            def start_session(agent_id, command, layout='sessions'):
                started.append(command)
                return True

            with patch('main.check_tmux', return_value=True), \
                 patch('main.resolve_agent', return_value=agent_config), \
                 patch('main.get_agent_id', return_value='emp-grok'), \
                 patch('main.session_exists', side_effect=session_exists), \
                 patch('main.get_repo_root', return_value=Path(tmpdir)), \
                 patch('main.resolve_launcher_command', return_value='grok'), \
                 patch('main.launcher_binary_exists', return_value=True), \
                 patch('main.start_session', side_effect=start_session), \
                 patch('main.get_session_info', return_value={'session': 'agent-emp-grok', 'mode': 'sessions'}), \
                 patch('main.wait_for_prompt', return_value=True), \
                 patch('main.wait_for_agent_ready', return_value=True), \
                 patch('main._grok_sessions_root', return_value=sessions_root), \
                 patch('main._load_provider_session_id', return_value=SESSION_ID), \
                 patch('main._save_provider_session_id') as save_session:
                output = io.StringIO()
                with redirect_stdout(output):
                    rc = main.cmd_start(args)

            text = output.getvalue()
            self.assertEqual(rc, 0, text)
            self.assertTrue(started)
            self.assertIn('--resume', started[0])
            self.assertIn(SESSION_ID, started[0])
            save_session.assert_called()

    def test_grok_session_dir_snapshot_find_and_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = str(Path(tmpdir) / 'work')
            Path(cwd).mkdir()
            sessions_root = Path(tmpdir) / 'sessions'
            encoded = quote(str(Path(cwd).resolve()), safe='')
            old_id = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
            new_id = '11111111-2222-4333-8444-555555555555'
            other_cwd = sessions_root / quote('/tmp/other-work', safe='') / new_id
            other_cwd.mkdir(parents=True)
            old_dir = sessions_root / encoded / old_id
            new_dir = sessions_root / encoded / new_id
            old_dir.mkdir(parents=True)
            new_dir.mkdir(parents=True)
            (sessions_root / encoded / 'prompt_history.jsonl').write_text('', encoding='utf-8')
            os.utime(old_dir, (1, 1))
            os.utime(new_dir, (2, 2))

            with patch('main._grok_sessions_root', return_value=sessions_root):
                self.assertEqual(main._snapshot_grok_sessions(cwd), {old_id, new_id})
                self.assertTrue(main._grok_session_exists(cwd, old_id))
                self.assertFalse(main._grok_session_exists(cwd, 'sid-other'))
                self.assertFalse(main._grok_session_exists('/tmp/other-work', old_id))
                self.assertEqual(
                    main._find_new_grok_session_id(cwd, before_session_ids={old_id}),
                    new_id,
                )
                self.assertEqual(
                    main._find_new_grok_session_id(cwd, before_session_ids={old_id, new_id}),
                    '',
                )
                self.assertTrue(main._provider_session_exists('grok', cwd, new_id))
                self.assertEqual(
                    main._find_new_provider_session_id_with_retry(
                        'grok',
                        cwd,
                        before_paths={old_id},
                        timeout_s=0,
                    ),
                    new_id,
                )


if __name__ == '__main__':
    unittest.main()
