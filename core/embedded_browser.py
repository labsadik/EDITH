"""Persistent, resizable embedded browser window for EDITH."""
from __future__ import annotations

from pathlib import Path
import json
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




def build_embedded_browser_script(action: str, arguments: dict | None = None) -> str:
    """Build a constrained DOM operation; user data is JSON-encoded, never eval'd."""
    args = arguments or {}
    mode = str(action or "").strip().lower()
    selector = str(args.get("selector") or "").strip()
    if len(selector) > 500:
        raise ValueError("CSS selector is too long")
    text_value = str(args.get("text") or args.get("description") or "")
    if len(text_value) > 4000:
        raise ValueError("Browser text input exceeds 4 KB")
    selector_js = json.dumps(selector)
    text_js = json.dumps(text_value)
    if mode == "get_url":
        return "location.href"
    if mode == "get_text":
        return "((document.body && document.body.innerText) || '').slice(0, 12000)"
    if mode in {"click", "smart_click"}:
        return f"""(() => {{
          const selector = {selector_js}, label = {text_js}.trim().toLocaleLowerCase();
          let matches = selector ? Array.from(document.querySelectorAll(selector)) :
            Array.from(document.querySelectorAll('button,a,[role="button"],input[type="button"],input[type="submit"]'))
              .filter(el => (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().toLocaleLowerCase() === label);
          matches = matches.filter(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length));
          if (matches.length !== 1) return {{ok:false, error:matches.length ? 'Target is ambiguous' : 'Target not found', matches:matches.length}};
          matches[0].click();
          return {{ok:true, action:'click'}};
        }})()"""
    if mode in {"type", "smart_type"}:
        return f"""(() => {{
          const selector = {selector_js}, value = {text_js};
          const el = selector ? document.querySelector(selector) : document.activeElement;
          if (!el || !('value' in el || el.isContentEditable)) return {{ok:false,error:'No editable target found'}};
          el.focus();
          if (el.isContentEditable) el.textContent = value;
          else {{
            const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value')?.set;
            if (setter) setter.call(el, value); else el.value = value;
          }}
          el.dispatchEvent(new Event('input', {{bubbles:true}}));
          el.dispatchEvent(new Event('change', {{bubbles:true}}));
          return {{ok:true, action:'type', characters:value.length}};
        }})()"""
    if mode == "fill_form":
        fields = args.get("fields")
        if not isinstance(fields, dict) or not fields or len(fields) > 20:
            raise ValueError("Fill form requires 1-20 CSS-selector fields")
        clean = {}
        for key, value in fields.items():
            css = str(key or "").strip()
            val = str(value or "")
            if not css or len(css) > 500 or len(val) > 4000:
                raise ValueError("Invalid selector or form value")
            clean[css] = val
        fields_js = json.dumps(clean, ensure_ascii=False)
        return f"""(() => {{
          const fields = {fields_js}, filled = [], missing = [];
          for (const [selector,value] of Object.entries(fields)) {{
            const el = document.querySelector(selector);
            if (!el || !('value' in el || el.isContentEditable)) {{ missing.push(selector); continue; }}
            el.focus();
            if (el.isContentEditable) el.textContent = value;
            else {{
              const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value')?.set;
              if (setter) setter.call(el, value); else el.value = value;
            }}
            el.dispatchEvent(new Event('input', {{bubbles:true}}));
            el.dispatchEvent(new Event('change', {{bubbles:true}}));
            filled.push(selector);
          }}
          return {{ok:missing.length === 0, filled:filled.length, missing}};
        }})()"""
    if mode == "scroll":
        direction = str(args.get("direction") or "down").strip().lower()
        if direction not in {"up", "down", "left", "right"}:
            raise ValueError("Scroll direction must be up, down, left or right")
        amount = max(1, min(abs(int(args.get("amount") or 500)), 2000))
        dx = (-amount if direction == "left" else amount if direction == "right" else 0)
        dy = (-amount if direction == "up" else amount if direction == "down" else 0)
        return f"(() => {{ window.scrollBy({dx}, {dy}); return {{ok:true, action:'scroll'}}; }})()"
    if mode == "press":
        key = str(args.get("key") or "").strip()
        if key not in {"Enter", "Escape", "Tab", "Space", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End"}:
            raise ValueError("Embedded browser key is not allowed")
        return f"""(() => {{
          const key = {json.dumps(key)};
          const target = document.activeElement || document.body;
          target.dispatchEvent(new KeyboardEvent('keydown', {{key, bubbles:true}}));
          target.dispatchEvent(new KeyboardEvent('keyup', {{key, bubbles:true}}));
          return {{ok:true, action:'press', key}};
        }})()"""
    raise ValueError(f"Unsupported embedded browser action: {mode}")


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

    def execute_action(self, action: str, arguments: dict | None, callback) -> None:
        """Run only the allowlisted embedded-browser operations on the Qt thread."""
        mode = str(action or "").strip().lower()
        try:
            self.show()
            self.raise_()
            self.activateWindow()
            if mode == "back":
                self._view.back()
                callback({"ok": True, "action": mode})
                return
            if mode == "forward":
                self._view.forward()
                callback({"ok": True, "action": mode})
                return
            if mode == "reload":
                self._view.reload()
                callback({"ok": True, "action": mode})
                return
            if mode == "go_to":
                target = str((arguments or {}).get("url") or "about:blank")
                self.navigate(target)
                callback({"ok": True, "action": "go_to", "url": self._view.url().toString()})
                return
            script = build_embedded_browser_script(mode, arguments)
            self._view.page().runJavaScript(script, callback)
        except Exception as exc:
            callback({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"})

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
