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


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(SCRIPTS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))

import main  # noqa: E402
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


SECRET = 'xai-test-secret-should-never-leak'


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
        self.assertEqual(get_prompt_patterns('grok'), ['❯'])

    def test_grok_busy_patterns_avoid_idle_false_positives(self):
        busy_patterns = get_runtime_config('grok').get('busy_patterns', [])
        self.assertNotIn('Working', busy_patterns)
        self.assertIn('esc to interrupt', busy_patterns)
        self.assertIn('Thinking…', busy_patterns)

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


if __name__ == '__main__':
    unittest.main()
