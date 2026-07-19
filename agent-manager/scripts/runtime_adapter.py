from __future__ import annotations

import contextlib
import io
import json
import os
import signal
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

SCHEMA_VERSION = '1'
ADAPTER_NAME = 'agent-manager-runtime'
SUPPORTED_OPERATIONS = (
    'inventory',
    'status',
    'start',
    'stop',
    'assign',
    'monitor',
    'logs',
    'health',
    'availability',
)
AVAILABLE_STATES = ('available', 'busy', 'unavailable', 'unknown')
ERROR_CODES = {
    'cancelled',
    'duplicate_command_id',
    'internal_error',
    'malformed_input',
    'missing_agent',
    'missing_command_id',
    'operation_failed',
    'timeout',
    'unsupported_operation',
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _bounded_text(text: str, *, limit: int = 5000) -> str:
    value = str(text or '')
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 20)] + '\n...<truncated>...'


def _parse_iso8601_utc(value: str) -> Optional[datetime]:
    text = str(value or '').strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _runtime_state_dir(repo_root: Path) -> Path:
    return repo_root / '.claude' / 'state' / 'agent-manager' / 'runtime-adapter'


def _runtime_ledger_path(repo_root: Path) -> Path:
    return _runtime_state_dir(repo_root) / 'command-ledger.jsonl'


def _heartbeat_audit_path(repo_root: Path, agent_id: str) -> Path:
    return repo_root / '.claude' / 'state' / 'agent-manager' / 'heartbeat-audit' / f'{agent_id}.jsonl'


def _load_latest_jsonl_record(path: Path) -> Optional[dict]:
    if not path.exists() or not path.is_file():
        return None
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except Exception:
        return None
    for raw in reversed(lines):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _load_latest_heartbeat_event(repo_root: Path, agent_id: str) -> Optional[dict]:
    return _load_latest_jsonl_record(_heartbeat_audit_path(repo_root, agent_id))


def _load_ledger(repo_root: Path) -> list[dict]:
    path = _runtime_ledger_path(repo_root)
    if not path.exists() or not path.is_file():
        return []
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except Exception:
        return []

    records: list[dict] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _lookup_ledger_response(repo_root: Path, command_id: str) -> Optional[dict]:
    for record in reversed(_load_ledger(repo_root)):
        if str(record.get('command_id') or '') == str(command_id):
            response = record.get('response')
            if isinstance(response, dict):
                return response
    return None


def _append_ledger_response(repo_root: Path, *, command_id: str, idempotency_key: str, operation: str, response: dict) -> None:
    path = _runtime_ledger_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        'command_id': str(command_id),
        'idempotency_key': str(idempotency_key or ''),
        'operation': str(operation),
        'recorded_at': _isoformat_utc(_utc_now()),
        'response': response,
    }
    with path.open('a', encoding='utf-8') as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + '\n')


def _error(code: str, message: str, *, detail: Optional[str] = None) -> dict:
    if code not in ERROR_CODES:
        code = 'internal_error'
    payload = {
        'code': code,
        'message': str(message),
    }
    if detail:
        payload['detail'] = str(detail)
    return payload


def _request_error(command_id: str, operation: str, code: str, message: str, *, detail: Optional[str] = None) -> dict:
    now = _isoformat_utc(_utc_now())
    return {
        'schema_version': SCHEMA_VERSION,
        'adapter': ADAPTER_NAME,
        'command_id': str(command_id or ''),
        'operation': str(operation or ''),
        'duplicate': False,
        'ok': False,
        'observed_at': now,
        'result': None,
        'error': _error(code, message, detail=detail),
    }


def _parse_timeout_seconds(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed <= 0:
        return 0.0
    return parsed


def _normalize_operation(value: Any) -> str:
    op = str(value or '').strip().lower()
    if op == 'read':
        return 'status'
    if op == 'ls':
        return 'inventory'
    return op


def parse_request(raw: Any) -> dict:
    if isinstance(raw, dict):
        payload = raw
    else:
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        if not isinstance(raw, str):
            raise ValueError('request must be a JSON object or JSON text')
        try:
            payload = json.loads(raw)
        except Exception as exc:
            raise ValueError(f'malformed JSON: {exc}') from exc

    if not isinstance(payload, dict):
        raise ValueError('request must be a JSON object')

    schema_version = str(payload.get('schema_version') or SCHEMA_VERSION).strip() or SCHEMA_VERSION
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f'unsupported schema_version: {schema_version}')

    command_id = str(payload.get('command_id') or '').strip()
    if not command_id:
        raise ValueError('command_id is required')

    operation = _normalize_operation(payload.get('operation'))
    if not operation:
        raise ValueError('operation is required')

    return {
        'schema_version': schema_version,
        'command_id': command_id,
        'idempotency_key': str(payload.get('idempotency_key') or '').strip(),
        'operation': operation,
        'agent': str(payload.get('agent') or payload.get('agent_id') or payload.get('agent_name') or '').strip(),
        'timeout_seconds': _parse_timeout_seconds(payload.get('timeout_seconds')),
        'cancel': bool(payload.get('cancel', False)),
        'params': payload.get('params') if isinstance(payload.get('params'), dict) else {},
        'raw': payload,
    }


def _resolve_agent_context(deps: Any, agent_value: str) -> tuple[Optional[dict], Optional[str], Optional[str], Optional[str]]:
    resolve_agent = getattr(deps, 'resolve_agent', None)
    get_agent_id = getattr(deps, 'get_agent_id', None)
    if not callable(resolve_agent) or not callable(get_agent_id):
        return None, None, None, 'agent lookup helpers unavailable'

    agent_config = resolve_agent(agent_value)
    if not agent_config:
        return None, None, None, f'agent not found: {agent_value}'

    agent_id = get_agent_id(agent_config)
    agent_name = str(agent_config.get('name') or agent_value or agent_id)
    return agent_config, str(agent_id), agent_name, None


def _heartbeat_freshness_seconds(repo_root: Path, agent_id: str, *, observed_at: datetime) -> Optional[int]:
    event = _load_latest_heartbeat_event(repo_root, agent_id)
    if not event:
        return None
    timestamp = _parse_iso8601_utc(str(event.get('timestamp') or ''))
    if not timestamp:
        return None
    delta = observed_at - timestamp
    return max(0, int(delta.total_seconds()))


def _build_runtime_snapshot(deps: Any, *, agent_id: str, agent_name: str) -> dict:
    get_agent_runtime_state = getattr(deps, 'get_agent_runtime_state', None)
    session_exists = getattr(deps, 'session_exists', None)
    get_session_info = getattr(deps, 'get_session_info', None)
    get_repo_root = getattr(deps, 'get_repo_root', None)

    runtime: dict[str, Any]
    if callable(get_agent_runtime_state):
        try:
            runtime = get_agent_runtime_state(agent_id)
        except TypeError:
            launcher = ''
            if hasattr(deps, 'resolve_agent') and callable(getattr(deps, 'resolve_agent')):
                try:
                    agent_config = deps.resolve_agent(agent_name)
                    launcher = str(agent_config.get('launcher', '') or '')
                except Exception:
                    launcher = ''
            runtime = get_agent_runtime_state(agent_id, launcher=launcher)
        except Exception as exc:
            runtime = {'state': 'unknown', 'reason': f'runtime_error:{exc.__class__.__name__}'}
    else:
        runtime = {'state': 'unknown', 'reason': 'runtime_probe_unavailable'}

    running = bool(session_exists(agent_id)) if callable(session_exists) else False
    session_info = get_session_info(agent_id) if callable(get_session_info) and running else None
    session_name = ''
    if isinstance(session_info, dict):
        session_name = str(session_info.get('session') or '')
    if not session_name:
        session_name = 'main' if agent_id == 'main' else f'agent-{agent_id}'

    observed_at = _utc_now()
    repo_root = get_repo_root() if callable(get_repo_root) else None
    freshness_seconds = None
    if isinstance(repo_root, Path):
        freshness_seconds = _heartbeat_freshness_seconds(repo_root, agent_id, observed_at=observed_at)

    state = str(runtime.get('state') or 'unknown').strip().lower()
    reason = str(runtime.get('reason') or '').strip()
    elapsed_seconds = runtime.get('elapsed_seconds')

    availability_state = 'unknown'
    if not running:
        availability_state = 'unavailable'
        if not reason:
            reason = 'session_not_running'
    elif state == 'idle':
        availability_state = 'available'
    elif state == 'busy':
        availability_state = 'busy'
    elif state in {'blocked', 'stuck', 'error', 'interrupted'}:
        availability_state = 'unavailable'
    elif state == 'unknown':
        availability_state = 'unknown'
    else:
        availability_state = 'unknown'

    if availability_state == 'unknown' and not reason:
        reason = 'runtime_unknown'

    result = {
        'agent_id': agent_id,
        'agent_name': agent_name,
        'session_name': session_name,
        'runtime_state': state,
        'runtime_reason': reason,
        'session_running': running,
        'availability': availability_state,
        'state': availability_state,
        'reason': reason,
        'observed_at': _isoformat_utc(observed_at),
        'freshness_seconds': freshness_seconds,
    }
    if elapsed_seconds is not None:
        result['elapsed_seconds'] = elapsed_seconds
    return result


def _build_inventory_result(deps: Any) -> dict:
    list_all_agents = getattr(deps, 'list_all_agents', None)
    if not callable(list_all_agents):
        return {'agents': [], 'count': 0}

    agents = list_all_agents() or {}
    rows = []
    if isinstance(agents, dict):
        items = sorted(agents.items(), key=lambda item: str(item[0]))
    else:
        items = []
        try:
            items = sorted(((str(idx), entry) for idx, entry in enumerate(agents)), key=lambda item: item[0])
        except Exception:
            items = []

    for key, config in items:
        if not isinstance(config, dict):
            continue
        agent_name = str(config.get('name') or key)
        agent_id = str(config.get('file_id') or config.get('agent_id') or '').strip().lower().replace('_', '-')
        if not agent_id:
            agent_id = agent_name.strip().lower().replace('_', '-')
        snapshot = _build_runtime_snapshot(deps, agent_id=agent_id, agent_name=agent_name)
        rows.append(
            {
                'agent_id': snapshot['agent_id'],
                'agent_name': snapshot['agent_name'],
                'enabled': bool(config.get('enabled', True)),
                'availability': snapshot['availability'],
                'runtime_state': snapshot['runtime_state'],
                'runtime_reason': snapshot['runtime_reason'],
                'session_running': snapshot['session_running'],
                'freshness_seconds': snapshot['freshness_seconds'],
            }
        )

    return {'agents': rows, 'count': len(rows)}


def _build_status_result(deps: Any, *, agent_config: dict, agent_id: str, agent_name: str) -> dict:
    snapshot = _build_runtime_snapshot(deps, agent_id=agent_id, agent_name=agent_name)
    get_session_info = getattr(deps, 'get_session_info', None)
    session_info = get_session_info(agent_id) if callable(get_session_info) else None
    session = ''
    if isinstance(session_info, dict):
        session = str(session_info.get('session') or '')
    if not session:
        session = snapshot['session_name']

    return {
        'agent_id': agent_id,
        'agent_name': agent_name,
        'enabled': bool(agent_config.get('enabled', True)),
        'session_name': session,
        'availability': snapshot['availability'],
        'runtime_state': snapshot['runtime_state'],
        'runtime_reason': snapshot['runtime_reason'],
        'session_running': snapshot['session_running'],
        'observed_at': snapshot['observed_at'],
        'freshness_seconds': snapshot['freshness_seconds'],
        'elapsed_seconds': snapshot.get('elapsed_seconds'),
    }


def _build_health_result(deps: Any) -> dict:
    check_tmux = getattr(deps, 'check_tmux', None)
    list_all_agents = getattr(deps, 'list_all_agents', None)
    repo_root = getattr(deps, 'get_repo_root', None)
    agents = list_all_agents() if callable(list_all_agents) else {}
    agent_count = len(agents) if isinstance(agents, dict) else 0
    root_path = repo_root() if callable(repo_root) else None
    ledger_path = ''
    if isinstance(root_path, Path):
        ledger_path = str(_runtime_ledger_path(root_path))
    return {
        'tmux_available': bool(check_tmux()) if callable(check_tmux) else False,
        'agent_count': agent_count,
        'ledger_path': ledger_path,
        'supported_operations': list(SUPPORTED_OPERATIONS),
        'schema_version': SCHEMA_VERSION,
    }


def _run_with_timeout(timeout_seconds: Optional[float], func):
    if not timeout_seconds or timeout_seconds <= 0:
        return func()

    if not hasattr(signal, 'setitimer'):
        return func()

    class _Timeout(Exception):
        pass

    def _handler(_signum, _frame):
        raise _Timeout('timed out')

    previous_handler = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, float(timeout_seconds))
    try:
        return func()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


@contextlib.contextmanager
def _temporary_stdin(text: Optional[str]):
    if text is None:
        yield None
        return
    import sys

    original = sys.stdin
    sys.stdin = io.StringIO(text)
    try:
        yield sys.stdin
    finally:
        sys.stdin = original


def _invoke_compat_handler(deps: Any, operation: str, *, agent_id: str, params: dict, request: dict) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    handler = None
    args = None
    task_file_path: Optional[str] = None

    if operation == 'start':
        handler = getattr(deps, 'cmd_start', None)
        args = SimpleNamespace(
            agent=agent_id,
            working_dir=params.get('working_dir'),
            restore=bool(params.get('restore', True)),
            tmux_layout=str(params.get('tmux_layout') or 'sessions'),
        )
    elif operation == 'stop':
        handler = getattr(deps, 'cmd_stop', None)
        args = SimpleNamespace(agent=agent_id)
    elif operation == 'assign':
        handler = getattr(deps, 'cmd_assign', None)
        task_text = str(params.get('task') or request.get('task') or request.get('message') or '').strip()
        task_file = str(params.get('task_file') or '').strip()
        if task_text and not task_file:
            task_file_handle = tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False, prefix='agent-manager-assign-', suffix='.txt')
            try:
                task_file_handle.write(task_text)
                task_file_handle.flush()
                task_file = task_file_handle.name
                task_file_path = task_file_handle.name
            finally:
                task_file_handle.close()
        args = SimpleNamespace(agent=agent_id, task_file=task_file or None)
    elif operation in {'monitor', 'logs'}:
        handler = getattr(deps, 'cmd_monitor', None)
        args = SimpleNamespace(
            agent=agent_id,
            follow=bool(params.get('follow', False) if operation == 'logs' else params.get('follow', False)),
            lines=int(params.get('lines', 100) or 100),
        )
    else:
        return 1, '', f'unsupported operation: {operation}'

    if not callable(handler):
        return 1, '', f'compat handler unavailable for {operation}'

    import sys as _sys
    with redirect_stdout(stdout), redirect_stderr(stderr):
        original_stdin = _sys.stdin
        try:
            rc = int(handler(args))
        except Exception as exc:
            rc = 1
            print(f'{exc.__class__.__name__}: {exc}', file=stderr)
        finally:
            _sys.stdin = original_stdin
            if task_file_path:
                try:
                    os.unlink(task_file_path)
                except Exception:
                    pass

    return rc, stdout.getvalue(), stderr.getvalue()


def _operation_result(deps: Any, request: dict) -> dict:
    operation = request['operation']
    params = request.get('params') or {}
    raw = request.get('raw') or request
    agent_value = str(request.get('agent') or '').strip()

    if bool(request.get('cancel', False)):
        return {
            'ok': False,
            'error': _error('cancelled', 'request was cancelled before execution'),
            'result': None,
        }

    timeout_seconds = request.get('timeout_seconds')
    if timeout_seconds is not None and timeout_seconds <= 0:
        return {
            'ok': False,
            'error': _error('timeout', 'timeout_seconds must be greater than zero'),
            'result': None,
        }

    if operation in {'inventory', 'health'}:
        if operation == 'inventory':
            result = _build_inventory_result(deps)
        else:
            result = _build_health_result(deps)
        return {'ok': True, 'error': None, 'result': result}

    if operation in {'status', 'availability', 'start', 'stop', 'assign', 'monitor', 'logs'} and not agent_value:
        return {
            'ok': False,
            'error': _error('missing_agent', f'operation {operation} requires agent'),
            'result': None,
        }

    agent_config, agent_id, agent_name, lookup_error = _resolve_agent_context(deps, agent_value)
    if lookup_error:
        return {
            'ok': False,
            'error': _error('missing_agent', lookup_error),
            'result': None,
        }
    assert agent_config is not None and agent_id is not None and agent_name is not None

    if operation == 'status':
        return {'ok': True, 'error': None, 'result': _build_status_result(deps, agent_config=agent_config, agent_id=agent_id, agent_name=agent_name)}

    if operation == 'availability':
        snapshot = _build_runtime_snapshot(deps, agent_id=agent_id, agent_name=agent_name)
        return {'ok': True, 'error': None, 'result': snapshot}

    if params.get('follow'):
        return {
            'ok': False,
            'error': _error('unsupported_operation', f'{operation} follow mode is not supported by the JSON adapter'),
            'result': None,
        }

    timeout = timeout_seconds

    def _run():
        return _invoke_compat_handler(deps, operation, agent_id=agent_value, params=params, request=raw)

    try:
        exit_code, stdout_text, stderr_text = _run_with_timeout(timeout, _run)
    except BaseException as exc:
        if exc.__class__.__name__ == '_Timeout' or isinstance(exc, TimeoutError):
            return {
                'ok': False,
                'error': _error('timeout', f'{operation} exceeded timeout'),
                'result': {
                    'stdout': '',
                    'stderr': '',
                    'exit_code': None,
                },
            }
        raise

    result = {
        'exit_code': exit_code,
        'stdout': _bounded_text(stdout_text),
        'stderr': _bounded_text(stderr_text),
    }
    ok = exit_code == 0
    if not ok:
        return {
            'ok': False,
            'error': _error('operation_failed', f'{operation} exited with {exit_code}', detail=_bounded_text(stderr_text or stdout_text, limit=1200)),
            'result': result,
        }

    return {'ok': True, 'error': None, 'result': result}


def handle_request(request: dict, *, deps: Any) -> dict:
    normalized = dict(request)
    normalized.setdefault('params', {})
    normalized.setdefault('raw', dict(request))
    schema_version = str(normalized['schema_version'])
    command_id = str(normalized['command_id'])
    operation = str(normalized['operation'])
    idempotency_key = str(normalized.get('idempotency_key') or '')

    existing = _lookup_ledger_response(deps.get_repo_root() if callable(getattr(deps, 'get_repo_root', None)) else Path.cwd(), command_id)
    if existing is not None:
        dup = dict(existing)
        dup['duplicate'] = True
        dup['observed_at'] = _isoformat_utc(_utc_now())
        return dup

    if operation not in SUPPORTED_OPERATIONS:
        response = _request_error(command_id, operation, 'unsupported_operation', f'unsupported operation: {operation}')
    else:
        outcome = _operation_result(deps, normalized)
        response = {
            'schema_version': schema_version,
            'adapter': ADAPTER_NAME,
            'command_id': command_id,
            'operation': operation,
            'duplicate': False,
            'ok': bool(outcome['ok']),
            'observed_at': _isoformat_utc(_utc_now()),
            'result': outcome['result'],
            'error': outcome['error'],
        }

    repo_root = deps.get_repo_root() if callable(getattr(deps, 'get_repo_root', None)) else Path.cwd()
    if isinstance(repo_root, Path):
        _append_ledger_response(repo_root, command_id=command_id, idempotency_key=idempotency_key, operation=operation, response=response)
    return response


def run_from_text(raw_text: str, *, deps: Any) -> dict:
    request = parse_request(raw_text)
    return handle_request(request, deps=deps)
