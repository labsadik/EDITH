from __future__ import annotations
import configparser
import os
from pathlib import Path
import shutil
from .base import SystemController

class LinuxController(SystemController):
    system='Linux'
    def _op_theme(self):
        if shutil.which('gsettings'):
            try:
                value=self._read_command(['gsettings','get','org.gnome.desktop.interface','color-scheme'])
                if 'prefer-dark' in value:return {'theme':'dark','source':'gsettings','known':True}
                if 'prefer-light' in value or 'default' in value:return {'theme':'light','source':'gsettings','known':True}
            except Exception:pass
        parser=configparser.ConfigParser()
        parser.read(Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'kdeglobals')
        name=parser.get('General','ColorScheme',fallback='')
        if name:return {'theme':'dark' if 'dark' in name.lower() else 'light','source':'kdeglobals','known':True}
        return {'theme':'dark','source':'fallback','known':False}
    def _op_window_list(self):
        if os.environ.get('WAYLAND_DISPLAY'):raise NotImplementedError('Wayland requires a compositor-specific window API')
        if not shutil.which('wmctrl'):raise NotImplementedError('Install wmctrl for X11 window listing')
        return [{'id':parts[0],'desktop':parts[1],'title':parts[3]} for line in self._read_command(['wmctrl','-l']).splitlines() if len(parts:=line.split(None,3))==4]
    def _op_volume(self,value):
        level=max(0,min(100,int(value)))
        if shutil.which('pactl'):return self._command(['pactl','set-sink-volume','@DEFAULT_SINK@',f'{level}%'])
        if shutil.which('wpctl'):return self._command(['wpctl','set-volume','@DEFAULT_AUDIO_SINK@',str(level/100)])
        raise NotImplementedError('PulseAudio/PipeWire volume control is unavailable')
    def _op_brightness(self,value):
        if not shutil.which('brightnessctl'):raise NotImplementedError('brightnessctl and a supported backlight device are required')
        return self._command(['brightnessctl','set',f'{max(0,min(100,int(value)))}%'])
    def _op_power(self,action):
        actions={'shutdown':'poweroff','restart':'reboot','sleep':'suspend'}
        if action not in actions:raise ValueError('Unknown power action')
        if not shutil.which('systemctl'):raise NotImplementedError('systemd/logind power actions are unavailable')
        # Polkit's graphical authentication agent handles any required elevation.
        return self._command(['systemctl','--no-ask-password',actions[action]])
    def _elevated_command(self,command,cwd=None):
        if not shutil.which('pkexec'):raise NotImplementedError('pkexec with a graphical polkit agent is required')
        import shlex
        if cwd:command='cd '+shlex.quote(cwd)+' && '+command
        return self._command(['pkexec','--disable-internal-agent','/bin/sh','-c',command])
