"""Persistent, resizable embedded browser window for EDITH."""
from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import quote

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout


def normalize_web_url(value: str) -> QUrl:
    raw = str(value or "").strip()
    if not raw:
        return QUrl("about:blank")

    # Reject dangerous schemes before QUrl.fromUserInput can reinterpret them
    # as a search term or a host name.
    if raw.lower() == "about:blank":
        return QUrl("about:blank")
    explicit_scheme = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*):", raw)
    if explicit_scheme:
        scheme = explicit_scheme.group(1).lower()
        if scheme not in {"http", "https"}:
            raise ValueError("Embedded browser accepts only http, https or about:blank URLs")
    elif "://" not in raw and "." not in raw and " " in raw:
        encoded_query = quote(raw, safe="")
        return QUrl.fromEncoded(
            f"https://www.google.com/search?q={encoded_query}".encode("ascii")
        )
    elif "://" not in raw:
        raw = "https://" + raw

    url = QUrl.fromUserInput(raw)
    if url.scheme().lower() not in {"http", "https"}:
        raise ValueError("Embedded browser accepts only http, https or about:blank URLs")
    if not url.host():
        raise ValueError("Enter a valid website address")
    return url


class EmbeddedBrowserDialog(QDialog):
    """One reusable browser dialog with a persistent cookie/storage profile."""

    def __init__(self, parent=None):
        super().__init__(parent)
        try:
            from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except ImportError as exc:
            raise RuntimeError("Install PyQt6-WebEngine to use the embedded browser") from exc
        self.setWindowTitle("EDITH · Embedded Browser")
        self.resize(1120, 760)
        self.setMinimumSize(640, 420)

        profile_dir = Path.home() / ".edith" / "browser-profile"
        cache_dir = Path.home() / ".edith" / "browser-cache"
        profile_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._profile = QWebEngineProfile("EDITHPersistentProfile", self)
        self._profile.setPersistentStoragePath(str(profile_dir))
        self._profile.setCachePath(str(cache_dir))
        self._profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        toolbar = QHBoxLayout()
        self._back = QPushButton("←")
        self._forward = QPushButton("→")
        self._reload = QPushButton("↻")
        self._address = QLineEdit()
        self._address.setPlaceholderText("Enter a website or search")
        self._go = QPushButton("GO")
        for button in (self._back, self._forward, self._reload, self._go):
            button.setMinimumHeight(34)
        toolbar.addWidget(self._back)
        toolbar.addWidget(self._forward)
        toolbar.addWidget(self._reload)
        toolbar.addWidget(self._address, 1)
        toolbar.addWidget(self._go)
        root.addLayout(toolbar)

        self._view = QWebEngineView(self)
        self._view.setPage(QWebEnginePage(self._profile, self._view))
        root.addWidget(self._view, 1)
        self._back.clicked.connect(self._view.back)
        self._forward.clicked.connect(self._view.forward)
        self._reload.clicked.connect(self._view.reload)
        self._go.clicked.connect(self._navigate_from_address)
        self._address.returnPressed.connect(self._navigate_from_address)
        self._view.urlChanged.connect(self._update_address)
        self._view.titleChanged.connect(self.setWindowTitle)
        self._view.loadFinished.connect(self._update_navigation_state)
        self._update_navigation_state(False)

    def navigate(self, target: str) -> None:
        self._view.setUrl(normalize_web_url(target))
        self.show()
        self.raise_()
        self.activateWindow()

    def _navigate_from_address(self) -> None:
        try:
            self._view.setUrl(normalize_web_url(self._address.text()))
        except ValueError as exc:
            self._address.setToolTip(str(exc))

    def _update_address(self, url: QUrl) -> None:
        self._address.setText(url.toString())
        self._address.setCursorPosition(0)

    def _update_navigation_state(self, _ok: bool) -> None:
        self._back.setEnabled(self._view.history().canGoBack())
        self._forward.setEnabled(self._view.history().canGoForward())
