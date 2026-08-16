from __future__ import annotations

import sys
import tempfile
import unittest
import os
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
    get_system_prompt_mode,
    resolve_launcher_command,
)


class CursorProviderTests(unittest.TestCase):
    def test_cursor_launcher_maps_to_cursor_provider(self):
        self.assertEqual(get_provider_key('cursor'), 'cursor')
        self.assertEqual(get_provider_key('cursor-cli'), 'cursor')
        self.assertEqual(get_provider_key('/home/test/.local/bin/cursor-agent'), 'cursor')

    def test_cursor_provider_capabilities(self):
        self.assertEqual(get_system_prompt_mode('cursor'), 'tmux_paste')
        self.assertEqual(get_agents_md_mode('cursor'), 'cwd')
        self.assertEqual(get_mcp_config_mode('cursor'), 'unsupported')
        self.assertEqual(get_prompt_patterns('cursor'), [])

    def test_cursor_resolves_installed_cursor_agent_without_exposing_credentials(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            cursor_agent = home / '.local' / 'bin' / 'cursor-agent'
            cursor_agent.parent.mkdir(parents=True)
            cursor_agent.touch()
            with patch.dict(os.environ, {'HOME': str(home)}):
                resolved = resolve_launcher_command('cursor')
            self.assertEqual(resolved, str(cursor_agent))

        command = main.build_start_command('/tmp/work', 'cursor-agent', ['--model', 'gpt-5.6-sol-medium'])
        self.assertIn('cursor-agent', command)
        self.assertIn('--model', command)
        self.assertNotIn('CURSOR_API_KEY', command)

    def test_cursor_prefers_documented_cursor_bin_and_never_generic_agent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            cursor_agent = home / '.cursor' / 'bin' / 'cursor-agent'
            generic_agent = home / '.local' / 'bin' / 'agent'
            cursor_agent.parent.mkdir(parents=True)
            generic_agent.parent.mkdir(parents=True)
            cursor_agent.touch()
            generic_agent.touch()
            with patch.dict(os.environ, {'HOME': str(home)}):
                resolved = resolve_launcher_command('cursor')
            self.assertEqual(resolved, str(cursor_agent))

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            generic_agent = home / '.local' / 'bin' / 'agent'
            generic_agent.parent.mkdir(parents=True)
            generic_agent.touch()
            with patch.dict(os.environ, {'HOME': str(home)}):
                resolved = resolve_launcher_command('cursor')
            self.assertEqual(resolved, 'cursor-agent')

    def test_cursor_runtime_avoids_idle_false_positive(self):
        busy_patterns = get_runtime_config('cursor').get('busy_patterns', [])
        self.assertIn('Thinking', busy_patterns)
        self.assertIn('esc to interrupt', busy_patterns)


if __name__ == '__main__':
    unittest.main()
