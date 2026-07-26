from __future__ import annotations
import json
import sys
import tempfile
import unittest
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
    get_system_prompt_mode,
)


class KimiCodeProviderTests(unittest.TestCase):
    def test_kimi_launcher_maps_to_kimi_code_provider(self):
        self.assertEqual(get_provider_key('kimi'), 'kimi-code')
        self.assertEqual(get_provider_key('kimi-code'), 'kimi-code')
        self.assertEqual(get_provider_key('/Users/test/.kimi-code/bin/kimi'), 'kimi-code')

    def test_kimi_code_provider_capabilities(self):
        self.assertEqual(get_session_restore_mode('kimi'), 'cli_optional_arg')
        self.assertEqual(get_session_restore_flag('kimi'), '--session')
        self.assertEqual(get_system_prompt_mode('kimi'), 'tmux_paste')
        self.assertEqual(get_agents_md_mode('kimi'), 'cwd')
        self.assertEqual(get_mcp_config_mode('kimi'), 'unsupported')
        self.assertEqual(get_prompt_patterns('kimi'), [])

    def test_kimi_code_busy_patterns_avoid_idle_status_false_positives(self):
        busy_patterns = get_runtime_config('kimi').get('busy_patterns', [])
        self.assertNotIn('Thinking', busy_patterns)
        self.assertNotIn('Running', busy_patterns)
        self.assertIn('esc to interrupt', busy_patterns)

    def test_kimi_code_restore_args_use_long_session_flag(self):
        args = main._apply_session_restore_args(
            provider_key='kimi-code',
            launcher='kimi',
            launcher_args=['--auto'],
            restore_flag='--session',
            session_id='193cf465-0a7b-4f8e-b9f9-915927c90746',
        )
        self.assertEqual(args, ['--session', '193cf465-0a7b-4f8e-b9f9-915927c90746', '--auto'])

    def test_kimi_code_session_index_snapshot_find_and_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / 'session_index.jsonl'
            cwd = '/Users/test/work'
            entries = [
                {'sessionId': 'sid-old', 'workDir': cwd, 'sessionDir': '/tmp/sid-old'},
                {'sessionId': 'sid-other', 'workDir': '/Users/test/other', 'sessionDir': '/tmp/sid-other'},
                {'sessionId': 'sid-new', 'workDir': cwd, 'sessionDir': '/tmp/sid-new'},
            ]
            index_path.write_text(''.join(json.dumps(entry) + '\n' for entry in entries), encoding='utf-8')

            with patch('main._kimi_code_session_index_path', return_value=index_path):
                self.assertEqual(main._snapshot_kimi_code_sessions(cwd), {'sid-old', 'sid-new'})
                self.assertTrue(main._kimi_code_session_exists(cwd, 'sid-old'))
                self.assertFalse(main._kimi_code_session_exists(cwd, 'sid-other'))
                self.assertEqual(
                    main._find_new_kimi_code_session_id(cwd, before_session_ids={'sid-old'}),
                    'sid-new',
                )
                self.assertEqual(
                    main._find_new_kimi_code_session_id(cwd, before_session_ids={'sid-old', 'sid-new'}),
                    '',
                )


if __name__ == '__main__':
    unittest.main()
