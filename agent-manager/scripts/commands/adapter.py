from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from runtime_adapter import ADAPTER_NAME, SCHEMA_VERSION, parse_request, handle_request, _request_error


def _read_request_text(args) -> str:
    request_file = getattr(args, 'request_file', None)
    if request_file:
        return Path(request_file).read_text(encoding='utf-8')
    return sys.stdin.read()


def cmd_adapter(args, *, deps: Any):
    """Run the local JSON runtime adapter over stdin/stdout."""
    try:
        raw_text = _read_request_text(args)
    except FileNotFoundError as exc:
        payload = _request_error('', '', 'malformed_input', 'request file not found', detail=str(exc))
        print(json.dumps(payload, ensure_ascii=False))
        return 1
    except Exception as exc:
        payload = _request_error('', '', 'malformed_input', 'failed to read request', detail=str(exc))
        print(json.dumps(payload, ensure_ascii=False))
        return 1

    try:
        request = parse_request(raw_text)
        response = handle_request(request, deps=deps)
        print(json.dumps(response, ensure_ascii=False))
        return 0 if response.get('ok', False) else 1
    except ValueError as exc:
        payload = _request_error('', '', 'malformed_input', 'invalid adapter request', detail=str(exc))
        print(json.dumps(payload, ensure_ascii=False))
        return 1
    except Exception as exc:
        payload = _request_error('', '', 'internal_error', 'adapter execution failed', detail=f'{exc.__class__.__name__}: {exc}')
        print(json.dumps(payload, ensure_ascii=False))
        return 1
