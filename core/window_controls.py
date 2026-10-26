"""Screen-aware placement for native operating-system window decorations."""
from PyQt6.QtCore import QRect


def initial_geometry(screen, default_width, default_height):
    """Keep the initial frame inside the work area, including nonzero origins.

    Leave space for native frame decorations; centering a fixed 780px client
    window on a 720px work area previously placed its title bar above the screen.
    """
    width = min(default_width, max(320, screen.width() - 32))
    height = min(default_height, max(300, screen.height() - 64))
    return QRect(screen.left() + max(16, (screen.width()-width)//2),
                 screen.top() + max(32, (screen.height()-height)//2), width, height)

