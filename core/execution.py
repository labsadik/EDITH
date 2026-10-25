"""Confirmed, streamed execution shared by shell and legacy coding tools."""
from __future__ import annotations
import asyncio
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import threading

from edith.platform import get_controller
from edith.platform.audit import AuditLog,redact
from edith.platform.base import result
from edith.platform.permissions import CURRENT,ExecutionContext,PermissionBroker,PermissionDenied,ActionCancelled
from edith.platform.processes import run_streamed,REGISTRY

class ExecutionService:
    def __init__(self,confirmer=None,output=None,audit=None):
        self.broker=PermissionBroker(confirmer=confirmer)
        self.output=output
        self.audit=audit or AuditLog()
        self.controller=get_controller(permissions=self.broker,audit=self.audit)

    @contextmanager
    def job(self,actor='code-tool'):
        token=CURRENT.set(ExecutionContext(actor,self.broker.generation))
        try:yield
        finally:CURRENT.reset(token)

    def emit(self,stream,text):
        if self.output:
            self.output(f'SHELL {stream}: {redact(text)}')

    def cancel(self):
        self.broker.cancel_all()
        threading.Thread(target=REGISTRY.cancel_all,daemon=True).start()

    def run_argv(self,argv,*,cwd=None,timeout=30,source_path=None,source=None,input_data=None):
        """Run the exact source through an audited, interruptible worker."""
        args={'argv':[str(v) for v in argv],'cwd':str(Path(cwd).expanduser().resolve()) if cwd else None,'timeout':timeout}
        token=None
        if CURRENT.get() is None:token=CURRENT.set(ExecutionContext('local-user',self.broker.generation))
        tier=2
        try:
            if not argv:raise ValueError('Empty command')
            if source_path:
                path=Path(source_path).expanduser().resolve()
                if path.stat().st_size>1_000_000:raise ValueError('Code exceeds the local review limit')
                source=path.read_text(encoding='utf-8',errors='replace')
                args['source_path']=str(path)
            if source is not None:
                args['source_sha256']=hashlib.sha256(source.encode()).hexdigest()
            preview={**args,'command':subprocess.list2cmdline(args['argv']) if os.name=='nt' else shlex.join(args['argv'])}
            if source is not None:preview['source']=source
            tier=self.broker.authorize('shell',preview)
            if source_path and path.read_text(encoding='utf-8',errors='replace')!=source:
                raise PermissionDenied('Code changed before execution; request execution again')
            value=run_streamed(args['argv'],cwd=args['cwd'],timeout=timeout,on_output=self.emit,broker=self.broker,input_data=input_data)
            ok=value['exit_code']==0 and not value['timed_out'] and not value['cancelled']
            receipt=result(ok,value,None if ok else 'Execution cancelled' if value['cancelled'] else 'Execution timed out' if value['timed_out'] else 'Execution failed')
        except (PermissionDenied,ActionCancelled) as exc:receipt=result(False,error='Execution cancelled: '+str(exc))
        except Exception as exc:receipt=result(False,error='Execution failed: '+str(redact(str(exc))))
        try:self.audit.write((CURRENT.get().actor if CURRENT.get() else 'local-user'),'code.execute',args,tier,receipt)
        except Exception:receipt=result(False,data=receipt,error='Execution failed: audit receipt unavailable; do not retry without checking the process result')
        finally:
            if token is not None:CURRENT.reset(token)
        return receipt

    def shell(self,command,cwd=None,timeout=60):
        return self.controller.shell(command,cwd,timeout,on_output=self.emit)

SERVICE=ExecutionService()

def configure_execution(ui):
    SERVICE.broker.confirmer=None
    SERVICE.broker.settings={'unattended':True}
    SERVICE.output=ui.write_log
    # The shared audit object is also used by the platform controller.  Attach
    # one redacted, thread-safe activity stream so controller and code receipts
    # become visible in the existing Activity Log without exposing arguments.
    def _audit_listener(entry):
        operation = str(entry.get('operation', 'action')) if isinstance(entry, dict) else 'action'
        result_value = entry.get('result') if isinstance(entry, dict) else None
        if operation.endswith('.start'):
            state = 'START'
        elif isinstance(result_value, dict):
            state = 'OK' if result_value.get('ok') else 'FAILED'
        else:
            state = 'RECORDED'
        ui.write_log(
            f"AUDIT {operation} · "
            f"tier {entry.get('tier', '?')} · {state}"
        )
    SERVICE.audit.listener=_audit_listener
    SERVICE.controller.audit.listener=_audit_listener

async def run_code_tool(handler,**kwargs):
    with SERVICE.job(getattr(handler,'__name__','code-tool')):
        return await asyncio.to_thread(handler,**kwargs)

def format_execution(receipt):
    data=receipt.get('data') or {}
    if not receipt['ok']:
        error=str(receipt.get('error') or '')
        prefix=('Execution cancelled: '+error) if data.get('cancelled') or 'cancel' in error.lower() or 'expired' in error.lower() else ('Execution timed out: '+error) if data.get('timed_out') else 'Execution failed: '+error
        return prefix+'\n'+str(data.get('stderr') or data.get('stdout') or '')
    return 'Exit code: 0\n'+('STDOUT:\n'+data['stdout'] if data.get('stdout') else '')+('\nSTDERR:\n'+data['stderr'] if data.get('stderr') else '')

def stopped(text):
    return str(text).startswith(('Execution cancelled','Execution timed out'))

