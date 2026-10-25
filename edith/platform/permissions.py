"""Backend-owned tiers and cancellation; UI cannot grant itself approval."""
from __future__ import annotations
import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
import json
import re
import threading

class PermissionDenied(RuntimeError): pass
class ActionCancelled(RuntimeError): pass

@dataclass(frozen=True)
class ExecutionContext:
    actor: str
    generation: int

CURRENT = contextvars.ContextVar('edith_execution_context', default=None)
_APPROVED_OPERATIONS = contextvars.ContextVar('edith_approved_operations', default=frozenset())
_CRITICAL = re.compile(r'(?i)(\bsudo\b|\brunas\b|\bshutdown\b|\breboot\b|\bsystemctl\s+(?:poweroff|reboot|suspend)|\b(?:diskpart|mkfs|format)\b|\breg(?:\.exe)?\s+(?:add|delete|import)|(?:Set|New|Remove)-ItemProperty|HKEY_|/etc/|/System/|Start-Process[^\n]*-Verb\s+RunAs)')

def operation_tier(operation, arguments=None):
    args = arguments or {}
    if operation.startswith('file_'):
        path=str(args.get('path','')).replace('\\','/').lower()
        if operation not in {'file_list','file_read'} and (path.startswith(('/etc/','/system/','/usr/','/boot/')) or re.match(r'^[a-z]:/(windows|program files)(/|$)',path)):
            return 3
    if operation in {'telemetry','process_list','network_info','window_list','installed_apps','theme','capabilities','clipboard_get','screenshot','file_list','file_read','system_info'}:
        return 0
    if operation in {'power','elevate','registry','system_config'}:
        return 3
    if operation == 'shell':
        return 3 if args.get('elevated') or _CRITICAL.search(str(args.get('command',''))) else 2
    if operation in {'file_delete','file_write','file_move','process_kill','volume','brightness','setting','install','uninstall','clipboard_set'}:
        return 2
    if operation in {'file_create','folder_create','app_launch','url_open','preference'}:
        return 1
    return 2

def tool_tier(name, args):
    action = str(args.get('action') or '').lower().replace('-','_')
    if name in {'system_status','performance_metrics','web_search','task_history','screen_process','close_camera'}:
        return 0 if name != 'close_camera' else 1
    if name == 'platform_system':
        return operation_tier(str(args.get('operation','')), args.get('arguments') or {})
    if name == 'shell_execute':
        return operation_tier('shell', args)
    if name == 'shutdown_edith':
        return 3
    if name == 'file_controller':
        if action in {'list','read','find','info','largest','disk_usage'}: return 0
        if action in {'create','create_folder','create_folders','mkdir'}: return 1
        return 2
    if name == 'open_app': return 0 if action in {'list','search','find','discover','list_installed'} else 1
    if name in {'save_memory','set_voice_mode','manage_monitor'}: return 1
    if name == 'computer_settings':
        if action in {'restart','shutdown','sleep','sleep_display','dark_mode','toggle_wifi'}: return 3 if action in {'restart','shutdown','sleep'} else 2
        return 2
    if name in {'browser_control','computer_control'}:
        if action in {'get_text','get_url','screenshot','clipboard_get','list','list_sessions'}: return 0
        if action in {'open','goto','go_to','search','new_tab'}: return 1
        return 2
    # Code/install/plugins can run commands or mutate files; unknown defaults sensitive.
    return 2

class PermissionBroker:
    def __init__(self, confirmer=None, settings=None):
        self.confirmer = confirmer
        self.settings = settings or {}
        self._generation = 0
        self._lock = threading.Lock()

    @property
    def generation(self):
        with self._lock: return self._generation

    def cancel_all(self):
        with self._lock: self._generation += 1

    def check_cancelled(self):
        ctx = CURRENT.get()
        if ctx and ctx.generation != self.generation:
            raise ActionCancelled('Interrupted by the user; action not started')

    @contextmanager
    def approved_context(self, *operations):
        """Carry one dispatcher approval into a worker thread without trusting model args.

        ``asyncio.to_thread`` copies context variables, so a confirmation obtained by
        the dispatcher can satisfy the same backend broker inside a controlled tool.
        The token is reset by the caller after the tool returns; a model-provided
        ``confirmed`` field never populates this context.
        """
        current = set(_APPROVED_OPERATIONS.get())
        current.update(str(op) for op in operations)
        token = _APPROVED_OPERATIONS.set(frozenset(current))
        try:
            yield token
        finally:
            _APPROVED_OPERATIONS.reset(token)

    def tier(self, operation, arguments, minimum=None):
        floor = operation_tier(operation, arguments) if minimum is None else int(minimum)
        try:
            configured = int(self.settings.get('tiers', {}).get(operation, floor))
        except (TypeError, ValueError, AttributeError):
            configured = floor
        return max(floor, min(3, configured))

    def authorize(self, operation, arguments, *, minimum=None, preapproved=False):
        self.check_cancelled()
        tier = self.tier(operation, arguments, minimum)
        if tier >= 2:
            # Never trust an argument such as confirmed=true or autoApprove.
            context_approved = operation in _APPROVED_OPERATIONS.get()
            if not preapproved and not context_approved and self.confirmer is None:
                raise PermissionDenied('Local confirmation is required before this action')
            if not preapproved and not context_approved:
                from .audit import redact
                preview = json.dumps(redact(arguments), ensure_ascii=False, indent=2, default=str)
                if not self.confirmer(f'Tier {tier} · Review {operation}', preview):
                    raise PermissionDenied('Cancelled or expired; nothing was executed')
            self.check_cancelled()
        return tier
