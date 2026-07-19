from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import runtime_adapter  # noqa: E402
from commands.adapter import cmd_adapter  # noqa: E402


class _FakeDeps:
    def __init__(self, repo_root: Path):
        self._repo_root = repo_root
        self.start_calls = 0
        self.stop_calls = 0
        self.assign_calls = 0
        self.monitor_calls = 0

    def get_repo_root(self):
        return self._repo_root

    @staticmethod
    def check_tmux():
        return True

    @staticmethod
    def list_all_agents():
        return {
            'EMP_0001': {
                'file_id': 'EMP_0001',
                'name': 'dev',
                'enabled': True,
                'launcher': 'codex',
            },
            'EMP_0002': {
                'file_id': 'EMP_0002',
                'name': 'qa',
                'enabled': False,
                'launcher': 'codex',
            },
        }

    @staticmethod
    def resolve_agent(value):
        text = str(value).strip().lower()
        if text in {'dev', 'emp_0001', 'emp-0001'}:
            return {
                'file_id': 'EMP_0001',
                'name': 'dev',
                'enabled': True,
                'launcher': 'codex',
            }
        if text in {'qa', 'emp_0002', 'emp-0002'}:
            return {
                'file_id': 'EMP_0002',
                'name': 'qa',
                'enabled': False,
                'launcher': 'codex',
            }
        return None

    @staticmethod
    def get_agent_id(agent_config):
        return str(agent_config.get('file_id') or '').lower().replace('_', '-')

    @staticmethod
    def session_exists(agent_id):
        return str(agent_id) == 'emp-0001'

    @staticmethod
    def get_session_info(agent_id):
        if str(agent_id) == 'emp-0001':
            return {'session': 'agent-emp-0001'}
        return None

    @staticmethod
    def get_agent_runtime_state(agent_id, launcher=''):
        if str(agent_id) == 'emp-0001':
            return {'state': 'idle', 'reason': 'ready', 'elapsed_seconds': 12}
        return {'state': 'busy', 'reason': 'busy_pattern:Thinking...', 'elapsed_seconds': 45}

    def cmd_start(self, args):
        self.start_calls += 1
        print(f'start:{args.agent}:{args.restore}:{args.tmux_layout}')
        return 0

    def cmd_stop(self, args):
        self.stop_calls += 1
        print(f'stop:{args.agent}')
        return 0

    def cmd_assign(self, args):
        self.assign_calls += 1
        print(f'assign:{args.agent}:{args.task_file}')
        return 0

    def cmd_monitor(self, args):
        self.monitor_calls += 1
        print(f'monitor:{args.agent}:{args.follow}:{args.lines}')
        print('line-1')
        print('line-2')
        return 0


class RuntimeAdapterTests(unittest.TestCase):
    def _fixture_path(self, name: str) -> Path:
        return Path(__file__).resolve().parent / 'fixtures' / 'runtime_adapter' / name

    def test_parse_request_rejects_malformed_json(self):
        with self.assertRaises(ValueError):
            runtime_adapter.parse_request('{not json}')

    def test_availability_fixture_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix='agent-manager-runtime-adapter-') as tmpdir:
            deps = _FakeDeps(Path(tmpdir))
            request = json.loads(self._fixture_path('availability-request.json').read_text(encoding='utf-8'))
            expected = json.loads(self._fixture_path('availability-response.json').read_text(encoding='utf-8'))

            response = runtime_adapter.handle_request(request, deps=deps)

            self.assertTrue(response['ok'])
            self.assertEqual(response['schema_version'], expected['schema_version'])
            self.assertEqual(response['adapter'], expected['adapter'])
            self.assertEqual(response['command_id'], expected['command_id'])
            self.assertEqual(response['operation'], expected['operation'])
            self.assertEqual(response['result']['availability'], expected['result']['availability'])
            self.assertEqual(response['result']['runtime_state'], expected['result']['runtime_state'])
            self.assertEqual(response['result']['freshness_seconds'], expected['result']['freshness_seconds'])

    def test_availability_normalizes_runtime_state_and_freshness(self):
        with tempfile.TemporaryDirectory(prefix='agent-manager-runtime-adapter-') as tmpdir:
            repo_root = Path(tmpdir)
            deps = _FakeDeps(repo_root)
            heartbeat_dir = repo_root / '.claude' / 'state' / 'agent-manager' / 'heartbeat-audit'
            heartbeat_dir.mkdir(parents=True, exist_ok=True)
            observed = datetime.now(timezone.utc)
            heartbeat_at = observed - timedelta(seconds=93)
            (heartbeat_dir / 'emp-0001.jsonl').write_text(
                json.dumps({'timestamp': heartbeat_at.isoformat().replace('+00:00', 'Z'), 'hb_id': 'hb-1'}) + '\n',
                encoding='utf-8',
            )

            response = runtime_adapter.handle_request(
                {
                    'schema_version': '1',
                    'command_id': 'cmd-availability-1',
                    'operation': 'availability',
                    'agent': 'dev',
                },
                deps=deps,
            )

            self.assertTrue(response['ok'])
            result = response['result']
            self.assertEqual(result['state'], 'available')
            self.assertEqual(result['runtime_state'], 'idle')
            self.assertEqual(result['runtime_reason'], 'ready')
            self.assertEqual(result['session_running'], True)
            self.assertIsInstance(result['freshness_seconds'], int)
            self.assertGreaterEqual(result['freshness_seconds'], 0)
            self.assertLess(result['freshness_seconds'], 180)

    def test_duplicate_command_id_does_not_execute_twice(self):
        with tempfile.TemporaryDirectory(prefix='agent-manager-runtime-adapter-') as tmpdir:
            repo_root = Path(tmpdir)
            deps = _FakeDeps(repo_root)
            request = {
                'schema_version': '1',
                'command_id': 'cmd-start-1',
                'operation': 'start',
                'agent': 'dev',
                'params': {'restore': True, 'tmux_layout': 'sessions'},
            }

            first = runtime_adapter.handle_request(request, deps=deps)
            second = runtime_adapter.handle_request(request, deps=deps)

            self.assertTrue(first['ok'])
            self.assertEqual(deps.start_calls, 1)
            self.assertFalse(first['duplicate'])
            self.assertTrue(second['duplicate'])
            self.assertEqual(deps.start_calls, 1)
            self.assertEqual(second['result']['exit_code'], 0)

    def test_assign_and_logs_operations_are_supported(self):
        with tempfile.TemporaryDirectory(prefix='agent-manager-runtime-adapter-') as tmpdir:
            deps = _FakeDeps(Path(tmpdir))
            assign = runtime_adapter.handle_request(
                {
                    'schema_version': '1',
                    'command_id': 'cmd-assign-1',
                    'operation': 'assign',
                    'agent': 'dev',
                    'params': {'task': 'do the thing'},
                },
                deps=deps,
            )
            logs = runtime_adapter.handle_request(
                {
                    'schema_version': '1',
                    'command_id': 'cmd-logs-1',
                    'operation': 'logs',
                    'agent': 'dev',
                    'params': {'lines': 2},
                },
                deps=deps,
            )

            self.assertTrue(assign['ok'])
            self.assertEqual(deps.assign_calls, 1)
            self.assertTrue(logs['ok'])
            self.assertEqual(deps.monitor_calls, 1)
            self.assertIn('line-2', logs['result']['stdout'])

    def test_inventory_and_status_return_canonical_results(self):
        with tempfile.TemporaryDirectory(prefix='agent-manager-runtime-adapter-') as tmpdir:
            deps = _FakeDeps(Path(tmpdir))
            inventory = runtime_adapter.handle_request(
                {
                    'schema_version': '1',
                    'command_id': 'cmd-inventory-1',
                    'operation': 'inventory',
                },
                deps=deps,
            )
            status = runtime_adapter.handle_request(
                {
                    'schema_version': '1',
                    'command_id': 'cmd-status-1',
                    'operation': 'status',
                    'agent': 'dev',
                },
                deps=deps,
            )

            self.assertTrue(inventory['ok'])
            self.assertEqual(inventory['result']['count'], 2)
            self.assertEqual(inventory['result']['agents'][0]['availability'], 'available')
            self.assertTrue(status['ok'])
            self.assertEqual(status['result']['availability'], 'available')
            self.assertEqual(status['result']['session_name'], 'agent-emp-0001')

    def test_adapter_command_reads_request_file_and_outputs_json(self):
        with tempfile.TemporaryDirectory(prefix='agent-manager-runtime-adapter-') as tmpdir:
            repo_root = Path(tmpdir)
            deps = _FakeDeps(repo_root)
            request = {
                'schema_version': '1',
                'command_id': 'cmd-health-1',
                'operation': 'health',
            }
            request_file = repo_root / 'request.json'
            request_file.write_text(json.dumps(request), encoding='utf-8')

            out = io.StringIO()
            with redirect_stdout(out):
                rc = cmd_adapter(type('Args', (), {'request_file': str(request_file)})(), deps=deps)

            self.assertEqual(rc, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload['ok'])
            self.assertEqual(payload['operation'], 'health')
            self.assertIn('tmux_available', payload['result'])

    def test_start_fixture_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix='agent-manager-runtime-adapter-') as tmpdir:
            deps = _FakeDeps(Path(tmpdir))
            request = json.loads(self._fixture_path('start-request.json').read_text(encoding='utf-8'))
            expected = json.loads(self._fixture_path('start-response.json').read_text(encoding='utf-8'))

            response = runtime_adapter.handle_request(request, deps=deps)

            self.assertTrue(response['ok'])
            self.assertEqual(response['schema_version'], expected['schema_version'])
            self.assertEqual(response['adapter'], expected['adapter'])
            self.assertEqual(response['command_id'], expected['command_id'])
            self.assertEqual(response['operation'], expected['operation'])
            self.assertEqual(response['result']['exit_code'], expected['result']['exit_code'])
            self.assertEqual(response['result']['stdout'], expected['result']['stdout'])
            self.assertEqual(response['result']['stderr'], expected['result']['stderr'])

    def test_adapter_command_rejects_follow_mode(self):
        with tempfile.TemporaryDirectory(prefix='agent-manager-runtime-adapter-') as tmpdir:
            deps = _FakeDeps(Path(tmpdir))
            response = runtime_adapter.handle_request(
                {
                    'schema_version': '1',
                    'command_id': 'cmd-monitor-1',
                    'operation': 'monitor',
                    'agent': 'dev',
                    'params': {'follow': True},
                },
                deps=deps,
            )

            self.assertFalse(response['ok'])
            self.assertEqual(response['error']['code'], 'unsupported_operation')


if __name__ == '__main__':
    unittest.main()
