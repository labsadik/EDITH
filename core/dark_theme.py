"""Native Qt palette and popup styling for system light/dark appearance."""
from PyQt6.QtCore import QObject, QEvent
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QMenu


def popup_style(c):
    return f"""
        QMenu {{background:{c.SHEET};color:{c.TEXT};border:1px solid {c.BORDER_B};
                border-radius:12px;padding:6px;}}
        QMenu::item {{color:{c.TEXT};background:transparent;padding:8px 26px 8px 15px;
                     border-radius:7px;}}
        QMenu::item:selected {{background:{c.HOVER};color:{c.TEXT};}}
        QMenu::item:disabled {{color:{c.TEXT_DIM};}}
        QMenu::separator {{height:1px;background:{c.BORDER};margin:4px 8px;}}
        QToolTip {{background:{c.SHEET};color:{c.TEXT};border:1px solid {c.BORDER_B};
                   border-radius:8px;padding:7px;}}
        QComboBox {{background:{c.INPUT};color:{c.TEXT};border:1px solid {c.BORDER};
                    border-radius:9px;padding:5px 10px;min-height:25px;}}
        QComboBox:hover, QComboBox:focus {{border-color:{c.PRI};}}
        QComboBox::drop-down {{border:0;width:24px;}}
        QComboBox QAbstractItemView {{background:{c.SHEET};color:{c.TEXT};
            border:1px solid {c.BORDER_B};selection-background-color:{c.HOVER};
            selection-color:{c.TEXT};outline:0;}}
    """


class DarkPopupFilter(QObject):
    def __init__(self, app, colors):
        super().__init__(app)
        self.colors = colors

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and isinstance(obj, QMenu):
            # Widget-local styles can otherwise override the application palette.
            obj.setPalette(self.parent().palette())
            obj.setStyleSheet(popup_style(self.colors))
        return super().eventFilter(obj, event)


def apply_dark_theme(app, c):
    palette = QPalette()
    colors = {
        'Window': c.PANEL, 'WindowText': c.TEXT, 'Base': c.DARK,
        'AlternateBase': c.PANEL2, 'Text': c.TEXT, 'Button': c.PANEL2,
        'ButtonText': c.TEXT, 'ToolTipBase': c.PANEL, 'ToolTipText': c.TEXT,
        'Highlight': c.PRI_GHO, 'HighlightedText': c.TEXT,
        'PlaceholderText': c.TEXT_DIM, 'Link': c.PRI,
    }
    for role, value in colors.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(value))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(c.TEXT_DIM))
    app.setPalette(palette)
    app.setStyleSheet(popup_style(c))
    if not hasattr(app, '_edith_popup_filter'):
        app._edith_popup_filter = DarkPopupFilter(app, c)
        app.installEventFilter(app._edith_popup_filter)
    else:
        app._edith_popup_filter.colors = c
