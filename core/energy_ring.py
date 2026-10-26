"""Procedural violet particle ring. Deterministic loop, no media or GPU required."""
from __future__ import annotations

import math
from functools import lru_cache
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QImage, QPainterPath, QPen, QRadialGradient, QPolygonF

TAU = math.tau
LOOP_SECONDS = 8.0
FRAME_COUNT = 32
FRAME_SIZE = 320


def ring_points(phase: float, radius: float, band: int = 0, count: int = 128):
    """Periodic ribbons with a stable seam, also used by the particle field."""
    points = []
    for i in range(count + 1):
        angle = i * TAU / count
        wave = .035 * math.sin(3 * angle + phase) + .018 * math.sin(7 * angle - phase * 2)
        twist = math.sin(angle * 2 - phase + band * .16)
        r = radius * (1 + wave + band * .009 + twist * .012)
        points.append((math.cos(angle) * r,
                       math.sin(angle) * r * (.97 + .025 * math.cos(phase)), twist))
    return points


def _render_ring(painter, rect, phase, input_level=0.0, speaking=False, muted=False):
    """Draw only the visual; audio capture and permission states live in the caller."""
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing)
    painter.fillRect(rect, QColor('#05030D'))
    width, height = rect.width(), rect.height()
    center = QPointF(rect.center().x(), rect.top() + height / 2)
    radius = max(12., min(width * .28, height * .36))
    energy = min(1., max(0., input_level))
    radius *= 1 + energy * .055
    intensity = .45 if muted else 1.0
    glow = QRadialGradient(center, radius * 1.6)
    glow.setColorAt(0, QColor(13, 5, 36, 0))
    glow.setColorAt(.43, QColor(40, 10, 110, int(30 * intensity)))
    glow.setColorAt(.65, QColor(88, 25, 220, int((135 + 30 * energy) * intensity)))
    glow.setColorAt(1, QColor(6, 2, 18, 0))
    painter.fillRect(rect, glow)
    painter.translate(center)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # Wide soft trails first, followed by thin woven strands.
    for band in (-12, -6, 0, 6, 12):
        path = QPainterPath()
        for index, (x, y, _) in enumerate(ring_points(phase, radius, band)):
            path.moveTo(x, y) if index == 0 else path.lineTo(x, y)
        painter.setPen(QPen(QColor(100, 50, 255, int(34 * intensity)), 12 + energy * 5))
        painter.drawPath(path)
    for band in range(-12, 13, 2):
        path = QPainterPath()
        for index, (x, y, _) in enumerate(ring_points(phase, radius, band)):
            path.moveTo(x, y) if index == 0 else path.lineTo(x, y)
        light = abs(band) / 12
        color = QColor(int(230 - 80 * light), int(210 - 140 * light), 255,
                       int((220 - 80 * light + energy * 30) * intensity))
        painter.setPen(QPen(color, .9 if band else 2.2))
        painter.drawPath(path)
    # Deterministic particles avoid flicker/random activity between audio packets.
    for band in range(-16, 17, 2):
        groups = [[], [], []]
        for index, (x, y, depth) in enumerate(ring_points(phase, radius, band, 100)):
            if index % 3 == 0:
                continue
            groups[min(2, int((depth + 1) * 1.5))].append(QPointF(x, y))
        for level, points in enumerate(groups):
            alpha = int((45 + level * 30) * intensity)
            painter.setPen(QPen(QColor(170, 130, 255, alpha), .8))
            painter.drawPoints(QPolygonF(points))
    painter.restore()


@lru_cache(maxsize=FRAME_COUNT)
def _frame(index):
    """At most 12.5 MiB of raster frames, shared between UI instances."""
    image = QImage(FRAME_SIZE, FRAME_SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor('#05030D'))
    painter = QPainter(image)
    try:
        _render_ring(painter, QRectF(0, 0, FRAME_SIZE, FRAME_SIZE),
                     (index % FRAME_COUNT) * TAU / FRAME_COUNT)
    finally:
        painter.end()
    return image


def draw_energy_ring(painter, rect, phase, input_level=0.0, speaking=False, muted=False):
    """Blend bounded cached frames; avoid recomputing every particle at 30 FPS."""
    position = (phase % TAU) / TAU * FRAME_COUNT
    index = int(position)
    fraction = position - index
    side = min(rect.width(), rect.height())
    scale = 1 + max(0., min(1., input_level)) * .055
    if speaking:
        scale += .01 * math.sin(phase * 4)
    side *= scale
    destination = QRectF(rect.center().x()-side/2, rect.center().y()-side/2, side, side)
    painter.save()
    painter.fillRect(rect, QColor('#05030D'))
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setOpacity(.45 if muted else 1.0)
    painter.drawImage(destination, _frame(index))
    if fraction > .001:
        painter.setOpacity(fraction * (.45 if muted else 1.0))
        painter.drawImage(destination, _frame((index+1) % FRAME_COUNT))
    painter.restore()
