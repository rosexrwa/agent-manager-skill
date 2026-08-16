"""Provider configurations for different CLI tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Dict, Optional


# Provider definitions
PROVIDERS: Dict[str, Dict] = {
    'codex': {
        'name': 'Codex',
        # Codex CLI commonly uses the arrow prompt (❯) or a chevron (›).
        # Include legacy prompts for compatibility.
        'prompt_patterns': ['❯', '›', '>', 'codex>', 'You>'],
        'startup_wait': 1,
        'description': 'OpenAI Codex CLI',
        'system_prompt': {
            # Codex supports overriding config keys via `-c/--config key=value`.
            # Agent-manager overlays should be injected as developer instructions.
            'mode': 'cli_config_kv',
            'flag': '-c',
            'key': 'developer_instructions',
            'value_mode': 'inline_text',
        },
        'launcher_config': {
            # Flat `launcher_config` entries are translated by the provider.
            'mode': 'cli_config_kv',
            'flag': '-c',
        },
        'agents_md': {
            'mode': 'cwd',
        },
        'mcp_config': {
            'mode': 'unsupported',
        },
        'session_restore': {
            # Codex supports `resume [SESSION_ID]` to continue an existing session.
            'mode': 'cli_optional_arg',
            'flag': 'resume',
        },
        'runtime': {
            'busy_patterns': [
                # Status lines commonly shown during work.
                '◦ Working',
                '• Working',
                'Working',
                'Monitoring',
                'Performing',
                'Executing',
                'Running',
                'Processing',
                'Analyzing',
                'Thinking',
                'Thinking…',
                'Thinking...',
                'thinking',
                # Codex often prints this without parentheses.
                'esc to interrupt',
            ],
            'blocked_patterns': [
                # Keep these patterns specific to avoid false positives (e.g., issue titles containing
                # the word "Approve").
                'actions require approval',
                'requires approval',
                'waiting for approval',
            ],
            'stuck_after_seconds': 180,
            'interrupted_patterns': [
                'Conversation interrupted',
            ],
            'suggestion_tip_pattern': r'^[›❯]\s+(?!\d+\.)',
            'context_left_patterns': [
                r'(\d{1,3})%\s*context left',
            ],
        },
    },
    'claude-code': {
        'name': 'Claude Code',
        # Claude Code v2.1+ often renders the prompt as "❯" in the TUI.
        'prompt_patterns': ['>', '>\xa0', '⟩', '❯', '›'],
        'startup_wait': 0,
        'description': 'Official Claude Code CLI',
        'launch_command': None,  # Uses ccc script
        'system_prompt': {
            'mode': 'cli_append',
            'flag': '--append-system-prompt',
        },
        'mcp_config': {
            # Claude Code supports passing MCP config JSON.
            # We pass: {"mcpServers": { ... }}
            'mode': 'cli_json',
            'flag': '--mcp-config',
        },
        'session_restore': {
            # Claude Code supports resuming a previous session by session ID.
            'mode': 'cli_optional_arg',
            'flag': '--resume',
        },
        # Best-effort runtime heuristics (used by agent-manager/tmux_helper).
        'runtime': {
            'busy_patterns': [
                '✻ Forging',
                '✻ Spelunking',
                '✻ Thinking',
                'Forging…',
                'Spelunking…',
                'Working…',
                '⏳ Thinking',
                '(esc to interrupt',
            ],
            'blocked_patterns': [
                'actions require approval',
                'requires approval',
                'waiting for approval',
            ],
            'stuck_after_seconds': 180,
            'context_left_patterns': [
                r'(\d{1,3})%\s*context left',
                r'context (?:window|budget)[: ]+(\d{1,3})%',
            ],
        },
    },
    'droid': {
        'name': 'Droid',
        'prompt_patterns': ['>', '>\xa0', '⟩'],
        'startup_wait': 5,
        'prompt_check': 'droid',  # Look for droid-specific patterns
        'description': 'Droid CLI agent',
        'launch_command': 'droid',  # Direct droid command
        'session_restore': {
            # Droid supports resuming a previous session. If no sessionId is
            # provided, it resumes the last modified session.
            'mode': 'cli_optional_arg',
            'flag': '--resume',
        },
        'system_prompt': {
            'mode': 'tmux_paste',
        },
        'agents_md': {
            'mode': 'cwd',
        },
        'mcp_config': {
            # Droid CLI MCP support is provider/version dependent; default to unsupported.
            'mode': 'unsupported',
        },
        'runtime': {
            'busy_patterns': [
                'Thinking...',
                'Thinking…',
                '⏳ Thinking',
                '⠋ Thinking',
                '⠙ Thinking',
                '⠹ Thinking',
                '⠸ Thinking',
                '⠼ Thinking',
                '⠴ Thinking',
                '⠦ Thinking',
                '⠧ Thinking',
                '⠇ Thinking',
                '(esc to interrupt',
            ],
            'blocked_patterns': [
                'all actions require approval',
                'actions require approval',
                'requires approval',
                'waiting for approval',
            ],
            'stuck_after_seconds': 180,
            'context_left_patterns': [
                r'(\d{1,3})%\s*context left',
            ],
        },
    },
    'claude': {
        'name': 'Claude',
        'prompt_patterns': ['>', '⟩', ':'],
        'startup_wait': 1,
        'description': 'Generic Claude CLI',
        'session_restore': {
            'mode': 'cli_optional_arg',
            'flag': '--resume',
        },
        'system_prompt': {
            'mode': 'cli_append',
            'flag': '--append-system-prompt',
        },
        'mcp_config': {
            'mode': 'cli_json',
            'flag': '--mcp-config',
        },
        'runtime': {
            'busy_patterns': [
                '✻ Thinking',
                'Thinking...',
                '⏳ Thinking',
                '(esc to interrupt',
            ],
            'blocked_patterns': [
                'actions require approval',
                'requires approval',
            ],
            'stuck_after_seconds': 180,
            'context_left_patterns': [
                r'(\d{1,3})%\s*context left',
                r'context remaining[: ]+(\d{1,3})%',
            ],
        },
    },
    'generic': {
        'name': 'Generic',
        'prompt_patterns': ['>', '$', '#', ':', '⟩'],
        'startup_wait': 1,
        'description': 'Generic CLI with common prompts',
        'system_prompt': {
            'mode': 'tmux_paste',
        },
        'mcp_config': {
            'mode': 'unsupported',
        },
        'runtime': {
            'busy_patterns': [
                'Thinking...',
                'Thinking…',
                'Working…',
                '⏳ Thinking',
                '(esc to interrupt',
            ],
            'blocked_patterns': [
                'actions require approval',
                'requires approval',
                'waiting for approval',
            ],
            'stuck_after_seconds': 180,
            'context_left_patterns': [
                r'(\d{1,3})%\s*context left',
            ],
        },
    },
    'gemini': {
        'name': 'Gemini',
        # Gemini CLI uses a full-screen TUI (Ink-based); tmux capture-pane
        # doesn't expose a stable prompt character.  Treat readiness as
        # "process started" and rely on startup_wait (similar to OpenCode).
        'prompt_patterns': [],
        'startup_wait': 3,
        'description': 'Google Gemini CLI',
        'launch_command': 'gemini',
        'system_prompt': {
            # Gemini CLI reads context from GEMINI.md files in the workspace.
            # For runtime system prompt injection, use tmux_paste fallback.
            'mode': 'tmux_paste',
        },
        'agents_md': {
            # Gemini reads GEMINI.md from CWD automatically.
            'mode': 'cwd',
        },
        'mcp_config': {
            # Gemini CLI manages MCP servers via `gemini mcp add/remove`
            # rather than a single JSON flag.  Not injectable at launch time.
            'mode': 'unsupported',
        },
        'session_restore': {
            # Gemini supports `--resume <id|latest>` to continue a session.
            'mode': 'cli_optional_arg',
            'flag': '--resume',
        },
        'runtime': {
            'busy_patterns': [
                'Thinking',
                'Thinking…',
                'Thinking...',
                'Working',
                'Working…',
                'Analyzing',
                'Processing',
                'Executing',
                '(esc to interrupt',
            ],
            'blocked_patterns': [
                'Allow this action',
                'requires approval',
                'waiting for approval',
            ],
            'stuck_after_seconds': 180,
            'context_left_patterns': [
                r'(\d{1,3})%\s*context left',
            ],
        },
    },
    'opencode': {
        'name': 'OpenCode',
        # OpenCode uses a full-screen TUI; tmux capture-pane often doesn't expose a stable prompt.
        # We treat readiness as "process started" and rely on startup_wait.
        'prompt_patterns': [],
        'startup_wait': 2,
        'description': 'OpenCode CLI agent (opencode.ai)',
        'launch_command': 'opencode',
        'session_restore': {
            # OpenCode supports continuing a session by session id.
            'mode': 'cli_optional_arg',
            'flag': '--session',
        },
        'system_prompt': {
            # OpenCode supports passing a prompt via CLI.
            'mode': 'cli_append',
            'flag': '--prompt',
        },
        'mcp_config': {
            'mode': 'unsupported',
        },
        'runtime': {
            'busy_patterns': [
                'Thinking...',
                'Thinking…',
                '⏳ Thinking',
                '(esc to interrupt',
            ],
            'blocked_patterns': [
                'actions require approval',
                'requires approval',
                'waiting for approval',
            ],
            'stuck_after_seconds': 180,
            'context_left_patterns': [
                r'(\d{1,3})%\s*context left',
            ],
        },
    },
    'kimi-code': {
        'name': 'Kimi Code',
        # Kimi Code uses a full-screen TUI; tmux capture-pane shows a bordered input box
        # rather than a stable bare prompt. Treat process start + startup_wait as ready.
        'prompt_patterns': [],
        'startup_wait': 2,
        'description': 'Kimi Code CLI',
        'launch_command': 'kimi',
        'system_prompt': {
            # Kimi Code v0.27 does not expose a CLI system-prompt flag; use tmux paste fallback.
            'mode': 'tmux_paste',
        },
        'agents_md': {
            'mode': 'cwd',
        },
        'mcp_config': {
            # Kimi Code MCP is configured via config files, not a launch-time JSON flag.
            'mode': 'unsupported',
        },
        'session_restore': {
            # Kimi Code supports `--session [id]` to resume a specific session.
            'mode': 'cli_optional_arg',
            'flag': '--session',
        },
        'runtime': {
            'busy_patterns': [
                # Kimi shows a persistent "K3 thinking: high" status line even when idle.
                # Only treat explicit in-turn interrupt/compaction signals as busy.
                '(esc to interrupt',
                'esc to interrupt',
                'Compacting',
                'Compacting…',
            ],
            'blocked_patterns': [
                'Allow this action',
                'actions require approval',
                'requires approval',
                'waiting for approval',
            ],
            'stuck_after_seconds': 180,
            'context_left_patterns': [
                r'(\d{1,3})%\s*context left',
                r'context left[: ]+(\d{1,3})%',
                r'(\d{1,3})%\s*context remaining',
            ],
        },
    },
    'cursor': {
        'name': 'Cursor CLI',
        # Cursor Agent is an Ink TUI and does not expose a stable bare prompt in
        # tmux capture-pane. Treat process start as ready after startup_wait.
        'prompt_patterns': [],
        'startup_wait': 3,
        'description': 'Cursor Agent CLI',
        'launch_command': 'cursor-agent',
        'system_prompt': {
            # Cursor CLI has no system-prompt launch flag; use the normal tmux
            # paste fallback so the existing dispatch protocol still applies.
            'mode': 'tmux_paste',
        },
        'agents_md': {
            'mode': 'cwd',
        },
        'mcp_config': {
            'mode': 'unsupported',
        },
        'runtime': {
            'busy_patterns': [
                'Thinking',
                'Working',
                'Analyzing',
                'Processing',
                'Executing',
                'esc to interrupt',
            ],
            'blocked_patterns': [
                'Workspace Trust Required',
                'API key',
                'requires approval',
                'waiting for approval',
            ],
            'stuck_after_seconds': 180,
            'context_left_patterns': [
                r'(\d{1,3})%\s*context left',
            ],
        },
    },
    'grok': {
        'name': 'Grok CLI',
        # Grok Build TUI (xAI `grok`) uses a full-screen pager. Treat process
        # start as ready after startup_wait rather than waiting for a bare prompt.
        'prompt_patterns': ['❯'],
        'startup_wait': 2,
        'description': 'xAI Grok Build CLI',
        'launch_command': 'grok',
        'system_prompt': {
            # Documented Claude Code alias accepted by Grok CLI.
            'mode': 'cli_append',
            'flag': '--append-system-prompt',
        },
        'agents_md': {
            'mode': 'cwd',
        },
        'mcp_config': {
            # MCP servers are managed with `grok mcp`, not a launch-time JSON flag.
            'mode': 'unsupported',
        },
        'session_restore': {
            'mode': 'cli_optional_arg',
            'flag': '--resume',
        },
        'runtime': {
            'busy_patterns': [
                'esc to interrupt',
                'Esc:reset',
                'Thinking…',
                'Thinking...',
            ],
            'blocked_patterns': [
                'requires approval',
                'waiting for approval',
                'grok login',
            ],
            'stuck_after_seconds': 180,
            'context_left_patterns': [
                r'(\d{1,3})%\s*context left',
            ],
        },
    },
}


def get_provider_key(launcher: str) -> str:
    """Get provider key based on launcher path/name."""
    launcher_lower = (launcher or "").lower()

    if 'cursor' in launcher_lower:
        return 'cursor'
    if Path(launcher_lower).name in {'grok', 'grok-cli', 'grok-build', 'xai-grok-pager'}:
        return 'grok'
    if launcher_lower in {'grok', 'grok-cli', 'grok-build', 'xai-grok-pager'}:
        return 'grok'
    if 'kimi' in launcher_lower:
        return 'kimi-code'
    if 'gemini' in launcher_lower:
        return 'gemini'
    if 'codex' in launcher_lower:
        return 'codex'
    if 'droid' in launcher_lower:
        return 'droid'
    if 'opencode' in launcher_lower:
        return 'opencode'
    if 'claude-code' in launcher_lower or 'ccc' in launcher_lower:
        return 'claude-code'
    if 'claude' in launcher_lower:
        return 'claude'
    return 'generic'


def resolve_launcher_command(launcher: str) -> str:
    """Resolve a launcher name to an executable path when possible.

    This keeps agent configs simple (e.g. `launcher: opencode`) while still working
    when PATH isn't set up in non-interactive shells.
    """
    launcher = (launcher or "").strip()
    if not launcher:
        return launcher

    # If launcher already looks like a path, don't rewrite it.
    if "/" in launcher or launcher.startswith("."):
        return launcher

    if launcher.lower() in {"kimi", "kimi-code"}:
        candidates = [
            Path(os.path.expanduser("~")) / ".kimi-code" / "bin" / "kimi",
            Path(os.path.expanduser("~")) / ".local" / "bin" / "kimi",
            Path(os.path.expanduser("~")) / "bin" / "kimi",
            Path("/usr/local/bin/kimi"),
            Path("/usr/bin/kimi"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return "kimi"

    if launcher.lower() in {"cursor", "cursor-cli", "cursor-agent"}:
        candidates = [
            Path(os.path.expanduser("~")) / ".cursor" / "bin" / "cursor-agent",
            Path(os.path.expanduser("~")) / ".local" / "bin" / "cursor-agent",
            Path(os.path.expanduser("~")) / "bin" / "cursor-agent",
            Path("/usr/local/bin/cursor-agent"),
            Path("/usr/bin/cursor-agent"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return "cursor-agent"

    if launcher.lower() in {"grok", "grok-cli", "grok-build", "xai-grok-pager"}:
        candidates = [
            Path(os.path.expanduser("~")) / ".local" / "bin" / "grok",
            Path(os.path.expanduser("~")) / ".grok" / "bin" / "grok",
            Path(os.path.expanduser("~")) / "bin" / "grok",
            Path("/opt/homebrew/bin/grok"),
            Path("/usr/local/bin/grok"),
            Path("/usr/bin/grok"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return "grok"

    if launcher.lower() == "opencode":
        candidate = Path(os.path.expanduser("~")) / ".opencode" / "bin" / "opencode"
        if candidate.exists():
            return str(candidate)

    if launcher.lower() == "gemini":
        candidates = [
            Path(os.path.expanduser("~")) / ".local" / "bin" / "gemini",
            Path(os.path.expanduser("~")) / "bin" / "gemini",
            Path("/usr/local/bin/gemini"),
            Path("/usr/bin/gemini"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        # Fall back to npx wrapper.
        return "npx @google/gemini-cli"

    if launcher.lower() == "codex":
        candidates = [
            Path(os.path.expanduser("~")) / ".local" / "bin" / "codex",
            Path(os.path.expanduser("~")) / "bin" / "codex",
            Path("/usr/local/bin/codex"),
            Path("/usr/bin/codex"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

    return launcher


def launcher_binary_exists(resolved: str) -> bool:
    """True when the resolved launcher can be executed without installing anything."""
    text = str(resolved or "").strip()
    if not text:
        return False
    if text.startswith("npx "):
        return True
    path = Path(os.path.expanduser(text))
    if path.exists():
        return True
    import shutil
    return shutil.which(text) is not None


def missing_launcher_help(provider_key: str) -> str:
    """Operator-facing install/auth hint. Never includes secrets."""
    if provider_key == "grok":
        return (
            "❌ Grok CLI not found.\n"
            "   Install: curl -fsSL https://x.ai/cli/install.sh | bash\n"
            "   Authenticate with `grok login` (or a shell env such as XAI_API_KEY).\n"
            "   Do not put API keys in launcher_args or agent YAML."
        )
    return f"❌ Launcher not found for provider '{provider_key}'"


def get_provider(launcher: str) -> Dict:
    """
    Get provider configuration based on launcher path/name.

    Args:
        launcher: Launcher path or name (e.g., 'droid', '/path/to/ccc')

    Returns:
        Provider configuration dict
    """
    return PROVIDERS[get_provider_key(launcher)]


def get_prompt_patterns(launcher: str) -> List[str]:
    """Get prompt patterns for a given launcher."""
    provider = get_provider(launcher)
    return provider.get('prompt_patterns', ['>', '$'])


def get_startup_wait(launcher: str) -> int:
    """Get startup wait time for a given launcher."""
    provider = get_provider(launcher)
    return provider.get('startup_wait', 1)


def get_system_prompt_config(launcher: str) -> Dict:
    """Get system prompt injection configuration for a given launcher."""
    provider = get_provider(launcher)
    return provider.get('system_prompt', {'mode': 'tmux_paste'})


def get_mcp_config_config(launcher: str) -> Dict:
    """Get MCP config injection configuration for a given launcher."""
    provider = get_provider(launcher)
    return provider.get('mcp_config', {'mode': 'unsupported'})


def get_runtime_config(launcher: str) -> Dict:
    """Get provider runtime heuristics configuration."""
    provider = get_provider(launcher)
    return provider.get('runtime', {})


def get_busy_patterns(launcher: str) -> List[str]:
    """Get busy patterns for a given launcher/provider."""
    cfg = get_runtime_config(launcher)
    return cfg.get('busy_patterns', [])


def get_blocked_patterns(launcher: str) -> List[str]:
    """Get blocked/approval patterns for a given launcher/provider."""
    cfg = get_runtime_config(launcher)
    return cfg.get('blocked_patterns', [])


def get_stuck_after_seconds(launcher: str) -> int:
    """Get "stuck" threshold (seconds) for a given launcher/provider."""
    cfg = get_runtime_config(launcher)
    return int(cfg.get('stuck_after_seconds', 180))


def get_context_left_patterns(launcher: str) -> List[str]:
    """Get provider-specific regex patterns for context-left detection."""
    cfg = get_runtime_config(launcher)
    return list(cfg.get('context_left_patterns', []) or [])


def get_system_prompt_mode(launcher: str) -> str:
    """Get system prompt injection mode.

    Modes:
    - cli_append: pass system prompt via CLI flag (true system prompt)
    - cli_config_kv: pass config override via CLI key=value (e.g. `-c developer_instructions="..."`)
    - tmux_paste: paste prompt into the session after startup (fallback)
    """
    return get_system_prompt_config(launcher).get('mode', 'tmux_paste')


def get_system_prompt_flag(launcher: str) -> Optional[str]:
    """Get the CLI flag to use for system prompt injection, if supported."""
    return get_system_prompt_config(launcher).get('flag')


def get_system_prompt_key(launcher: str) -> Optional[str]:
    """Get the config key to override for system prompt injection, if supported."""
    return get_system_prompt_config(launcher).get('key')


def get_system_prompt_value_mode(launcher: str) -> str:
    """Get how the system prompt payload should be encoded for CLI config injection.

    Modes:
    - file_path: write prompt to disk and pass a file path
    - inline_text: pass prompt contents as an inline TOML string
    """
    return get_system_prompt_config(launcher).get('value_mode', 'file_path')


def get_agents_md_mode(launcher: str) -> str:
    """Get AGENTS.md discovery mode for a given launcher/provider.

    Modes:
    - cwd: provider reads `AGENTS.md` from working directory
    - disabled: provider does not support / not enabled
    """
    provider = get_provider(launcher)
    return (provider.get('agents_md') or {}).get('mode', 'disabled')


def get_launcher_config_config(launcher: str) -> Dict:
    """Get provider-specific launcher_config injection settings."""
    provider = get_provider(launcher)
    return provider.get('launcher_config', {'mode': 'unsupported'})


def get_launcher_config_mode(launcher: str) -> str:
    """Get how flat `launcher_config` entries should be injected for a provider.

    Modes:
    - cli_config_kv: append one key=value config override per entry
    - unsupported: provider does not support launcher_config injection
    """
    return get_launcher_config_config(launcher).get('mode', 'unsupported')


def get_launcher_config_flag(launcher: str) -> Optional[str]:
    """Get the CLI flag used to inject launcher_config entries, if supported."""
    return get_launcher_config_config(launcher).get('flag')


def get_mcp_config_mode(launcher: str) -> str:
    """Get MCP config injection mode.

    Modes:
    - cli_json: pass MCP config as JSON via CLI flag
    - unsupported: provider does not support MCP config injection
    """
    return get_mcp_config_config(launcher).get('mode', 'unsupported')


def get_mcp_config_flag(launcher: str) -> Optional[str]:
    """Get the CLI flag to use for MCP config injection, if supported."""
    return get_mcp_config_config(launcher).get('flag')


def get_session_restore_config(launcher: str) -> Dict:
    """Get provider session restore configuration.

    Modes:
    - cli_optional_arg: add flag (and optional value) to resume provider session
    - unsupported: provider has no resume support
    """
    provider = get_provider(launcher)
    return provider.get('session_restore', {'mode': 'unsupported'})


def get_session_restore_mode(launcher: str) -> str:
    """Get session restore mode for a given launcher/provider."""
    return get_session_restore_config(launcher).get('mode', 'unsupported')


def get_session_restore_flag(launcher: str) -> Optional[str]:
    """Get the CLI flag to use for session restore, if supported."""
    return get_session_restore_config(launcher).get('flag')


def list_providers() -> Dict[str, Dict]:
    """List all available providers."""
    return PROVIDERS
