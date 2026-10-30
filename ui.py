from __future__ import annotations

import json
import math
import os
import platform
import random
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QSettings, QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QDragEnterEvent, QDropEvent, QFont,
    QFontDatabase, QKeySequence, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QGraphicsDropShadowEffect, QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QProgressBar, QInputDialog, QTabWidget,
)

from core.icons import svg_icon
from core.window_controls import initial_geometry
from core.video_visual import LoopingVideo, draw_blended_video
from core.dark_theme import apply_dark_theme
from core.secrets import get_gemini_api_key, save_gemini_api_key, get_config_secret, save_config_secret
from core.theme_service import SystemThemeMonitor, normalise_theme
from core.app_paths import config_path, resource_dir

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = resource_dir()
API_FILE   = config_path()
CONFIG_DIR = API_FILE.parent

# Modern Font Families
FONT_MAIN = "Segoe UI" if platform.system() == "Windows" else "Helvetica Neue"
FONT_MONO = "Consolas" if platform.system() == "Windows" else "Menlo"
FONT_FALLBACKS = [FONT_MAIN, "Nirmala UI", "Noto Sans Bengali", "Noto Sans", "sans-serif"]

def _read_full_config() -> dict:
    """Read api_keys.json config dict. Returns {} on any error."""
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

_DEFAULT_W, _DEFAULT_H = 1360, 860
_MIN_W,     _MIN_H     = 840, 560
_LEFT_W  = 208
_RIGHT_W = 372

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

class C:
    # Opaque text/palette values and layered native glass surfaces. All
    # widget styles consume these tokens so OS appearance changes repaint live.
    BG        = "#0A0F18"
    PANEL     = "#141C29"
    PANEL2    = "#1D2939"
    BORDER    = "#1B2533"
    BORDER_B  = "#29374A"
    BORDER_A  = "#36485E"
    PRI       = "#B39AFB"
    PRI_DIM   = "#987FE4"
    PRI_GHO   = "#392C5B"
    ACC       = "#83C8EC"
    ACC2      = "#F5C879"
    GREEN     = "#70D9B6"
    GREEN_D   = "#318B70"
    RED       = "#FF8798"
    MUTED_C   = "#FF8798"
    TEXT      = "#F1F3F8"
    TEXT_DIM  = "#96A4B7"
    TEXT_MED  = "#CBD3E0"
    WHITE     = "#FFFFFF"
    DARK      = "#0E1622"
    BAR_BG    = "#26364A"
    HEADER    = "#F0111724"
    SIDEBAR   = "#ED121B2A"
    GLASS     = "#D8172230"
    GLASS_CARD = "#DF1A2636"
    GLASS_RIM = "#28B39AFB"
    INPUT     = "#F00D1420"
    SHEET     = "#FC141D2B"
    HOVER     = "#B82F3C54"
    DANGER_BG = "#55A33A4A"
    DANGER_HOVER = "#80C44758"
    SUCCESS_BG = "#50205C4B"
    SUCCESS_HOVER = "#80307862"
    VIDEO_BG  = "#000000"
    SHADOW    = "#A0000000"


# Complete palettes are centralised. Widgets retain the original native layout
# and refer to C, so a palette transition repaints in place.
_THEME_COLOR_KEYS = (
    "BG", "PANEL", "PANEL2", "BORDER", "BORDER_B", "BORDER_A", "PRI",
    "PRI_DIM", "PRI_GHO", "ACC", "ACC2", "GREEN", "GREEN_D", "RED",
    "MUTED_C", "TEXT", "TEXT_DIM", "TEXT_MED", "WHITE", "DARK", "BAR_BG",
    "HEADER", "SIDEBAR", "GLASS", "GLASS_CARD", "GLASS_RIM", "INPUT",
    "SHEET", "HOVER", "DANGER_BG", "DANGER_HOVER", "SUCCESS_BG",
    "SUCCESS_HOVER", "VIDEO_BG",
    "SHADOW",
)
_THEME_DEFAULTS = {
    "dark": {key: getattr(C, key) for key in _THEME_COLOR_KEYS},
    "light": {
        "BG": "#EEF1F7", "PANEL": "#F8F9FC", "PANEL2": "#EEF0F7",
        "BORDER": "#E7ECF3", "BORDER_B": "#D8E0EB", "BORDER_A": "#C4CFDE",
        "PRI": "#7156C8", "PRI_DIM": "#806BD0", "PRI_GHO": "#E9E2FB",
        "ACC": "#26769F", "ACC2": "#946018", "GREEN": "#187A60",
        "GREEN_D": "#246D58", "RED": "#BD4057", "MUTED_C": "#BD4057",
        "TEXT": "#20283A", "TEXT_DIM": "#68748A", "TEXT_MED": "#3D4960",
        "WHITE": "#FFFFFF", "DARK": "#F0F2F8", "BAR_BG": "#E1E5EF",
        "HEADER": "#F4F8FBFF",
        "SIDEBAR": "#E8EDF6F5",
        "GLASS": "#E4FFFFFF",
        "GLASS_CARD": "#D8FFFFFF",
        "GLASS_RIM": "#EEFFFFFF",
        "INPUT": "#F5FFFFFF",
        "SHEET": "#FCF9FDFF",
        "HOVER": "#EFE7F5F7",
        "DANGER_BG": "#DDFCE7EB",
        "DANGER_HOVER": "#FADAE0E8",
        "SUCCESS_BG": "#DCE0F5EC",
        "SUCCESS_HOVER": "#F8CBEBDD",
        "VIDEO_BG": "#000000",
        "SHADOW": "#38212D48",
    },
}

def apply_ui_theme(theme: str) -> str:
    """Apply the selected system palette without user-defined accent overrides."""
    resolved = normalise_theme(theme)
    for key, value in _THEME_DEFAULTS[resolved].items():
        setattr(C, key, value)
    return resolved


def current_palette() -> dict[str, str]:
    """C sınıfındaki accent'e bağlı renklerin anlık kopyası."""
    return {k: getattr(C, k) for k in _THEME_COLOR_KEYS}


def _set_theme_icon(button: QPushButton, name: str, color_role: str) -> None:
    button.setProperty("edith_icon", name)
    button.setProperty("edith_icon_color", color_role)
    button.setIcon(svg_icon(name, getattr(C, color_role)))


def _glass_shadow(widget: QWidget) -> None:
    """Add a soft composited shadow to a floating sheet, never to the video."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(28)
    effect.setOffset(0, 9)
    effect.setColor(QColor(C.SHADOW))
    widget.setGraphicsEffect(effect)
    widget.setProperty("edith_glass_shadow", True)


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """
    CANLI tam tema değişimi. Uygulamadaki HER widget'ın stylesheet'inde eski
    palet renklerini yenileriyle değiştirir ve yeniden çizdirir. Böylece renk
    değişimi yalnızca boyanan öğelerde değil, panel/buton/kenarlık dahil tüm
    arayüzde ANINDA uygulanır — yeniden başlatma gerekmez.
    """
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    app = QApplication.instance()
    if app is None:
        return
    apply_dark_theme(app, C)
    # One case-insensitive pass is essential: QSS literals are often uppercase
    # while a replacement may itself match another old palette value.
    pattern = re.compile(
        "(?:" + "|".join(re.escape(value) for value in
                          sorted(mapping, key=len, reverse=True)) + ")(?![0-9a-f])",
        re.IGNORECASE,
    )
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            if ss:
                s2 = pattern.sub(lambda match: mapping[match.group().lower()], ss)
                if s2 != ss:
                    w.setStyleSheet(s2)
            if isinstance(w, LogWidget):
                w.retheme_entries(old, new)
            icon_name = w.property("edith_icon")
            icon_color = w.property("edith_icon_color")
            if icon_name and icon_color and hasattr(w, "setIcon"):
                w.setIcon(svg_icon(str(icon_name), getattr(C, str(icon_color))))
            if w.property("edith_glass_shadow"):
                effect = w.graphicsEffect()
                if isinstance(effect, QGraphicsDropShadowEffect):
                    effect.setColor(QColor(C.SHADOW))
            w.update()
        except Exception:
            pass


UI_BRAND = "EDITH"


def _display_assistant_name(_name: str = "") -> str:
    """Return the fixed product display name without exposing old/custom branding."""
    return UI_BRAND


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


# ── Windows GPU via NVML DLL (no subprocess, no console window) ──────────────
_nvml_lib: object = None   # cached ctypes DLL
_nvml_ok:  object = None   # None=untested, True=works, False=unavailable


def _nvml_gpu_windows() -> float:
    """Return NVIDIA GPU utilisation % using nvml.dll directly — zero subprocess."""
    global _nvml_lib, _nvml_ok
    if _nvml_ok is False:
        return -1.0
    try:
        import ctypes

        class _Util(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

        if _nvml_lib is None:
            for dll_name in ("nvml", r"C:\Windows\System32\nvml.dll"):
                try:
                    lib = ctypes.WinDLL(dll_name)
                    lib.nvmlInit_v2()
                    _nvml_lib = lib
                    break
                except Exception:
                    continue

        if _nvml_lib is None:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            _nvml_ok = True
            return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)

        dev = ctypes.c_void_p()
        _nvml_lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
        util = _Util()
        _nvml_lib.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(util))
        _nvml_ok = True
        return float(util.gpu)
    except Exception:
        _nvml_ok = False
        return -1.0


class _SysMetrics:
    def __init__(self):
        from edith.platform.service import telemetry_service
        self._service = telemetry_service()

    def snapshot(self) -> dict:
        data = self._service.snapshot().get("data") or {}
        net = data.get("throughput")
        return {
            "cpu":data.get("cpu_percent"),
            "mem":(data.get("memory") or {}).get("percent"),
            "net":((net.get("sent_bps",0)+net.get("received_bps",0))/1048576) if net else None,
            "gpu":(data.get("gpu") or {}).get("percent"),
            "tmp":(data.get("temperature") or {}).get("celsius"),
            "uptime_seconds":data.get("uptime_seconds"),
            "process_count":data.get("process_count"),
        }


_metrics = _SysMetrics()

class HudCanvas(QWidget):
    def __init__(self, face_path: str, assistant_name: str = "EDITH", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(240, 240)
        self._loop_started = time.monotonic()
        self._video = LoopingVideo(BASE_DIR / "assets" / "hud_reference.mp4", self)
        self._video.frame_ready.connect(self.update)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"
        self._assistant_name = assistant_name
        # UI-only audio feedback: zero when no captured PCM arrives recently.
        self._mic_target = 0.0
        self._mic_level = 0.0
        self._mic_last_packet = 0.0
        self._mic_source = "PC"
        self._out_level = 0.0
        self._out_last = 0.0

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.monotonic()
        self._scan       = 0.0
        self._scan2      = 180.0
        self._rings      = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 50.0, 100.0]
        self._blink      = True
        self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        # The center visual is always the app's neutral orb; do not load character/brand art.
        self._face_px = None

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        # 30 FPS gives smooth HUD feedback without repainting the full canvas
        # 60 times per second on battery-powered or low-end machines.
        self._tmr.start(33)

    def hideEvent(self, event):
        self._video.sync(False, getattr(self, "reduced_motion", False))
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._video.sync(True, getattr(self, "reduced_motion", False))

    def shutdown(self) -> None:
        """Release animation timers and multimedia resources before widget teardown."""
        self._tmr.stop()
        try:
            self._video.frame_ready.disconnect(self.update)
        except (TypeError, RuntimeError):
            pass
        self._video.shutdown()

    def set_input_level(self, level: float, source: str = "PC") -> None:
        """Qt-thread-only; values arrive through MainWindow's queued signal."""
        if self.muted or self.speaking:
            return
        self._mic_target = max(0.0, min(1.0, float(level)))
        self._mic_last_packet = time.monotonic()
        self._mic_source = "PHONE" if source == "PHONE" else "PC"

    def set_output_level(self, level: float) -> None:
        self._out_level = max(0.0, min(1.0, level))
        self._out_last = time.monotonic()
        self.update()

    def clear_input_level(self) -> None:
        self._mic_target = 0.0
        self._mic_level = 0.0
        self._mic_last_packet = 0.0

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap(); px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None

    def _step(self):
        self._video.sync(self.isVisible() and not self.window().isMinimized(), getattr(self, "reduced_motion", False))
        if getattr(self, "reduced_motion", False):
            self._mic_level = self._mic_target if time.monotonic() - self._mic_last_packet < .65 else 0.0
            self._tmr.setInterval(250)
            self.update()
            return
        self._tick += 1
        now = time.monotonic()
        mic_fresh = (now - self._mic_last_packet) < 0.65
        listening = self.state in {"LISTENING", "THINKING", "WORKING", "AWAITING APPROVAL"} and not self.muted and not self.speaking
        drive = self._mic_target if listening and mic_fresh else 0.0
        self._mic_level += (drive - self._mic_level) * 0.36
        input_active = listening and mic_fresh and self._mic_level > 0.08
        # Do not spend full-rate painting time while idle or camera view is shown.
        frame_ms = 250 if not self.isVisible() or self.window().isMinimized() else 33
        if self._tmr.interval() != frame_ms:
            self._tmr.setInterval(frame_ms)
        if now - self._last_t > (0.12 if self.speaking or input_active else 0.5):
            if self.speaking:
                self._tgt_scale = random.uniform(1.06, 1.14)
                self._tgt_halo  = random.uniform(145, 190)
            elif self.muted:
                self._tgt_scale = 1.0
                self._tgt_halo  = 20.0
            elif input_active:
                # Real PCM intensity drives the input heartbeat, not fake noise.
                self._tgt_scale = 1.006 + self._mic_level * 0.075
                self._tgt_halo = 62.0 + self._mic_level * 115.0
            else:
                self._tgt_scale = 1.003
                self._tgt_halo  = 54.0
            self._last_t = now

        sp = 0.38 if self.speaking else (0.27 if input_active else 0.15)
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        speeds = [1.3, -0.9, 2.0] if self.speaking else [0.55, -0.35, 0.9]
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd) % 360

        self._scan  = (self._scan  + (3.0 if self.speaking else 1.3)) % 360
        self._scan2 = (self._scan2 + (-2.0 if self.speaking else -0.75)) % 360

        fw  = min(self.width(), self.height())
        lim = fw * 0.74
        spd = 4.2 if self.speaking else 2.0
        self._pulses = [r + spd for r in self._pulses if r + spd < lim]
        if len(self._pulses) < 3 and random.random() < (0.07 if self.speaking else 0.025):
            self._pulses.append(0.0)

        if self.speaking and random.random() < 0.28:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.28
            self._particles.append([
                cx + math.cos(ang) * r_s, cy + math.sin(ang) * r_s,
                math.cos(ang) * random.uniform(0.9, 2.4),
                math.sin(ang) * random.uniform(0.9, 2.4) - 0.4, 1.0,
            ])
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.028]
            for p in self._particles if p[4] > 0
        ]

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(C.BG))
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 18, 18)
        painter.setClipPath(clip)
        visual = QRectF(12, 10, max(1, self.width() - 24), max(60, self.height() - 104))
        fresh = time.monotonic() - self._mic_last_packet < .65
        input_level = self._mic_level if fresh and not self.muted and not self.speaking else 0.0
        output_level = self._out_level if self.speaking and time.monotonic() - self._out_last < .65 else 0.0
        stage = QPainterPath()
        stage.addRoundedRect(visual, 16, 16)
        painter.save()
        painter.setClipPath(stage, Qt.ClipOperation.IntersectClip)
        draw_blended_video(painter, visual, self._video.frame, C.VIDEO_BG)
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(C.BORDER), 1))
        painter.drawRoundedRect(visual, 16, 16)
        if self._video.frame.isNull():
            painter.setPen(QColor(C.TEXT_DIM))
            painter.setFont(QFont(FONT_MAIN, 10))
            painter.drawText(visual, Qt.AlignmentFlag.AlignCenter,
                             "Animation unavailable" if self._video.error else "Loading animation…")
        state = self.state.upper()
        text = state
        if self.muted and state not in {"WORKING", "THINKING", "SPEAKING"}:
            text = "MICROPHONE MUTED"
        color = {"LISTENING": C.GREEN, "THINKING": C.PRI, "WORKING": C.ACC2,
                 "AWAITING APPROVAL": C.ACC2, "SPEAKING": C.ACC}.get(state, C.TEXT)
        painter.setPen(QColor(color))
        painter.setFont(QFont(FONT_MAIN, 14, QFont.Weight.Bold))
        painter.drawText(QRectF(10, self.height()-83, self.width()-20, 28), Qt.AlignmentFlag.AlignCenter, text)
        detail = ("Voice output" if self.speaking else "Microphone muted" if self.muted else
                  self._mic_source + " AUDIO DETECTED" if fresh and input_level > .11 else
                  self._mic_source + " MIC READY" if fresh else "WAITING FOR MIC AUDIO")
        painter.setFont(QFont(FONT_MAIN, 9))
        painter.setPen(QColor(C.TEXT))
        painter.drawText(QRectF(10, self.height()-55, self.width()-20, 22), Qt.AlignmentFlag.AlignCenter, detail)
        level = output_level if self.speaking else input_level
        center = self.width()/2
        for i in range(36):
            height = 3 + int(level * 28 * (.3 + .7 * abs(math.sin(i*.6))))
            painter.fillRect(QRectF(center-107+i*6, self.height()-13-height, 3, height), QColor(color if level > .02 else C.BORDER_B))


class MetricBar(QWidget):

    def __init__(self, label: str, color: str = "PRI", parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(42)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.GLASS_CARD)))
        p.setPen(QPen(qcol(C.BORDER), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 9, 9)
        p.setPen(QPen(qcol(C.GLASS_RIM), 1))
        p.drawLine(QPointF(9, 2), QPointF(W - 9, 2))

        bar_h   = 5
        bar_y   = H - bar_h - 6
        bar_w   = W - 12
        bar_x   = 6
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(getattr(C, self._color, self._color))

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(8, 5, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont(FONT_MONO, 10, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM) if self._text in {"--", "N/A"} else bar_col, 1))
        p.drawText(QRectF(0, 4, W - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        # Bound on-screen history so a long agent session cannot fill GUI memory.
        self.document().setMaximumBlockCount(700)
        self.setFont(QFont(FONT_MONO, 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.GLASS};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 12px;
                padding: 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 6px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 3px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._ai_name_lc = "edith"   # updated when assistant name changes
        self._reduced_motion = False
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def set_reduced_motion(self, enabled: bool) -> None:
        """Display new log entries promptly, without the typewriter effect."""
        self._reduced_motion = bool(enabled)

    def retheme_entries(self, old: dict[str, str], new: dict[str, str]) -> None:
        """Keep already printed activity lines legible after a live OS switch."""
        colors = {QColor(old[key]).name(): QColor(new[key]) for key in
                  ("TEXT", "PRI", "RED", "GREEN", "ACC2")}
        document = self.document()
        replacements = []
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid():
                    previous = fragment.charFormat().foreground().color().name()
                    replacement = colors.get(previous)
                    if replacement is not None:
                        fmt = fragment.charFormat()
                        fmt.setForeground(replacement)
                        replacements.append((fragment.position(), fragment.length(), fmt))
                iterator += 1
            block = block.next()
        for position, length, fmt in replacements:
            cursor = self.textCursor()
            cursor.setPosition(position)
            cursor.setPosition(position + length, cursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(fmt)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        _ai_pfx = f"{self._ai_name_lc}:"
        if   tl.startswith("you:"):                              self._tag = "you"
        elif tl.startswith(_ai_pfx) or tl.startswith("edith:"): self._tag = "ai"
        elif tl.startswith("file:"):                             self._tag = "file"
        elif "err" in tl:                                        self._tag = "err"
        else:                                                    self._tag = "sys"
        # Preserve the existing typewriter style while avoiding per-character
        # repaints when several concurrent tasks finish close together.
        self._tmr.start(16)

    def _step(self):
        if self._pos < len(self._text):
            step = len(self._text) if self._reduced_motion else (160 if len(self._queue) > 5 else 24)
            chunk = self._text[self._pos:self._pos + step]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.TEXT),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(chunk, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += len(chunk)
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(0 if self._reduced_motion else 20, self._next)

_FILE_ICONS = {
    "image":   ("file-image",        "#A5B4FC"),
    "video":   ("file-video",        "#A5B4FC"),
    "audio":   ("file-audio",        "#D7B8F7"),
    "pdf":     ("file-pdf",          "#F48F9D"),
    "word":    ("file-word",         "#A5B4FC"),
    "excel":   ("file-spreadsheet",  "#76D7B0"),
    "code":    ("file-code",         "#E8C995"),
    "archive": ("file-archive",      "#D7B8F7"),
    "pptx":    ("file-presentation", "#A5B4FC"),
    "text":    ("file-text",         "#B1B9C8"),
    "data":    ("file-data",         "#A5B4FC"),
    "unknown": ("file-generic",      "#7F899B"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_cleared = pyqtSignal()
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(90)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()
        self.file_cleared.emit()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 4
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol(C.HOVER if z._drag_over or z._hovering else C.GLASS_CARD)
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 12, 12)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 12, 12)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 12), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 12))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 12))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont(FONT_MAIN, 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here or Click to Browse")
        p.setFont(QFont(FONT_MAIN, 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, cy + 22, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        icon_obj = svg_icon("upload", C.PRI)
        icon_pix = icon_obj.pixmap(QSize(24, 24)) if icon_obj else QPixmap()
        if not icon_pix.isNull():
            p.drawPixmap(int((W - 24) / 2), int(cy - 24), icon_pix)
        else:
            p.setPen(QPen(qcol(C.PRI), 1))
            p.drawLine(QPointF(W / 2, cy - 12), QPointF(W / 2, cy + 4))
            p.drawLine(QPointF(W / 2 - 7, cy - 3), QPointF(W / 2, cy - 12))
            p.drawLine(QPointF(W / 2 + 7, cy - 3), QPointF(W / 2, cy - 12))
        p.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 10, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 50
        # Local SVG file-type mark with a colored rail for consistent, professional UI.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol(icon_col, 220)))
        p.drawRoundedRect(QRectF(block_x, H * 0.25, 3, H * 0.5), 1.5, 1.5)
        icon_obj = svg_icon(icon, icon_col)
        icon_pix = icon_obj.pixmap(QSize(28, 28)) if icon_obj else QPixmap()
        if not icon_pix.isNull():
            p.drawPixmap(int(block_x + 11), int((H - 28) / 2), icon_pix)
        else:
            p.setFont(QFont(FONT_MAIN, 7, QFont.Weight.Bold))
            p.setPen(QPen(qcol(icon_col), 1))
            p.drawText(QRectF(block_x + 4, 0, block_w - 8, H),
                       Qt.AlignmentFlag.AlignCenter, cat[:4].upper())

        tx = block_x + block_w + 6
        tw = W - tx - 32

        p.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT), 1))
        name = path.name if len(path.name) <= 32 else path.name[:29] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont(FONT_MONO, 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 16, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        close_icon = svg_icon("x", C.RED)
        close_pix = close_icon.pixmap(QSize(14, 14)) if close_icon else QPixmap()
        if not close_pix.isNull():
            p.drawPixmap(W - 24, int((H - 14) / 2), close_pix)
        else:
            p.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
            p.setPen(QPen(qcol(C.RED, 180), 1))
            p.drawText(QRectF(W - 30, 0, 24, H), Qt.AlignmentFlag.AlignCenter, "X")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 30:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class _CameraPreview(QWidget):
    """Floating overlay that briefly shows what the camera captured."""

    _W, _H = 244, 188

    def __init__(self, parent=None):
        super().__init__(parent)
        _glass_shadow(self)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            _CameraPreview {{
                background: {C.SHEET};
                border: 1px solid {C.PRI};
                border-radius: 16px;
            }}
        """)
        self.setFixedWidth(self._W)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        title = QLabel("◈  VISION INPUT")
        title.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()
        close_btn = QPushButton()
        _set_theme_icon(close_btn, "x", "TEXT_DIM")
        close_btn.setIconSize(QSize(12, 12))
        close_btn.setFixedSize(18, 18)
        close_btn.setFont(QFont(FONT_MAIN, 8))
        close_btn.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; border: none;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(self._img_lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self.hide()

    def show_frame(self, img_bytes: bytes) -> None:
        px = QPixmap()
        px.loadFromData(img_bytes)
        if not px.isNull():
            scaled = px.scaled(
                self._W - 16, 150,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img_lbl.setPixmap(scaled)
            self._img_lbl.setFixedSize(scaled.width(), scaled.height())
            self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(6_000)   # auto-dismiss after 6 s


class ApiKeyOverlay(QWidget):
    """Real API-key editor. The Test action opens an actual Gemini Live session."""

    saved = pyqtSignal()
    _test_result = pyqtSignal(bool, str, str, int)
    _local_connection_result = pyqtSignal(bool, str, str, str, str)
    _local_test_result = pyqtSignal(bool, str, str, int)

    _OW, _OH = 860, 760
    _SEARCH_SECRET_NAMES = {
        "tavily": "tavily_api_key",
        "brave": "brave_search_api_key",
        "serpapi": "serpapi_api_key",
        "exa": "exa_api_key",
    }

    def __init__(self, current_key: str = "", parent=None):
        super().__init__(parent)
        _glass_shadow(self)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ApiKeyOverlay {{
                background: {C.SHEET};
                border: 1px solid {C.BORDER_B};
                border-radius: 18px;
            }}
        """)
        self._tested_key = ""
        self._test_running = False
        self._local_test_running = False
        self._local_provider = "ollama"
        self._local_url = "http://localhost:11434"
        self._local_model = "llama3.2"

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(8)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        self._close_btn = QPushButton()
        self._close_btn.setAccessibleName("Close API settings")
        self._close_btn.setToolTip("Close")
        self._close_btn.setIcon(svg_icon("x", C.TEXT_DIM))
        self._close_btn.setIconSize(QSize(18, 18))
        self._close_btn.setFixedSize(38, 38)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; border: 1px solid {C.BORDER};
                           border-radius: 12px; }}
            QPushButton:hover {{ background: {C.DANGER_BG}; border-color: {C.RED}; }}
        """)
        self._close_btn.clicked.connect(self.hide)
        close_row.addWidget(self._close_btn)
        root.addLayout(close_row)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 0; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 4px; min-height: 26px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(6, 4, 10, 10)
        layout.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        eyebrow = QLabel("LLM & API CONNECTION")
        eyebrow.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        eyebrow.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        layout.addWidget(eyebrow)

        title = QLabel("CONNECTIONS & API ACCESS")
        title.setFont(QFont(FONT_MAIN, 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        layout.addWidget(title)

        desc = QLabel("Manage EDITH voice access and your text-model connection. Test a real response before saving credentials.")
        desc.setWordWrap(True)
        desc.setFont(QFont(FONT_MAIN, 9))
        desc.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        layout.addWidget(desc)

        status_card = QFrame(self)
        status_card.setStyleSheet(
            f"QFrame {{ background: {C.GLASS_CARD}; border: 1px solid {C.BORDER}; border-radius: 16px; }}"
        )
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(14, 12, 14, 12)
        status_layout.setSpacing(5)

        self._provider_info = QLabel("PROVIDER  Google Gemini Live API · cloud-hosted")
        self._model_info = QLabel("MODEL  models/gemini-2.5-flash-native-audio-preview-12-2025")
        self._local_provider_info = QLabel("LOCAL AGENT PROVIDER  CHECKING CONFIG…")
        self._local_model_info = QLabel("LOCAL AGENT MODEL  —")
        self._local_url_info = QLabel("LOCAL AGENT ENDPOINT  —")
        self._local_info = QLabel("LOCAL AGENT CONNECTION  CHECKING…")
        self._connection_status = QLabel("CLOUD API LAST TEST  NOT TESTED")
        self._latency_status = QLabel("CLOUD MODEL FIRST RESPONSE  —")
        self._local_latency_status = QLabel("LOCAL MODEL INFERENCE  NOT TESTED")
        for info in (self._provider_info, self._model_info, self._local_provider_info,
                     self._local_model_info, self._local_url_info, self._local_info,
                     self._connection_status, self._latency_status, self._local_latency_status):
            info.setWordWrap(True)
            info.setFont(QFont(FONT_MAIN, 9, QFont.Weight.DemiBold))
            info.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
            status_layout.addWidget(info)
        self._connection_status.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; border: none; font-weight: 700;"
        )
        layout.addWidget(status_card)

        local_row = QHBoxLayout()
        local_row.setSpacing(8)
        self._local_test_btn = QPushButton("TEST LOCAL LLM")
        self._local_test_btn.setFixedHeight(32)
        self._local_test_btn.setStyleSheet(self._secondary_style())
        self._local_test_btn.setToolTip("Run a real inference request through EDITH's existing core.llm_client configuration.")
        self._local_test_btn.clicked.connect(self._test_local_llm)
        local_row.addWidget(self._local_test_btn)
        layout.addLayout(local_row)

        local_hint = QLabel("Uses the existing llm_provider / llm_url / llm_model settings from config/api_keys.json. Server reachability and a real model response are checked separately.")
        local_hint.setWordWrap(True)
        local_hint.setFont(QFont(FONT_MAIN, 8))
        local_hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        layout.addWidget(local_hint)

        voice_heading = QLabel("VOICE PROVIDER")
        voice_heading.setFont(QFont(FONT_MAIN, 11, QFont.Weight.Bold))
        voice_heading.setStyleSheet(f"color: {C.TEXT}; background: transparent; padding-top: 5px;")
        layout.addWidget(voice_heading)
        self._voice_provider = QComboBox()
        self._voice_provider.addItem("Google Gemini Live", "gemini_live")
        self._voice_provider.setAccessibleName("Voice provider")
        self._voice_provider.setFixedHeight(40)
        self._voice_provider.setStyleSheet(f"""
            QComboBox {{ background: {C.INPUT}; color: {C.TEXT}; border: 1px solid {C.BORDER};
                        border-radius: 10px; padding: 8px 12px; }}
            QComboBox:focus {{ border-color: {C.PRI}; }}
            QComboBox::drop-down {{ border: 0; width: 28px; }}
        """)
        voice_note = QLabel("Gemini Live is the voice transport currently enabled in this build.")
        voice_note.setWordWrap(True)
        voice_note.setFont(QFont(FONT_MAIN, 8))
        voice_note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        layout.addWidget(self._voice_provider)
        layout.addWidget(voice_note)

        self._key_input = QLineEdit(current_key)
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("Paste Gemini API key")
        self._key_input.setFont(QFont(FONT_MONO, 10))
        self._key_input.setFixedHeight(42)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.INPUT}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 12px; padding: 9px 12px;
                selection-background-color: {C.PRI_GHO};
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        voice_key_label = QLabel("VOICE API KEY")
        voice_key_label.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        voice_key_label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        layout.addWidget(voice_key_label)
        layout.addWidget(self._key_input)

        if current_key:
            key_hint = QLabel(f"Saved key loaded · ends in {current_key[-4:]}")
        else:
            key_hint = QLabel("No saved key found")
        key_hint.setFont(QFont(FONT_MAIN, 8))
        key_hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        layout.addWidget(key_hint)

        brain_heading = QLabel("BRAIN PROVIDER")
        brain_heading.setFont(QFont(FONT_MAIN, 11, QFont.Weight.Bold))
        brain_heading.setStyleSheet(f"color: {C.TEXT}; background: transparent; padding-top: 5px;")
        layout.addWidget(brain_heading)
        self._brain_panel = ProviderSettingsOverlay(parent=body, embedded=True)
        self._brain_panel.saved.connect(self._provider_settings_saved)
        self._brain_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._brain_panel)


        self._status = QLabel("Test both the API connection and an actual model response before saving.")
        self._status.setWordWrap(True)
        self._status.setMinimumHeight(34)
        self._status.setFont(QFont(FONT_MAIN, 9))
        self._status.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        layout.addWidget(self._status)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._reveal_btn = QPushButton("SHOW")
        self._reveal_btn.setFixedHeight(40)
        self._reveal_btn.setStyleSheet(self._secondary_style())
        self._reveal_btn.clicked.connect(self._toggle_reveal)
        row.addWidget(self._reveal_btn)

        self._test_btn = QPushButton("TEST KEY")
        self._test_btn.setFixedHeight(40)
        self._test_btn.setStyleSheet(self._secondary_style())
        self._test_btn.clicked.connect(self._test_key)
        row.addWidget(self._test_btn)

        self._save_btn = QPushButton("SAVE & RECONNECT")
        self._save_btn.setFixedHeight(40)
        self._save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI}; color: {C.DARK}; font-weight: 700;
                border: 1px solid {C.PRI}; border-radius: 6px; padding: 0 12px;
            }}
            QPushButton:disabled {{
                background: {C.PANEL2}; color: {C.TEXT_DIM}; border-color: {C.BORDER};
            }}
        """)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_key)
        row.addWidget(self._save_btn)
        layout.addLayout(row)

        search_card = QFrame(body)
        search_card.setStyleSheet(
            f"QFrame {{ background: {C.GLASS_CARD}; border: 1px solid {C.BORDER}; border-radius: 16px; }}"
        )
        search_layout = QVBoxLayout(search_card)
        search_layout.setContentsMargins(16, 14, 16, 14)
        search_layout.setSpacing(9)
        search_title_row = QHBoxLayout()
        search_icon = QLabel()
        search_icon.setPixmap(svg_icon("wifi", C.ACC).pixmap(QSize(20, 20)))
        search_title_row.addWidget(search_icon)
        search_title = QLabel("REAL-TIME SEARCH")
        search_title.setFont(QFont(FONT_MAIN, 11, QFont.Weight.Bold))
        search_title.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        search_title_row.addWidget(search_title, 1)
        search_layout.addLayout(search_title_row)
        search_note = QLabel("Connect a live web-search API. This is separate from local file or normal application search.")
        search_note.setWordWrap(True)
        search_note.setFont(QFont(FONT_MAIN, 8))
        search_note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        search_layout.addWidget(search_note)

        self._search_provider = QComboBox()
        for label, identifier in (
            ("Tavily Search", "tavily"),
            ("Brave Search API", "brave"),
            ("SerpAPI", "serpapi"),
            ("Exa", "exa"),
        ):
            self._search_provider.addItem(label, identifier)
        self._search_provider.setAccessibleName("Real-time search provider")
        self._search_provider.setFixedHeight(40)
        self._search_provider.setStyleSheet(f"""
            QComboBox {{ background: {C.INPUT}; color: {C.TEXT}; border: 1px solid {C.BORDER};
                        border-radius: 10px; padding: 8px 12px; }}
            QComboBox:focus {{ border-color: {C.PRI}; }}
            QComboBox::drop-down {{ border: 0; width: 28px; }}
        """)
        search_layout.addWidget(QLabel("SEARCH PROVIDER"))
        search_layout.addWidget(self._search_provider)
        self._search_key = QLineEdit()
        self._search_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._search_key.setPlaceholderText("Paste real-time search API key")
        self._search_key.setFixedHeight(42)
        self._search_key.setStyleSheet(f"""
            QLineEdit {{ background: {C.INPUT}; color: {C.TEXT}; border: 1px solid {C.BORDER};
                        border-radius: 10px; padding: 9px 12px; }}
            QLineEdit:focus {{ border-color: {C.PRI}; }}
        """)
        search_layout.addWidget(QLabel("API KEY"))
        search_layout.addWidget(self._search_key)
        search_actions = QHBoxLayout()
        search_actions.addStretch(1)
        self._search_save_btn = QPushButton("SAVE SEARCH KEY")
        self._search_save_btn.setFixedHeight(38)
        self._search_save_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PRI}; color: {C.DARK}; border: 1px solid {C.PRI};
                           border-radius: 10px; padding: 0 16px; font-weight: 700; }}
            QPushButton:hover {{ background: {C.PRI_DIM}; }}
        """)
        self._search_save_btn.clicked.connect(self._save_realtime_search_settings)
        search_actions.addWidget(self._search_save_btn)
        search_layout.addLayout(search_actions)
        self._search_status = QLabel("No search provider key loaded.")
        self._search_status.setWordWrap(True)
        self._search_status.setFont(QFont(FONT_MAIN, 8))
        self._search_status.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        search_layout.addWidget(self._search_status)
        layout.addWidget(search_card)

        self._search_provider.currentIndexChanged.connect(self._on_search_provider_changed)
        self._load_realtime_search_settings()
        self._key_input.textChanged.connect(self._on_key_edited)
        self._test_result.connect(self._finish_test)
        self._local_connection_result.connect(self._finish_local_connection)
        self._local_test_result.connect(self._finish_local_test)
        self._refresh_local_llm_config()
        threading.Thread(target=self._probe_local_connection, args=(
            self._local_provider, self._local_url, self._local_model
        ), daemon=True).start()

    @staticmethod
    def _secondary_style() -> str:
        return f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 6px; padding: 0 10px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.PRI_DIM}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; }}
        """

    def _refresh_local_llm_config(self) -> tuple[str, str, str]:
        """Read the exact Powerful Brain provider profile used by runtime."""
        try:
            from core.provider_registry import load_provider_settings, provider_spec
            settings = load_provider_settings(API_FILE, "powerful")
            self._local_provider = str(settings.get("provider") or "ollama").strip().lower()
            self._local_url = str(settings.get("url") or "").rstrip("/")
            self._local_model = str(settings.get("model") or "").strip()
            provider_label = provider_spec(self._local_provider).label
        except Exception as exc:
            self._local_provider = "unknown"
            self._local_url = ""
            self._local_model = ""
            provider_label = "Unknown"
            self._local_info.setText(f"POWERFUL BRAIN CONNECTION  CONFIG ERROR · {type(exc).__name__}")
            self._local_info.setStyleSheet(
                f"color: {C.RED}; background: transparent; border: none; font-weight: 700;"
            )
        self._local_provider_info.setText(f"POWERFUL BRAIN PROVIDER  {provider_label}")
        self._local_model_info.setText(f"POWERFUL BRAIN MODEL  {self._local_model or 'not configured'}")
        self._local_url_info.setText(f"POWERFUL BRAIN ENDPOINT  {self._local_url or 'not configured'}")
        return self._local_provider, self._local_url, self._local_model

    def _probe_local_connection(self, provider: str, url: str, model: str):
        """Use the same authenticated completion probe as the provider workspace."""
        try:
            from core.provider_registry import probe_provider, provider_api_key
            key = provider_api_key(provider, API_FILE, "powerful")
            outcome = probe_provider(provider, url, model, api_key=key, timeout=25.0)
            ok = bool(outcome.get("ok"))
            detail = (
                f"Live inference succeeded · {outcome.get('latency_ms', 0)} ms."
                if ok else str(outcome.get("error") or "Provider probe failed.")
            )
            self._local_connection_result.emit(ok, provider, url, model, detail)
        except Exception as exc:
            self._local_connection_result.emit(
                False, provider, url, model, f"{type(exc).__name__}: {str(exc)[:180]}"
            )

    def _finish_local_connection(
        self, ok: bool, provider: str, url: str, model: str, detail: str
    ):
        current_provider, current_url, current_model = self._refresh_local_llm_config()
        if (provider, url, model) != (current_provider, current_url, current_model):
            self._local_info.setText("LOCAL AGENT CONNECTION  CONFIG CHANGED · REOPEN SETTINGS")
            self._local_info.setStyleSheet(
                f"color: {C.ACC2}; background: transparent; border: none; font-weight: 700;"
            )
            return
        if ok:
            self._local_info.setText(f"LOCAL AGENT CONNECTION  {detail}")
            self._local_info.setStyleSheet(
                f"color: {C.GREEN}; background: transparent; border: none; font-weight: 700;"
            )
        else:
            self._local_info.setText(f"LOCAL AGENT CONNECTION  NOT READY · {detail}")
            self._local_info.setStyleSheet(
                f"color: {C.RED}; background: transparent; border: none; font-weight: 700;"
            )
        self._local_info.setToolTip(detail)

    def _test_local_llm(self):
        if self._local_test_running:
            return
        provider, url, model = self._refresh_local_llm_config()
        if not url or not model:
            self._local_info.setText("LOCAL AGENT CONNECTION  CONFIG ERROR · URL/model missing")
            self._local_info.setStyleSheet(
                f"color: {C.RED}; background: transparent; border: none; font-weight: 700;"
            )
            return
        self._local_test_running = True
        self._local_test_btn.setEnabled(False)
        self._local_latency_status.setText("LOCAL MODEL INFERENCE  TESTING…")
        self._local_info.setText("LOCAL AGENT CONNECTION  RUNNING REAL INFERENCE…")
        self._local_info.setStyleSheet(
            f"color: {C.ACC2}; background: transparent; border: none; font-weight: 700;"
        )
        threading.Thread(
            target=self._probe_local_llm, args=(provider, url, model), daemon=True
        ).start()

    def _probe_local_llm(self, provider: str, url: str, model: str):
        started = time.perf_counter()
        try:
            from core.llm_client import call_llm
            from core.provider_registry import load_provider_settings

            settings = load_provider_settings(API_FILE, "powerful")
            if (provider, url, model) != (settings["provider"], settings["url"], settings["model"]):
                raise RuntimeError("Powerful Brain config changed during the test; reopen Settings.")
            result = call_llm(
                [{"role": "user", "content": "Reply with only the word OK."}],
                timeout=45,
            )
            answer = str(result.get("content") or "").strip()
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if not answer:
                raise RuntimeError("Configured local model returned no text response.")
            self._local_test_result.emit(True, model, url, elapsed_ms)
        except Exception as exc:
            self._local_test_result.emit(
                False, f"{type(exc).__name__}: {str(exc)[:150]}", url, -1
            )

    def _finish_local_test(self, ok: bool, message: str, url: str, latency_ms: int):
        self._local_test_running = False
        self._local_test_btn.setEnabled(True)
        current_provider, current_url, current_model = self._refresh_local_llm_config()
        if url != current_url:
            self._local_info.setText("LOCAL AGENT CONNECTION  CONFIG CHANGED · REOPEN SETTINGS")
            self._local_info.setStyleSheet(
                f"color: {C.ACC2}; background: transparent; border: none; font-weight: 700;"
            )
            self._local_latency_status.setText("LOCAL MODEL INFERENCE  NOT VERIFIED")
            return
        if ok:
            from core.provider_registry import provider_spec
            provider_label = provider_spec(current_provider).label
            self._local_info.setText(
                f"LOCAL AGENT CONNECTION  ONLINE · {provider_label} inference succeeded"
            )
            self._local_info.setStyleSheet(
                f"color: {C.GREEN}; background: transparent; border: none; font-weight: 700;"
            )
            self._local_latency_status.setText(f"LOCAL MODEL INFERENCE  {latency_ms} ms · {current_model}")
            self._local_latency_status.setToolTip(f"Successful inference through the configured provider at {url}.")
        else:
            self._local_info.setText(f"LOCAL AGENT CONNECTION  INFERENCE FAILED · {message}")
            self._local_info.setStyleSheet(
                f"color: {C.RED}; background: transparent; border: none; font-weight: 700;"
            )
            self._local_latency_status.setText("LOCAL MODEL INFERENCE  FAILED")
            self._local_latency_status.setToolTip(message)

    def _toggle_reveal(self):
        reveal = self._key_input.echoMode() == QLineEdit.EchoMode.Password
        self._key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if reveal else QLineEdit.EchoMode.Password
        )
        self._reveal_btn.setText("HIDE" if reveal else "SHOW")

    def _on_key_edited(self, _text: str):
        self._tested_key = ""
        self._save_btn.setEnabled(False)
        if not self._test_running:
            self._status.setText("Key changed. Test it before saving.")
            self._status.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            self._connection_status.setText("LAST TEST  NOT TESTED")
            self._connection_status.setStyleSheet(
                f"color: {C.TEXT_DIM}; background: transparent; border: none; font-weight: 700;"
            )
            self._latency_status.setText("TIME TO FIRST MODEL RESPONSE  —")

    def _test_key(self):
        key = self._key_input.text().strip()
        if not key:
            self._status.setText("Paste a key to test.")
            return
        if self._test_running:
            return
        self._test_running = True
        self._test_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._status.setText("Opening a Live session and waiting for an actual model response…")
        self._status.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
        self._connection_status.setText("LAST TEST  RUNNING…")
        self._connection_status.setStyleSheet(
            f"color: {C.ACC2}; background: transparent; border: none; font-weight: 700;"
        )
        self._latency_status.setText("TIME TO FIRST MODEL RESPONSE  measuring…")
        threading.Thread(target=self._probe_live_key, args=(key,), daemon=True).start()

    def _probe_live_key(self, key: str):
        latency_ms = -1
        try:
            import asyncio
            from google import genai
            from google.genai import types

            async def _probe():
                started = time.perf_counter()
                client = genai.Client(
                    api_key=key,
                    http_options={"api_version": "v1beta"},
                )
                config = types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Kore"
                            )
                        )
                    ),
                )
                async with client.aio.live.connect(
                    model="models/gemini-2.5-flash-native-audio-preview-12-2025",
                    config=config,
                ) as session:
                    await session.send_client_content(
                        turns={"parts": [{"text": "Say only: OK."}]},
                        turn_complete=True,
                    )

                    async def _wait_for_first_output() -> bool:
                        async for response in session.receive():
                            if getattr(response, "data", None):
                                return True
                            server_content = getattr(response, "server_content", None)
                            if server_content:
                                model_turn = getattr(server_content, "model_turn", None)
                                parts = getattr(model_turn, "parts", None) or []
                                if any(
                                    getattr(part, "inline_data", None) is not None
                                    or bool(getattr(part, "text", None))
                                    for part in parts
                                ):
                                    return True
                                if getattr(server_content, "turn_complete", False):
                                    return False
                        return False

                    got_output = await asyncio.wait_for(_wait_for_first_output(), timeout=18.0)
                    elapsed = int((time.perf_counter() - started) * 1000)
                    if not got_output:
                        raise RuntimeError("Live session opened, but the model returned no output.")
                    return elapsed

            latency_ms = asyncio.run(asyncio.wait_for(_probe(), timeout=22.0))
            message = f"Live API connected and the model responded successfully in {latency_ms} ms."
            self._test_result.emit(True, message, key, latency_ms)
        except Exception as exc:
            detail = str(exc).replace(key, "[REDACTED]")[:180]
            message = f"Live model test failed ({type(exc).__name__}). {detail}"
            self._test_result.emit(False, message, key, latency_ms)

    def _finish_test(self, ok: bool, message: str, key: str, latency_ms: int):
        self._test_running = False
        self._test_btn.setEnabled(True)
        key_still_matches = key == self._key_input.text().strip()
        if ok and key_still_matches:
            self._status.setText(message)
            self._status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
            self._connection_status.setText("LAST TEST  PASSED · MODEL RESPONSE RECEIVED")
            self._connection_status.setStyleSheet(
                f"color: {C.GREEN}; background: transparent; border: none; font-weight: 700;"
            )
            self._latency_status.setText(f"TIME TO FIRST MODEL RESPONSE  {latency_ms} ms")
            self._tested_key = key
            self._save_btn.setEnabled(True)
            return

        self._tested_key = ""
        self._save_btn.setEnabled(False)
        if not key_still_matches:
            self._status.setText("The input changed during testing. Test the current key again.")
            self._status.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
            self._connection_status.setText("LAST TEST  NOT TESTED")
            self._connection_status.setStyleSheet(
                f"color: {C.TEXT_DIM}; background: transparent; border: none; font-weight: 700;"
            )
            self._latency_status.setText("TIME TO FIRST MODEL RESPONSE  —")
        else:
            self._status.setText(message)
            self._status.setStyleSheet(f"color: {C.RED}; background: transparent;")
            self._connection_status.setText("LAST TEST  FAILED · SEE DETAILS BELOW")
            self._connection_status.setStyleSheet(
                f"color: {C.RED}; background: transparent; border: none; font-weight: 700;"
            )
            self._latency_status.setText("TIME TO FIRST MODEL RESPONSE  —")

    def _save_key(self):
        key = self._key_input.text().strip()
        if not key or key != self._tested_key:
            self._status.setText("Test the exact key before saving.")
            self._save_btn.setEnabled(False)
            return
        try:
            status = save_gemini_api_key(key, API_FILE)
        except Exception as exc:
            self._status.setText(f"Could not save API key: {type(exc).__name__}: {exc}")
            self._status.setStyleSheet(f"color: {C.RED}; background: transparent;")
            return

        if status.storage == "legacy":
            self._status.setText(
                "Key saved, but no OS keychain is available. It will migrate automatically when one is available."
            )
            self._status.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
        else:
            self._status.setText("Key saved to the OS keychain. Reconnecting to Gemini Live…")
            self._status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        self.saved.emit()
        self.hide()

    def _open_provider_settings(self):
        parent = self.parentWidget() or self
        panel = ProviderSettingsOverlay(parent=parent)
        panel.saved.connect(self._provider_settings_saved)
        width, height = ProviderSettingsOverlay._OW, ProviderSettingsOverlay._OH
        panel.setGeometry(max(8, (parent.width() - width) // 2),
                          max(8, (parent.height() - height) // 2),
                          min(width, parent.width() - 16), min(height, parent.height() - 16))
        panel.show()
        panel.raise_()
        self._provider_settings_overlay = panel

    def _provider_settings_saved(self):
        self._refresh_local_llm_config()
        self._local_info.setText("LOCAL AGENT CONNECTION  PROVIDER SETTINGS SAVED · TEST AGAIN TO VERIFY")
        self._local_info.setStyleSheet(
            f"color: {C.ACC2}; background: transparent; border: none; font-weight: 700;"
        )

    def _load_realtime_search_settings(self):
        data = _read_full_config()
        provider = str(data.get("realtime_search_provider") or "tavily").strip().lower()
        index = self._search_provider.findData(provider)
        self._search_provider.setCurrentIndex(max(0, index))
        self._on_search_provider_changed()

    def _on_search_provider_changed(self, *_args):
        provider = str(self._search_provider.currentData() or "tavily")
        secret_name = self._SEARCH_SECRET_NAMES.get(provider)
        saved = get_config_secret(secret_name, API_FILE).value if secret_name else None
        self._search_key.setText(saved or "")
        if saved:
            self._search_status.setText(f"{self._search_provider.currentText()} key loaded from local credential storage.")
        else:
            self._search_status.setText(f"Paste a {self._search_provider.currentText()} API key, then save it.")
        self._search_status.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")

    def _save_realtime_search_settings(self):
        provider = str(self._search_provider.currentData() or "")
        secret_name = self._SEARCH_SECRET_NAMES.get(provider)
        key = self._search_key.text().strip()
        if not secret_name or not key:
            self._search_status.setText("Choose a provider and paste its API key before saving.")
            self._search_status.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
            return
        try:
            status = save_config_secret(secret_name, key, API_FILE)
            data = _read_full_config()
            data["realtime_search_provider"] = provider
            API_FILE.parent.mkdir(parents=True, exist_ok=True)
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
        except Exception as exc:
            self._search_status.setText(f"Could not save search settings: {type(exc).__name__}.")
            self._search_status.setStyleSheet(f"color: {C.RED}; background: transparent;")
            return
        if status.storage == "legacy":
            self._search_status.setText("Search key saved locally; OS keychain is unavailable on this machine.")
            self._search_status.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
        else:
            self._search_status.setText("Search provider and API key saved to local credential storage.")
            self._search_status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        self._search_key.clear()
        self._search_key.setPlaceholderText(
            "Saved locally · paste a new key to replace"
            if status.storage == "legacy"
            else "Saved to OS keychain · paste a new key to replace"
        )

class ProviderSettingsOverlay(QWidget):
    """Provider-specific endpoint/model/key editor; the Gemini Live editor remains above."""

    saved = pyqtSignal()
    _test_result = pyqtSignal(object)
    _OW, _OH = 620, 620

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent)
        self._embedded = bool(embedded)
        if not self._embedded:
            _glass_shadow(self)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ProviderSettingsOverlay {{ background: {C.SHEET}; border: 1px solid {C.BORDER_B}; border-radius: 20px; }}
        """)
        self._tested_signature: tuple[str, str, str, str] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(11)

        title_row = QHBoxLayout()
        title = QLabel("BRAIN  /  TEXT MODEL PROVIDERS")
        title.setFont(QFont(FONT_MAIN, 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        title_row.addWidget(title, 1)
        if not self._embedded:
            close_btn = QPushButton()
            close_btn.setAccessibleName("Close Brain provider settings")
            close_btn.setToolTip("Close")
            close_btn.setIcon(svg_icon("x", C.TEXT_DIM))
            close_btn.setIconSize(QSize(18, 18))
            close_btn.setFixedSize(36, 36)
            close_btn.setStyleSheet(f"QPushButton {{ background:{C.PANEL2}; border:1px solid {C.BORDER}; border-radius:11px; }} QPushButton:hover {{ background:{C.DANGER_BG}; border-color:{C.RED}; }}")
            close_btn.clicked.connect(self.hide)
            title_row.addWidget(close_btn)
        layout.addLayout(title_row)
        hint = QLabel("Choose the reasoning model EDITH uses for text tasks. Voice is configured separately. Credentials use the OS keychain when available.")
        hint.setWordWrap(True); hint.setFont(QFont(FONT_MAIN, 8))
        hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        layout.addWidget(hint)

        self._provider = QComboBox()
        for identifier, label in (("ollama", "Ollama (local)"), ("openai", "OpenAI / ChatGPT"),
                                  ("anthropic", "Anthropic Claude"), ("xai", "xAI Grok"),
                                  ("openai_compatible", "OpenAI-compatible local server")):
            self._provider.addItem(label, identifier)
        self._provider.setAccessibleName("Text model provider")
        layout.addWidget(self._field_label("PROVIDER")); layout.addWidget(self._provider)
        self._url = QLineEdit(); self._model = QLineEdit(); self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText("Required for cloud providers; never written to activity logs")
        for title_text, field in (("API ENDPOINT", self._url), ("MODEL ID", self._model), ("API KEY", self._key)):
            layout.addWidget(self._field_label(title_text)); field.setFixedHeight(40); field.setStyleSheet(self._field_style()); layout.addWidget(field)
        self._status = QLabel("Select a provider, then test a real minimal response.")
        self._status.setWordWrap(True); self._status.setMinimumHeight(36)
        self._status.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        layout.addWidget(self._status)
        row = QHBoxLayout(); row.setSpacing(8)
        test = QPushButton("TEST CONNECTION"); save = QPushButton("SAVE PROVIDER")
        test.setMinimumWidth(142); save.setMinimumWidth(142)
        self._test = test; self._save = save
        test.setStyleSheet(ApiKeyOverlay._secondary_style()); test.setFixedHeight(40)
        save.setStyleSheet(f"QPushButton {{ background:{C.PRI}; color:{C.DARK}; border:1px solid {C.PRI}; border-radius:10px; font-weight:700; padding:0 12px; }} QPushButton:disabled {{ background:{C.PANEL2}; color:{C.TEXT_DIM}; border-color:{C.BORDER}; }}")
        save.setFixedHeight(40); save.setEnabled(False)
        test.clicked.connect(self._test_connection); save.clicked.connect(self._save_provider)
        row.addWidget(test); row.addWidget(save); layout.addLayout(row)
        self._provider.currentIndexChanged.connect(self._provider_changed)
        for field in (self._url, self._model, self._key): field.textChanged.connect(lambda _text: self._save.setEnabled(False))
        self._test_result.connect(self._finish_test)
        self._load_current()

    @staticmethod
    def _field_style() -> str:
        return f"QLineEdit, QComboBox {{ background:{C.DARK}; color:{C.TEXT}; border:1px solid {C.BORDER}; border-radius:10px; padding:8px 11px; }} QLineEdit:focus, QComboBox:focus {{ border-color:{C.PRI}; }}"

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text); label.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold)); label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        return label

    def _signature(self) -> tuple[str, str, str, str]:
        return (str(self._provider.currentData()), self._url.text().strip().rstrip("/"), self._model.text().strip(), self._key.text().strip())

    def _load_current(self):
        from core.provider_registry import load_provider_settings, provider_api_key
        settings = load_provider_settings(API_FILE)
        index = self._provider.findData(settings["provider"])
        self._provider.setCurrentIndex(max(0, index))
        self._url.setText(settings["url"]); self._model.setText(settings["model"])
        saved_key = provider_api_key(settings["provider"], API_FILE) or ""
        self._key.setText(saved_key)
        self._provider_changed()

    def _provider_changed(self, *_args):
        from core.provider_registry import provider_spec
        spec = provider_spec(self._provider.currentData())
        if not self._url.text().strip() or self._url.property("provider_default"):
            self._url.setText(spec.default_url); self._url.setProperty("provider_default", True)
        if not self._model.text().strip() or self._model.property("provider_default"):
            self._model.setText(spec.default_model); self._model.setProperty("provider_default", True)
        self._key.setEnabled(bool(spec.secret_name))
        self._key.setPlaceholderText("Not required for this local provider" if not spec.secret_name else "API key stored through the OS keychain")
        self._save.setEnabled(False)

    def _test_connection(self):
        if not self._url.text().strip() or not self._model.text().strip():
            self._status.setText("Endpoint and model are required."); return
        signature = self._signature(); self._test.setEnabled(False); self._save.setEnabled(False)
        self._status.setText("Sending a minimal real provider request…")
        self._status.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
        def worker():
            from core.provider_registry import probe_provider
            result = probe_provider(*signature[:3], api_key=signature[3] or None)
            self._test_result.emit((signature, result))
        threading.Thread(target=worker, daemon=True).start()

    def _finish_test(self, payload):
        self._test.setEnabled(True)
        signature, result = payload
        if signature != self._signature():
            self._status.setText("Settings changed during the test; test the current values again.")
            self._status.setStyleSheet(f"color: {C.ACC2}; background: transparent;"); return
        if result.get("ok"):
            self._tested_signature = signature; self._save.setEnabled(True)
            self._status.setText(f"Connection passed · {result.get('latency_ms')} ms · model responded.")
            self._status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        else:
            self._tested_signature = None; self._save.setEnabled(False)
            self._status.setText(f"Connection failed · {result.get('error')}")
            self._status.setStyleSheet(f"color: {C.RED}; background: transparent;")

    def _save_provider(self):
        signature = self._signature()
        if signature != self._tested_signature:
            self._status.setText("Test the exact provider settings before saving."); return
        try:
            from core.provider_registry import save_provider_settings
            save_provider_settings(API_FILE, *signature)
        except Exception as exc:
            self._status.setText(f"Could not save provider: {type(exc).__name__}: {exc}")
            self._status.setStyleSheet(f"color: {C.RED}; background: transparent;"); return
        self._status.setText("Provider settings saved. The next local-agent request uses this provider.")
        self._status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        self.saved.emit()
        if not self._embedded:
            self.hide()




class _ApiTabBase(QWidget):
    """Shared quiet surface, field and feedback helpers for API provider tabs."""

    def _init_surface(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QWidget {{ background: transparent; color: {C.TEXT}; }}
            QLabel {{ background: transparent; }}
        """)

    def _create_scroll_form(self) -> QVBoxLayout:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: 0; }}
            QScrollBar:vertical {{ background: transparent; width: 7px; margin: 4px 0; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 3px; min-height: 26px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        return layout

    @staticmethod
    def _field_style() -> str:
        return f"""
            QLineEdit, QComboBox {{
                background: {C.INPUT}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 11px;
                padding: 9px 12px; min-height: 22px;
                selection-background-color: {C.PRI_GHO};
            }}
            QLineEdit:focus, QComboBox:focus {{ border: 1px solid {C.PRI_DIM}; }}
            QComboBox::drop-down {{ border: 0; width: 28px; }}
            QComboBox QAbstractItemView {{
                background: {C.PANEL}; color: {C.TEXT};
                border: 0; selection-background-color: {C.PRI_GHO};
                outline: 0; padding: 5px;
            }}
        """

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        return label

    @staticmethod
    def _button(text: str, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(40)
        button.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        if primary:
            button.setStyleSheet(f"""
                QPushButton {{ background: {C.PRI}; color: {C.DARK};
                               border: 0; border-radius: 11px; padding: 0 17px; }}
                QPushButton:hover {{ background: {C.PRI_DIM}; }}
                QPushButton:disabled {{ background: {C.PANEL2}; color: {C.TEXT_DIM}; }}
            """)
        else:
            button.setStyleSheet(f"""
                QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_MED};
                               border: 0; border-radius: 11px; padding: 0 15px; }}
                QPushButton:hover {{ background: {C.HOVER}; color: {C.TEXT}; }}
                QPushButton:disabled {{ color: {C.TEXT_DIM}; }}
            """)
        return button

    def _set_status(self, text: str, tone: str = "neutral") -> None:
        palette = {"success": C.GREEN, "error": C.RED, "warning": C.ACC2,
                   "neutral": C.TEXT_DIM, "working": C.PRI}
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {palette.get(tone, C.TEXT_DIM)}; background: transparent;")

    @staticmethod
    def _secret_preview(key: str) -> str:
        if not key:
            return "No saved key"
        return f"Saved key available · ending {key[-4:]}"


class _ProviderProfileTab(_ApiTabBase):
    """Account-aware provider/model/key setup for Main Brain or Powerful Brain."""

    saved = pyqtSignal()
    _models_result = pyqtSignal(object)
    _test_result = pyqtSignal(object)

    _PROVIDERS = (
        ("Ollama · Local", "ollama"),
        ("OpenAI", "openai"),
        ("Anthropic Claude", "anthropic"),
        ("Groq", "groq"),
        ("xAI · Grok", "xai"),
        ("OpenAI-compatible local server", "openai_compatible"),
    )

    def __init__(self, profile: str, parent=None):
        super().__init__(parent)
        self.profile = profile
        self._tested_signature = None
        self._loading_models = False
        self._key_revealed = False
        self._previous_provider: str | None = None

        layout = self._create_scroll_form()

        title_row = QHBoxLayout()
        icon = QLabel()
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(svg_icon("brain-circuit" if profile == "main" else "cpu", C.PRI).pixmap(QSize(21, 21)))
        icon.setStyleSheet(f"background: {C.PANEL2}; border-radius: 12px;")
        title_row.addWidget(icon)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Main reasoning model" if profile == "main" else "High-capability reasoning model")
        title.setFont(QFont(FONT_MAIN, 12, QFont.Weight.Bold))
        title_col.addWidget(title)
        hint = QLabel("Select provider, load its available models, test the exact setup, then save.")
        hint.setWordWrap(True)
        hint.setFont(QFont(FONT_MAIN, 8))
        hint.setStyleSheet(f"color: {C.TEXT_DIM};")
        title_col.addWidget(hint)
        title_row.addLayout(title_col, 1)
        layout.addLayout(title_row)

        if profile == "powerful":
            self._inherit_note = QLabel("Powerful Brain currently follows Main Brain until you save its own profile.")
            self._inherit_note.setWordWrap(True)
            self._inherit_note.setFont(QFont(FONT_MAIN, 8))
            self._inherit_note.setStyleSheet(f"color: {C.ACC2}; background: {C.PANEL2}; border-radius: 9px; padding: 8px 10px;")
            self._inherit_note.setVisible(not __import__("core.provider_registry", fromlist=["has_provider_profile"]).has_provider_profile(API_FILE, "powerful"))
            layout.addWidget(self._inherit_note)

        layout.addWidget(self._label("Provider"))
        self._provider = QComboBox()
        for label_text, identifier in self._PROVIDERS:
            self._provider.addItem(label_text, identifier)
        self._provider.setAccessibleName(f"{profile.title()} Brain API provider")
        self._provider.setFixedHeight(42)
        self._provider.setStyleSheet(self._field_style())
        layout.addWidget(self._provider)

        layout.addWidget(self._label("API endpoint"))
        self._url = QLineEdit()
        self._url.setFixedHeight(42)
        self._url.setStyleSheet(self._field_style())
        layout.addWidget(self._url)

        layout.addWidget(self._label("API key"))
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText("Paste provider API key · not written to logs")
        self._key.setFixedHeight(42)
        self._key.setStyleSheet(self._field_style())
        key_row.addWidget(self._key, 1)
        self._reveal = self._button("")
        self._reveal.setAccessibleName(f"Preview {profile} Brain API key")
        self._reveal.setToolTip("Show or hide saved API key")
        self._reveal.setIcon(svg_icon("eye", C.TEXT_DIM))
        self._reveal.setIconSize(QSize(18, 18))
        self._reveal.setFixedSize(44, 42)
        self._reveal.clicked.connect(self._toggle_reveal)
        key_row.addWidget(self._reveal)
        layout.addLayout(key_row)
        self._key_hint = QLabel("No saved key")
        self._key_hint.setFont(QFont(FONT_MAIN, 8))
        self._key_hint.setStyleSheet(f"color: {C.TEXT_DIM};")
        layout.addWidget(self._key_hint)

        layout.addWidget(self._label("Model"))
        model_row = QHBoxLayout()
        model_row.setSpacing(8)
        self._model = QComboBox()
        self._model.setEditable(True)
        self._model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._model.setAccessibleName(f"{profile.title()} Brain model")
        self._model.setFixedHeight(42)
        self._model.setStyleSheet(self._field_style())
        model_row.addWidget(self._model, 1)
        self._refresh_btn = self._button("LOAD MODELS")
        self._refresh_btn.setToolTip("Fetch models currently available to this provider API key")
        self._refresh_btn.clicked.connect(self._refresh_models)
        model_row.addWidget(self._refresh_btn)
        layout.addLayout(model_row)

        self._status = QLabel("Choose a model. Save is enabled only after a successful live test.")
        self._status.setWordWrap(True)
        self._status.setMinimumHeight(34)
        self._status.setFont(QFont(FONT_MAIN, 8))
        self._status.setStyleSheet(f"color: {C.TEXT_DIM};")
        layout.addWidget(self._status)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._test_btn = self._button("TEST CONNECTION")
        self._save_btn = self._button("SAVE / UPDATE", primary=True)
        self._test_btn.clicked.connect(self._test_connection)
        self._save_btn.clicked.connect(self._save_profile)
        self._save_btn.setEnabled(False)
        actions.addWidget(self._test_btn)
        actions.addWidget(self._save_btn)
        layout.addLayout(actions)
        layout.addStretch(1)

        self._models_result.connect(self._finish_models)
        self._test_result.connect(self._finish_test)
        self._provider.currentIndexChanged.connect(self._provider_changed)
        self._url.textChanged.connect(self._invalidate)
        self._key.textChanged.connect(self._on_key_changed)
        self._model.currentTextChanged.connect(self._invalidate)
        self._load_current()

    def _signature(self):
        return (str(self._provider.currentData() or ""),
                self._url.text().strip().rstrip("/"),
                self._model.currentText().strip(),
                self._key.text().strip())

    def _invalidate(self, *_args):
        self._tested_signature = None
        self._save_btn.setEnabled(False)
        if hasattr(self, "_status") and self._status.text().startswith("TEST PASSED"):
            self._set_status("Settings changed. Test this exact provider, key and model again.", "warning")

    def _on_key_changed(self, *_args):
        self._key_hint.setText("Unsaved key changes · test before saving")
        self._invalidate()

    def _toggle_reveal(self):
        self._key_revealed = not self._key_revealed
        self._key.setEchoMode(QLineEdit.EchoMode.Normal if self._key_revealed else QLineEdit.EchoMode.Password)
        self._reveal.setIcon(svg_icon("eye-off" if self._key_revealed else "eye", C.TEXT_DIM))
        self._reveal.setToolTip("Hide API key" if self._key_revealed else "Preview API key")

    def _load_current(self):
        from core.provider_registry import load_provider_settings, provider_api_key
        settings = load_provider_settings(API_FILE, self.profile)
        self._provider.blockSignals(True)
        self._provider.setCurrentIndex(max(0, self._provider.findData(settings["provider"])))
        self._provider.blockSignals(False)
        self._url.setText(settings["url"])
        self._model.clear()
        self._model.addItem(settings["model"])
        self._model.setCurrentText(settings["model"])
        key = provider_api_key(settings["provider"], API_FILE, self.profile) or ""
        self._key.blockSignals(True)
        self._key.setText(key)
        self._key.blockSignals(False)
        self._key_hint.setText(self._secret_preview(key))
        self._previous_provider = settings["provider"]
        self._provider_changed()

    def _provider_changed(self, *_args):
        from core.provider_registry import provider_spec, provider_api_key
        provider = str(self._provider.currentData() or "ollama")
        spec = provider_spec(provider)
        if provider != self._previous_provider:
            self._url.setText(spec.default_url)
            self._model.blockSignals(True)
            self._model.clear()
            self._model.addItem(spec.default_model)
            self._model.setCurrentText(spec.default_model)
            self._model.blockSignals(False)
            self._previous_provider = provider
        saved_key = provider_api_key(provider, API_FILE, self.profile) or ""
        self._key.blockSignals(True)
        self._key.setText(saved_key)
        self._key.blockSignals(False)
        self._key_hint.setText(self._secret_preview(saved_key))
        self._model.setEnabled(True)
        self._refresh_btn.setEnabled(True)
        self._key.setPlaceholderText("Not required for this local provider" if not spec.secret_name
                                     else f"Paste {spec.label} API key")
        self._invalidate()
        if self._key_revealed:
            self._key.setEchoMode(QLineEdit.EchoMode.Password)
            self._key_revealed = False
            self._reveal.setIcon(svg_icon("eye", C.TEXT_DIM))

    def _refresh_models(self):
        from core.provider_registry import list_provider_models
        signature = self._signature()
        provider, url, _model, key = signature
        if provider not in {"ollama", "openai_compatible"} and not key:
            self._set_status("Paste this provider's API key before loading its model list.", "warning")
            return
        if self._loading_models:
            return
        self._loading_models = True
        self._refresh_btn.setEnabled(False)
        self._set_status("Loading models available to this API key…", "working")

        def worker():
            try:
                models = list_provider_models(provider, url, key or None)
                self._models_result.emit({"signature": signature, "models": models, "error": None})
            except Exception as exc:
                self._models_result.emit({"signature": signature, "models": [], "error": str(exc)})
        threading.Thread(target=worker, daemon=True).start()

    def _finish_models(self, payload):
        self._loading_models = False
        self._refresh_btn.setEnabled(True)
        loaded = payload.get("signature") or ("", "", "", "")
        current_signature = self._signature()
        if (loaded[0], loaded[1], loaded[3]) != (
            current_signature[0], current_signature[1], current_signature[3]
        ):
            self._set_status("Provider, endpoint or key changed while models were loading. Load again.", "warning")
            return
        if payload.get("error"):
            self._set_status(payload["error"], "error")
            return
        current = self._model.currentText().strip()
        self._model.blockSignals(True)
        self._model.clear()
        self._model.addItems(payload["models"])
        if current and current not in payload["models"]:
            self._model.addItem(current)
        self._model.setCurrentText(current if current else payload["models"][0])
        self._model.blockSignals(False)
        self._invalidate()
        self._set_status(f"Loaded {len(payload['models'])} available model(s) from {self._provider.currentText()}.", "success")

    def _test_connection(self):
        from core.provider_registry import probe_provider
        signature = self._signature()
        provider, url, model, key = signature
        if not url or not model:
            self._set_status("Choose a provider, endpoint and model first.", "warning")
            return
        spec_has_key = provider not in {"ollama", "openai_compatible"}
        if spec_has_key and not key:
            self._set_status("Paste the provider API key before testing.", "warning")
            return
        self._test_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._set_status("Testing the selected model with a live request…", "working")

        def worker():
            result = probe_provider(provider, url, model, key or None)
            self._test_result.emit({"signature": signature, "result": result})
        threading.Thread(target=worker, daemon=True).start()

    def _finish_test(self, payload):
        self._test_btn.setEnabled(True)
        signature = payload.get("signature")
        result = payload.get("result") or {}
        if signature != self._signature():
            self._set_status("Inputs changed during the test. Run the test again.", "warning")
            return
        if result.get("ok"):
            self._tested_signature = signature
            self._save_btn.setEnabled(True)
            self._set_status(f"TEST PASSED · {result.get('latency_ms', 0)} ms · {result.get('model', '')}", "success")
        else:
            self._tested_signature = None
            self._save_btn.setEnabled(False)
            self._set_status(f"TEST FAILED · {result.get('error') or 'No model response'}", "error")

    def _save_profile(self):
        from core.provider_registry import save_provider_settings, has_provider_profile
        signature = self._signature()
        if signature != self._tested_signature:
            self._set_status("Test the exact provider, model and key before saving.", "warning")
            return
        try:
            provider, url, model, key = signature
            save_provider_settings(API_FILE, provider, url, model, key, profile=self.profile)
        except Exception as exc:
            self._set_status(f"Could not save settings: {type(exc).__name__}: {exc}", "error")
            return
        self._tested_signature = signature
        if self.profile == "powerful" and hasattr(self, "_inherit_note"):
            self._inherit_note.hide()
        self._key_hint.setText(self._secret_preview(key))
        self._set_status("Saved. EDITH will use this provider and model for this Brain profile.", "success")
        self.saved.emit()


class _VoiceProviderTab(_ApiTabBase):
    """Gemini Live voice provider settings with real model response validation."""

    saved = pyqtSignal()
    _models_result = pyqtSignal(object)
    _test_result = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tested_signature = None
        self._loading_models = False
        self._key_revealed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(12)

        title_row = QHBoxLayout()
        icon = QLabel()
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(svg_icon("mic", C.PRI).pixmap(QSize(20, 20)))
        icon.setStyleSheet(f"background: {C.PANEL2}; border-radius: 12px;")
        title_row.addWidget(icon)
        title_col = QVBoxLayout()
        title = QLabel("Voice connection")
        title.setFont(QFont(FONT_MAIN, 12, QFont.Weight.Bold))
        title_col.addWidget(title)
        hint = QLabel("The current EDITH audio transport supports Google Gemini Live.")
        hint.setFont(QFont(FONT_MAIN, 8))
        hint.setStyleSheet(f"color: {C.TEXT_DIM};")
        title_col.addWidget(hint)
        title_row.addLayout(title_col, 1)
        layout.addLayout(title_row)

        layout.addWidget(self._label("Voice provider"))
        self._provider = QComboBox()
        self._provider.addItem("Google Gemini Live", "gemini_live")
        self._provider.setAccessibleName("Voice API provider")
        self._provider.setFixedHeight(42)
        self._provider.setStyleSheet(self._field_style())
        layout.addWidget(self._provider)

        layout.addWidget(self._label("Voice model"))
        model_row = QHBoxLayout()
        self._model = QComboBox()
        self._model.setEditable(True)
        self._model.setFixedHeight(42)
        self._model.setStyleSheet(self._field_style())
        model_row.addWidget(self._model, 1)
        self._refresh_btn = self._button("LOAD MODELS")
        self._refresh_btn.clicked.connect(self._refresh_models)
        model_row.addWidget(self._refresh_btn)
        layout.addLayout(model_row)

        layout.addWidget(self._label("Voice API key"))
        key_row = QHBoxLayout()
        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText("Paste Gemini Live API key")
        self._key.setFixedHeight(42)
        self._key.setStyleSheet(self._field_style())
        key_row.addWidget(self._key, 1)
        self._reveal = self._button("")
        self._reveal.setIcon(svg_icon("eye", C.TEXT_DIM))
        self._reveal.setIconSize(QSize(18, 18))
        self._reveal.setFixedSize(44, 42)
        self._reveal.setAccessibleName("Preview Voice API key")
        self._reveal.clicked.connect(self._toggle_reveal)
        key_row.addWidget(self._reveal)
        layout.addLayout(key_row)
        self._key_hint = QLabel("No saved key")
        self._key_hint.setFont(QFont(FONT_MAIN, 8))
        self._key_hint.setStyleSheet(f"color: {C.TEXT_DIM};")
        layout.addWidget(self._key_hint)

        self._status = QLabel("Test the selected Live model before saving or updating the key.")
        self._status.setWordWrap(True)
        self._status.setMinimumHeight(36)
        self._status.setFont(QFont(FONT_MAIN, 8))
        self._status.setStyleSheet(f"color: {C.TEXT_DIM};")
        layout.addWidget(self._status)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self._test_btn = self._button("TEST VOICE")
        self._save_btn = self._button("SAVE / UPDATE", primary=True)
        self._save_btn.setEnabled(False)
        self._test_btn.clicked.connect(self._test_voice)
        self._save_btn.clicked.connect(self._save_voice)
        actions.addWidget(self._test_btn)
        actions.addWidget(self._save_btn)
        layout.addLayout(actions)
        layout.addStretch(1)

        self._models_result.connect(self._finish_models)
        self._test_result.connect(self._finish_test)
        self._model.currentTextChanged.connect(self._invalidate)
        self._key.textChanged.connect(self._on_key_changed)
        self._load_current()

    def _signature(self):
        return (str(self._provider.currentData() or "gemini_live"),
                self._model.currentText().strip(), self._key.text().strip())

    def _invalidate(self, *_args):
        self._tested_signature = None
        self._save_btn.setEnabled(False)

    def _on_key_changed(self, *_args):
        self._key_hint.setText("Unsaved key changes · test before saving")
        self._invalidate()

    def _load_current(self):
        from core.provider_registry import load_voice_settings
        from core.secrets import get_gemini_api_key
        settings = load_voice_settings(API_FILE)
        self._model.addItem(settings["model"])
        key = get_gemini_api_key(API_FILE) or ""
        self._key.setText(key)
        self._key_hint.setText(self._secret_preview(key))

    def _toggle_reveal(self):
        self._key_revealed = not self._key_revealed
        self._key.setEchoMode(QLineEdit.EchoMode.Normal if self._key_revealed else QLineEdit.EchoMode.Password)
        self._reveal.setIcon(svg_icon("eye-off" if self._key_revealed else "eye", C.TEXT_DIM))

    def _refresh_models(self):
        from core.provider_registry import list_voice_models
        key = self._key.text().strip()
        if not key:
            self._set_status("Paste the Voice API key before loading account models.", "warning")
            return
        if self._loading_models:
            return
        self._loading_models = True
        self._refresh_btn.setEnabled(False)
        self._set_status("Loading Live models available to this API key…", "working")
        def worker():
            try:
                models = list_voice_models(key)
                self._models_result.emit({"key": key, "models": models, "error": None})
            except Exception as exc:
                self._models_result.emit({"key": key, "models": [], "error": str(exc)})
        threading.Thread(target=worker, daemon=True).start()

    def _finish_models(self, payload):
        self._loading_models = False
        self._refresh_btn.setEnabled(True)
        if payload.get("key") != self._key.text().strip():
            self._set_status("Voice key changed while models were loading. Load again.", "warning")
            return
        if payload.get("error"):
            self._set_status(payload["error"], "error")
            return
        current = self._model.currentText().strip()
        self._model.blockSignals(True)
        self._model.clear()
        self._model.addItems(payload["models"])
        if current and current not in payload["models"]:
            self._model.addItem(current)
        self._model.setCurrentText(current if current else payload["models"][0])
        self._model.blockSignals(False)
        self._invalidate()
        self._set_status(f"Loaded {len(payload['models'])} Live model(s).", "success")

    def _test_voice(self):
        from core.provider_registry import probe_voice_provider
        signature = self._signature()
        if not signature[1] or not signature[2]:
            self._set_status("Choose a Live model and paste the Voice API key.", "warning")
            return
        self._test_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._set_status("Opening a real Gemini Live session and waiting for model output…", "working")
        def worker():
            result = probe_voice_provider(*signature)
            self._test_result.emit({"signature": signature, "result": result})
        threading.Thread(target=worker, daemon=True).start()

    def _finish_test(self, payload):
        self._test_btn.setEnabled(True)
        signature = payload.get("signature")
        result = payload.get("result") or {}
        if signature != self._signature():
            self._set_status("Inputs changed during the test. Test the current Voice setup again.", "warning")
            return
        if result.get("ok"):
            self._tested_signature = signature
            self._save_btn.setEnabled(True)
            self._set_status(f"TEST PASSED · Live model responded in {result.get('latency_ms', 0)} ms.", "success")
        else:
            self._tested_signature = None
            self._save_btn.setEnabled(False)
            self._set_status(f"TEST FAILED · {result.get('error') or 'No Live response'}", "error")

    def _save_voice(self):
        from core.provider_registry import save_voice_settings
        signature = self._signature()
        if signature != self._tested_signature:
            self._set_status("Test the exact Voice provider, model and key before saving.", "warning")
            return
        try:
            status = save_voice_settings(API_FILE, signature[0], signature[1], signature[2])
        except Exception as exc:
            self._set_status(f"Could not save Voice settings: {type(exc).__name__}", "error")
            return
        self._key_hint.setText(self._secret_preview(signature[2]))
        tone = "warning" if status.storage == "legacy" else "success"
        self._set_status("Voice settings saved. EDITH will use this Live model on reconnect.", tone)
        self.saved.emit()


class _RealtimeSearchTab(_ApiTabBase):
    """Test and securely store the selected live search API."""

    saved = pyqtSignal()
    _test_result = pyqtSignal(object)
    _PROVIDERS = (
        ("Tavily Search", "tavily"),
        ("Brave Search API", "brave"),
        ("SerpAPI", "serpapi"),
        ("Exa", "exa"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tested_signature = None
        self._key_revealed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(12)
        title_row = QHBoxLayout()
        icon = QLabel()
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(svg_icon("search", C.PRI).pixmap(QSize(20, 20)))
        icon.setStyleSheet(f"background: {C.PANEL2}; border-radius: 12px;")
        title_row.addWidget(icon)
        text_col = QVBoxLayout()
        title = QLabel("Real-time search engine")
        title.setFont(QFont(FONT_MAIN, 12, QFont.Weight.Bold))
        text_col.addWidget(title)
        hint = QLabel("Live web results for current information. Separate from local file search.")
        hint.setFont(QFont(FONT_MAIN, 8))
        hint.setStyleSheet(f"color: {C.TEXT_DIM};")
        text_col.addWidget(hint)
        title_row.addLayout(text_col, 1)
        layout.addLayout(title_row)

        layout.addWidget(self._label("Search provider"))
        self._provider = QComboBox()
        for label, provider in self._PROVIDERS:
            self._provider.addItem(label, provider)
        self._provider.setAccessibleName("Real-time search provider")
        self._provider.setFixedHeight(42)
        self._provider.setStyleSheet(self._field_style())
        layout.addWidget(self._provider)

        layout.addWidget(self._label("API key"))
        key_row = QHBoxLayout()
        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText("Paste real-time search API key")
        self._key.setFixedHeight(42)
        self._key.setStyleSheet(self._field_style())
        key_row.addWidget(self._key, 1)
        self._reveal = self._button("")
        self._reveal.setIcon(svg_icon("eye", C.TEXT_DIM))
        self._reveal.setIconSize(QSize(18, 18))
        self._reveal.setFixedSize(44, 42)
        self._reveal.setAccessibleName("Preview real-time search API key")
        self._reveal.clicked.connect(self._toggle_reveal)
        key_row.addWidget(self._reveal)
        layout.addLayout(key_row)
        self._key_hint = QLabel("No saved key")
        self._key_hint.setFont(QFont(FONT_MAIN, 8))
        self._key_hint.setStyleSheet(f"color: {C.TEXT_DIM};")
        layout.addWidget(self._key_hint)

        note = QLabel("Test sends a small live query to the selected provider. Save is available only after a successful response.")
        note.setWordWrap(True)
        note.setFont(QFont(FONT_MAIN, 8))
        note.setStyleSheet(f"color: {C.TEXT_DIM};")
        layout.addWidget(note)
        self._status = QLabel("Choose a provider and test its API key.")
        self._status.setWordWrap(True)
        self._status.setMinimumHeight(36)
        self._status.setFont(QFont(FONT_MAIN, 8))
        self._status.setStyleSheet(f"color: {C.TEXT_DIM};")
        layout.addWidget(self._status)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self._test_btn = self._button("TEST SEARCH")
        self._save_btn = self._button("SAVE / UPDATE", primary=True)
        self._save_btn.setEnabled(False)
        self._test_btn.clicked.connect(self._test_search)
        self._save_btn.clicked.connect(self._save_search)
        actions.addWidget(self._test_btn)
        actions.addWidget(self._save_btn)
        layout.addLayout(actions)
        layout.addStretch(1)

        self._test_result.connect(self._finish_test)
        self._provider.currentIndexChanged.connect(self._provider_changed)
        self._key.textChanged.connect(self._key_changed)
        self._load_current()

    def _signature(self):
        return (str(self._provider.currentData() or "tavily"), self._key.text().strip())

    def _invalidate(self):
        self._tested_signature = None
        self._save_btn.setEnabled(False)

    def _key_changed(self, *_args):
        self._key_hint.setText("Unsaved key changes · test before saving")
        self._invalidate()

    def _load_current(self):
        from core.provider_registry import load_realtime_search_settings, realtime_search_api_key
        settings = load_realtime_search_settings(API_FILE)
        self._provider.blockSignals(True)
        self._provider.setCurrentIndex(max(0, self._provider.findData(settings["provider"])))
        self._provider.blockSignals(False)
        key = realtime_search_api_key(settings["provider"], API_FILE) or ""
        self._key.setText(key)
        self._key_hint.setText(self._secret_preview(key))

    def _provider_changed(self, *_args):
        from core.provider_registry import realtime_search_api_key
        provider = str(self._provider.currentData() or "tavily")
        key = realtime_search_api_key(provider, API_FILE) or ""
        self._key.blockSignals(True)
        self._key.setText(key)
        self._key.blockSignals(False)
        self._key_hint.setText(self._secret_preview(key))
        self._invalidate()
        if self._key_revealed:
            self._key.setEchoMode(QLineEdit.EchoMode.Password)
            self._key_revealed = False
            self._reveal.setIcon(svg_icon("eye", C.TEXT_DIM))

    def _toggle_reveal(self):
        self._key_revealed = not self._key_revealed
        self._key.setEchoMode(QLineEdit.EchoMode.Normal if self._key_revealed else QLineEdit.EchoMode.Password)
        self._reveal.setIcon(svg_icon("eye-off" if self._key_revealed else "eye", C.TEXT_DIM))

    def _test_search(self):
        from core.provider_registry import probe_realtime_search
        signature = self._signature()
        if not signature[1]:
            self._set_status("Paste the selected search provider API key first.", "warning")
            return
        self._test_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._set_status("Testing a real-time query against the selected search engine…", "working")
        def worker():
            result = probe_realtime_search(*signature)
            self._test_result.emit({"signature": signature, "result": result})
        threading.Thread(target=worker, daemon=True).start()

    def _finish_test(self, payload):
        self._test_btn.setEnabled(True)
        signature = payload.get("signature")
        result = payload.get("result") or {}
        if signature != self._signature():
            self._set_status("Provider or key changed during the test. Test again.", "warning")
            return
        if result.get("ok"):
            self._tested_signature = signature
            self._save_btn.setEnabled(True)
            self._set_status(f"TEST PASSED · {result.get('result_count', 0)} live result · {result.get('latency_ms', 0)} ms.", "success")
        else:
            self._tested_signature = None
            self._save_btn.setEnabled(False)
            self._set_status(f"TEST FAILED · {result.get('error') or 'No search results returned'}", "error")

    def _save_search(self):
        from core.provider_registry import save_realtime_search_settings
        signature = self._signature()
        if signature != self._tested_signature:
            self._set_status("Test the exact search provider and key before saving.", "warning")
            return
        try:
            status = save_realtime_search_settings(API_FILE, *signature)
        except Exception as exc:
            self._set_status(f"Could not save search settings: {type(exc).__name__}", "error")
            return
        self._key_hint.setText(self._secret_preview(signature[1]))
        tone = "warning" if status.storage == "legacy" else "success"
        self._set_status("Real-time search provider and key saved. EDITH will use it for live search.", tone)
        self.saved.emit()


class ApiProviderWorkspace(QWidget):
    """Three-tab provider workspace: Voice transport, one Powerful Brain, live search."""

    settings_saved = pyqtSignal()
    voice_saved = pyqtSignal()
    _OW, _OH = 900, 720

    def __init__(self, parent=None):
        super().__init__(parent)
        _glass_shadow(self)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ApiProviderWorkspace {{
                background: {C.SHEET};
                border: 0;
                border-radius: 22px;
            }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        mark = QLabel()
        mark.setFixedSize(40, 40)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(svg_icon("key", C.PRI).pixmap(QSize(22, 22)))
        mark.setStyleSheet(f"background: {C.PANEL2}; border-radius: 13px;")
        header.addWidget(mark)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel("API PROVIDERS")
        title.setFont(QFont(FONT_MAIN, 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        text_col.addWidget(title)
        subtitle = QLabel("Manage credentials, select models and verify every connection")
        subtitle.setFont(QFont(FONT_MAIN, 8))
        subtitle.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        text_col.addWidget(subtitle)
        header.addLayout(text_col, 1)

        close_btn = QPushButton()
        close_btn.setAccessibleName("Close API Providers")
        close_btn.setToolTip("Close API Providers")
        close_btn.setIcon(svg_icon("x", C.TEXT_DIM))
        close_btn.setIconSize(QSize(18, 18))
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; border: 0; border-radius: 13px; }}
            QPushButton:hover {{ background: {C.DANGER_BG}; }}
        """)
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)
        root.addLayout(header)

        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)
        self._tabs.setMovable(False)
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 0; background: transparent; top: 0; }}
            QTabBar {{ background: transparent; }}
            QTabBar::tab {{
                background: transparent; color: {C.TEXT_DIM};
                border: 0; border-bottom: 2px solid transparent;
                padding: 13px 17px; margin-right: 8px;
                font-family: "{FONT_MAIN}"; font-size: 9pt; font-weight: 700;
            }}
            QTabBar::tab:selected {{ color: {C.PRI}; border-bottom: 2px solid {C.PRI}; }}
            QTabBar::tab:hover:!selected {{ color: {C.TEXT}; }}
        """)
        self._voice = _VoiceProviderTab()
        # Powerful Brain is the single canonical text/reasoning provider.
        # The Main Brain profile remains only as a provider-config migration fallback.
        self._powerful_brain = _ProviderProfileTab("powerful")
        self._search = _RealtimeSearchTab()
        self._tabs.addTab(self._voice, svg_icon("mic", C.PRI), "VOICE")
        self._tabs.addTab(self._powerful_brain, svg_icon("cpu", C.PRI), "POWERFUL BRAIN")
        self._tabs.addTab(self._search, svg_icon("search", C.PRI), "REAL-TIME SEARCH")
        root.addWidget(self._tabs, 1)

        self._voice.saved.connect(self._on_voice_saved)
        self._powerful_brain.saved.connect(self.settings_saved.emit)
        self._search.saved.connect(self.settings_saved.emit)

    def _on_voice_saved(self):
        self.settings_saved.emit()
        self.voice_saved.emit()


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        _glass_shadow(self)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: {C.SHEET};
                border: 1px solid {C.BORDER_B};
                border-radius: 18px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont(FONT_MAIN, font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 14, True))
        layout.addWidget(_lbl("Configure your assistant before first boot.", 9, color=C.TEXT_MED))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("VOICE API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza...")
        self._key_input.setFont(QFont(FONT_MONO, 10))
        self._key_input.setFixedHeight(36)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.DARK}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 6px 10px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(8)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","Windows"),("mac","macOS"),("linux","Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
            btn.setFixedHeight(34)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  INITIALISE SYSTEMS")
        init_btn.setFont(QFont(FONT_MAIN, 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(38)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 4px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,"#001A20"),"mac":(C.ACC2,"#1A1400"),"linux":(C.GREEN,"#001A0D")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 4px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.DARK}; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 4px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)


class CustomizeOverlay(QWidget):
    """Minimal preferences sheet: identity and system appearance only."""

    saved = pyqtSignal(str, str)
    theme_saved = pyqtSignal(str)
    _OW, _OH = 420, 300

    def __init__(self, assistant_name="EDITH", user_name="",
                 theme_preference="system", parent=None):
        super().__init__(parent)
        _glass_shadow(self)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CustomizeOverlay {{
                background: {C.SHEET};
                border: 0;
                border-radius: 20px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 22)
        lay.setSpacing(12)

        header = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(svg_icon("settings", C.PRI).pixmap(QSize(22, 22)))
        header.addWidget(icon_lbl)
        title = QLabel("PREFERENCES")
        title.setFont(QFont(FONT_MAIN, 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        header.addWidget(title, 1)
        self._close_btn = QPushButton()
        self._close_btn.setAccessibleName("Close preferences")
        self._close_btn.setToolTip("Close")
        self._close_btn.setIcon(svg_icon("x", C.TEXT_DIM))
        self._close_btn.setIconSize(QSize(18, 18))
        self._close_btn.setFixedSize(38, 38)
        self._close_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; border: 0; border-radius: 13px; }}
            QPushButton:hover {{ background: {C.DANGER_BG}; }}
        """)
        self._close_btn.clicked.connect(self._cancel)
        header.addWidget(self._close_btn)
        lay.addLayout(header)

        def _label(text: str):
            w = QLabel(text.upper())
            w.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
            w.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            return w

        lay.addWidget(_label("Your name (optional)"))
        self._user_input = QLineEdit(user_name)
        self._user_input.setPlaceholderText("Your name")
        self._user_input.setFixedHeight(42)
        self._user_input.setStyleSheet(f"""
            QLineEdit {{ background: {C.INPUT}; color: {C.TEXT}; border: 0;
                         border-radius: 11px; padding: 8px 12px; }}
            QLineEdit:focus {{ background: {C.PANEL2}; }}
        """)
        lay.addWidget(self._user_input)

        lay.addWidget(_label("Appearance"))
        self._initial_theme = str(theme_preference or "system").lower()
        if self._initial_theme not in {"system", "dark", "light"}:
            self._initial_theme = "system"
        self._sel_theme = self._initial_theme
        self._theme_picker = QComboBox()
        self._theme_picker.addItem("System", "system")
        self._theme_picker.addItem("Dark", "dark")
        self._theme_picker.addItem("Light", "light")
        self._theme_picker.setCurrentIndex(("system", "dark", "light").index(self._sel_theme))
        self._theme_picker.setAccessibleName("EDITH appearance theme")
        self._theme_picker.setFixedHeight(42)
        self._theme_picker.setStyleSheet(f"""
            QComboBox {{ background: {C.INPUT}; color: {C.TEXT}; border: 0;
                         border-radius: 11px; padding: 8px 12px; }}
            QComboBox:focus {{ background: {C.PANEL2}; }}
            QComboBox QAbstractItemView {{ background: {C.PANEL}; color: {C.TEXT};
                                           border: 0; selection-background-color: {C.PRI_GHO}; }}
        """)
        self._theme_picker.currentIndexChanged.connect(self._on_theme_changed)
        lay.addWidget(self._theme_picker)

        note = QLabel("Accent colours are managed by EDITH's system theme.")
        note.setFont(QFont(FONT_MAIN, 8))
        note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(note)
        lay.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("CANCEL")
        cancel.setFixedHeight(40)
        cancel.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_MED}; border: 0;
                           border-radius: 11px; padding: 0 16px; }}
            QPushButton:hover {{ background: {C.HOVER}; }}
        """)
        cancel.clicked.connect(self._cancel)
        save = QPushButton("SAVE CHANGES")
        save.setFixedHeight(40)
        save.setStyleSheet(f"""
            QPushButton {{ background: {C.PRI}; color: {C.DARK}; border: 0;
                           border-radius: 11px; padding: 0 18px; font-weight: 700; }}
            QPushButton:hover {{ background: {C.PRI_DIM}; }}
        """)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        lay.addLayout(buttons)

        self.on_theme_preview = None

    def _cancel(self):
        if getattr(self, "on_theme_preview", None):
            self.on_theme_preview(None)
        self.hide()

    def _save(self):
        self.saved.emit("EDITH", self._user_input.text().strip())
        self.theme_saved.emit(self._sel_theme)
        self.hide()

    def _on_theme_changed(self, index: int):
        self._sel_theme = str(self._theme_picker.itemData(index) or "system")
        if getattr(self, "on_theme_preview", None):
            self.on_theme_preview(self._sel_theme)


class MCPConnectionDialog(QDialog):
    """Local setup surface for a configured MCP server.

    It deliberately stores only an owner-pasted bearer token through the
    keychain callback. OAuth client creation/consent remains at the provider;
    this dialog never asks for, prints, or logs a password.
    """

    def __init__(self, record: dict, parent=None):
        super().__init__(parent)
        self.record = record
        self.setWindowTitle(f"Connect {record.get('name', 'MCP')}")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        self.setMinimumWidth(560)
        self.resize(640, 430)
        self.setStyleSheet(f"""
            QDialog {{ background: {C.SHEET}; color: {C.TEXT}; }}
            QLabel {{ color: {C.TEXT}; }}
            QLineEdit {{ background: {C.INPUT}; color: {C.TEXT}; border: 1px solid {C.BORDER}; border-radius: 11px; padding: 10px 12px; }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
            QLabel {{ background: transparent; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(12)
        title_row = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(svg_icon("wifi", C.PRI).pixmap(QSize(23, 23)))
        mark.setFixedSize(34, 34)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.addWidget(mark)
        title = QLabel(str(record.get("name") or "MCP Server"))
        title.setFont(QFont(FONT_MAIN, 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        title_row.addWidget(title, 1)
        self._close_btn = QPushButton()
        self._close_btn.setAccessibleName("Close MCP connection dialog")
        self._close_btn.setToolTip("Cancel and close")
        self._close_btn.setIcon(svg_icon("x", C.TEXT_DIM))
        self._close_btn.setIconSize(QSize(18, 18))
        self._close_btn.setFixedSize(36, 36)
        self._close_btn.setStyleSheet(f"QPushButton {{ background:{C.PANEL2}; border:1px solid {C.BORDER}; border-radius:11px; }} QPushButton:hover {{ background:{C.DANGER_BG}; border-color:{C.RED}; }}")
        self._close_btn.clicked.connect(self.reject)
        title_row.addWidget(self._close_btn)
        layout.addLayout(title_row)
        note = QLabel(
            "Open the provider setup page, finish its OAuth/API consent, then paste only the issued access token. "
            "The token is stored in your OS keychain when available."
        )
        note.setFont(QFont(FONT_MAIN, 8))
        note.setStyleSheet(f"color: {C.TEXT_MED};")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(QLabel("STREAMABLE-HTTP MCP ENDPOINT"))
        self.endpoint = QLineEdit()
        self.endpoint.setFixedHeight(42)
        self.endpoint.setPlaceholderText("https://your-trusted-mcp-server.example/mcp")
        try:
            info = record.get("connection", lambda: {})() or {}
        except Exception:
            info = {}
        self.endpoint.setText(str(info.get("endpoint") or ""))
        layout.addWidget(self.endpoint)
        layout.addWidget(QLabel("ACCESS TOKEN  (optional for unauthenticated/local servers)"))
        self.token = QLineEdit()
        self.token.setFixedHeight(42)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("Paste a provider-issued bearer token")
        layout.addWidget(self.token)
        self.status = QLabel(self._status_text(info))
        self.status.setWordWrap(True)
        self.status.setFont(QFont(FONT_MAIN, 8))
        self.status.setStyleSheet(f"color: {C.TEXT_DIM};")
        layout.addWidget(self.status)
        buttons = QHBoxLayout(); buttons.setSpacing(7)
        setup = QPushButton("OPEN SETUP")
        setup.clicked.connect(self._open_setup)
        save = QPushButton("SAVE")
        save.clicked.connect(self._save)
        test = QPushButton("SAVE & TEST")
        test.clicked.connect(self._test)
        cancel = QPushButton("CANCEL")
        cancel.clicked.connect(self.reject)
        for button in (setup, save, test, cancel):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(38)
            button.setStyleSheet(f"""
                QPushButton {{ background: {C.GLASS_CARD}; color: {C.PRI}; border: 1px solid {C.BORDER}; border-radius: 10px; padding: 0 12px; }}
                QPushButton:hover {{ border-color: {C.PRI}; background: {C.HOVER}; }}
            """)
            buttons.addWidget(button)
        layout.addLayout(buttons)

    @staticmethod
    def _status_text(info: dict) -> str:
        configured = str(info.get("configured") or "false") == "true"
        token = str(info.get("token_storage") or "missing")
        return f"Endpoint: {'configured' if configured else 'not configured'} · Token: {token}."

    def _open_setup(self):
        callback = self.record.get("begin_login")
        if not callable(callback):
            self.status.setText("No provider setup URL is configured for this connector.")
            return
        try:
            result = callback() or {}
            self.status.setText("Provider setup opened. Complete it, then return here to save/test the connection.")
        except Exception as exc:
            self.status.setText(f"Could not open provider setup: {type(exc).__name__}: {exc}")

    def _save_values(self) -> bool:
        endpoint = self.endpoint.text().strip()
        token = self.token.text().strip()
        try:
            configure = self.record.get("configure_remote")
            if endpoint and callable(configure):
                configure(endpoint)
            elif endpoint and not callable(configure):
                raise RuntimeError("This connector cannot accept an HTTP endpoint.")
            save_token = self.record.get("save_access_token")
            if token and callable(save_token):
                save_token(token)
            toggle = self.record.get("toggle")
            if callable(toggle):
                toggle(True)
            self.record["enabled"] = True
            self.token.clear()
            return True
        except Exception as exc:
            self.status.setText(f"Connection was not saved: {type(exc).__name__}: {exc}")
            return False

    def _save(self):
        if self._save_values():
            self.status.setText("Saved. The connector is ON; use Save & Test to verify its provider response.")

    def _test(self):
        if not self._save_values():
            return
        callback = self.record.get("test_connection")
        if not callable(callback):
            self.status.setText("Saved, but this connector has no test action.")
            return
        try:
            tools = callback() or []
            self.status.setText(f"Connected. Provider reported {len(tools)} tool(s).")
        except Exception as exc:
            self.status.setText(f"Test failed: {type(exc).__name__}: {exc}")


class PluginManagerOverlay(QWidget):
    """Scrollable catalog for local agents, Home Assistant and configured MCP servers."""

    home_assistant_pair_finished = pyqtSignal(object)
    _OW, _OH = 700, 640

    def __init__(self, plugins: list[dict], parent=None):
        super().__init__(parent)
        self.home_assistant_pair_finished.connect(self._on_home_assistant_pair_finished)
        _glass_shadow(self)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginManagerOverlay {{
                background: {C.SHEET};
                border: 1px solid {C.BORDER_B};
                border-radius: 20px;
            }}
        """)
        self.setMinimumSize(560, 420)
        self.setMaximumSize(780, 740)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        mark = QLabel()
        mark.setFixedSize(42, 42)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(svg_icon("puzzle", C.PRI).pixmap(QSize(22, 22)))
        mark.setStyleSheet(
            f"background: {C.PRI_GHO}; border: 1px solid {C.BORDER}; border-radius: 13px;"
        )
        head.addWidget(mark)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        hdr = QLabel("PLUGINS & MCP SERVERS")
        hdr.setFont(QFont(FONT_MAIN, 15, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        title_col.addWidget(hdr)
        subtitle = QLabel("Manage local tools and trusted external connectors")
        subtitle.setFont(QFont(FONT_MAIN, 9))
        subtitle.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        title_col.addWidget(subtitle)
        head.addLayout(title_col, 1)
        count = QLabel(f"{len(plugins)}  ITEMS")
        count.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        count.setStyleSheet(
            f"color: {C.PRI}; background: {C.PRI_GHO}; "
            f"border: 1px solid {C.BORDER}; border-radius: 9px; padding: 7px 10px;"
        )
        head.addWidget(count, 0, Qt.AlignmentFlag.AlignTop)
        close_btn = QPushButton()
        close_btn.setAccessibleName("Close Plugins manager")
        close_btn.setToolTip("Close")
        close_btn.setIcon(svg_icon("x", C.TEXT_DIM))
        close_btn.setIconSize(QSize(18, 18))
        close_btn.setFixedSize(36, 36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 11px; }}
            QPushButton:hover {{ background: {C.DANGER_BG}; border-color: {C.RED}; }}
        """)
        close_btn.clicked.connect(self.hide)
        head.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"color: {C.BORDER};")
        root.addWidget(divider)

        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)
        self._tabs.setMovable(False)
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {C.BORDER}; border-radius: 14px; background: transparent; top: -1px; }}
            QTabBar::tab {{ background: {C.PANEL2}; color: {C.TEXT_DIM}; border: 1px solid {C.BORDER};
                           padding: 11px 18px; margin-right: 6px; border-top-left-radius: 10px;
                           border-top-right-radius: 10px; font-weight: 700; }}
            QTabBar::tab:selected {{ background: {C.PRI_GHO}; color: {C.PRI}; border-color: {C.PRI_DIM}; }}
            QTabBar::tab:hover:!selected {{ color: {C.TEXT}; }}
        """)
        mcp_items = [item for item in plugins if str(item.get("kind") or "").lower() == "mcp"]
        agent_items = [item for item in plugins if str(item.get("kind") or "").lower() != "mcp"]
        self._mcp_tab = self._build_catalog_tab(
            mcp_items, "No MCP servers configured",
            "Trusted remote MCP servers will appear here after they are discovered."
        )
        self._agents_tab = self._build_catalog_tab(
            agent_items, "No agents discovered",
            "Local agents and Python tools will appear here after they are discovered."
        )
        self._tabs.addTab(self._mcp_tab, svg_icon("wifi", C.PRI), "MCP SERVERS")
        self._tabs.addTab(self._agents_tab, svg_icon("puzzle", C.PRI), "AGENTS")
        self._tabs.setAccessibleName("Plugin categories")
        root.addWidget(self._tabs, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer_note = QLabel("Only enabled, tested MCP connectors are exposed to EDITH.")
        footer_note.setWordWrap(True)
        footer_note.setFont(QFont(FONT_MAIN, 8))
        footer_note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        footer.addWidget(footer_note, 1)
        root.addLayout(footer)
        self.adjustSize()

    def _build_catalog_tab(self, records: list[dict], empty_title: str, empty_note: str) -> QScrollArea:
        catalog = QScrollArea(self)
        catalog.setWidgetResizable(True)
        catalog.setFrameShape(QFrame.Shape.NoFrame)
        catalog.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        catalog.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 0; }}
            QScrollBar::handle:vertical {{ background: {C.BORDER_B}; border-radius: 4px; min-height: 28px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        content = QVBoxLayout(body)
        content.setContentsMargins(10, 10, 10, 10)
        content.setSpacing(9)
        if records:
            ordered = sorted(records, key=lambda item: str(item.get("name") or "").casefold())
            for item in ordered:
                content.addWidget(self._build_row(item))
        else:
            empty = QFrame()
            empty.setStyleSheet(
                f"background: {C.GLASS_CARD}; border: 1px dashed {C.BORDER_B}; border-radius: 14px;"
            )
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(18, 22, 18, 22)
            icon = QLabel()
            icon.setPixmap(svg_icon("wifi" if "MCP" in empty_title else "puzzle", C.PRI).pixmap(QSize(24, 24)))
            empty_layout.addWidget(icon)
            title = QLabel(empty_title)
            title.setFont(QFont(FONT_MAIN, 11, QFont.Weight.Bold))
            title.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
            empty_layout.addWidget(title)
            note = QLabel(empty_note)
            note.setWordWrap(True)
            note.setFont(QFont(FONT_MAIN, 9))
            note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            empty_layout.addWidget(note)
            content.addWidget(empty)
        content.addStretch(1)
        catalog.setWidget(body)
        return catalog

    def _build_row(self, record: dict) -> QWidget:
        card = QFrame()
        card.setObjectName("PluginCard")
        card.setStyleSheet(f"""
            QFrame#PluginCard {{
                background: {C.GLASS_CARD};
                border: 1px solid {C.BORDER};
                border-radius: 13px;
            }}
        """)
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(11)

        kind = str(record.get("kind") or "python").lower()
        badge = QLabel()
        badge.setFixedSize(40, 40)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(svg_icon("wifi" if kind == "mcp" else "puzzle", C.PRI).pixmap(QSize(21, 21)))
        badge.setStyleSheet(
            f"background: {C.PRI_GHO}; border: 1px solid {C.BORDER}; border-radius: 11px;"
        )
        row.addWidget(badge)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        valid = bool(record.get("valid"))
        name = str(record.get("name") or "Unnamed plugin")
        label_text = name if valid else f"{name}  ·  INVALID"
        label = QLabel(label_text)
        label.setFont(QFont(FONT_MAIN, 10, QFont.Weight.Bold))
        label.setStyleSheet(
            f"color: {C.TEXT if valid else C.RED}; background: transparent;"
        )
        label.setToolTip(str(record.get("error") or record.get("description") or ""))
        text_col.addWidget(label)
        description = str(record.get("description") or record.get("file") or "")
        if len(description) > 96:
            description = description[:93].rstrip() + "…"
        detail = QLabel(description)
        detail.setWordWrap(True)
        detail.setFont(QFont(FONT_MAIN, 8))
        detail.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        detail.setToolTip(str(record.get("description") or record.get("error") or ""))
        text_col.addWidget(detail)
        row.addLayout(text_col, 1)

        state = QLabel("ENABLED" if record.get("enabled") else "DISABLED")
        state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        state.setFont(QFont(FONT_MONO, 7, QFont.Weight.Bold))
        state.setStyleSheet(
            f"color: {C.GREEN if record.get('enabled') else C.TEXT_DIM}; "
            f"background: {C.SUCCESS_BG if record.get('enabled') else C.PANEL}; "
            f"border: 1px solid {C.BORDER}; border-radius: 8px; padding: 5px 7px;"
        )
        row.addWidget(state)

        toggle = QPushButton()
        toggle.setFixedSize(78, 34)
        toggle.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        if not valid:
            toggle.setText("INVALID")
            toggle.setEnabled(False)
        else:
            self._style_toggle(toggle, bool(record.get("enabled")))
            toggle.clicked.connect(
                lambda _checked=False, item=record, button=toggle, status=state:
                    self._toggle(item, button, status)
            )
        row.addWidget(toggle)

        if kind == "mcp" and valid:
            connect = QPushButton("SET UP")
            connect.setFixedSize(76, 34)
            connect.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
            connect.setCursor(Qt.CursorShape.PointingHandCursor)
            connect.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PRI_GHO}; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 9px; padding: 0 10px;
                }}
                QPushButton:hover {{ background: {C.HOVER}; border-color: {C.PRI}; }}
            """)
            connect.setToolTip("Configure endpoint, access token and test the MCP connection")
            connect.clicked.connect(lambda _checked=False, item=record: self._connect(item))
            row.addWidget(connect)

        if kind != "mcp" and record.get("agent_id") == "smart_network" and valid:
            paired = bool(record.get("home_assistant_paired"))
            pair = QPushButton("UPDATE HA" if paired else "PAIR HA")
            pair.setFixedSize(86, 34)
            pair.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
            pair.setCursor(Qt.CursorShape.PointingHandCursor)
            pair.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PRI_GHO}; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 9px; padding: 0 8px;
                }}
                QPushButton:hover {{ background: {C.HOVER}; border-color: {C.PRI}; }}
                QPushButton:disabled {{ color: {C.TEXT_DIM}; background: {C.PANEL}; }}
            """)
            pair.setToolTip(
                "Verify your Home Assistant URL and long-lived token, then save the token securely"
            )
            pair.clicked.connect(
                lambda _checked=False, item=record, button=pair, description=detail:
                    self._pair_home_assistant(item, button, description)
            )
            row.addWidget(pair)
        return card

    def _pair_home_assistant(self, record: dict, button: QPushButton, detail: QLabel) -> None:
        """Verify the user's Home Assistant token before persisting it off the UI thread."""
        default_url = str(record.get("home_assistant_url") or "http://homeassistant.local:8123")
        url, accepted = QInputDialog.getText(
            self, "Pair Home Assistant",
            "Home Assistant URL (for example http://homeassistant.local:8123):",
            QLineEdit.EchoMode.Normal, default_url,
        )
        if not accepted or not url.strip():
            return
        token, accepted = QInputDialog.getText(
            self, "Pair Home Assistant",
            "Long-lived access token (input is hidden):",
            QLineEdit.EchoMode.Password, "",
        )
        if not accepted or not token.strip():
            return

        button.setEnabled(False)
        button.setText("TESTING")
        detail.setText("Home Assistant: checking API access before saving credentials…")

        def pair_worker() -> None:
            try:
                from agents.smart_network import configure_home_assistant, test_home_assistant_connection
                test_home_assistant_connection(url, token, timeout=5.0)
                saved = configure_home_assistant(url, token)
                storage = str(saved.get("token_storage") or "unknown")
                message = (
                    "Home Assistant paired · token stored in OS keychain."
                    if storage in {"keyring", "migrated"}
                    else "Home Assistant paired, but OS keychain is unavailable; token uses the local config fallback."
                )
                result = {
                    "ok": True, "message": message, "storage": storage,
                    "url": str(saved.get("url") or url).strip(),
                    "button": button, "detail": detail, "record": record,
                }
            except Exception as exc:
                safe_error = str(exc).replace(token, "[hidden]")[:240]
                result = {
                    "ok": False,
                    "message": f"Home Assistant pairing failed: {type(exc).__name__}: {safe_error}",
                    "button": button, "detail": detail, "record": record,
                }
            try:
                self.home_assistant_pair_finished.emit(result)
            except RuntimeError:
                pass

        threading.Thread(
            target=pair_worker, daemon=True, name="edith-home-assistant-pair"
        ).start()

    def _on_home_assistant_pair_finished(self, result: dict) -> None:
        button = result.get("button")
        detail = result.get("detail")
        record = result.get("record")
        ok = bool(result.get("ok"))
        if ok and isinstance(record, dict):
            record["home_assistant_paired"] = True
            record["home_assistant_url"] = result.get("url", "")
        try:
            if button is not None:
                button.setEnabled(True)
                button.setText("UPDATE HA" if ok else "RETRY HA")
                button.setToolTip(str(result.get("message") or ""))
            if detail is not None:
                detail.setText(str(result.get("message") or "Home Assistant pairing result"))
                detail.setToolTip(str(result.get("message") or ""))
                detail.setStyleSheet(
                    f"color: {C.GREEN if ok else C.RED}; background: transparent;"
                )
        except RuntimeError:
            # The user may have closed the Plugins overlay while the test was running.
            pass

    def _connect(self, record: dict):
        dialog = MCPConnectionDialog(record, self)
        dialog.exec()

    def _style_toggle(self, btn: QPushButton, enabled: bool):
        btn.setText("ON" if enabled else "OFF")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if enabled:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.SUCCESS_BG}; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 9px;
                }}
                QPushButton:hover {{ background: {C.SUCCESS_HOVER}; }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PANEL}; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 9px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
            """)

    def _toggle(self, record: dict, btn: QPushButton, state_label: QLabel | None = None):
        from memory.config_manager import get_plugin_enabled, save_plugin_enabled
        toggle = record.get("toggle")
        if callable(toggle):
            new_val = not bool(record.get("enabled"))
            toggle(new_val)
        else:
            name = record.get("name", "")
            new_val = not get_plugin_enabled(name)
            save_plugin_enabled(name, new_val)
        record["enabled"] = new_val
        self._style_toggle(btn, new_val)
        if state_label is not None:
            state_label.setText("ENABLED" if new_val else "DISABLED")
            state_label.setStyleSheet(
                f"color: {C.GREEN if new_val else C.TEXT_DIM}; "
                f"background: {C.SUCCESS_BG if new_val else C.PANEL}; "
                f"border: 1px solid {C.BORDER}; border-radius: 8px; padding: 5px 7px;"
            )


class ClipboardPanel(QWidget):
    """Floating panel shown when text is copied — offers quick assistant actions."""

    action_requested = pyqtSignal(str)
    _W, _H = 320, 110

    def __init__(self, parent=None):
        super().__init__(parent)
        _glass_shadow(self)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ClipboardPanel {{
                background: {C.SHEET};
                border: 1px solid {C.BORDER_B};
                border-radius: 16px;
            }}
        """)
        self.setFixedWidth(self._W)
        self._clip_text = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout(); hdr.setSpacing(4)
        icon_lbl = QLabel("◈  CLIPBOARD DETECTED")
        icon_lbl.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        icon_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
        hdr.addWidget(icon_lbl); hdr.addStretch()
        x_btn = QPushButton("✕")
        x_btn.setFixedSize(18, 18)
        x_btn.setFont(QFont(FONT_MAIN, 8))
        x_btn.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        x_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        x_btn.clicked.connect(self.hide)
        hdr.addWidget(x_btn)
        lay.addLayout(hdr)

        self._preview = QLabel()
        self._preview.setFont(QFont(FONT_MAIN, 9))
        self._preview.setStyleSheet(f"""
            color: {C.TEXT}; background: {C.PANEL2};
            border: 1px solid {C.BORDER}; border-radius: 4px; padding: 6px 8px;
        """)
        self._preview.setWordWrap(False)
        self._preview.setFixedHeight(28)
        lay.addWidget(self._preview)

        btn_row = QHBoxLayout(); btn_row.setSpacing(5)
        _bs = (f"QPushButton {{ background: {C.GLASS_CARD}; color: {C.TEXT_MED}; "
               f"border: 1px solid {C.BORDER}; border-radius: 8px; }}"
               f"QPushButton:hover {{ color: {C.PRI}; background: {C.HOVER}; }}")
        for label, cmd_fmt in [
            ("Translate", "Translate this text to English: {text}"),
            ("Summarise", "Summarise this: {text}"),
            ("Explain",   "Explain this: {text}"),
            ("Fix",       "Fix grammar and spelling: {text}"),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(24)
            b.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_bs)
            b.clicked.connect(lambda _, c=cmd_fmt: self._trigger(c))
            btn_row.addWidget(b)
        lay.addLayout(btn_row)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide)
        self.hide()

    def _trigger(self, cmd_fmt: str):
        if self._clip_text:
            self.action_requested.emit(cmd_fmt.format(text=self._clip_text[:800]))
        self.hide()

    def show_clipboard(self, text: str):
        self._clip_text = text
        preview = text[:50].replace('\n', ' ')
        if len(text) > 50:
            preview += "…"
        self._preview.setText(f'"{preview}"')
        self.show(); self.raise_()
        self._dismiss_timer.start(8000)


class RemoteKeyOverlay(QWidget):
    """Floating overlay — QR code for instant phone pairing + manual key fallback."""

    closed = pyqtSignal()

    _OW, _OH = 400, 460

    def __init__(self, url: str, key: str, auto_login_url: str = "",
                 manual_url: str = "", expiry_secs: int = 600, parent=None):
        super().__init__(parent)
        _glass_shadow(self)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            RemoteKeyOverlay {{
                background: {C.SHEET};
                border: 1px solid {C.BORDER_B};
                border-radius: 12px;
            }}
        """)
        self._expiry          = time.time() + expiry_secs
        self._on_new_key      = None
        self._auto_login_url  = auto_login_url
        self._manual_url      = manual_url or url

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 20, 28, 20)
        lay.setSpacing(8)

        def _lbl(txt, fs=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont(FONT_MAIN, fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            w.setWordWrap(True)
            return w

        title_row = QHBoxLayout()
        remote_icon = QLabel()
        remote_icon.setPixmap(svg_icon("wifi", C.PRI).pixmap(QSize(22, 22)))
        title_row.addWidget(remote_icon)
        title_row.addWidget(_lbl("REMOTE ACCESS", 13, True), 1)
        self._close_btn = QPushButton()
        self._close_btn.setAccessibleName("Close remote access")
        self._close_btn.setToolTip("Close")
        self._close_btn.setIcon(svg_icon("x", C.TEXT_DIM))
        self._close_btn.setIconSize(QSize(18, 18))
        self._close_btn.setFixedSize(36, 36)
        self._close_btn.setStyleSheet(f"QPushButton {{ background:{C.PANEL2}; border:1px solid {C.BORDER}; border-radius:11px; }} QPushButton:hover {{ background:{C.DANGER_BG}; border-color:{C.RED}; }}")
        self._close_btn.clicked.connect(self._do_close)
        title_row.addWidget(self._close_btn)
        lay.addLayout(title_row)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        # ── QR code ───────────────────────────────────────────────────────────
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedSize(170, 170)
        self._qr_label.setStyleSheet(
            "background: white; border-radius: 8px; padding: 4px;"
        )
        qr_row = QHBoxLayout()
        qr_row.addStretch()
        qr_row.addWidget(self._qr_label)
        qr_row.addStretch()
        lay.addLayout(qr_row)

        self._update_qr(auto_login_url)

        lay.addWidget(_lbl("Scan with phone camera to connect instantly", 8, color=C.TEXT_DIM))

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_lbl("Or enter manually:", 7, color=C.TEXT_DIM,
                           align=Qt.AlignmentFlag.AlignLeft))

        self._url_lbl = QLabel(self._manual_url)
        self._url_lbl.setFont(QFont(FONT_MONO, 9))
        self._url_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        self._url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._url_lbl)

        self._key_lbl = QLabel(key)
        self._key_lbl.setFont(QFont(FONT_MONO, 26, QFont.Weight.Bold))
        self._key_lbl.setStyleSheet(f"""
            color: {C.ACC};
            background: {C.PANEL2};
            border: 1px solid {C.BORDER_B};
            border-radius: 8px;
            padding: 8px 4px;
            letter-spacing: 8px;
        """)
        self._key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._key_lbl)

        self._timer_lbl = QLabel()
        self._timer_lbl.setFont(QFont(FONT_MAIN, 8))
        self._timer_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._timer_lbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        new_btn = QPushButton("NEW KEY")
        new_btn.setFixedHeight(34)
        new_btn.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        new_btn.clicked.connect(self._refresh_key)
        btn_row.addWidget(new_btn)

        close_btn = QPushButton("DISMISS")
        close_btn.setFixedHeight(34)
        close_btn.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self._do_close)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self._ctimer = QTimer(self)
        self._ctimer.timeout.connect(self._tick)
        self._ctimer.start(1000)
        self._tick()

    def set_new_key_callback(self, fn) -> None:
        self._on_new_key = fn

    def _update_qr(self, url: str) -> None:
        if not url:
            self._qr_label.setText("—")
            return
        try:
            import qrcode as _qrmod
            from io import BytesIO
            qr = _qrmod.QRCode(
                box_size=5, border=2,
                error_correction=_qrmod.constants.ERROR_CORRECT_M,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._qr_label.setPixmap(
                px.scaled(160, 160,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        except ImportError:
            self._qr_label.setText("pip install\nqrcode[pil]")
            self._qr_label.setFont(QFont(FONT_MAIN, 8))
            self._qr_label.setStyleSheet(
                "color: #888; background: white; border-radius: 8px; padding: 4px;"
            )
        except Exception:
            self._qr_label.setText(url[:28])
            self._qr_label.setFont(QFont(FONT_MAIN, 8))
            self._qr_label.setStyleSheet(
                f"color: {C.PRI}; background: white; border-radius: 8px; padding: 4px;"
            )

    def _tick(self):
        remaining = max(0, int(self._expiry - time.time()))
        m, s = divmod(remaining, 60)
        self._timer_lbl.setText(f"Key expires in  {m:02d}:{s:02d}")
        if remaining == 0:
            self._do_close()

    def mark_connected(self) -> None:
        """Call from any thread when a phone successfully connects."""
        self._ctimer.stop()
        self._key_lbl.setText("CONNECTED")
        self._key_lbl.setStyleSheet(f"""
            color: {C.GREEN};
            background: rgba(0,255,136,0.08);
            border: 2px solid rgba(0,255,136,0.4);
            border-radius: 8px;
            padding: 8px 4px;
            letter-spacing: 4px;
        """)
        self._qr_label.setText("✓")
        self._qr_label.setFont(QFont(FONT_MAIN, 50, QFont.Weight.Bold))
        self._qr_label.setStyleSheet(
            f"color: {C.GREEN}; background: {C.PANEL2}; border-radius: 8px;"
        )
        self._timer_lbl.setText("Phone connected — Assistant ready")
        self._timer_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")

    def _refresh_key(self):
        if self._on_new_key:
            result = self._on_new_key()
            if result:
                url    = result[0]
                key    = result[1]
                auto   = result[2] if len(result) >= 3 else ""
                manual = result[3] if len(result) >= 4 else url
                self._manual_url     = manual or url
                self._url_lbl.setText(self._manual_url)
                self._key_lbl.setText(key)
                self._auto_login_url = auto
                self._update_qr(auto or url)
                self._expiry = time.time() + 600
                self._key_lbl.setStyleSheet(f"""
                    color: {C.ACC};
                    background: {C.PANEL2};
                    border: 1px solid {C.BORDER_B};
                    border-radius: 8px;
                    padding: 8px 4px;
                    letter-spacing: 8px;
                """)
                self._timer_lbl.setStyleSheet(
                    f"color: {C.TEXT_MED}; background: transparent;"
                )
                self._ctimer.start(1000)
                self._tick()

    def _do_close(self):
        self._ctimer.stop()
        self.hide()
        self.closed.emit()


class MainWindow(QMainWindow):
    browser_open_signal = pyqtSignal(str)
    browser_action_signal = pyqtSignal(object)
    _url_prompt_sig = pyqtSignal(object)
    voice_mode_signal = pyqtSignal(str)
    open_api_key_settings_signal = pyqtSignal()
    _log_sig        = pyqtSignal(str)
    _state_sig      = pyqtSignal(str)
    _playback_sig = pyqtSignal(bool)
    _output_level_sig = pyqtSignal(float)
    _mic_level_sig  = pyqtSignal(float, str)  # thread-safe captured PCM activity
    _content_sig    = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _reconfig_sig   = pyqtSignal()           # trigger setup overlay from any thread
    _camera_sig     = pyqtSignal(bytes)      # show camera frame preview (small overlay)
    _cam_stream_sig = pyqtSignal(bool)       # True=start live stream, False=stop
    _cam_frame_sig  = pyqtSignal(bytes)      # live camera frame → HUD area
    _clipboard_sig  = pyqtSignal(str)        # clipboard text changed (thread-safe)
    _confirm_action_sig = pyqtSignal(str, str, object)  # title, details, state
    task_status_signal = pyqtSignal(int, int, int)  # running, queued, finished
    task_detail_signal = pyqtSignal(object)  # bounded task metadata; no arguments/results
    text_send_failed_signal = pyqtSignal(str)  # restore only when input is still empty
    theme_changed_signal = pyqtSignal(str)  # SystemThemeMonitor worker -> Qt UI thread

    def __init__(self, face_path: str):
        super().__init__()
        self._requested_state = "INITIALISING"
        self._playback_active = False
        self._running_tasks = 0
        QApplication.instance().edith_window = self
        self._url_prompt_sig.connect(self._show_url_prompt)
        self._confirmation_busy = False
        self._confirmation_queue = []
        self.voice_mode_signal.connect(self.set_voice_mode_display)
        self.browser_open_signal.connect(self._open_embedded_browser)
        self.browser_action_signal.connect(self._execute_embedded_browser_action)
        self._embedded_browser_dialog = None
        self.task_status_signal.connect(self._update_task_status)
        self.task_detail_signal.connect(self._update_task_details)
        self.text_send_failed_signal.connect(self._restore_unsent_command)
        self.open_api_key_settings_signal.connect(self._open_api_key_settings)
        self.theme_changed_signal.connect(self._on_system_theme_changed)
        self._face_path = face_path

        # Load customization from config
        _cfg = _read_full_config()
        self._theme_preference = str(_cfg.get("ui_theme") or "system").strip().lower()
        if self._theme_preference not in {"system", "dark", "light"}:
            self._theme_preference = "system"
        # Qt's native hint avoids a light-mode flash while the OS-specific
        # appearance worker starts and watches for subsequent changes.
        scheme = QApplication.styleHints().colorScheme()
        self._system_theme = "light" if scheme == Qt.ColorScheme.Light else "dark"
        self._theme_preview_preference: str | None = None
        self._assistant_name: str = "EDITH"
        _display = _display_assistant_name(self._assistant_name)
        self._display_name = _display

        # Keep the new default theme when an older installation saved the old cyan default.
        # Appearance follows the system palette; manual accent editing is intentionally unavailable.
        apply_ui_theme(self._resolved_theme())
        apply_dark_theme(QApplication.instance(), C)

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowTitleHint
                            | Qt.WindowType.WindowSystemMenuHint | Qt.WindowType.WindowMinMaxButtonsHint
                            | Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle("EDITH • PERSONAL ASSISTANT")
        self.setWindowIcon(svg_icon("edith-app", C.PRI))
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        geometry = initial_geometry(screen, _DEFAULT_W, _DEFAULT_H)
        self.setMinimumSize(min(_MIN_W, geometry.width()), min(_MIN_H, geometry.height()))
        self.setGeometry(geometry)

        self.on_text_command   = None
        self.on_remote_clicked = None   # callable: () -> (url, key) | None
        self.on_api_key_saved  = None   # callback after a tested key is saved
        self.on_voice_mode_clicked = None
        self.on_interrupt      = None   # callable: () -> None — stop speech
        self.on_cancel_queued_tasks = None  # queue-only cancellation callback
        self.get_plugins       = None   # callable: () -> list[dict], set by EdithLive
        self._muted            = False
        self._current_file: str | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None
        self._customize_overlay: CustomizeOverlay | None = None
        self._api_key_overlay: ApiProviderWorkspace | None = None
        self._voice_mode = str(_cfg.get("voice_mode") or "female").lower()
        if self._voice_mode not in {"female", "male"}:
            self._voice_mode = "female"
        # Store display-only preferences separately; do not touch cloud/local LLM keys.
        self._reduced_motion = QSettings("EDITH", "EDITH").value(
            "reduced_log_motion", False, type=bool
        )
        self._voice_female_btn: QPushButton | None = None
        self._voice_male_btn: QPushButton | None = None

        central = QWidget()
        central.setObjectName("EdithRoot")
        central.setStyleSheet(f"""
            QWidget#EdithRoot {{
                background: qradialgradient(cx:0.52,cy:0.16,radius:1.0,
                    fx:0.52,fy:0.16,stop:0 {C.PANEL},stop:1 {C.BG});
            }}
        """)
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        # Center column: HUD + resizable content panel via QSplitter
        self.hud = HudCanvas(face_path, _display)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_panel = self._build_content_panel()

        # Live camera container — replaces HUD when camera stream is active
        _cam_cont = QWidget()
        _cam_cont.setStyleSheet(f"background: {C.BG};")
        _cam_v = QVBoxLayout(_cam_cont)
        _cam_v.setContentsMargins(0, 0, 0, 0)
        _cam_v.setSpacing(0)
        _cam_hdr = QHBoxLayout()
        _cam_hdr.setContentsMargins(12, 8, 12, 8)
        _cam_title = QLabel("CAMERA FEED")
        _cam_title.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        _cam_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _cam_hdr.addWidget(_cam_title)
        _cam_hdr.addStretch()
        _cam_x = QPushButton("CLOSE")
        _set_theme_icon(_cam_x, "x", "TEXT_DIM")
        _cam_x.setIconSize(QSize(13, 13))
        _cam_x.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        _cam_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _cam_x.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_DIM}; background: transparent;
                border: none; padding: 2px 6px;
            }}
            QPushButton:hover {{ color: {C.PRI}; }}
        """)
        _cam_x.clicked.connect(self.stop_camera_stream)
        _cam_hdr.addWidget(_cam_x)
        _cam_v.addLayout(_cam_hdr)
        self._cam_live_lbl = QLabel()
        self._cam_live_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_live_lbl.setStyleSheet("background: transparent;")
        self._cam_live_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        _cam_v.addWidget(self._cam_live_lbl, stretch=1)

        # Stack: 0 = animated HUD, 1 = live camera
        self._hud_cam_stack = QStackedWidget()
        self._hud_cam_stack.addWidget(self.hud)
        self._hud_cam_stack.addWidget(_cam_cont)

        self._center_split = QSplitter(Qt.Orientation.Vertical)
        self._center_split.setStyleSheet(f"""
            QSplitter::handle {{
                background: {C.BORDER};
                height: 2px;
            }}
            QSplitter::handle:hover {{
                background: {C.PRI_DIM};
            }}
        """)
        self._center_split.addWidget(self._hud_cam_stack)
        self._center_split.addWidget(self._content_panel)
        self._center_split.setStretchFactor(0, 3)
        self._center_split.setStretchFactor(1, 1)
        self._center_split.setCollapsible(0, False)
        body.addWidget(self._center_split, stretch=5)

        self._right_panel = self._build_right_panel()
        self._log.set_reduced_motion(self._reduced_motion)
        self.hud.reduced_motion = self._reduced_motion
        body.addWidget(self._right_panel, stretch=0)
        self._adjust_side_panels()

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        # Quick-access drawer (floating overlay, built after central widget layout is done)
        self._quick_drawer = self._build_quick_drawer()
        self._migrate_legacy_autostart()
        self._update_autostart_btn(self._check_autostart())
        from memory.config_manager import get_brief_enabled as _gbe
        self._update_brief_btn(_gbe())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # The signal bar refreshes at 4 Hz; the HUD animation runs at 30 FPS.
        self._mic_status_tmr = QTimer(self)
        self._mic_status_tmr.timeout.connect(self._refresh_mic_status)
        self._mic_status_tmr.start(250)
        self._refresh_mic_status()

        # Metrik güncelleme timer'ı
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._playback_sig.connect(self._on_playback_state)
        self._output_level_sig.connect(self.hud.set_output_level)
        self._mic_level_sig.connect(self._on_mic_level)
        self._content_sig.connect(self._show_content)
        self._reconfig_sig.connect(self._show_setup)
        self._camera_sig.connect(self._show_camera_frame)
        self._cam_stream_sig.connect(self._on_cam_stream)
        self._cam_frame_sig.connect(self._on_cam_frame)
        self._clipboard_sig.connect(self._show_clipboard_panel)
        self._confirm_action_sig.connect(self._show_action_confirmation)
        self._cam_stop = threading.Event()

        # OS appearance reads may invoke gsettings/defaults. Keep them off the
        # Qt event loop and relay changes through the queued Qt signal above.
        self._theme_monitor = SystemThemeMonitor(self.theme_changed_signal.emit, interval=2.0)
        self._theme_monitor.start()

        # Camera preview overlay (child of central widget, positioned in resizeEvent)
        self._cam_preview = _CameraPreview(self.centralWidget())

        # Clipboard panel (child of central widget, bottom-center)
        self._clipboard_panel = ClipboardPanel(self.centralWidget())
        self._clipboard_panel.action_requested.connect(self._on_clipboard_action)
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_intr = QShortcut(QKeySequence("Escape"), self)
        sc_intr.activated.connect(self._escape_action)
        sc_focus = QShortcut(QKeySequence("Ctrl+K"), self)
        sc_focus.activated.connect(self._focus_command_input)

    def _resolved_theme(self, preference: str | None = None) -> str:
        selected = str(preference or self._theme_preference).lower()
        return self._system_theme if selected == "system" else normalise_theme(selected)

    def _render_theme(self, preference: str | None = None) -> None:
        """Repaint native widgets in place without changing their geometry."""
        old = current_palette()
        apply_ui_theme(self._resolved_theme(preference))
        retheme_all_widgets(old, current_palette())
        self.setWindowIcon(svg_icon("edith-app", C.PRI))

    def _preview_theme_preference(self, preference: str | None) -> None:
        self._theme_preview_preference = preference
        self._render_theme(preference)

    def _save_theme_preference(self, preference: str) -> None:
        preference = str(preference or "system").lower()
        self._theme_preference = preference if preference in {"system", "dark", "light"} else "system"
        self._theme_preview_preference = None
        self._render_theme()
        try:
            data = _read_full_config()
            data["ui_theme"] = self._theme_preference
            API_FILE.parent.mkdir(parents=True, exist_ok=True)
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self._log.append_log(f"SYS: Appearance set to {self._theme_preference.title()}.")
        except Exception as exc:
            self._log.append_log(f"ERR: Theme preference save failed — {type(exc).__name__}: {exc}")

    def _on_system_theme_changed(self, theme: str) -> None:
        self._system_theme = normalise_theme(theme)
        active = self._theme_preview_preference
        if active is None:
            active = self._theme_preference
        if active == "system":
            self._render_theme(active)

    def closeEvent(self, event):
        if getattr(self, "_theme_monitor", None):
            self._theme_monitor.stop()
        if getattr(self, "hud", None) is not None:
            self.hud.shutdown()
        for timer_name in ("_clock_tmr", "_mic_status_tmr", "_metric_tmr"):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                timer.stop()
        self._cam_stop.set() if hasattr(self, "_cam_stop") else None
        super().closeEvent(event)

    def _show_url_prompt(self, request):
        try:
            dialog = QInputDialog(self)
            dialog.setWindowTitle("EDITH · YouTube video")
            dialog.setLabelText(request["prompt"])
            dialog.setOkButtonText("Continue")
            timer = QTimer(dialog)
            timer.setSingleShot(True)
            timer.timeout.connect(dialog.reject)
            timer.start(180000)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                request["value"] = dialog.textValue().strip() or None
        finally:
            request["event"].set()


    def _clear_selected_file(self):
        self._current_file = None
        self._file_hint.setText("No file selected. Drop a file or browse to attach one.")


    def _escape_action(self):
        for attr in ('_customize_overlay', '_remote_overlay', '_api_key_overlay', '_plugin_manager_overlay'):
            panel = getattr(self, attr, None)
            if panel and panel.isVisible():
                if hasattr(panel, '_cancel'):
                    panel._cancel()
                elif hasattr(panel, '_do_close'):
                    panel._do_close()
                else:
                    panel.hide()
                return
        if self._quick_drawer.isVisible():
            self._drawer_btn.setChecked(False)
            self._quick_drawer.hide()
        else:
            self._do_interrupt()

    def _show_camera_frame(self, img_bytes: bytes):
        """Slot — display camera preview overlay (main thread)."""
        self._cam_preview.show_frame(img_bytes)
        cw = self.centralWidget()
        pw = _CameraPreview._W
        ph = self._cam_preview.height()
        self._cam_preview.setGeometry(
            cw.width() - self._right_panel.width() - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )

    # --- Live camera stream in HUD area ------------------------------------
    def _on_cam_stream(self, start: bool) -> None:
        if start:
            self._hud_cam_stack.setCurrentIndex(1)
        else:
            self._hud_cam_stack.setCurrentIndex(0)
            self._cam_live_lbl.clear()

    def _on_cam_frame(self, data: bytes) -> None:
        px = QPixmap()
        px.loadFromData(data)
        if not px.isNull():
            w, h = self._cam_live_lbl.width(), self._cam_live_lbl.height()
            if w > 1 and h > 1:
                self._cam_live_lbl.setPixmap(
                    px.scaled(w, h,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )

    def start_camera_stream(self) -> None:
        self._cam_stop.clear()
        self._cam_stream_sig.emit(True)
        t = threading.Thread(target=self._cam_loop, daemon=True, name="cam-stream")
        t.start()

    def _cam_loop(self) -> None:
        try:
            import cv2
            # Reuse camera index detected by screen_processor (cached in api_keys.json)
            cam_idx = 0
            try:
                import json as _j
                cfg = _j.loads((CONFIG_DIR / "api_keys.json").read_text())
                cam_idx = int(cfg.get("camera_index", 0))
            except Exception:
                pass
            try:
                backend = cv2.CAP_DSHOW if _OS == "Windows" else cv2.CAP_ANY
            except AttributeError:
                backend = 0
            cap = cv2.VideoCapture(cam_idx, backend)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return
            # warm-up frames
            for _ in range(5):
                cap.read()
            while not self._cam_stop.wait(0.033) and cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    self._cam_frame_sig.emit(buf.tobytes())
            cap.release()
        except Exception as e:
            print(f"[Camera] Stream error: {e}")
        finally:
            self._cam_stream_sig.emit(False)

    def stop_camera_stream(self) -> None:
        self._cam_stop.set()

    # ------------------------------------------------------------------
    # Dedicated EDITH monogram icon; generated locally in standard Windows sizes.
    @staticmethod
    def _build_assistant_icon(out_path: Path) -> bool:
        """Produce the permanent EDITH desktop icon from the same local asset."""
        from core.app_icon import build_edith_icon
        return build_edith_icon(out_path)

    @staticmethod
    def _create_lnk_windows(lnk: str, target: str, args: str,
                             work_dir: str, icon_loc: str) -> None:
        """
        Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd.
        Tries win32com (pywin32) first; falls back to wscript.exe + VBScript.
        wscript.exe is a GUI-mode host — it never opens a console window.
        """
        # ── Option 1: pywin32 (pure Python COM, zero subprocess) ──────────
        try:
            from win32com.client import Dispatch   # type: ignore
            sh = Dispatch("WScript.Shell")
            sc = sh.CreateShortCut(lnk)
            sc.TargetPath       = target
            sc.Arguments        = f'"{args}"'
            sc.WorkingDirectory = work_dir
            sc.Description      = "EDITH Personal Assistant"
            sc.IconLocation     = icon_loc
            sc.save()
            return
        except ImportError:
            pass

        # ── Option 2: wscript.exe + VBScript (always available on Windows,
        #    GUI-mode executable — never opens a console window) ────────────
        vbs = "\n".join([
            'Set ws = CreateObject("WScript.Shell")',
            f'Set sc = ws.CreateShortcut("{lnk}")',
            f'sc.TargetPath = "{target}"',
            f'sc.Arguments = Chr(34) & "{args}" & Chr(34)',
            f'sc.WorkingDirectory = "{work_dir}"',
            'sc.Description = "EDITH Personal Assistant"',
            f'sc.IconLocation = "{icon_loc}"',
            'sc.Save',
        ])
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".vbs")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(vbs)
            proc = subprocess.Popen(
                ["wscript.exe", "/nologo", tmp],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            proc.wait(timeout=10)
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    @staticmethod
    def _get_desktop_dir() -> Path:
        """
        Resolve the user's REAL desktop directory instead of assuming
        ~/Desktop, which breaks when:
          • OneDrive "Known Folder Move" relocates the desktop
            (C:/Users/x/OneDrive/Desktop) — very common on Win 10/11;
          • the XDG desktop is localized on Linux (~/Masaüstü,
            ~/Schreibtisch, ~/Bureau, …).
        Falls back to ~/Desktop only as a last resort.
        """
        home = Path.home()
        _os = platform.system()

        if _os == "Windows":
            # ── 1) SHGetKnownFolderPath(FOLDERID_Desktop) — the canonical
            #       answer; follows OneDrive redirection. No dependencies. ──
            try:
                import ctypes
                from ctypes import wintypes

                class _GUID(ctypes.Structure):
                    _fields_ = [("Data1", wintypes.DWORD),
                                ("Data2", wintypes.WORD),
                                ("Data3", wintypes.WORD),
                                ("Data4", ctypes.c_ubyte * 8)]

                # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
                fid = _GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9,
                                                 0x9A, 0x87, 0xC6, 0x41))
                buf = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(
                        ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
                    p = Path(buf.value)
                    ctypes.windll.ole32.CoTaskMemFree(buf)
                    if p.is_dir():
                        return p
            except Exception:
                pass

            # ── 2) Registry: User Shell Folders (may contain %VARS%) ──────
            try:
                import winreg
                with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Explorer\User Shell Folders") as key:
                    val, _t = winreg.QueryValueEx(key, "Desktop")
                p = Path(os.path.expandvars(val))
                if p.is_dir():
                    return p
            except Exception:
                pass

        elif _os == "Linux":
            # ── xdg-user-dir honours localized names (~/Masaüstü, …) ──────
            try:
                out = subprocess.run(["xdg-user-dir", "DESKTOP"],
                                     capture_output=True, text=True, timeout=5)
                p = Path(out.stdout.strip())
                if out.stdout.strip() and p != home and p.is_dir():
                    return p
            except Exception:
                pass
            try:
                cfg = home / ".config" / "user-dirs.dirs"
                for line in cfg.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("XDG_DESKTOP_DIR"):
                        val = line.split("=", 1)[1].strip().strip('"')
                        p = Path(val.replace("$HOME", str(home)))
                        if p != home and p.is_dir():
                            return p
            except Exception:
                pass

        # macOS: ~/Desktop is always the real path (localization is
        # display-only). Everything else lands here as a last resort.
        return home / "Desktop"

    @staticmethod
    def _remove_verified_old_shortcuts(desktop: Path, script: Path) -> int:
        """Remove legacy launchers only when they point at this exact EDITH main.py.

        Never delete a shortcut by name alone. Unverifiable entries stay intact,
        so unrelated applications and user-customized shortcuts are protected.
        """
        removed = 0
        expected = str(script.resolve()).casefold()
        if platform.system() == "Windows":
            try:
                from win32com.client import Dispatch
                shell = Dispatch("WScript.Shell")
            except (ImportError, OSError):
                return 0
            for shortcut in desktop.glob("*.lnk"):
                if shortcut.stem.lower() == "edith":
                    continue
                name = shortcut.stem.casefold()
                if not any(word in name for word in ("jarvis", "ai assistant", "mark xl")):
                    continue
                try:
                    old = shell.CreateShortcut(str(shortcut))
                    details = f"{old.TargetPath} {old.Arguments}".casefold()
                    if expected in details:
                        shortcut.unlink()
                        removed += 1
                except Exception:
                    continue
        elif platform.system() == "Linux":
            for name in ("ai-assistant.desktop", "jarvis.desktop"):
                old = desktop / name
                try:
                    if old.is_file() and expected in old.read_text(encoding="utf-8").casefold():
                        old.unlink()
                        removed += 1
                except OSError:
                    pass
        return removed

    def _create_desktop_shortcut(self):
        """
        Create a desktop shortcut on Windows / macOS / Linux.
        Never opens a terminal, console, or PowerShell window on any platform.
        """
        import stat as _stat
        script  = Path(__file__).resolve().parent / "main.py"
        python  = Path(sys.executable)
        desktop = self._get_desktop_dir()

        # Dedicated EDITH application icon (.ico, exported as .png for Linux/macOS)
        ico_path = Path(__file__).resolve().parent / "config" / "edith.ico"
        if not ico_path.exists() and not self._build_assistant_icon(ico_path):
            self._log.append_log("ERR: EDITH icon unavailable. Install Pillow and retry.")
            return

        try:
            _os = platform.system()

            # ── Windows ───────────────────────────────────────────────────────
            if _os == "Windows":
                pythonw  = python.parent / "pythonw.exe"
                target   = str(pythonw if pythonw.exists() else python)
                lnk      = str(desktop / "EDITH.lnk")
                icon_loc = str(ico_path) if ico_path.exists() else f"{target},0"
                self._create_lnk_windows(lnk, target, str(script),
                                         str(script.parent), icon_loc)

            # ── macOS — proper .app bundle (no Terminal window) ───────────────
            elif _os == "Darwin":
                app     = desktop / "EDITH.app"
                mac_dir = app / "Contents" / "MacOS"
                res_dir = app / "Contents" / "Resources"
                mac_dir.mkdir(parents=True, exist_ok=True)
                res_dir.mkdir(exist_ok=True)

                # Launcher executable (bash — runs as background process,
                # macOS does NOT open Terminal for executables inside .app bundles)
                launcher = mac_dir / "EDITH"
                launcher.write_text(
                    "#!/usr/bin/env bash\n"
                    f'cd "{script.parent}"\n'
                    f'exec "{python}" "{script}"\n'
                )
                launcher.chmod(launcher.stat().st_mode
                               | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)

                # Minimal Info.plist (required for .app recognition)
                (app / "Contents" / "Info.plist").write_text(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>CFBundleExecutable</key><string>EDITH</string>\n'
                    '  <key>CFBundleIdentifier</key>'
                    '<string>app.edith.assistant</string>\n'
                    '  <key>CFBundleName</key><string>EDITH</string>\n'
                    '  <key>CFBundlePackageType</key><string>APPL</string>\n'
                    '  <key>CFBundleVersion</key><string>1.0</string>\n'
                    '</dict></plist>\n'
                )

                # Optional: copy icon as .icns (skip silently if Pillow is missing)
                try:
                    import PIL.Image
                    icns = res_dir / "AppIcon.icns"
                    PIL.Image.open(ico_path).save(icns, format="ICNS")
                    # Inject icon reference into plist
                    plist = app / "Contents" / "Info.plist"
                    txt = plist.read_text()
                    plist.write_text(
                        txt.replace(
                            '</dict></plist>',
                            '  <key>CFBundleIconFile</key>'
                            '<string>AppIcon</string>\n</dict></plist>\n',
                        )
                    )
                except Exception:
                    pass  # icon is optional

            # ── Linux — .desktop file (Terminal=false, no console) ────────────
            else:
                # Export .ico → .png for better desktop integration
                png_path = ico_path.with_suffix(".png")
                if not png_path.exists() and ico_path.exists():
                    try:
                        import PIL.Image
                        PIL.Image.open(ico_path).resize(
                            (256, 256), PIL.Image.LANCZOS
                        ).save(png_path, format="PNG")
                    except Exception:
                        png_path = ico_path  # fallback to .ico

                icon_line = f"Icon={png_path}\n" if png_path.exists() else ""
                desk = desktop / "edith.desktop"
                desk.write_text(
                    "[Desktop Entry]\n"
                    "Name=EDITH\n"
                    f"Exec={python} {script}\n"
                    f"Path={script.parent}\n"
                    "Type=Application\n"
                    "Terminal=false\n"
                    "Categories=Utility;\n"
                    + icon_line
                )
                desk.chmod(desk.stat().st_mode | 0o755)

            removed = self._remove_verified_old_shortcuts(desktop, script)
            self._log.append_log(f"SYS: EDITH desktop shortcut created; {removed} verified old shortcut(s) cleaned.")
        except Exception as e:
            self._log.append_log(f"ERR: Shortcut failed — {e}")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _adjust_side_panels(self) -> None:
        """Preserve the EDITH layout but free HUD space on narrow windows."""
        if not hasattr(self, "_left_panel") or not hasattr(self, "_right_panel"):
            return
        viewport = self.centralWidget().width()
        self._left_panel.setFixedWidth(142 if viewport < 980 else _LEFT_W)
        self._right_panel.setFixedWidth(max(290, min(_RIGHT_W, int(viewport * 0.33))))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "_cam_preview"):
            return
        self._adjust_side_panels()
        cw = self.centralWidget()
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._remote_overlay and self._remote_overlay.isVisible():
            ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
            self._remote_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._customize_overlay and self._customize_overlay.isVisible():
            ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
            self._customize_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        # Camera preview — bottom-right corner of the center/HUD area
        pw = _CameraPreview._W
        ph = self._cam_preview.height() or _CameraPreview._H
        self._cam_preview.setGeometry(
            cw.width() - self._right_panel.width() - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )
        # Clipboard panel — bottom-center
        if hasattr(self, '_clipboard_panel') and self._clipboard_panel.isVisible():
            self._position_clipboard_panel()
        # Quick drawer — reposition if open
        if hasattr(self, '_quick_drawer') and self._quick_drawer.isVisible():
            self._position_quick_drawer()

    def _update_metrics(self):
        # Cached values only: no psutil, sensor or subprocess call on the Qt loop.
        snap = _metrics.snapshot()
        for name, bar in (("cpu",self._bar_cpu),("mem",self._bar_mem),
                          ("gpu",self._bar_gpu),("tmp",self._bar_tmp)):
            value = snap.get(name)
            suffix = "°C" if name == "tmp" else "%"
            bar.set_value(value if value is not None else 0,
                          f"{value:.0f}{suffix}" if value is not None else "N/A")
        net = snap.get("net")
        net_text = "N/A" if net is None else f"{net*1024:.0f}KB/s" if net < 1 else f"{net:.1f}MB/s"
        self._bar_net.set_value(min(100,net*10) if net is not None else 0,net_text)
        elapsed = snap.get("uptime_seconds")
        self._uptime_lbl.setText(f"UP  {int(elapsed//3600):02d}:{int(elapsed%3600//60):02d}"
                                if elapsed is not None else "UP  N/A")
        count = snap.get("process_count")
        self._proc_lbl.setText(f"PROC  {count}" if count is not None else "PROC  N/A")


    def _build_header(self) -> QWidget:
        """Build a calm, readable product header with clear brand hierarchy."""
        w = QWidget()
        w.setObjectName("WorkspaceHeader")
        w.setFixedHeight(74)
        w.setStyleSheet(f"""
            QWidget#WorkspaceHeader {{
                background: {C.HEADER};
                border-bottom: 1px solid {C.BORDER};
            }}
        """)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(22, 0, 22, 0)
        lay.setSpacing(14)

        brand = QVBoxLayout()
        brand.setSpacing(2)
        brand_title = QLabel("EDITH SYSTEMS")
        brand_title.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        brand_title.setStyleSheet(
            f"color: {C.TEXT}; background: transparent; letter-spacing: 1px;"
        )
        brand_hint = QLabel("PERSONAL AI WORKSPACE")
        brand_hint.setFont(QFont(FONT_MAIN, 7))
        brand_hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        brand.addWidget(brand_title)
        brand.addWidget(brand_hint)
        lay.addLayout(brand)

        self._drawer_btn = QPushButton()
        _set_theme_icon(self._drawer_btn, "settings", "PRI")
        self._drawer_btn.setIconSize(QSize(18, 18))
        self._drawer_btn.setFixedSize(36, 36)
        self._drawer_btn.setAccessibleName("Open workspace controls")
        self._drawer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drawer_btn.setToolTip("Settings and workspace controls")
        self._drawer_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.GLASS_CARD}; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 11px;
            }}
            QPushButton:hover {{
                color: {C.PRI}; background: {C.HOVER}; border-color: {C.PRI_DIM};
            }}
            QPushButton:checked {{
                color: {C.PRI}; border-color: {C.PRI}; background: {C.PRI_GHO};
            }}
        """)
        self._drawer_btn.setCheckable(True)
        self._drawer_btn.clicked.connect(self._toggle_drawer)
        lay.addWidget(self._drawer_btn)
        lay.addStretch(1)

        mid = QVBoxLayout()
        mid.setSpacing(2)
        self._title_lbl = QLabel(self._display_name)
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_lbl.setFont(QFont(FONT_MAIN, 19, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;"
        )
        mid.addWidget(self._title_lbl)

        self._sub_lbl = QLabel(
            "PERSONAL AI WORKSPACE  ·  VOICE  ·  VISION  ·  AUTOMATION"
        )
        self._sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub_lbl.setFont(QFont(FONT_MAIN, 8))
        self._sub_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        mid.addWidget(self._sub_lbl)
        lay.addLayout(mid, stretch=2)
        lay.addStretch(1)

        right_col = QVBoxLayout()
        right_col.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont(FONT_MONO, 14, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont(FONT_MAIN, 8))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)
        return w


    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_left_panel(self) -> QWidget:
        """Show useful, real system telemetry in a compact health panel."""
        w = QWidget()
        w.setObjectName("SystemHealthPanel")
        w.setFixedWidth(_LEFT_W)
        w.setStyleSheet(f"""
            QWidget#SystemHealthPanel {{
                background: {C.SIDEBAR};
                border: 1px solid {C.BORDER};
                border-radius: 18px;
            }}
        """)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        hdr = QLabel("SYSTEM HEALTH")
        hdr.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        hdr.setStyleSheet(
            f"color: {C.TEXT}; background: transparent; "
            f"padding-bottom: 7px; border-bottom: 1px solid {C.BORDER}; "
            "letter-spacing: 0.6px;"
        )
        lay.addWidget(hdr)

        hint = QLabel("Live resource usage")
        hint.setFont(QFont(FONT_MAIN, 8))
        hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(hint)

        self._bar_cpu = MetricBar("CPU", "PRI")
        self._bar_mem = MetricBar("MEM", "ACC2")
        self._bar_net = MetricBar("NET", "GREEN")
        self._bar_gpu = MetricBar("GPU", "ACC")
        self._bar_tmp = MetricBar("TEMP", "RED")
        for bar in (self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp):
            lay.addWidget(bar)

        info_panel = QFrame()
        info_panel.setObjectName("SystemDetailsCard")
        info_panel.setStyleSheet(f"""
            QFrame#SystemDetailsCard {{
                background: {C.GLASS_CARD};
                border: 1px solid {C.BORDER};
                border-radius: 13px;
            }}
        """)
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(11, 10, 11, 10)
        ip_lay.setSpacing(7)

        self._uptime_lbl = QLabel("UPTIME  —")
        self._uptime_lbl.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(
            f"color: {C.GREEN}; background: transparent; border: none;"
        )
        ip_lay.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROCESSES  —")
        self._proc_lbl.setFont(QFont(FONT_MONO, 8))
        self._proc_lbl.setStyleSheet(
            f"color: {C.TEXT_MED}; background: transparent; border: none;"
        )
        ip_lay.addWidget(self._proc_lbl)

        os_name = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}.get(
            _OS, _OS
        )
        os_lbl = QLabel(f"PLATFORM  {os_name}")
        os_lbl.setFont(QFont(FONT_MONO, 8))
        os_lbl.setStyleSheet(
            f"color: {C.ACC2}; background: transparent; border: none;"
        )
        ip_lay.addWidget(os_lbl)

        lay.addWidget(info_panel)
        lay.addStretch(1)

        note = QLabel("Telemetry refreshes every 2 seconds")
        note.setWordWrap(True)
        note.setFont(QFont(FONT_MAIN, 7))
        note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(note)
        return w


    def _update_task_status(self, running: int, queued: int, completed: int) -> None:
        self._running_tasks = max(0, running)
        self._render_activity_state()
        self._task_status_lbl.setText(f"TASKS  {running} RUN  ·  {queued} WAIT")
        self._task_status_lbl.setToolTip(
            f"Running: {running} | Queued: {queued} | Completed: {completed}"
        )
        self._cancel_queued_btn.setEnabled(queued > 0)

    def _request_cancel_queued(self) -> None:
        if self.on_cancel_queued_tasks:
            self.on_cancel_queued_tasks()

    def _toggle_task_details(self, checked: bool) -> None:
        """Show current tasks without covering the original EDITH HUD."""
        self._task_details_panel.setVisible(bool(checked))
        self._task_details_btn.setToolTip(
            "Hide recent tasks" if checked else "Show running, queued and recent tasks"
        )

    def _update_task_details(self, summary: dict) -> None:
        """Render bounded scheduler metadata on the Qt UI thread."""
        tasks = summary.get("visible", [])
        total = int(summary.get("total", 0))
        self._task_details_btn.setEnabled(total > 0)
        if not total:
            self._task_details_btn.setChecked(False)
            self._task_details_panel.hide()
        colors = {
            "running": C.GREEN, "queued": C.ACC2,
            "succeeded": C.GREEN, "failed": C.RED, "blocked": C.RED,
            "interrupted": C.ACC2, "cancelled": C.TEXT_DIM,
        }
        for index, (row, name, status) in enumerate(self._task_detail_rows):
            if index >= len(tasks):
                row.hide()
                continue
            item = tasks[index]
            full = str(item.get("label") or "Task")
            name.setText(name.fontMetrics().elidedText(
                full, Qt.TextElideMode.ElideRight,
                max(115, self._right_panel.width() - 144),
            ))
            name.setToolTip(full)
            state = str(item.get("status") or "queued").lower()
            status.setText(state.upper())
            status.setStyleSheet(
                f"color: {colors.get(state, C.TEXT_MED)}; background: transparent;"
            )
            row.show()
        remaining = max(0, total - len(tasks))
        self._task_more_lbl.setText(
            f"+ {remaining} more task(s) in this session" if remaining else ""
        )
        self._task_more_lbl.setVisible(remaining > 0)

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setObjectName("OperationsPanel")
        w.setFixedWidth(_RIGHT_W)
        w.setStyleSheet(f"QWidget#OperationsPanel {{ background: {C.SIDEBAR}; border: 1px solid {C.BORDER}; border-radius: 18px; }}")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(11)

        def _sec(txt):
            l = QLabel(txt)
            l.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
            l.setStyleSheet(
                f"color: {C.TEXT_MED}; background: transparent; "
                f"padding: 2px 0 6px; border-bottom: 1px solid {C.BORDER}; "
                "letter-spacing: 0.5px;"
            )
            return l

        # Keep the existing EDITH panel; task state is a compact extension,
        # not a new dashboard or a redesign of the current application.
        tasks_row = QHBoxLayout()
        tasks_row.setSpacing(6)
        self._task_status_lbl = QLabel("TASKS  0 RUN  ·  0 WAIT")
        self._task_status_lbl.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        self._task_status_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent;"
        )
        self._task_status_lbl.setToolTip("Live tasks: running and queued")
        tasks_row.addWidget(self._task_status_lbl, stretch=1)

        self._cancel_queued_btn = QPushButton("Cancel queued")
        self._cancel_queued_btn.setFixedHeight(30)
        self._cancel_queued_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.DemiBold))
        self._cancel_queued_btn.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_MED}; background: {C.GLASS_CARD};
                border: 1px solid {C.BORDER}; border-radius: 8px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI}; }}
            QPushButton:disabled {{ color: {C.TEXT_DIM}; }}
        """)
        self._cancel_queued_btn.setToolTip(
            "CANCEL WAITING — Cancel only tasks that have not started. Running OS actions continue."
        )
        self._cancel_queued_btn.setEnabled(False)
        self._cancel_queued_btn.clicked.connect(self._request_cancel_queued)
        tasks_row.addWidget(self._cancel_queued_btn)

        self._task_details_btn = QPushButton()
        _set_theme_icon(self._task_details_btn, "chevron-down", "TEXT_MED")
        self._task_details_btn.setIconSize(QSize(13, 13))
        self._task_details_btn.setFixedSize(26, 25)
        self._task_details_btn.setCheckable(True)
        self._task_details_btn.setEnabled(False)
        self._task_details_btn.setToolTip("Show running, queued and recent tasks")
        self._task_details_btn.setAccessibleName("Show or hide EDITH task details")
        self._task_details_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.GLASS_CARD}; border: 1px solid {C.BORDER};
                border-radius: 8px;
            }}
            QPushButton:checked {{ border-color: {C.PRI_DIM}; }}
            QPushButton:hover {{ border-color: {C.PRI}; }}
            QPushButton:disabled {{ border-color: {C.BORDER}; }}
        """)
        self._task_details_btn.toggled.connect(self._toggle_task_details)
        tasks_row.addWidget(self._task_details_btn)
        lay.addLayout(tasks_row)

        self._task_details_panel = QFrame()
        self._task_details_panel.setObjectName("TaskDetailsPanel")
        self._task_details_panel.setStyleSheet(f"""
            QFrame#TaskDetailsPanel {{
                background: {C.GLASS}; border: 1px solid {C.BORDER};
                border-radius: 11px;
            }}
        """)
        detail_lay = QVBoxLayout(self._task_details_panel)
        detail_lay.setContentsMargins(8, 5, 8, 5)
        detail_lay.setSpacing(3)
        self._task_detail_rows = []
        for _ in range(4):
            item_row = QWidget()
            item_lay = QHBoxLayout(item_row)
            item_lay.setContentsMargins(0, 0, 0, 0)
            item_lay.setSpacing(5)
            task_name = QLabel("")
            task_name.setTextFormat(Qt.TextFormat.PlainText)
            task_name.setFont(QFont(FONT_MAIN, 8))
            task_name.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            item_lay.addWidget(task_name, stretch=1)
            task_state = QLabel("")
            task_state.setFont(QFont(FONT_MONO, 7, QFont.Weight.Bold))
            task_state.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            task_state.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            item_lay.addWidget(task_state)
            detail_lay.addWidget(item_row)
            item_row.hide()
            self._task_detail_rows.append((item_row, task_name, task_state))
        self._task_more_lbl = QLabel("")
        self._task_more_lbl.setFont(QFont(FONT_MAIN, 7))
        self._task_more_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._task_more_lbl.hide()
        detail_lay.addWidget(self._task_more_lbl)
        self._task_details_panel.hide()
        lay.addWidget(self._task_details_panel)

        lay.addWidget(_sec("ACTIVITY LOG"))
        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_sec("ATTACHMENTS"))
        self._drop_zone = FileDropZone()
        self._drop_zone.setAccessibleName("File attachment drop zone")
        self._drop_zone.setToolTip("Drop a file here or click to browse for an attachment")
        self._drop_zone.file_selected.connect(self._on_file_selected)
        self._drop_zone.file_cleared.connect(self._clear_selected_file)
        lay.addWidget(self._drop_zone)

        self._file_hint = QLabel("No attachment selected · Drop a file above or click to browse")
        self._file_hint.setFont(QFont(FONT_MAIN, 8))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._file_hint.setWordWrap(True)
        lay.addWidget(self._file_hint)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_sec("MESSAGE EDITH"))
        lay.addLayout(self._build_input_row())

        self._interrupt_btn = QPushButton("Stop response  ·  Esc")
        _set_theme_icon(self._interrupt_btn, "stop-circle", "MUTED_C")
        self._interrupt_btn.setIconSize(QSize(16, 16))
        self._interrupt_btn.setFixedHeight(38)
        self._interrupt_btn.setFont(QFont(FONT_MAIN, 9, QFont.Weight.DemiBold))
        self._interrupt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._interrupt_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.DANGER_BG}; color: {C.MUTED_C};
                border: 1px solid {C.MUTED_C}; border-radius: 9px;
            }}
            QPushButton:hover {{
                background: {C.DANGER_HOVER}; border: 1px solid {C.RED};
            }}
            QPushButton:pressed {{
                background: {C.DANGER_HOVER};
            }}
        """)
        self._interrupt_btn.clicked.connect(self._do_interrupt)
        lay.addWidget(self._interrupt_btn)

        self._mute_btn = QPushButton("MICROPHONE ACTIVE")
        self._mute_btn.setFixedHeight(32)
        self._mute_btn.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        lay.addWidget(self._mute_btn)

        return w

    def _build_quick_drawer(self) -> QWidget:
        """Floating overlay panel shown when the settings header button is toggled."""
        _BTN_STYLE_PRI = f"""
            QPushButton {{
                background: {C.GLASS_CARD}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 9px;
                text-align: left; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {C.HOVER}; border-color: {C.PRI}; }}
        """
        _BTN_STYLE_DIM = f"""
            QPushButton {{
                background: {C.GLASS_CARD}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 9px;
                text-align: left; padding: 0 10px;
            }}
            QPushButton:hover {{ color: {C.PRI}; background: {C.HOVER}; border-color: {C.BORDER_B}; }}
        """

        w = QWidget(self.centralWidget())
        w.setObjectName("QuickDrawer")
        _glass_shadow(w)
        w.setStyleSheet(f"""
            QWidget#QuickDrawer {{
                background: {C.SHEET};
                border: 1px solid {C.BORDER_B};
                border-radius: 16px;
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(6)

        hdr = QLabel("◈ CONTROLS")
        hdr.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 6px;")
        lay.addWidget(hdr)

        remote_btn = QPushButton("◉  REMOTE CONTROL")
        remote_btn.setFixedHeight(32)
        remote_btn.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        remote_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remote_btn.setStyleSheet(_BTN_STYLE_PRI)
        remote_btn.clicked.connect(self._open_remote)
        lay.addWidget(remote_btn)

        fs_btn = QPushButton("FULLSCREEN  [F11]")
        _set_theme_icon(fs_btn, "maximize", "PRI")
        fs_btn.setIconSize(QSize(15, 15))
        fs_btn.setFixedHeight(28)
        fs_btn.setFont(QFont(FONT_MAIN, 8))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(_BTN_STYLE_DIM)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(fs_btn)

        sc_btn = QPushButton("⊞  CREATE DESKTOP SHORTCUT")
        sc_btn.setFixedHeight(28)
        sc_btn.setFont(QFont(FONT_MAIN, 8))
        sc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sc_btn.setStyleSheet(_BTN_STYLE_DIM)
        sc_btn.clicked.connect(self._create_desktop_shortcut)
        lay.addWidget(sc_btn)

        self._autostart_btn = QPushButton("◉  AUTO-START: OFF")
        self._autostart_btn.setFixedHeight(28)
        self._autostart_btn.setFont(QFont(FONT_MAIN, 8))
        self._autostart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._autostart_btn.clicked.connect(self._toggle_autostart)
        lay.addWidget(self._autostart_btn)

        cust_btn = QPushButton("PREFERENCES & THEME")
        _set_theme_icon(cust_btn, "settings", "PRI")
        cust_btn.setIconSize(QSize(15, 15))
        cust_btn.setFixedHeight(28)
        cust_btn.setFont(QFont(FONT_MAIN, 8))
        cust_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cust_btn.setStyleSheet(_BTN_STYLE_DIM)
        cust_btn.clicked.connect(self._open_customize)
        lay.addWidget(cust_btn)

        self._motion_btn = QPushButton()
        self._motion_btn.setCheckable(True)
        self._motion_btn.setChecked(self._reduced_motion)
        self._motion_btn.setText(
            "REDUCED LOG ANIMATION: ON" if self._reduced_motion
            else "REDUCED LOG ANIMATION: OFF"
        )
        self._motion_btn.setFixedHeight(28)
        self._motion_btn.setFont(QFont(FONT_MAIN, 8))
        self._motion_btn.setStyleSheet(_BTN_STYLE_DIM)
        self._motion_btn.setToolTip("Reduce visual motion and show activity lines immediately")
        self._motion_btn.toggled.connect(self._toggle_reduced_motion)
        lay.addWidget(self._motion_btn)

        key_btn = QPushButton("API PROVIDERS")
        _set_theme_icon(key_btn, "key", "PRI")
        key_btn.setIconSize(QSize(15, 15))
        key_btn.setFixedHeight(32)
        key_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        key_btn.setStyleSheet(_BTN_STYLE_DIM)
        key_btn.clicked.connect(self._open_api_key_settings)
        lay.addWidget(key_btn)

        voice_hdr = QLabel("VOICE OUTPUT")
        voice_hdr.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        voice_hdr.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(voice_hdr)

        self._voice_female_btn = QPushButton("FEMALE VOICE")
        self._voice_female_btn.setFixedHeight(28)
        self._voice_female_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._voice_female_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._voice_female_btn.clicked.connect(lambda: self._request_voice_mode("female"))
        lay.addWidget(self._voice_female_btn)

        self._voice_male_btn = QPushButton("MALE VOICE")
        self._voice_male_btn.setFixedHeight(28)
        self._voice_male_btn.setFont(QFont(FONT_MAIN, 8, QFont.Weight.Bold))
        self._voice_male_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._voice_male_btn.clicked.connect(lambda: self._request_voice_mode("male"))
        lay.addWidget(self._voice_male_btn)
        self._update_voice_buttons(self._voice_mode)

        self._brief_btn = QPushButton()
        self._brief_btn.setFixedHeight(28)
        self._brief_btn.setFont(QFont(FONT_MAIN, 8))
        self._brief_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._brief_btn.clicked.connect(self._toggle_brief)
        lay.addWidget(self._brief_btn)

        plugin_btn = QPushButton("PLUGINS")
        _set_theme_icon(plugin_btn, "puzzle", "PRI")
        plugin_btn.setIconSize(QSize(15, 15))
        plugin_btn.setFixedHeight(28)
        plugin_btn.setFont(QFont(FONT_MAIN, 8))
        plugin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plugin_btn.setStyleSheet(_BTN_STYLE_DIM)
        plugin_btn.clicked.connect(self._open_plugin_manager)
        lay.addWidget(plugin_btn)

        w.adjustSize()
        return w

    def _toggle_reduced_motion(self, enabled: bool) -> None:
        self._reduced_motion = bool(enabled)
        self._log.set_reduced_motion(self._reduced_motion)
        self.hud.reduced_motion = self._reduced_motion
        self._motion_btn.setText(
            "REDUCED LOG ANIMATION: ON" if enabled
            else "REDUCED LOG ANIMATION: OFF"
        )
        QSettings("EDITH", "EDITH").setValue("reduced_log_motion", enabled)

    def _request_voice_mode(self, mode: str):
        mode = (mode or "").strip().lower()
        if mode not in {"female", "male"}:
            return
        if not self.on_voice_mode_clicked:
            self._log.append_log("SYS: Voice control is not connected yet.")
            return
        self.on_voice_mode_clicked(mode)

    def set_voice_mode_display(self, mode: str):
        mode = (mode or "").strip().lower()
        if mode in {"female", "male"}:
            self._voice_mode = mode
            self._update_voice_buttons(mode)

    def _update_voice_buttons(self, mode: str):
        if not hasattr(self, "_voice_female_btn") or not self._voice_female_btn:
            return
        for name, btn in (("female", self._voice_female_btn), ("male", self._voice_male_btn)):
            active = name == mode
            btn.setText(f"{'●' if active else '○'}  {name.upper()} VOICE")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.PRI_GHO if active else 'transparent'};
                    color: {C.PRI if active else C.TEXT_MED};
                    border: 1px solid {C.PRI_DIM if active else C.BORDER};
                    border-radius: 5px; text-align: left; padding: 0 10px;
                    font-weight: 700;
                }}
                QPushButton:hover {{ border-color: {C.PRI}; }}
            """)

    def _open_api_key_settings(self):
        if self._api_key_overlay:
            self._api_key_overlay.hide()
        cw = self.centralWidget()
        ov = ApiProviderWorkspace(parent=cw)
        ov.voice_saved.connect(self._on_api_key_saved)
        ov.settings_saved.connect(self._on_api_provider_saved)
        width = min(ApiProviderWorkspace._OW, max(560, cw.width() - 24))
        height = min(ApiProviderWorkspace._OH, max(440, cw.height() - 24))
        ov.setGeometry(
            max(8, (cw.width() - width) // 2),
            max(8, (cw.height() - height) // 2),
            width, height,
        )
        ov.show()
        ov.raise_()
        self._api_key_overlay = ov

    def _on_api_key_saved(self):
        self._log.append_log("SYS: Voice API provider and key saved after a successful Live test.")
        if self.on_api_key_saved:
            self.on_api_key_saved()

    def _on_api_provider_saved(self):
        self._log.append_log("SYS: API provider settings saved after a successful connection test.")

    def _toggle_drawer(self, checked: bool):
        if checked:
            self._position_quick_drawer()
            self._quick_drawer.show()
            self._quick_drawer.raise_()
        else:
            self._quick_drawer.hide()

    def _position_quick_drawer(self):
        if not hasattr(self, '_quick_drawer'):
            return
        self._quick_drawer.setFixedWidth(230)
        self._quick_drawer.adjustSize()
        self._quick_drawer.setGeometry(14, 56, 230, self._quick_drawer.sizeHint().height())

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setAccessibleName("EDITH command input")
        self._input.setToolTip("Type a command or question. Ctrl+K focuses this field.")
        self._input.setPlaceholderText("Ask EDITH anything or type a command…")
        self._input.setFont(QFont(FONT_MAIN, 10))
        self._input.setFixedHeight(36)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.INPUT}; color: {C.TEXT};
                selection-background-color: {C.PRI_DIM};
                border: 1px solid {C.BORDER_B}; border-radius: 10px;
                padding: 5px 12px;
            }}
            QLineEdit:hover {{ border: 1px solid {C.PRI_DIM}; }}
            QLineEdit:focus {{ border: 2px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton()
        _set_theme_icon(send, "arrow-up", "PRI")
        send.setIconSize(QSize(17, 17))
        send.setFixedSize(36, 36)
        send.setFont(QFont(FONT_MAIN, 12, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.GLASS_CARD}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 10px;
            }}
            QPushButton:hover {{ background: {C.HOVER}; border: 1px solid {C.PRI}; }}
            QPushButton:pressed {{ background: {C.PRI_GHO}; }}
        """)
        send.setAccessibleName("Send command to EDITH")
        send.setToolTip("Send command (Enter)")
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _focus_command_input(self) -> None:
        self._input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._input.selectAll()

    def _build_content_panel(self) -> QWidget:
        """
        Collapsible panel below the HUD — shows search results, news, briefings.
        Hidden by default; appears when show_content() is called.
        """
        w = QWidget()
        w.setObjectName("ContentPanel")
        w.setStyleSheet(f"""
            QWidget#ContentPanel {{
                background: {C.GLASS};
                border-top: 1px solid {C.BORDER};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 10, 16, 12)
        lay.setSpacing(8)

        # ── header row ───────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(8)

        dot = QLabel("◈")
        dot.setFont(QFont(FONT_MAIN, 10, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._content_title_lbl = QLabel("BRIEFING")
        self._content_title_lbl.setFont(QFont(FONT_MAIN, 9, QFont.Weight.Bold))
        self._content_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;"
        )
        hdr.addWidget(self._content_title_lbl)
        hdr.addStretch()

        self._content_ts_lbl = QLabel("")
        self._content_ts_lbl.setFont(QFont(FONT_MONO, 8))
        self._content_ts_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._content_ts_lbl)

        dismiss = QPushButton("DISMISS")
        _set_theme_icon(dismiss, "x", "TEXT_DIM")
        dismiss.setIconSize(QSize(12, 12))
        dismiss.setFont(QFont(FONT_MAIN, 8))
        dismiss.setFixedHeight(22)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 0 8px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        dismiss.clicked.connect(w.hide)
        hdr.addWidget(dismiss)
        lay.addLayout(hdr)

        # ── separator ─────────────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); lay.addWidget(sep)

        # ── text display ──────────────────────────────────────────────────────
        self._content_display = QTextEdit()
        self._content_display.setReadOnly(True)
        self._content_display.setFont(QFont(FONT_MAIN, 10))
        self._content_display.setMinimumHeight(60)
        self._content_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_display.setStyleSheet(f"""
            QTextEdit {{
                background: {C.INPUT};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 11px;
                padding: 8px 10px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 3px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none;
            }}
        """)
        lay.addWidget(self._content_display)

        return w

    def _show_action_confirmation(self, title: str, details: str, state: dict):
        """Show a scrollable, default-cancel local approval dialog on the Qt UI thread."""
        if self._confirmation_busy:
            self._confirmation_queue.append((title, details, state))
            return
        self._confirmation_busy = True
        try:
            remaining = state.get("deadline", time.monotonic() + state.get("timeout", 180)) - time.monotonic()
            if remaining <= 0:
                return
            dialog = QDialog(self)
            dialog.setWindowTitle((title or "Confirm sensitive action")[:100])
            dialog.setModal(True)
            dialog.setMinimumSize(640, 460)
            dialog.resize(760, 560)
            dialog.setStyleSheet(f"""
                QDialog {{
                    background: {C.SHEET};
                    color: {C.TEXT};
                }}
                QLabel {{
                    color: {C.TEXT};
                    background: transparent;
                }}
                QTextEdit {{
                    background: {C.INPUT};
                    color: {C.TEXT};
                    border: 1px solid {C.BORDER_B};
                    border-radius: 12px;
                    padding: 10px;
                    selection-background-color: {C.PRI_GHO};
                }}
                QPushButton {{
                    min-height: 34px;
                    padding: 0 14px;
                    border-radius: 9px;
                    background: {C.GLASS_CARD};
                    color: {C.TEXT};
                    border: 1px solid {C.BORDER_B};
                }}
                QPushButton:hover {{ background: {C.HOVER}; border-color: {C.PRI_DIM}; }}
                QPushButton#confirmAction {{
                    background: {C.DANGER_BG};
                    border-color: {C.RED};
                    color: {C.RED};
                    font-weight: 600;
                }}
                QPushButton#confirmAction:hover {{ background: {C.DANGER_HOVER}; }}
            """)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(18, 18, 18, 16)
            layout.setSpacing(10)

            heading = QLabel("Review this action before it runs")
            heading.setFont(QFont(FONT_MAIN, 12, QFont.Weight.Bold))
            heading.setWordWrap(True)
            layout.addWidget(heading)

            preview = QTextEdit()
            preview.setReadOnly(True)
            preview.setAcceptRichText(False)
            preview.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            preview.setPlainText(
                (details or "Review the requested operation.")
                + "\n\nNothing will be changed unless you choose Confirm and Execute."
            )
            preview.setMinimumHeight(280)
            layout.addWidget(preview, stretch=1)

            buttons = QHBoxLayout()
            buttons.addStretch()
            cancel_btn = QPushButton("Cancel")
            cancel_btn.setDefault(True)
            confirm_btn = QPushButton("Confirm and Execute")
            confirm_btn.setObjectName("confirmAction")
            confirm_btn.setDefault(False)
            confirm_btn.setAutoDefault(False)
            cancel_btn.clicked.connect(dialog.reject)
            confirm_btn.clicked.connect(dialog.accept)
            buttons.addWidget(cancel_btn)
            buttons.addWidget(confirm_btn)
            layout.addLayout(buttons)

            confirm_btn.setProperty("role", "danger")
            timer = QTimer(dialog)
            timer.setSingleShot(True)
            timer.timeout.connect(dialog.reject)
            timer.start(max(1, int(remaining * 1000)))
            state["confirmed"] = int(dialog.exec()) == int(QDialog.DialogCode.Accepted)
            timer.stop()
        except Exception as exc:
            print(f"[Confirmation] Dialog unavailable: {type(exc).__name__}")
            state["confirmed"] = False
        finally:
            event = state.get("event")
            if event is not None:
                event.set()
            self._confirmation_busy = False
            if self._confirmation_queue:
                pending = self._confirmation_queue.pop(0)
                QTimer.singleShot(0, lambda: self._show_action_confirmation(*pending))

    def _show_content(self, title: str, text: str):
        """Slot — runs on Qt main thread. Updates and shows the content panel."""
        import time as _time
        self._content_title_lbl.setText(title.upper()[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setPlainText(text)
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start
        )
        first_show = not self._content_panel.isVisible()
        self._content_panel.show()
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 220, 120), 220])

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setObjectName("WorkspaceFooter")
        w.setFixedHeight(30)
        w.setStyleSheet(
            f"QWidget#WorkspaceFooter {{ background: {C.DARK}; "
            f"border-top: 1px solid {C.BORDER}; }}"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(10)

        def _fl(txt, color=C.TEXT_MED, weight=QFont.Weight.Normal):
            label = QLabel(txt)
            label.setFont(QFont(FONT_MAIN, 8, weight))
            label.setStyleSheet(f"color: {color}; background: transparent;")
            return label

        lay.addWidget(_fl("EDITH", C.PRI, QFont.Weight.Bold))
        lay.addWidget(_fl("F4  Mute   ·   F11  Fullscreen", C.TEXT_DIM))

        self._activity_lbl = _fl("INITIALISING", C.TEXT, QFont.Weight.DemiBold)
        self._activity_lbl.setAccessibleName("EDITH activity status")
        lay.addWidget(self._activity_lbl)
        lay.addStretch(1)

        self._mic_footer_bar = QProgressBar()
        self._mic_footer_bar.setRange(0, 100)
        self._mic_footer_bar.setValue(0)
        self._mic_footer_bar.setTextVisible(False)
        self._mic_footer_bar.setFixedSize(72, 6)
        self._mic_footer_bar.setStyleSheet(f"""
            QProgressBar {{ border: none; background: {C.PANEL2}; border-radius: 3px; }}
            QProgressBar::chunk {{ background: {C.GREEN}; border-radius: 3px; }}
        """)
        self._mic_footer_bar.setAccessibleName("Live microphone intensity meter")
        lay.addWidget(self._mic_footer_bar)

        self._mic_footer_lbl = _fl("MIC  WAITING", C.ACC2, QFont.Weight.DemiBold)
        self._mic_footer_lbl.setAccessibleName("Microphone capture status")
        self._mic_footer_lbl.setToolTip(
            "Shows captured audio intensity, not speech recognition or cloud delivery."
        )
        lay.addWidget(self._mic_footer_lbl)
        return w


    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        size = _fmt_size(p.stat().st_size)
        self._file_hint.setText(f"{p.name}  ·  {size}  ·  Tell {self._display_name} what to do with it")
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            try:
                self.on_text_command(msg)
            except Exception as exc:
                self._log.append_log(
                    f"ERR: Could not queue uploaded-file request ({type(exc).__name__})."
                )

    def notify_phone_connected(self) -> None:
        if self._remote_overlay and self._remote_overlay.isVisible():
            self._remote_overlay.mark_connected()

    def _open_remote(self):
        if not self.on_remote_clicked:
            self._log.append_log("SYS: Dashboard not running — remote unavailable.")
            return
        result = self.on_remote_clicked()
        if not result:
            self._log.append_log("SYS: Could not generate remote key.")
            return
        url    = result[0]
        key    = result[1]
        auto   = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        if self._remote_overlay:
            self._remote_overlay._do_close()
        cw  = self.centralWidget()
        ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
        ov  = RemoteKeyOverlay(url, key, auto_login_url=auto, manual_url=manual,
                               expiry_secs=600, parent=cw)
        ov.set_new_key_callback(self.on_remote_clicked)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.closed.connect(lambda: setattr(self, '_remote_overlay', None))
        ov.show()
        self._remote_overlay = ov
        self._log.append_log(f"SYS: Remote key generated — manual: {manual or url}")

    # ── Auto-start ──────────────────────────────────────────────────────────────

    def _migrate_legacy_autostart(self) -> None:
        """Rename only auto-start entries verified as belonging to this install.

        Do not delete an unrelated application merely because of its old name.
        EDITH continues to use the identical command when migrating an entry.
        """
        script = str(Path(__file__).resolve().parent / "main.py")
        try:
            if _OS == "Windows":
                import winreg
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_READ | winreg.KEY_SET_VALUE,
                ) as reg:
                    try:
                        command, _ = winreg.QueryValueEx(reg, "JARVIS_AI")
                    except FileNotFoundError:
                        return
                    if script.lower() not in str(command).lower():
                        return
                    try:
                        winreg.QueryValueEx(reg, "EDITH")
                    except FileNotFoundError:
                        winreg.SetValueEx(reg, "EDITH", 0, winreg.REG_SZ, command)
                    winreg.DeleteValue(reg, "JARVIS_AI")
            elif _OS == "Darwin":
                root = Path.home() / "Library" / "LaunchAgents"
                old = root / "com.jarvis.assistant.plist"
                new = root / "app.edith.assistant.plist"
                if old.is_file():
                    content = old.read_text(encoding="utf-8")
                    if script in content:
                        if not new.exists():
                            new.write_text(
                                content.replace("local.aiassistant.desktop", "app.edith.assistant"),
                                encoding="utf-8",
                            )
                        old.unlink()
            else:
                root = Path.home() / ".config" / "autostart"
                old = root / "jarvis.desktop"
                new = root / "edith.desktop"
                if old.is_file():
                    content = old.read_text(encoding="utf-8")
                    if script in content:
                        if not new.exists():
                            new.write_text(
                                content.replace("Name=JARVIS", "Name=EDITH")
                                       .replace("Name=Jarvis", "Name=EDITH"),
                                encoding="utf-8",
                            )
                        old.unlink()
        except OSError as exc:
            print(f"[EDITH] Auto-start migration skipped: {type(exc).__name__}")

    def _check_autostart(self) -> bool:
        """Report EDITH auto-start registration; legacy entries migrate above."""
        try:
            if _OS == "Windows":
                import winreg
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_READ,
                ) as reg:
                    winreg.QueryValueEx(reg, "EDITH")
                    return True
            if _OS == "Darwin":
                return (Path.home() / "Library" / "LaunchAgents"
                        / "app.edith.assistant.plist").exists()
            return (Path.home() / ".config" / "autostart" / "edith.desktop").exists()
        except (FileNotFoundError, OSError):
            return False

    def _toggle_autostart(self):
        currently_on = self._check_autostart()
        try:
            script = str(Path(__file__).resolve().parent / "main.py")
            if _OS == "Windows":
                import winreg
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_READ | winreg.KEY_SET_VALUE,
                ) as reg:
                    if currently_on:
                        winreg.DeleteValue(reg, "EDITH")
                    else:
                        pythonw = Path(sys.executable).parent / "pythonw.exe"
                        exe = str(pythonw if pythonw.exists() else sys.executable)
                        winreg.SetValueEx(
                            reg, "EDITH", 0, winreg.REG_SZ,
                            f'"{exe}" "{script}"',
                        )
            elif _OS == "Darwin":
                plist_dir = Path.home() / "Library" / "LaunchAgents"
                plist_dir.mkdir(parents=True, exist_ok=True)
                plist = plist_dir / "app.edith.assistant.plist"
                if currently_on:
                    plist.unlink(missing_ok=True)
                else:
                    plist.write_text(
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict>\n'
                        '  <key>Label</key><string>app.edith.assistant</string>\n'
                        '  <key>ProgramArguments</key><array>\n'
                        f'    <string>{sys.executable}</string>\n'
                        f'    <string>{script}</string>\n'
                        '  </array>\n'
                        '  <key>RunAtLoad</key><true/>\n'
                        '</dict></plist>\n',
                        encoding="utf-8",
                    )
            else:
                desk_dir = Path.home() / ".config" / "autostart"
                desk_dir.mkdir(parents=True, exist_ok=True)
                desk = desk_dir / "edith.desktop"
                if currently_on:
                    desk.unlink(missing_ok=True)
                else:
                    desk.write_text(
                        "[Desktop Entry]\n"
                        "Name=EDITH\n"
                        f"Exec={sys.executable} {script}\n"
                        "Type=Application\nTerminal=false\n"
                        "X-GNOME-Autostart-enabled=true\n",
                        encoding="utf-8",
                    )
            self._update_autostart_btn(not currently_on)
            self._log.append_log(
                f"SYS: EDITH auto-start {'disabled' if currently_on else 'enabled'}."
            )
        except Exception as exc:
            self._log.append_log(f"ERR: Auto-start failed — {type(exc).__name__}: {exc}")

    def _update_autostart_btn(self, enabled: bool):
        if not hasattr(self, '_autostart_btn'):
            return
        if enabled:
            self._autostart_btn.setText("◉  AUTO-START: ON")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.SUCCESS_BG}; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 8px;
                }}
                QPushButton:hover {{ background: {C.SUCCESS_HOVER}; }}
            """)
        else:
            self._autostart_btn.setText("◉  AUTO-START: OFF")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 4px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    def _toggle_brief(self):
        from memory.config_manager import get_brief_enabled, save_brief_enabled
        new_val = not get_brief_enabled()
        save_brief_enabled(new_val)
        self._update_brief_btn(new_val)

    def _update_brief_btn(self, enabled: bool):
        if not hasattr(self, '_brief_btn'):
            return
        if enabled:
            self._brief_btn.setText("MORNING BRIEF: ON")
            _set_theme_icon(self._brief_btn, "sun", "ACC2")
            self._brief_btn.setIconSize(QSize(15, 15))
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.SUCCESS_BG}; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 8px;
                    text-align: left; padding: 0 10px;
                }}
                QPushButton:hover {{ background: {C.SUCCESS_HOVER}; }}
            """)
        else:
            self._brief_btn.setText("MORNING BRIEF: OFF")
            _set_theme_icon(self._brief_btn, "sun", "TEXT_DIM")
            self._brief_btn.setIconSize(QSize(15, 15))
            self._brief_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 4px;
                    text-align: left; padding: 0 10px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    # ── Customization ────────────────────────────────────────────────────────────

    def _open_customize(self):
        cfg = _read_full_config()
        if self._customize_overlay and self._customize_overlay.isVisible():
            self._customize_overlay._cancel()
        cw = self.centralWidget()
        ov = CustomizeOverlay(
            self._display_name,
            cfg.get("user_name", ""),
            theme_preference=self._theme_preference,
            parent=cw,
        )
        ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
        oh = min(oh, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.on_theme_preview = self._preview_theme_preference
        ov.saved.connect(self._apply_name_update)
        ov.theme_saved.connect(self._save_theme_preference)
        ov.show()
        self._customize_overlay = ov

    def _apply_name_update(self, name: str, user_name: str):
        """Update identity fields without exposing manual accent controls."""
        self._assistant_name = "EDITH"
        self._display_name = UI_BRAND
        display = self._display_name
        self.setWindowTitle("EDITH • PERSONAL ASSISTANT")
        self._title_lbl.setText(UI_BRAND)
        self._sub_lbl.setText("PERSONAL ASSISTANT SYSTEM  •  VOICE  •  VISION")
        self._log._ai_name_lc = self._assistant_name.lower()
        self.hud._assistant_name = display
        try:
            data = _read_full_config()
            data["assistant_name"] = self._assistant_name
            data["user_name"] = user_name.strip()
            data.pop("ui_color", None)
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self._log.append_log(f"SYS: Identity updated — {display}")
        except Exception as exc:
            self._log.append_log(f"ERR: Config save failed — {type(exc).__name__}")

    def _ensure_embedded_browser(self):
        from core.embedded_browser import EmbeddedBrowserDialog
        if self._embedded_browser_dialog is None:
            self._embedded_browser_dialog = EmbeddedBrowserDialog(self)
        return self._embedded_browser_dialog

    def _open_embedded_browser(self, url: str = "about:blank"):
        """Open or reuse EDITH's persistent embedded browser window."""
        try:
            self._ensure_embedded_browser().navigate(url)
        except Exception as exc:
            self._log.append_log(
                f"ERR: Embedded browser unavailable ({type(exc).__name__}). "
                "Install PyQt6-WebEngine and restart EDITH."
            )

    def _execute_embedded_browser_action(self, request: dict):
        """Qt-thread slot; always releases the worker waiting on its result."""
        state = request.get("state") if isinstance(request, dict) else None
        if not isinstance(state, dict):
            return
        def finish(value):
            state["result"] = value
            state["event"].set()
        try:
            dialog = self._ensure_embedded_browser()
            dialog.execute_action(
                str(request.get("action") or ""),
                request.get("arguments") if isinstance(request.get("arguments"), dict) else {},
                finish,
            )
        except Exception as exc:
            finish({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"})

    def _open_plugin_manager(self):
        plugins = self.get_plugins() if self.get_plugins else []
        cw = self.centralWidget()
        ov = PluginManagerOverlay(plugins, parent=cw)
        ov.adjustSize()
        ov.setGeometry(
            (cw.width()  - ov.width())  // 2,
            (cw.height() - ov.height()) // 2,
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()
        self._plugin_manager_overlay = ov   # keep a reference so it isn't GC'd

    # ── Clipboard intelligence ───────────────────────────────────────────────────

    def _on_clipboard_changed(self):
        try:
            text = QApplication.clipboard().text().strip()
            if len(text) >= 10:
                self._clipboard_sig.emit(text)
        except Exception:
            pass

    def _show_clipboard_panel(self, text: str):
        self._clipboard_panel.show_clipboard(text)
        self._position_clipboard_panel()

    def _position_clipboard_panel(self):
        cw = self.centralWidget()
        pw = ClipboardPanel._W
        ph = self._clipboard_panel.sizeHint().height() or ClipboardPanel._H
        x = (cw.width() - pw) // 2
        y = cw.height() - ph - 8
        self._clipboard_panel.setGeometry(x, y, pw, ph)
        self._clipboard_panel.raise_()

    def _on_clipboard_action(self, cmd: str):
        if self.on_text_command:
            try:
                self.on_text_command(cmd)
            except Exception as exc:
                self._log.append_log(
                    f"ERR: Could not queue clipboard request ({type(exc).__name__})."
                )

    # ────────────────────────────────────────────────────────────────────────────

    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self.hud.clear_input_level()
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("MICROPHONE MUTED")
            _set_theme_icon(self._mute_btn, "mic-off", "MUTED_C")
            self._mute_btn.setIconSize(QSize(16, 16))
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.DANGER_BG}; color: {C.MUTED_C};
                    border: 1px solid {C.MUTED_C}; border-radius: 9px;
                }}
            """)
        else:
            self._mute_btn.setText("MICROPHONE ACTIVE")
            _set_theme_icon(self._mute_btn, "mic", "GREEN")
            self._mute_btn.setIconSize(QSize(16, 16))
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.SUCCESS_BG}; color: {C.GREEN};
                    border: 1px solid {C.GREEN}; border-radius: 9px;
                }}
                QPushButton:hover {{ background: {C.SUCCESS_HOVER}; }}
            """)

    def _restore_unsent_command(self, text: str) -> None:
        """Never overwrite a draft the user started after the failed send."""
        if not self._input.text().strip():
            self._input.setText(text)
            self._input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _send(self):
        txt = self._input.text().strip()
        if not txt:
            return
        if not self.on_text_command:
            self._log.append_log("NET: EDITH is not connected; command kept for retry.")
            return
        # The Live handler queues an asyncio coroutine thread-safely.
        # Keep the draft if the command cannot even be scheduled.
        try:
            accepted = self.on_text_command(txt)
        except Exception as exc:
            self._log.append_log(
                f"ERR: Could not queue text request ({type(exc).__name__})."
            )
            return
        if accepted is False:
            return
        self._input.clear()
        self._log.append_log(f"You: {txt}")

    def _on_mic_level(self, level: float, source: str) -> None:
        if not self._muted and not self.hud.speaking:
            self.hud.set_input_level(level, source)

    def _refresh_mic_status(self) -> None:
        """Keep the input status truthful when audio packets stop arriving."""
        if self._muted:
            label, color, level = "MIC  MUTED", C.MUTED_C, 0.0
        elif self.hud.speaking:
            label, color, level = "EDITH  SPEAKING", C.ACC, 0.0
        elif self.hud.state in {"LISTENING", "THINKING", "WORKING", "AWAITING APPROVAL"}:
            fresh = time.monotonic() - self.hud._mic_last_packet < 0.65
            if fresh:
                level = self.hud._mic_level
                label = (f"{self.hud._mic_source}  AUDIO INPUT"
                         if level > 0.11 else f"{self.hud._mic_source}  MIC READY")
                color = C.GREEN
            else:
                label, color, level = "MIC  NO AUDIO", C.ACC2, 0.0
        else:
            label, color, level = "MIC  STANDBY", C.TEXT_DIM, 0.0
        if self._mic_footer_lbl.text() != label:
            self._mic_footer_lbl.setText(label)
            self._mic_footer_lbl.setStyleSheet(
                f"color: {color}; background: transparent;"
            )
        value = max(0, min(100, int(level * 100)))
        if self._mic_footer_bar.value() != value:
            self._mic_footer_bar.setValue(value)

    def _apply_state(self, state: str):
        self._requested_state = state.upper()
        self._render_activity_state()

    def _on_playback_state(self, active: bool):
        self._playback_active = active
        if not active and self._requested_state == "SPEAKING":
            self._requested_state = "LISTENING"
        self._render_activity_state()

    def _render_activity_state(self):
        state = "SPEAKING" if self._playback_active else self._requested_state
        if self._running_tasks and state not in {"SPEAKING", "AWAITING APPROVAL"}:
            state = "WORKING"
        self.hud.state = state
        self.hud.speaking = (state == "SPEAKING")
        if self.hud.speaking or state in {"SLEEPING", "MUTED"}:
            self.hud.clear_input_level()
        if hasattr(self, '_activity_lbl'):
            self._activity_lbl.setText(state)
        self.hud.update()

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(get_gemini_api_key(API_FILE)) and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 390
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        from memory.config_manager import save_initial_setup
        try:
            save_initial_setup(key, os_name)
        except (OSError, ValueError, TypeError) as exc:
            self._log.append_log(
                f"ERR: EDITH setup could not safely save config ({type(exc).__name__}). "
                "Existing API and local LLM settings were not replaced."
            )
            return
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._assistant_name = "EDITH"
        self._display_name = UI_BRAND
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. {self._display_name} online.")

class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        return self._app.exec()
    def protocol(self, *_):
        pass


class EdithUI:
    def __init__(self, face_path: str, size=None):
        if platform.system() == "Windows":
            # Keep EDITH taskbar identity separate from generic pythonw.exe apps.
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "EDITH.PersonalAssistant.Desktop"
                )
            except (AttributeError, OSError):
                pass
        self._app = QApplication.instance() or QApplication(sys.argv)
        from PyQt6.QtGui import QFontDatabase
        for script in (QFontDatabase.WritingSystem.Bengali,):
            if hasattr(QFontDatabase, "addApplicationFallbackFontFamily"):
                from PyQt6.QtCore import QChar
                for family in FONT_FALLBACKS[1:-1]:
                    QFontDatabase.addApplicationFallbackFontFamily(QChar.Script.Script_Bengali, family)
        self._app.setStyle("Fusion")
        self._app.setApplicationName("EDITH")
        self._app.setWindowIcon(svg_icon("edith-app", C.PRI))
        self._closed = threading.Event()
        self._win = MainWindow(face_path)
        # The Live/audio thread can outlive the QWidget during Qt shutdown.
        # Mark both normal app exit and direct QWidget destruction.
        self._app.aboutToQuit.connect(self._mark_closed)
        self._win.destroyed.connect(self._mark_closed)
        self._win.show()
        self.root = _RootShim(self._app)

    def _mark_closed(self, *_args) -> None:
        """Prevent background callbacks from addressing destroyed Qt objects."""
        self._closed.set()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def _emit_if_open(self, signal_name: str, *args) -> bool:
        """Safely publish from worker threads across a concurrent Qt teardown."""
        if self._closed.is_set():
            return False
        try:
            getattr(self._win, signal_name).emit(*args)
        except RuntimeError as exc:
            # A QWidget may be deleted after the check, before signal.emit().
            if "wrapped C/C++ object" in str(exc) and "deleted" in str(exc):
                self._closed.set()
                return False
            raise
        return True

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_remote_clicked(self):
        return self._win.on_remote_clicked

    @on_remote_clicked.setter
    def on_remote_clicked(self, cb):
        self._win.on_remote_clicked = cb

    @property
    def on_interrupt(self):
        return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb):
        self._win.on_interrupt = cb

    @property
    def get_plugins(self):
        return self._win.get_plugins

    @get_plugins.setter
    def get_plugins(self, cb):
        self._win.get_plugins = cb

    def notify_phone_connected(self) -> None:
        self._win.notify_phone_connected()

    def set_state(self, state: str):
        self._emit_if_open("_state_sig", state)

    def show_input_level(self, level: float, source: str = "PC") -> None:
        """Display captured input intensity; safe to call from audio threads."""
        self._emit_if_open("_mic_level_sig", level, source)

    def show_playback_state(self, active: bool) -> None:
        self._emit_if_open("_playback_sig", active)

    def show_output_level(self, level: float) -> None:
        self._emit_if_open("_output_level_sig", level)

    def write_log(self, text: str):
        self._emit_if_open("_log_sig", text)

    def wait_for_api_key(self) -> bool:
        while not self.closed:
            if self._win._ready:
                return True
            time.sleep(0.1)
        return False

    def show_content(self, title: str, text: str):
        """Thread-safe: display content in the panel below the HUD."""
        self._emit_if_open("_content_sig", title[:48], text[:4000])

    def open_embedded_browser(self, url: str = "about:blank") -> None:
        """Thread-safe request to open EDITH's embedded browser."""
        self._emit_if_open("browser_open_signal", str(url or "about:blank"))

    def execute_embedded_browser_action(
        self, action: str, arguments: dict | None = None, timeout: float = 15.0
    ):
        """Execute one embedded-browser action on Qt's thread and return its receipt."""
        state = {"event": threading.Event(), "result": None}
        request = {
            "action": str(action or ""),
            "arguments": dict(arguments or {}),
            "state": state,
        }
        if not self._emit_if_open("browser_action_signal", request):
            return {"ok": False, "error": "Embedded browser UI is closed"}
        if not state["event"].wait(max(1.0, min(float(timeout), 30.0))):
            return {"ok": False, "error": "Embedded browser action timed out"}
        return state.get("result")

    def confirm_sensitive_action(self, title: str, details: str, timeout: float = 180.0) -> bool:
        """Ask the user through the Qt GUI; timeout/cancellation never authorizes the action."""
        state = {"event": threading.Event(), "confirmed": False, "timeout": timeout, "deadline": time.monotonic() + timeout}
        self._win._confirm_action_sig.emit(
            str(title or "")[:100], str(details or ""), state
        )
        if not state["event"].wait(max(1.0, float(timeout))):
            self.write_log("ACTIVITY CANCELLED: confirmation timed out; no action was executed.")
            return False
        return bool(state.get("confirmed", False))

    def prompt_reconfig(self):
        """Thread-safe: show the API key setup overlay (e.g. after an auth error)."""
        if self.closed:
            return
        self._win._ready = False
        self._emit_if_open("_reconfig_sig")

    def show_camera_frame(self, img_bytes: bytes):
        """Thread-safe: show a webcam frame in the small overlay (screen captures)."""
        self._emit_if_open("_camera_sig", img_bytes)

    def start_camera_stream(self) -> None:
        """Thread-safe: start live camera feed in the full HUD area."""
        self._win.start_camera_stream()

    def stop_camera_stream(self) -> None:
        """Thread-safe: stop the live camera feed."""
        self._win.stop_camera_stream()

    @property
    def assistant_name(self) -> str:
        return self._win._assistant_name

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")

