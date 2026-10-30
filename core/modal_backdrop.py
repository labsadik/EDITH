"""Focused modal backdrop for first-run setup.

The background is captured once, blurred as a lightweight Qt widget, and
covered by a dark scrim. Mouse and keyboard events cannot reach the window
behind the modal.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsBlurEffect, QLabel, QWidget


class ModalBackdrop(QWidget):
    """Blur and dim a parent's current contents while a modal child is open."""

    def __init__(
        self,
        parent: QWidget,
        *,
        blur_radius: float = 20.0,
        tint: str = "rgba(4, 7, 14, 188)",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EdithModalBackdrop")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Capture before the backdrop is shown; the image is independent of
        # later repainting and avoids applying a graphics effect to the dialog.
        self._snapshot = parent.grab()
        self._image = QLabel(self)
        self._image.setObjectName("EdithModalBackdropImage")
        self._image.setPixmap(self._snapshot)
        self._image.setScaledContents(True)
        self._image.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._blur = QGraphicsBlurEffect(self._image)
        self._blur.setBlurRadius(max(0.0, float(blur_radius)))
        self._blur.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        self._image.setGraphicsEffect(self._blur)

        self._scrim = QWidget(self)
        self._scrim.setObjectName("EdithModalBackdropScrim")
        self._scrim.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._scrim.setStyleSheet(f"background-color: {tint};")

        # Set the size only after the child layers exist: QWidget may deliver
        # resizeEvent synchronously from setGeometry().
        self.setGeometry(parent.rect())
        self._layout_layers()

    def _layout_layers(self) -> None:
        image = getattr(self, "_image", None)
        scrim = getattr(self, "_scrim", None)
        if image is None or scrim is None:
            return
        rect = self.rect()
        image.setGeometry(rect)
        scrim.setGeometry(rect)
        scrim.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._layout_layers()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt override
        event.accept()

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        # The setup sheet owns keyboard input. Do not let shortcuts or keys
        # fall through to the dashboard behind it.
        event.accept()
