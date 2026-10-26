"""Shared native presentation primitives. No model or device dependencies."""
from __future__ import annotations

import html
import sys
import re
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QWidget, QScrollArea,
    QPushButton, QLineEdit, QTextEdit, QLabel, QFrame, QSizePolicy,
)


def palette():
    return sys.modules['ui'].C


def control_style():
    c = palette()
    return f"""
    QPushButton {{background:{c.PANEL2}; color:{c.TEXT}; border:1px solid {c.BORDER};
        border-radius:12px; padding:7px 14px; font-weight:500;}}
    QPushButton:hover {{background:{c.PRI_GHO}; border-color:{c.PRI_DIM};}}
    QPushButton:pressed, QPushButton:checked {{background:{c.PRI_GHO}; border-color:{c.PRI};}}
    QPushButton:focus {{border:2px solid {c.PRI};}}
    QPushButton:disabled {{color:{c.TEXT_DIM}; background:{c.PANEL}; border-color:{c.BORDER};}}
    QPushButton[role="primary"] {{background:{c.PRI}; color:#FFFFFF; font-weight:600;}}
    QPushButton[role="danger"] {{color:{c.RED}; border-color:{c.RED};}}
    QLineEdit, QTextEdit {{background:{c.DARK}; color:{c.TEXT}; border:1px solid {c.BORDER};
        border-radius:12px; padding:9px; selection-background-color:{c.PRI_GHO};}}
    QLineEdit:focus, QTextEdit:focus {{border:1px solid {c.PRI};}}
    QScrollBar:vertical {{background:{c.PANEL}; width:10px;}}
    QScrollBar::handle:vertical {{background:{c.BORDER_B}; min-height:24px; border-radius:5px;}}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{height:0;}}
    """


def polish_controls(root):
    """Apply one interaction vocabulary to existing and newly opened surfaces."""
    style = control_style()
    for widget in [root, *root.findChildren(QWidget)]:
        if isinstance(widget, (QPushButton, QLineEdit, QTextEdit)):
            widget.setStyleSheet(style)
            font = widget.font()
            font.setPointSizeF(max(10, font.pointSizeF()))
            widget.setFont(font)
            if not isinstance(widget, QTextEdit):
                if widget.maximumWidth() <= 36:
                    widget.setFixedSize(36, 36)
                else:
                    if isinstance(widget, QPushButton) and widget.maximumWidth() < 200:
                        widget.setFixedWidth(max(widget.maximumWidth(), widget.fontMetrics().horizontalAdvance(widget.text()) + 30))
                    widget.setMinimumHeight(max(36, widget.minimumHeight()))
                    widget.setMaximumHeight(16777215)
            if isinstance(widget, QPushButton):
                from core.icons import svg_icon
                text = widget.text()
                clean = re.sub(r'^[◉◈▸⊞✕✓●○\s]+', '', text)
                if clean.lower() in {'female voice', 'male voice'}:
                    clean = clean.capitalize()
                if clean != text and clean:
                    widget.setText(clean)
                if widget.icon().isNull() and clean:
                    words = clean.lower()
                    symbol = None
                    if any(word in words for word in ('close', 'cancel', 'dismiss')):
                        symbol = 'x'
                    elif any(word in words for word in ('save', 'apply', 'test', 'continue', 'get started')):
                        symbol = 'checkmark'
                    elif 'key' in words or 'connection' in words:
                        symbol = 'key'
                    elif 'connect a device' in words:
                        symbol = 'wifi'
                    elif 'default' in words:
                        symbol = 'rotate-left'
                    if symbol:
                        widget.setIcon(svg_icon(symbol, palette().PRI))
                if 36 < widget.maximumWidth() < 200 and not widget.icon().isNull():
                    widget.setFixedWidth(max(widget.maximumWidth(), widget.fontMetrics().horizontalAdvance(widget.text()) + 52))
                widget.setCursor(Qt.CursorShape.PointingHandCursor)
                if not widget.accessibleName():
                    widget.setAccessibleName(widget.toolTip() or widget.text().replace('&&', '&') or 'Close preview')
        elif isinstance(widget, QLabel):
            font = widget.font()
            font.setPointSizeF(max(9, font.pointSizeF()))
            widget.setFont(font)


class SurfaceDialog(QDialog):
    """Scrollable, window-modal forms with consistent focus and dismissal."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint
                            | Qt.WindowType.WindowSystemMenuHint | Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle('EDITH · Settings')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setSizeGripEnabled(True)
        self._wrapped = False
        self._previous_focus = None

    def showEvent(self, event):
        if not self._wrapped and self.layout():
            content = QWidget()
            content.setLayout(self.layout())
            self._content = content
            layout = content.layout()
            layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            footer = []
            last = layout.takeAt(layout.count()-1)
            footer.insert(0, last)
            if type(self).__name__ == 'ApiKeyOverlay' and layout.itemAt(layout.count()-1).layout():
                footer.insert(0, layout.takeAt(layout.count()-1))
            self._scroll = QScrollArea()
            self._scroll.setFrameShape(QFrame.Shape.NoFrame)
            self._scroll.setWidgetResizable(True)
            self._scroll.setWidget(content)
            outer = QVBoxLayout(self)
            outer.setContentsMargins(8, 8, 8, 8)
            close = QPushButton('Close')
            close.setAccessibleName('Close dialog')
            close.clicked.connect(self.reject)
            from PyQt6.QtWidgets import QHBoxLayout
            header = QHBoxLayout()
            header.addStretch()
            header.addWidget(close)
            outer.addLayout(header)
            outer.addWidget(self._scroll, 1)
            if type(self).__name__ == 'RemoteKeyOverlay':
                layout.removeWidget(self._timer_lbl)
                outer.addWidget(self._timer_lbl)
            for item in footer:
                if item.layout():
                    outer.addLayout(item.layout())
                elif item.widget():
                    outer.addWidget(item.widget())
            self._wrapped = True
        c = palette()
        self.setStyleSheet(f'QDialog, QScrollArea, QWidget {{background:{c.BG}; color:{c.TEXT};}}')
        polish_controls(self)
        for frame in self.findChildren(QFrame):
            if frame.frameShape() == QFrame.Shape.HLine:
                frame.setFixedHeight(1)
        for label in self.findChildren(QLabel):
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._content.layout().activate()
        self._content.setMinimumHeight(self._content.layout().minimumSize().height())
        self.setMinimumWidth(320)
        self.setMaximumWidth(16777215)
        owner = self.parentWidget()
        screen = self.screen().availableGeometry()
        self.resize(min(getattr(self, '_OW', 520), screen.width()-32),
                    min(max(getattr(self, '_OH', self._content.minimumHeight()+100), 300), screen.height()-64))
        center = owner.mapToGlobal(owner.rect().center()) if owner else screen.center()
        self.move(max(screen.left()+8, min(center.x()-self.width()//2, screen.right()-self.width()-8)),
                  max(screen.top()+8, min(center.y()-self.height()//2, screen.bottom()-self.height()-8)))
        if self._previous_focus is None and owner:
            self._previous_focus = owner.window().focusWidget()
        titles = {'SetupOverlay': 'Get started', 'ApiKeyOverlay': 'Model connections',
                  'CustomizeOverlay': 'Preferences', 'PluginManagerOverlay': 'Plugins',
                  'RemoteKeyOverlay': 'Remote access'}
        self.setWindowTitle('EDITH · ' + titles.get(type(self).__name__, 'Settings'))
        super().showEvent(event)
        fields = self.findChildren(QLineEdit)
        if fields:
            QTimer.singleShot(0, fields[0].setFocus)

    def reject(self):
        # Setup must either complete or be closed using the window manager.
        if type(self).__name__ == 'SetupOverlay':
            self.hide()
            owner = self.parentWidget()
            if owner:
                owner.window().close()
            return
        if hasattr(self, '_cancel'):
            self._cancel()
        elif hasattr(self, '_do_close'):
            self._do_close()
        else:
            self.hide()

    def closeEvent(self, event):
        self.reject()
        event.accept()

    def hideEvent(self, event):
        super().hideEvent(event)
        focus = self._previous_focus
        if focus is not None:
            try:
                focus.setFocus()
            except RuntimeError:
                pass


class ConversationView(QTextEdit):
    """Selectable, bounded transcript; diagnostics remain in the activity panel."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAccessibleName('Conversation with EDITH')
        self.document().setMaximumBlockCount(700)
        self._empty = True
        self.setHtml('<h2>How can I help?</h2><p>Speak to EDITH or type a command below.</p>'
                     '<p>Attach a file to work with documents, images or code.</p>')

    def append_line(self, line):
        speaker, sep, text = line.partition(':')
        if not sep or speaker.lower() not in {'you', 'edith'}:
            return
        if self._empty:
            self.clear()
            self._empty = False
        bar = self.verticalScrollBar()
        pinned = bar.value() >= bar.maximum()-8
        position = bar.value()
        c = palette()
        color = c.PRI if speaker.lower() == 'edith' else c.TEXT_MED
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(f'<p style="color:{color};font-size:10pt"><b>{html.escape(speaker)}</b></p>'
                          f'<p style="color:{c.TEXT};font-size:11pt">{html.escape(text.strip()).replace(chr(10), "<br>")}</p><br>')
        if pinned:
            bar.setValue(bar.maximum())
        else:
            bar.setValue(position)
