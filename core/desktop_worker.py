"""Worker for generated desktop snippets, always launched by the Rust sandbox.

The reduced builtin namespace is defense in depth only; the OS-enforced
AppContainer/bubblewrap/Seatbelt boundary is the security isolation layer.
Use native computer-control tools for real foreground desktop interaction.
"""
import json
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

def run(source):
    safe={}
    import builtins
    for name in ('print','len','str','int','float','bool','list','dict','tuple','range','enumerate','sorted','isinstance','hasattr','getattr','max','min','sum','abs','zip','map','filter'):
        safe[name]=getattr(builtins,name)
    scope={'__builtins__':safe,'Path':Path,'time':time,'shutil':SimpleNamespace(copy2=shutil.copy2,copytree=shutil.copytree,disk_usage=shutil.disk_usage),'os_path':__import__('os').path}
    try:
        import pyautogui
        scope['pyautogui']=pyautogui
    except Exception:pass
    if sys.platform=='win32':
        import ctypes,winreg
        scope.update(ctypes=ctypes,winreg=SimpleNamespace(OpenKey=winreg.OpenKey,QueryValueEx=winreg.QueryValueEx,HKEY_CURRENT_USER=winreg.HKEY_CURRENT_USER))
    exec(compile(source,'<approved-desktop-task>','exec'),scope)

if __name__=='__main__':
    run(json.load(sys.stdin)['source'])
