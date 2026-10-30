"""Tests for the first-run modal backdrop."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QGraphicsBlurEffect, QWidget

from core.modal_backdrop import ModalBackdrop


class ModalBackdropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_backdrop_covers_parent_and_blurs_captured_background(self):
        parent = QWidget()
        parent.resize(800, 600)
        parent.show()
        self.app.processEvents()

        backdrop = ModalBackdrop(parent, blur_radius=24)
        self.assertEqual(backdrop.geometry(), parent.rect())
        self.assertIsInstance(backdrop._image.graphicsEffect(), QGraphicsBlurEffect)
        self.assertEqual(backdrop._image.graphicsEffect().blurRadius(), 24)
        self.assertTrue(backdrop._snapshot.isNull() is False)

        backdrop.show()
        self.app.processEvents()
        backdrop.resize(640, 480)
        self.app.processEvents()
        self.assertEqual(backdrop._image.geometry(), backdrop.rect())
        self.assertEqual(backdrop._scrim.geometry(), backdrop.rect())

        backdrop.close()
        parent.close()


if __name__ == "__main__":
    unittest.main()
