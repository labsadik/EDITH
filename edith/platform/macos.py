from __future__ import annotations
import json
import shutil
from .base import SystemController

class MacOSController(SystemController):
    system='Darwin'
    def _op_theme(self):
        try:value=self._read_command(['defaults','read','-g','AppleInterfaceStyle'])
        except FileNotFoundError:return {'theme':'dark','source':'fallback','known':False}
        except OSError:return {'theme':'light','source':'defaults','known':True}
        return {'theme':'dark' if value.strip().lower()=='dark' else 'light','source':'defaults','known':True}
    def _op_window_list(self):
        text=self._read_command(['osascript','-e','tell application "System Events" to get name of every process whose background only is false'])
        return [{'title':x.strip()} for x in text.split(',') if x.strip()]
    def _op_volume(self,value):
        level=max(0,min(100,int(value)))
        return self._command(['osascript','-e',f'set volume output volume {level}'])
    def _op_brightness(self,value):
        tool=shutil.which('brightness')
        if not tool:raise NotImplementedError('Install a compatible brightness utility for supported displays')
        return self._command([tool,str(max(0,min(100,int(value)))/100)])
    def _op_power(self,action):
        commands={'shutdown':'shut down','restart':'restart','sleep':'sleep'}
        if action not in commands:raise ValueError('Unknown power action')
        return self._command(['osascript','-e','tell application "System Events" to '+commands[action]])
    def _elevated_command(self,command,cwd=None):
        import shlex
        if cwd:command='cd '+shlex.quote(cwd)+' && '+command
        return self._command(['osascript','-e','do shell script '+json.dumps(command)+' with administrator privileges'])
