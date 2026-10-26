from __future__ import annotations
import json
from .base import SystemController, result

class WindowsController(SystemController):
    system='Windows'
    def _op_theme(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                light=winreg.QueryValueEx(key,'AppsUseLightTheme')[0]
            return {'theme':'light' if light else 'dark','source':'registry','known':True}
        except OSError:return {'theme':'dark','source':'fallback','known':False}
    def _op_window_list(self):
        import ctypes
        from ctypes import wintypes
        user=ctypes.windll.user32;items=[]
        callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        def collect(hwnd,_):
            if user.IsWindowVisible(hwnd):
                length=user.GetWindowTextLengthW(hwnd)
                if length:
                    buf=ctypes.create_unicode_buffer(length+1);user.GetWindowTextW(hwnd,buf,len(buf))
                    items.append({'id':int(hwnd),'title':buf.value})
            return True
        user.EnumWindows(callback(collect),0);return items
    def _op_volume(self,value):
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities,IAudioEndpointVolume
        import ctypes
        endpoint=AudioUtilities.GetSpeakers().Activate(IAudioEndpointVolume._iid_,CLSCTX_ALL,None)
        volume=ctypes.cast(endpoint,ctypes.POINTER(IAudioEndpointVolume))
        level=max(0,min(100,int(value)));volume.SetMasterVolumeLevelScalar(level/100,None)
        return {'percent':level}
    def _op_brightness(self,value):
        level=max(0,min(100,int(value)))
        return self._command(['powershell','-NoProfile','-Command',f'$m=Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop; if (!$m) {{ throw "No supported brightness device" }}; $m | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1;Brightness=[byte]{level}}} -ErrorAction Stop'])
    def _op_power(self,action):
        commands={'shutdown':['shutdown.exe','/s','/t','0'],'restart':['shutdown.exe','/r','/t','0'],
                  'sleep':['powershell','-NoProfile','-Command','Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState([System.Windows.Forms.PowerState]::Suspend,$false,$false)']}
        if action not in commands:raise ValueError('Unknown power action')
        return self._command(commands[action])
    def _elevated_command(self,command,cwd=None):
        # UAC owns credentials. A cancelled elevation reports an OS error.
        import ctypes
        from ctypes import wintypes
        from .processes import REGISTRY, NativeProcess
        class SHELLEXECUTEINFO(ctypes.Structure):
            _fields_=[('cbSize',wintypes.DWORD),('fMask',ctypes.c_ulong),('hwnd',wintypes.HWND),('lpVerb',wintypes.LPCWSTR),('lpFile',wintypes.LPCWSTR),('lpParameters',wintypes.LPCWSTR),('lpDirectory',wintypes.LPCWSTR),('nShow',ctypes.c_int),('hInstApp',wintypes.HINSTANCE),('lpIDList',ctypes.c_void_p),('lpClass',wintypes.LPCWSTR),('hkeyClass',wintypes.HKEY),('dwHotKey',wintypes.DWORD),('hIcon',wintypes.HANDLE),('hProcess',wintypes.HANDLE)]
        import base64
        encoded=base64.b64encode(command.encode('utf-16-le')).decode()
        info=SHELLEXECUTEINFO();info.cbSize=ctypes.sizeof(info);info.fMask=0x40;info.lpVerb='runas';info.lpFile='powershell.exe';info.lpParameters='-NoProfile -EncodedCommand '+encoded;info.lpDirectory=cwd;info.nShow=1
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):raise OSError('UAC elevation denied or unavailable')
        kernel=ctypes.windll.kernel32
        try:
            kernel.GetProcessId.argtypes=[wintypes.HANDLE];kernel.GetProcessId.restype=wintypes.DWORD
            pid=kernel.GetProcessId(info.hProcess);proc=NativeProcess(pid);REGISTRY.add(proc)
            code=proc.wait(timeout=120)
            return result(code == 0, {'pid':pid,'exit_code':code,'elevated':True,'output':'Elevated output is owned by the OS window'}, None if code == 0 else 'Elevated completion failed or could not be verified')
        finally:kernel.CloseHandle(info.hProcess)
