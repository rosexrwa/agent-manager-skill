from __future__ import annotations
from typing import Callable, Optional


def get_command_handlers(
    *,
    cmd_list: Callable,
    cmd_doctor: Callable,
    cmd_adapter: Optional[Callable] = None,
    cmd_start: Callable,
    cmd_stop: Callable,
    cmd_status: Callable,
    cmd_monitor: Callable,
    cmd_send: Callable,
    cmd_assign: Callable,
    cmd_schedule: Callable,
    cmd_heartbeat: Callable,
    cmd_dream: Callable,
    cmd_timer: Callable,
    cmd_inbound: Callable,
) -> dict[str, Callable]:
    handlers = {
        'list': cmd_list,
        'doctor': cmd_doctor,
        'start': cmd_start,
        'stop': cmd_stop,
        'status': cmd_status,
        'monitor': cmd_monitor,
        'send': cmd_send,
        'assign': cmd_assign,
        'schedule': cmd_schedule,
        'heartbeat': cmd_heartbeat,
        'dream': cmd_dream,
        'timer': cmd_timer,
        'inbound': cmd_inbound,
    }
    if cmd_adapter is not None:
        handlers['adapter'] = cmd_adapter
    return handlers
