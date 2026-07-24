from __future__ import annotations

from typing import Any, Optional


META_SECTION = "--- Meta ---"
BODY_SECTION = "--- Body ---"
FOOTER_SECTION = "--- Footer ---"


def generate_message_id(deps: Any) -> str:
    datetime_mod = getattr(deps, 'datetime')
    uuid_mod = getattr(deps, 'uuid')
    now = datetime_mod.now()
    return f"msg_{now.strftime('%Y%m%d_%H%M%S')}_{uuid_mod.uuid4().hex[:8]}"


def _clean_optional_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _validate_meta_value(field: str, value: str) -> Optional[str]:
    if not str(value or '').strip():
        return f"Meta field '{field}' is required"
    if '\n' in str(value) or '\r' in str(value):
        return f"Meta field '{field}' must be a single line"
    return None


def render_envelope(
    *,
    message_id: str,
    message_type: str,
    from_agent: str,
    to_agent: str,
    body: str,
    footer: str = "",
    reply_to: str = "",
) -> str:
    fields = {
        'id': message_id,
        'type': message_type,
        'from': from_agent,
        'to': to_agent,
    }
    if reply_to:
        fields['reply_to'] = reply_to

    meta_lines = [f"{key}: {value}" for key, value in fields.items()]
    parts = [
        META_SECTION,
        *meta_lines,
        "",
        BODY_SECTION,
        body,
    ]
    if footer:
        parts.extend(["", FOOTER_SECTION, footer])
    return "\n".join(parts)


def build_envelope(
    *,
    deps: Any,
    message_type: str,
    from_agent: str,
    to_agent: str,
    body: str,
    footer: Optional[str] = None,
    message_id: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], str]:
    message_type = str(message_type or '').strip()
    if message_type not in {'message', 'reply'}:
        return None, None, "Message type must be 'message' or 'reply'"

    cleaned = {
        'id': _clean_optional_text(message_id) or generate_message_id(deps),
        'type': message_type,
        'from': _clean_optional_text(from_agent),
        'to': _clean_optional_text(to_agent),
    }
    cleaned_reply_to = _clean_optional_text(reply_to)
    if message_type == 'reply' and not cleaned_reply_to:
        return None, None, "Meta field 'reply_to' is required for replies"
    if cleaned_reply_to:
        cleaned['reply_to'] = cleaned_reply_to

    for field, value in cleaned.items():
        error = _validate_meta_value(field, value)
        if error:
            return None, None, error

    if body is None or not str(body).strip():
        return None, None, "Body is required"

    envelope = render_envelope(
        message_id=cleaned['id'],
        message_type=message_type,
        from_agent=cleaned['from'],
        to_agent=cleaned['to'],
        body=str(body),
        footer=_clean_optional_text(footer),
        reply_to=cleaned_reply_to,
    )
    return envelope, cleaned['id'], ""


def _agent_meta_name(agent_config: dict, fallback: str) -> str:
    return str(agent_config.get('file_id') or agent_config.get('name') or fallback)


def _resolve_target(args: Any, deps: Any, *, value: str) -> tuple[Optional[dict], str, str]:
    agent_config = deps.resolve_agent(value)
    if not agent_config:
        return None, "", f"Agent not found: {value}"
    return agent_config, _agent_meta_name(agent_config, value), ""


def _send_envelope(args: Any, deps: Any, *, target_config: dict, envelope: str) -> int:
    check_tmux = deps.check_tmux
    session_exists = deps.session_exists
    get_agent_id = deps.get_agent_id
    resolve_launcher_command = deps.resolve_launcher_command
    send_keys = deps.send_keys

    agent_name = target_config['name']
    agent_id = get_agent_id(target_config)

    if not check_tmux():
        print("❌ tmux is not installed")
        return 1

    if not session_exists(agent_id):
        print(f"⚠️  Agent '{agent_name}' is not running")
        return 1

    launcher = resolve_launcher_command(target_config.get('launcher', ''))
    is_codex = 'codex' in launcher.lower()
    if not send_keys(
        agent_id,
        envelope,
        send_enter=True,
        clear_input=is_codex,
        escape_first=is_codex,
        enter_via_key=is_codex,
    ):
        print(f"❌ Failed to send protocol message to {agent_name}")
        return 1

    print(f"✅ Protocol message sent to {agent_name}")
    print("   Note: delivery success only means tmux accepted the send operation.")
    return 0


def cmd_message(args: Any, *, deps: Any) -> int:
    command = getattr(args, 'message_command', None)
    if command == 'compose':
        envelope, _message_id, error = build_envelope(
            deps=deps,
            message_type='message',
            from_agent=args.from_agent,
            to_agent=args.to_agent,
            body=args.body,
            footer=getattr(args, 'footer', None),
            message_id=getattr(args, 'id', None),
        )
        if error:
            print(f"❌ {error}")
            return 1
        print(envelope)
        return 0

    if command == 'send':
        target_config, to_agent, error = _resolve_target(args, deps, value=args.agent)
        if error:
            print(f"❌ {error}")
            return 1
        envelope, _message_id, error = build_envelope(
            deps=deps,
            message_type='message',
            from_agent=args.from_agent,
            to_agent=to_agent,
            body=args.body,
            footer=getattr(args, 'footer', None),
            message_id=getattr(args, 'id', None),
        )
        if error:
            print(f"❌ {error}")
            return 1
        return _send_envelope(args, deps, target_config=target_config, envelope=envelope)

    if command == 'reply':
        target_config, to_agent, error = _resolve_target(args, deps, value=args.to_agent)
        if error:
            print(f"❌ {error}")
            return 1
        envelope, _message_id, error = build_envelope(
            deps=deps,
            message_type='reply',
            from_agent=args.from_agent,
            to_agent=to_agent,
            body=args.body,
            footer=getattr(args, 'footer', None),
            message_id=getattr(args, 'id', None),
            reply_to=args.reply_to,
        )
        if error:
            print(f"❌ {error}")
            return 1
        return _send_envelope(args, deps, target_config=target_config, envelope=envelope)

    print("❌ Missing message subcommand")
    return 1
