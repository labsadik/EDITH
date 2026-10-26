"""Math and rendering contracts for the seamless, bounded visual animation."""
import math
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class EnergyRingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from core import energy_ring
        except ImportError as exc:
            if os.environ.get('CI') == 'true':
                raise
            raise unittest.SkipTest(str(exc))
        cls.ring = energy_ring

    def test_full_cycle_matches_start_and_seam_is_closed(self):
        first = self.ring.ring_points(0, 100, 4)
        last = self.ring.ring_points(math.tau, 100, 4)
        for start, end in zip(first, last):
            for a, b in zip(start, end):
                self.assertAlmostEqual(a, b, places=8)
        for a, b in zip(first[0], first[-1]):
            self.assertAlmostEqual(a, b, places=8)

    def test_cached_render_changes_through_cycle_and_is_bounded(self):
        from PyQt6.QtGui import QImage, QPainter
        from PyQt6.QtCore import QRectF
        ring = self.ring
        frames = []
        for phase in [0, math.pi / 3, math.tau]:
            image = QImage(400, 240, QImage.Format.Format_ARGB32_Premultiplied)
            painter = QPainter(image)
            ring.draw_energy_ring(painter, QRectF(0, 0, 400, 240), phase)
            painter.end()
            frames.append(image)
        self.assertNotEqual(frames[0], frames[1])
        self.assertEqual(frames[0], frames[2])
        for index in range(ring.FRAME_COUNT * 2):
            ring._frame(index % ring.FRAME_COUNT)
        self.assertLessEqual(ring._frame.cache_info().currsize, ring.FRAME_COUNT)
