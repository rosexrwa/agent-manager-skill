# Runtime JSON Adapter

`agent-manager` exposes a local-only JSON adapter via:

```bash
python3 agent-manager/scripts/main.py adapter < request.json
```

The adapter is intentionally machine-readable and local-process only. It does **not** start a public listener.

## Schema

### Request envelope

- `schema_version` — current version: `"1"`
- `command_id` — required unique command identifier
- `idempotency_key` — optional caller key for replay correlation
- `operation` — one of:
  - `inventory`
  - `status`
  - `start`
  - `stop`
  - `assign`
  - `monitor`
  - `logs`
  - `health`
  - `availability`
- `agent` / `agent_id` / `agent_name` — required for agent-scoped operations
- `timeout_seconds` — optional local timeout guard
- `cancel` — optional pre-execution cancellation flag
- `params` — operation-specific object

### Response envelope

- `schema_version`
- `adapter` — `agent-manager-runtime`
- `command_id`
- `operation`
- `duplicate` — `true` when a replayed `command_id` is served from the local ledger
- `ok`
- `observed_at` — UTC timestamp
- `result` — operation payload or `null`
- `error` — stable error object or `null`

## Stable error codes

- `cancelled`
- `duplicate_command_id`
- `internal_error`
- `malformed_input`
- `missing_agent`
- `missing_command_id`
- `operation_failed`
- `timeout`
- `unsupported_operation`

## Canonical availability mapping

The adapter normalizes runtime evidence into one of:

- `available`
- `busy`
- `unavailable`
- `unknown`

Mapping:

- runtime `idle` → `available`
- runtime `busy` → `busy`
- runtime `blocked|stuck|error|interrupted` → `unavailable`
- missing session → `unavailable`
- unreadable/indeterminate runtime evidence → `unknown`

The availability payload also includes:

- `reason`
- `observed_at`
- `freshness_seconds`
- `runtime_state`
- `runtime_reason`
- `session_running`

Freshness is derived from the latest heartbeat audit event when available.

## Local replay ledger

The adapter stores request/response pairs in:

- `.claude/state/agent-manager/runtime-adapter/command-ledger.jsonl`

A repeated `command_id` returns the prior response instead of re-executing the lifecycle action.

## Compatibility note

Human CLI commands remain unchanged. The JSON adapter is a compatibility surface for other local tools, not a replacement for the current CLI.
