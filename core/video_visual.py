"""Silent local looping video with soft edges; independent of agent/audio state."""
from PyQt6.QtCore import QObject, QUrl, Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QImage, QColor, QLinearGradient, QPainter


class LoopingVideo(QObject):
    frame_ready = pyqtSignal()

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.frame = QImage()
        self.player = None
        self.error = ''
        self.active = False
        self.reduced = False
        try:
            if not path.is_file():
                raise FileNotFoundError('Bundled animation is missing')
            from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink
            self.player = QMediaPlayer(self)
            self.sink = QVideoSink(self)
            self.player.setVideoSink(self.sink)
            # No QAudioOutput is attached. The bundled file has no audio track.
            self.player.setLoops(QMediaPlayer.Loops.Infinite)
            self.sink.videoFrameChanged.connect(self._receive_frame)
            self.player.errorOccurred.connect(self._error)
            self.player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        except (ImportError, OSError, RuntimeError) as exc:
            self.error = str(exc)

    def _error(self, *args):
        self.error = self.player.errorString() or 'Video could not be decoded'
        self.frame_ready.emit()

    def _receive_frame(self, frame):
        image = frame.toImage()
        if not image.isNull():
            self.frame = image
            self.frame_ready.emit()
            if self.reduced or not self.active:
                self.player.pause()

    def sync(self, active, reduced=False):
        changed = (active, reduced) != (self.active, self.reduced)
        self.active, self.reduced = active, reduced
        if not self.player or self.error:
            return
        if not active or (reduced and not self.frame.isNull()):
            self.player.pause()
        elif changed:
            self.player.play()


def draw_blended_video(painter, area, image, background):
    """Keep aspect ratio, then fade each video edge into the surrounding surface."""
    color = QColor(background)
    painter.fillRect(area, color)
    if image.isNull():
        return
    size = image.size().scaled(int(area.width()), int(area.height()), Qt.AspectRatioMode.KeepAspectRatio)
    target = QRectF(area.center().x()-size.width()/2, area.center().y()-size.height()/2,
                    size.width(), size.height())
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(target, image)
    fade = min(target.width(), target.height()) * .13
    transparent = QColor(color)
    transparent.setAlpha(0)
    gradients = [
        (QRectF(target.left(), target.top(), fade, target.height()), target.left(), 0, target.left()+fade, 0),
        (QRectF(target.right()-fade, target.top(), fade, target.height()), target.right(), 0, target.right()-fade, 0),
        (QRectF(target.left(), target.top(), target.width(), fade), 0, target.top(), 0, target.top()+fade),
        (QRectF(target.left(), target.bottom()-fade, target.width(), fade), 0, target.bottom(), 0, target.bottom()-fade),
    ]
    for rect, x1, y1, x2, y2 in gradients:
        gradient = QLinearGradient(x1, y1, x2, y2)
        gradient.setColorAt(0, color)
        gradient.setColorAt(1, transparent)
        painter.fillRect(rect, gradient)
    painter.restore()
