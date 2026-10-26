"""Owned process trees and a streaming shell with bounded output/timeout."""
from __future__ import annotations
import os
import codecs
import queue
import shutil
import signal
import subprocess
import threading
import time
import platform
from .permissions import CURRENT, ActionCancelled

_ORIGINAL_POPEN = subprocess.Popen

class ProcessRegistry:
    def __init__(self):
        self._lock = threading.RLock()
        self._processes = {}
        self._generation = 0

    def add(self, process):
        with self._lock:
            self._processes[process.pid] = process
            # Bound exited history; retain live handles for ownership checks.
            self._processes = {pid:p for pid,p in self._processes.items() if p.poll() is None}

    def stop(self, process):
        if getattr(process,"_edith_owns_group",False):
            try: os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError): pass
        if process.poll() is not None: return
        try:
            import psutil
            parent = psutil.Process(process.pid)
            # Capture descendants before parent termination/reparenting.
            descendants = parent.children(recursive=True)
            for child in reversed(descendants):
                try: child.terminate()
                except psutil.Error: pass
            try: parent.terminate()
            except psutil.Error: pass
            _, alive = psutil.wait_procs(descendants + [parent], timeout=.4)
            for child in alive:
                try: child.kill()
                except psutil.Error: pass
        except Exception:
            try: process.terminate()
            except OSError: pass
        if platform.system() != 'Windows':
            try:
                if os.getpgid(process.pid) == process.pid:
                    os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError): pass
        try:
            process.wait(timeout=.5)
        except subprocess.TimeoutExpired:
            try: process.kill()
            except OSError: pass

    def cancel_all(self):
        with self._lock:
            processes = list(self._processes.values())
        for process in processes: self.stop(process)
        return len(processes)

    def snapshot(self):
        with self._lock:
            return [pid for pid,p in self._processes.items() if p.poll() is None]

REGISTRY = ProcessRegistry()

def shell_argv(command, system=None):
    system = system or platform.system()
    if system == 'Windows':
        powershell = shutil.which('pwsh') or shutil.which('powershell')
        return [powershell, '-NoProfile', '-NonInteractive', '-Command', command] if powershell else [os.environ.get('COMSPEC','cmd.exe'), '/d', '/s', '/c', command]
    shell = (shutil.which('zsh') or shutil.which('bash')) if system == 'Darwin' else (shutil.which('bash') or shutil.which('sh'))
    if not shell: raise FileNotFoundError('No supported shell is installed')
    return [shell, '-c', command]

def run_streamed(argv, *, cwd=None, timeout=60, on_output=None, broker=None, output_limit=200000, input_data=None):
    if broker: broker.check_cancelled()
    ctx = CURRENT.get()
    kwargs = dict(cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                  stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL, bufsize=0)
    if platform.system() != 'Windows': kwargs['start_new_session'] = True
    process = _ORIGINAL_POPEN(argv, **kwargs)
    process._edith_owns_group = platform.system() != 'Windows'
    REGISTRY.add(process)
    if input_data is not None:
        def send_input():
            try:process.stdin.write(input_data);process.stdin.flush()
            except (OSError, BrokenPipeError):pass
            finally:process.stdin.close()
        threading.Thread(target=send_input,daemon=True).start()
    events = queue.Queue(maxsize=256)
    def read(pipe, name):
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        try:
            while True:
                chunk = os.read(pipe.fileno(),4096)
                if not chunk: break
                text = decoder.decode(chunk)
                if text: events.put((name,text))
            tail = decoder.decode(b"",final=True)
            if tail: events.put((name,tail))
        finally:
            pipe.close()
            events.put((name,None))
    for name, pipe in [('stdout',process.stdout),('stderr',process.stderr)]:
        threading.Thread(target=read, args=(pipe,name), daemon=True).start()
    output = {'stdout':'','stderr':''}
    ended = set()
    deadline = time.monotonic() + max(.1,float(timeout))
    timed_out = cancelled = False
    try:
        while len(ended) < 2:
            if broker and ctx and ctx.generation != broker.generation:
                cancelled = True; REGISTRY.stop(process)
            if time.monotonic() >= deadline and not timed_out:
                timed_out = True; REGISTRY.stop(process)
            try: name,text = events.get(timeout=.025)
            except queue.Empty:
                if process.poll() is not None and len(ended)==2: break
                continue
            if text is None: ended.add(name); continue
            remaining = output_limit-len(output[name])
            if remaining>0: output[name]+=text[:remaining]
            if on_output:
                try: on_output(name,text[:4000])
                except Exception: pass
        code = process.wait(timeout=1)
        return {'stdout':output['stdout'],'stderr':output['stderr'], 'exit_code':code,
                'pid':process.pid,'timed_out':timed_out,'cancelled':cancelled,
                'truncated':any(len(v)>=output_limit for v in output.values())}
    finally:
        if process.poll() is None: REGISTRY.stop(process)

class NativeProcess:
    """A PID returned by the native elevation API, never an arbitrary PID."""
    def __init__(self,pid):
        import psutil
        self.pid=int(pid);self._process=psutil.Process(self.pid)
    def poll(self):
        import psutil
        try:return None if self._process.is_running() and self._process.status()!=psutil.STATUS_ZOMBIE else 0
        except psutil.Error:return 0
    def wait(self,timeout=None):return self._process.wait(timeout=timeout)
    def terminate(self):self._process.terminate()
    def kill(self):self._process.kill()
