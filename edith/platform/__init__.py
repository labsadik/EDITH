"""Select capabilities from the real OS, not a saved installation label."""
import platform

def get_controller(system=None, **kwargs):
    name = system or platform.system()
    if name == 'Windows':
        from .windows import WindowsController as Controller
    elif name == 'Darwin':
        from .macos import MacOSController as Controller
    elif name == 'Linux':
        from .linux import LinuxController as Controller
    else:
        from .generic import GenericController as Controller
    return Controller(**kwargs)
