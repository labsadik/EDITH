"""Public capability interface; every mutation crosses the permission boundary."""
from __future__ import annotations
import os
import platform
import shutil
import subprocess
from pathlib import Path
import contextvars
from .audit import AuditLog, redact
from .permissions import PermissionBroker, CURRENT, ExecutionContext, PermissionDenied, ActionCancelled
from .processes import REGISTRY, run_streamed, shell_argv, _ORIGINAL_POPEN

def result(ok=True, data=None, error=None, unsupported=False):
    return {'ok':bool(ok),'data':data,'error':error,'unsupported':bool(unsupported)}

class SystemController:
    system = 'Generic'
    OPERATIONS = ('telemetry','system_info','process_list','process_kill','shell','file_list','file_read',
        'file_create','folder_create','file_write','file_delete','file_move','app_launch','url_open',
        'window_list','clipboard_get','clipboard_set','screenshot','volume','brightness','network_info',
        'power','installed_apps','theme','capabilities','hardware_inventory',
        'display_list','audio_devices')

    def __init__(self, *, permissions=None, audit=None):
        self.permissions = permissions or PermissionBroker()
        self.audit = audit or AuditLog()
        self._collector = None

    def invoke(self, operation, arguments=None, *, on_output=None):
        args = {}
        ctx = CURRENT.get()
        token = None
        if ctx is None:
            ctx = ExecutionContext('local-user', self.permissions.generation)
            token = CURRENT.set(ctx)
        tier = 2
        try:
            args = dict(arguments or {})
            tier = self.permissions.tier(operation,args)
            if operation not in self.OPERATIONS:
                raise NotImplementedError('Unknown system capability: '+str(operation))
            self.permissions.authorize(operation,args)
            self.permissions.check_cancelled()
            method = getattr(self,'_op_'+operation,None)
            if method is None: raise NotImplementedError(f'{operation} is unavailable on {self.system}')
            data = method(**args, **({'on_output':on_output} if operation=='shell' else {}))
            value = data if isinstance(data,dict) and set(('ok','data','error','unsupported')).issubset(data) else result(data=data)
        except (NotImplementedError, ImportError) as exc:
            value = result(False,error=str(exc),unsupported=True)
        except (PermissionDenied,ActionCancelled) as exc:
            value = result(False,error=str(exc))
        except Exception as exc:
            value = result(False,error=redact(f'{type(exc).__name__}: {exc}'))
        try:
            self.audit.write(ctx.actor,operation,args,tier,value)
        except Exception:
            value = result(False,data=value,error="Audit receipt unavailable; inspect action result before retrying")
        finally:
            if token is not None: CURRENT.reset(token)
        return value

    # Explicit stable public interface, including direct callers outside the UI.
    def telemetry(self): return self.invoke('telemetry')
    def system_info(self): return self.invoke('system_info')
    def process_list(self): return self.invoke('process_list')
    def process_control(self,pid): return self.invoke('process_kill',{'pid':pid})
    def shell(self,command,cwd=None,timeout=60,on_output=None,elevated=False):
        return self.invoke('shell',dict(command=command,cwd=cwd,timeout=timeout,elevated=elevated),on_output=on_output)
    def file_operations(self,operation,**args): return self.invoke(operation,args)
    def app_launch(self,app): return self.invoke('app_launch',{'app':app})
    def window_list(self): return self.invoke('window_list')
    def clipboard(self,text=None): return self.invoke('clipboard_get' if text is None else 'clipboard_set',{} if text is None else {'text':text})
    def screenshot(self,monitor=1): return self.invoke('screenshot',{'monitor':monitor})
    def volume(self,value): return self.invoke('volume',{'value':value})
    def brightness(self,value): return self.invoke('brightness',{'value':value})
    def network_info(self): return self.invoke('network_info')
    def power(self,action): return self.invoke('power',{'action':action})
    def installed_apps(self): return self.invoke('installed_apps')
    def theme(self): return self.invoke('theme')
    def hardware_inventory(self): return self.invoke('hardware_inventory')
    def display_list(self): return self.invoke('display_list')
    def audio_devices(self): return self.invoke('audio_devices')

    def _read_command(self,argv,timeout=3):
        completed = subprocess.run(argv,capture_output=True,text=True,timeout=timeout,check=False)
        if completed.returncode: raise OSError(completed.stderr.strip() or f'{argv[0]} exited {completed.returncode}')
        return completed.stdout.strip()

    def _command(self,argv):
        output = run_streamed(argv,broker=self.permissions,timeout=30)
        ok = output["exit_code"] == 0 and not output["cancelled"] and not output["timed_out"]
        return result(ok,output,None if ok else "Native command failed or was interrupted")

    def _op_system_info(self):
        return {'os':self.system,'release':platform.release(),'kernel':platform.version(),
                'architecture':platform.machine(),'python':platform.python_version()}
    def _op_capabilities(self):
        return {'system':self.system,'operations':list(self.OPERATIONS),
                'note':'Each operation reports actual permission/dependency failure at execution; declared availability is not a device test.'}
    def _hardware_snapshot(self):
        from .hardware import collect_hardware_inventory
        return collect_hardware_inventory(self.system, self._read_command)
    def _op_hardware_inventory(self):
        return self._hardware_snapshot()
    def _op_display_list(self):
        return self._hardware_snapshot().get('displays', [])
    def _op_audio_devices(self):
        return self._hardware_snapshot().get('audio_devices', [])
    def _op_telemetry(self):
        if self._collector is None:
            from .telemetry import TelemetryCollector
            self._collector = TelemetryCollector(system=self.system,read_command=self._read_command)
        return self._collector.sample()
    def _op_network_info(self):
        import psutil
        stats = psutil.net_if_stats()
        return {'interfaces':{name:{'addresses':[a.address for a in addresses],
                'up':bool(stats[name].isup) if name in stats else None,
                'link_speed_mbps':stats[name].speed if name in stats else None}
                for name,addresses in psutil.net_if_addrs().items()},
                'note':'Link speed and throughput are not measured Internet download speed.'}
    def _op_process_list(self):
        import psutil
        items=[]
        for proc in psutil.process_iter(['pid','name','status','cpu_percent','memory_info']):
            try:
                p=proc.info; mem=p.get('memory_info')
                items.append({'pid':p['pid'],'name':p['name'],'status':p['status'],
                              'cpu_percent':p.get('cpu_percent'),'rss':mem.rss if mem else None})
            except psutil.Error: continue
        return items
    def _op_process_kill(self,pid):
        import psutil
        pid=int(pid)
        if pid in {0,1,os.getpid(),os.getppid()}: raise PermissionDenied('Protected EDITH/parent/system process')
        process=psutil.Process(pid)
        process.terminate()
        try: process.wait(timeout=3)
        except psutil.TimeoutExpired: raise OSError('Process did not exit; forced kill requires another explicit request')
        return {'pid':pid,'terminated':True}
    def _op_shell(self,command,cwd=None,timeout=60,elevated=False,on_output=None):
        if not str(command).strip(): raise ValueError('Command is empty')
        if cwd is not None and not Path(cwd).expanduser().is_dir(): raise ValueError('Working directory does not exist')
        if elevated:
            return self._elevated_command(str(command),cwd)
        if cwd is not None: cwd=str(Path(cwd).expanduser().resolve())
        output=run_streamed(shell_argv(str(command),self.system),cwd=cwd,timeout=min(3600,max(.1,float(timeout))),on_output=on_output,broker=self.permissions)
        return result(output['exit_code']==0 and not output['timed_out'] and not output['cancelled'],output,
                      'Interrupted' if output['cancelled'] else 'Command timed out' if output['timed_out'] else None if output['exit_code']==0 else 'Command failed')
    def _elevated_command(self,command,cwd=None):
        raise NotImplementedError('Native elevation is not available on this OS')
    def _path(self,path): return Path(path).expanduser().resolve()
    def _op_file_list(self,path):
        return [{'name':p.name,'directory':p.is_dir(),'bytes':p.stat().st_size if p.is_file() else None} for p in self._path(path).iterdir()]
    def _op_file_read(self,path):
        p=self._path(path)
        if p.stat().st_size>2_000_000: raise ValueError('Use the existing file processor for files over 2 MB')
        return {'path':str(p),'text':p.read_text(encoding='utf-8',errors='replace')}
    def _op_file_create(self,path,text=''):
        p=self._path(path);p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('x',encoding='utf-8') as f:f.write(str(text))
        return {'path':str(p),'created':True}
    def _op_folder_create(self,path):
        p=self._path(path);p.mkdir(parents=True,exist_ok=False);return {'path':str(p)}
    def _op_file_write(self,path,text=''):
        p=self._path(path);p.write_text(str(text),encoding='utf-8');return {'path':str(p),'bytes':p.stat().st_size}
    def _op_file_delete(self,path):
        from send2trash import send2trash
        p=self._path(path)
        if p in {Path.home().resolve(),Path(p.anchor)}:raise PermissionDenied('Refusing a home/filesystem root')
        send2trash(str(p));return {'path':str(p),'trashed':True}
    def _op_file_move(self,path,destination):
        src,dst=self._path(path),self._path(destination)
        if dst.exists():raise FileExistsError('Destination exists; explicit overwrite operation required')
        shutil.move(str(src),str(dst));return {'path':str(dst)}
    def _op_app_launch(self,app):
        from actions.open_app import open_app
        return open_app(parameters={'action':'open','app_name':str(app)})
    def _op_url_open(self,url):
        from urllib.parse import urlsplit
        if urlsplit(url).scheme not in {'https','http'}:raise ValueError('Only HTTP/HTTPS URLs are allowed')
        import webbrowser
        return {'opened':bool(webbrowser.open(url))}
    def _op_installed_apps(self):
        from actions.open_app import discover_installed_apps
        return discover_installed_apps()
    def _op_clipboard_get(self):
        import pyperclip
        return {'text':pyperclip.paste()}
    def _op_clipboard_set(self,text):
        import pyperclip
        pyperclip.copy(str(text));return {'updated':True}
    def _op_screenshot(self,monitor=1):
        import base64
        import mss,mss.tools
        if self.system=='Linux' and os.environ.get('WAYLAND_DISPLAY') and not os.environ.get('DISPLAY'):
            raise NotImplementedError('Wayland screenshot portal is required; X11 MSS capture is unavailable')
        with mss.mss() as sct:
            index=int(monitor)
            if not 0<=index<len(sct.monitors):raise ValueError('Unknown monitor')
            image=sct.grab(sct.monitors[index]);data=mss.tools.to_png(image.rgb,image.size)
        return {'mime_type':'image/png','base64':base64.b64encode(data).decode()}
