"""Bundled SVG line icons for the EDITH desktop UI.

These tiny vectors are embedded locally: no CDN, remote image URL, or network request
is needed to render controls or file-type marks.
"""
from __future__ import annotations

import re

# Shared Lucide-inspired outline style, authored for this application.
_ICON_PATHS: dict[str, str] = {
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "arrow-up": '<path d="M12 20V4m-6 6 6-6 6 6"/>',
    "sliders": '<path d="M4 7h6m4 0h6M4 17h10m4 0h2"/><circle cx="12" cy="7" r="2"/><circle cx="16" cy="17" r="2"/>',
    "activity": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "folder": '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>',
    "cpu": '<rect x="6" y="6" width="12" height="12" rx="3"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4"/>',
    "minimize": '<path d="M5 12h14"/>',
    "restore": '<path d="M8 7V4h12v12h-3"/><rect x="4" y="8" width="12" height="12" rx="2"/>',
    "checkmark": '<path d="m5 12 4 4L19 6"/>',
    "key": '<circle cx="8" cy="8" r="5"/><path d="m12 12 8 8m-3-3 3-3m-6 0 3-3"/>',
    "wifi": '<path d="M3 8a15 15 0 0 1 18 0M6 12a10 10 0 0 1 12 0m-9 4a5 5 0 0 1 6 0"/><circle cx="12" cy="20" r=".75"/>',
    "rotate-left": '<path d="M4 10a8 8 0 1 1 1 8M4 4v6h6"/>',
    # Dedicated EDITH application mark: E monogram inside a rounded panel.
    # Unlike generic toolbar icons, this is used for the window/taskbar identity.
    "edith-app": (
        '<rect x="2" y="2" width="20" height="20" rx="5" />'
        '<path d="M16.5 6.5H8v11h8.5M8 12h7" stroke-width="2.2" />'
        '<path d="M5.5 5.5h.01M18.5 18.5h.01" />'
    ),
    "mic": (
        '<rect x="9" y="2.5" width="6" height="12" rx="3"/>'
        '<path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3M8.5 21h7"/>'
    ),
    "mic-off": (
        '<path d="M9 9v5a3 3 0 0 0 5.12 2.12M15 9.34V5.5a3 3 0 0 0-5.83-.9"/>'
        '<path d="M5.5 11.5a6.5 6.5 0 0 0 10.96 4.7M12 18v3M8.5 21h7M3 3l18 18"/>'
    ),
    "stop-circle": '<circle cx="12" cy="12" r="9"/><rect x="9" y="9" width="6" height="6" rx="1"/>',
    "settings": (
        '<path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z"/>'
        '<path d="m19.4 15 .1.1 1.2.9-1.2 2.1-1.4-.5a8 8 0 0 1-1.5.9l-.2 1.5h-2.4l-.3-1.5a8 8 0 0 1-1.7 0l-.3 1.5H9.3l-.2-1.5a8 8 0 0 1-1.5-.9l-1.4.5L5 16l1.2-.9a7 7 0 0 1-.3-1.6L4.5 13v-2.4L6 10.3a7 7 0 0 1 .7-1.6L6 7.4l1.7-1.7 1.2.7a7 7 0 0 1 1.6-.5l.4-1.4h2.4l.4 1.4a7 7 0 0 1 1.6.5l1.2-.7 1.7 1.7-.7 1.3a7 7 0 0 1 .7 1.6l1.5.3V13l-1.5.4a7 7 0 0 1-.4 1.6Z"/>'
    ),
    "puzzle": (
        '<path d="M4 4h5a2.5 2.5 0 1 1 5 0h5v5a2.5 2.5 0 1 0 0 5v6h-6a2.5 2.5 0 1 0-5 0H4v-6a2.5 2.5 0 1 1 0-5V4Z"/>'
    ),
    "camera": (
        '<path d="M4 7h3l1.5-2h7L17 7h3v12H4z"/>'
        '<circle cx="12" cy="13" r="3.5"/>'
    ),
    "x": '<path d="m6 6 12 12M18 6 6 18"/>',
    "upload": '<path d="M12 16V4m-5 5 5-5 5 5M4 16v4h16v-4"/>',
    "paperclip": '<path d="m8 12.5 6.8-6.8a3.1 3.1 0 0 1 4.4 4.4l-8.7 8.7a5 5 0 0 1-7.1-7.1l8.1-8.1"/>',
    "file-image": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M8 17l2.5-3 2.5 2 2-2 2 3"/>'
        '<circle cx="9" cy="10.5" r="1"/>'
    ),
    "file-video": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M9 12l6 3-6 3z"/>'
    ),
    "file-audio": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M10 16V11l5-1v5"/>'
        '<circle cx="8.5" cy="16.5" r="1.5"/><circle cx="13.5" cy="15.5" r="1.5"/>'
    ),
    "file-pdf": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M8 17h2a1.5 1.5 0 0 0 0-3H8v6m5-6v6h1a3 3 0 0 0 0-6h-1"/>'
    ),
    "file-text": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M8 13h8M8 17h8"/>'
    ),
    "file-word": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M7.5 12l1.5 6 2-4 2 4 1.5-6"/>'
    ),
    "file-spreadsheet": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M8 12h8M8 16h8M12 10v8"/>'
    ),
    "file-presentation": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M8 17v-4h8v4M12 13v-2"/>'
    ),
    "file-code": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M10 12l-2 2 2 2M14 12l2 2-2 2"/>'
    ),
    "file-archive": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M10 10h4M10 13h4M10 16h4M11 7h2"/>'
    ),
    "file-data": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M8 12h8M8 16h5"/>'
    ),
    "file-generic": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6"/>'
    ),
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.65 17.65l1.42 1.42M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.65 6.35l1.42-1.42"/>'
    ),
    "maximize": (
        '<path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3"/>'
    ),
    "alert-triangle": (
        '<path d="M10.3 3.9 2.6 17.2A2 2 0 0 0 4.3 20h15.4a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0Z"/>'
        '<path d="M12 9v4M12 17h.01"/>'
    ),
}


def svg_markup(name: str, color: str = "#A5B4FC") -> str:
    """Return a standalone SVG string for a known icon, with a validated stroke color."""
    body = _ICON_PATHS.get(name, _ICON_PATHS["file-generic"])
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color or ""):
        color = "#A5B4FC"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


def svg_icon(name: str, color: str = "#A5B4FC"):
    """Create a PyQt6 QIcon from a bundled SVG; return an empty icon if SVG support is absent."""
    try:
        from PyQt6.QtCore import QByteArray, Qt
        from PyQt6.QtGui import QIcon, QPainter, QPixmap
        from PyQt6.QtSvg import QSvgRenderer

        renderer = QSvgRenderer(QByteArray(svg_markup(name, color).encode("utf-8")))
        if not renderer.isValid():
            return QIcon()
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)
    except Exception:
        try:
            from PyQt6.QtGui import QIcon
            return QIcon()
        except Exception:
            return None


def icon_names() -> tuple[str, ...]:
    """Names available for tests and UI callers."""
    return tuple(sorted(_ICON_PATHS))

