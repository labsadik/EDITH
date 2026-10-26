"""Actual local media decoding plus offline blending and playback lifecycle gates."""
import os
import unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class VideoVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PyQt6.QtWidgets import QApplication
            from core.video_visual import LoopingVideo, draw_blended_video
        except ImportError as exc:
            if os.environ.get('CI') == 'true':
                raise
            raise unittest.SkipTest(str(exc))
        cls.app = QApplication.instance() or QApplication([])
        cls.Video = LoopingVideo
        cls.draw = staticmethod(draw_blended_video)
        cls.source = Path(__file__).resolve().parents[1] / 'assets/hud_reference.mp4'

    def test_bundled_video_decodes_loops_and_obeys_visibility_and_reduced_motion(self):
        from PyQt6.QtTest import QTest
        from PyQt6.QtMultimedia import QMediaPlayer
        visual = self.Video(self.source)
        self.assertIsNotNone(visual.player, visual.error)
        try:
            visual.sync(True)
            for _ in range(60):
                QTest.qWait(50)
                if not visual.frame.isNull() or visual.error: break
            self.assertEqual(visual.error, '')
            self.assertFalse(visual.frame.isNull())
            self.assertEqual(visual.frame.width(), 720)
            self.assertEqual(visual.player.loops(), QMediaPlayer.Loops.Infinite)
            self.assertIsNone(visual.player.audioOutput())
            # Decode at the end, then verify the player wraps into another cycle.
            visual.player.setPosition(max(0, visual.player.duration()-150))
            QTest.qWait(650)
            self.assertLess(visual.player.position(), 2000)
            visual.sync(False)
            QTest.qWait(100)
            self.assertEqual(visual.player.playbackState(), QMediaPlayer.PlaybackState.PausedState)
            visual.sync(True, True)
            self.assertEqual(visual.player.playbackState(), QMediaPlayer.PlaybackState.PausedState)
        finally:
            visual.player.stop()
            visual.deleteLater()
            self.app.processEvents()

    def test_missing_asset_does_not_crash_status_ui(self):
        visual = self.Video(self.source.with_name('missing-video.mp4'))
        self.assertIn('missing', visual.error.lower())
        visual.sync(True)
        visual.deleteLater()

    def test_video_edges_match_the_surrounding_background(self):
        from PyQt6.QtGui import QImage, QPainter, QColor
        from PyQt6.QtCore import QRectF
        image = QImage(100, 100, QImage.Format.Format_ARGB32)
        image.fill(QColor('white'))
        canvas = QImage(160, 100, QImage.Format.Format_ARGB32)
        painter = QPainter(canvas)
        self.draw(painter, QRectF(0, 0, 160, 100), image, '#070D17')
        painter.end()
        self.assertEqual(canvas.pixelColor(0, 50), QColor('#070D17'))
        self.assertGreater(canvas.pixelColor(80, 50).lightness(), 240)
        self.assertLess(canvas.pixelColor(31, 50).lightness(), 70)

    def test_only_video_stage_has_a_black_background_in_both_themes(self):
        import ui
        from PyQt6.QtGui import QColor
        for mode in ("dark", "light"):
            self.assertEqual(QColor(ui._THEME_DEFAULTS[mode]["VIDEO_BG"]), QColor("black"))
        self.assertNotEqual(ui._THEME_DEFAULTS["light"]["BG"], "#000000")

