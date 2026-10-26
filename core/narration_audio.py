"""Lossless PCM narration buffering and a dedicated blocking PortAudio writer.

Microphone traffic can discard stale packets; generated speech must not do that.
All buffer operations are thread-safe, including an interrupt from the Qt thread.
"""
from collections import deque
import queue
import threading
import time

from core.audio_meter import pcm16_level

SAMPLE_RATE = 24000
BYTES_PER_SECOND = SAMPLE_RATE * 2  # mono PCM16
WRITE_BYTES = BYTES_PER_SECOND // 20  # 50 ms, never a whole narration in one write
PREFILL_BYTES = BYTES_PER_SECOND * 150 // 1000
MAX_PREFILL_BYTES = BYTES_PER_SECOND * 500 // 1000


class PlaybackReset(Exception):
    pass


class SpeechBuffer:
    """FIFO with a byte budget; overflow is explicit, never drop-oldest."""
    def __init__(self, max_bytes=BYTES_PER_SECOND * 300):
        self.max_bytes = max_bytes
        self._parts = deque()
        self._size = 0
        self._epoch = 0
        self._finished = True
        self._closed = False
        self._condition = threading.Condition()

    @property
    def epoch(self):
        with self._condition:
            return self._epoch

    @property
    def pending_bytes(self):
        with self._condition:
            return self._size

    @property
    def finished(self):
        with self._condition:
            return self._finished

    def empty(self):
        return self.pending_bytes == 0

    def put_nowait(self, data):
        data = bytes(data)
        if not data:
            return
        with self._condition:
            if self._closed:
                raise RuntimeError('Narration buffer is closed')
            if self._size + len(data) > self.max_bytes:
                raise BufferError('Narration exceeded its audio buffer budget; no speech was silently skipped')
            self._parts.append(data)
            self._size += len(data)
            self._finished = False
            self._condition.notify_all()

    def finish_turn(self):
        with self._condition:
            if self._size % 2:
                raise ValueError('Incomplete PCM16 sample at the end of a narration')
            self._finished = True
            self._condition.notify_all()

    def clear(self):
        with self._condition:
            self._parts.clear()
            self._size = 0
            self._finished = True
            self._epoch += 1
            self._condition.notify_all()

    def close(self):
        with self._condition:
            self._closed = True
            self.clear()

    def read(self, epoch, *, prefill=False, prefill_bytes=None, timeout=.1):
        """Read one PCM chunk without losing packet order.

        ``prefill_bytes`` lets the writer temporarily absorb more network
        jitter after a real output underrun.  Finished short responses still
        drain immediately so the final words are never held back.
        """
        threshold = (max(WRITE_BYTES, int(prefill_bytes))
                     if prefill and prefill_bytes is not None else
                     PREFILL_BYTES if prefill else WRITE_BYTES)
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                if self._closed:
                    raise EOFError()
                if epoch != self._epoch:
                    raise PlaybackReset()
                if self._size >= threshold or (self._finished and self._size):
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return b''
                self._condition.wait(remaining)
            count = min(WRITE_BYTES, self._size // 2 * 2)
            result = bytearray()
            while count:
                part = self._parts.popleft()
                take = min(count, len(part))
                result.extend(part[:take])
                if take < len(part):
                    self._parts.appendleft(part[take:])
                self._size -= take
                count -= take
            return bytes(result)


class SpeechPlayer:
    """One audio writer thread, independent of model/tool/GUI scheduling."""
    def __init__(self, buffer, stream_factory, *, retry_seconds=5):
        self.buffer = buffer
        self.stream_factory = stream_factory
        self.retry_seconds = retry_seconds
        self.stopping = threading.Event()
        self.stopped = threading.Event()
        self.events = queue.Queue(maxsize=32)
        self._lock = threading.Lock()
        self._state = {
            'ready': False, 'playing': False, 'level': 0., 'underflows': 0,
            'prefill_bytes': PREFILL_BYTES,
        }
        self._thread = threading.Thread(target=self._run, daemon=True, name='edith-speech-output')

    def snapshot(self):
        with self._lock:
            return dict(self._state)

    def _update(self, **values):
        with self._lock:
            self._state.update(values)

    def _event(self, message):
        try:
            self.events.put_nowait(message)
        except queue.Full:
            pass  # Only diagnostics are bounded/dropped; never PCM.

    def start(self):
        self._thread.start()

    def stop(self):
        self.stopping.set()
        self.buffer.close()

    def _run(self):
        unavailable = False
        try:
            while not self.stopping.is_set():
                stream = None
                started = False
                try:
                    stream = self.stream_factory(samplerate=SAMPLE_RATE, channels=1,
                                                 dtype='int16', blocksize=0, latency='high')
                    if unavailable:
                        self.buffer.clear()  # Do not replay old speech after device recovery.
                        self._event('AUDIO: Speaker available again; stale output was not replayed.')
                    unavailable = False
                    self._update(ready=True)
                    epoch = self.buffer.epoch
                    prefill = True
                    prefill_bytes = PREFILL_BYTES
                    self._update(prefill_bytes=prefill_bytes)
                    buffering = False
                    while not self.stopping.is_set():
                        try:
                            chunk = self.buffer.read(
                                epoch, prefill=prefill, prefill_bytes=prefill_bytes
                            )
                        except PlaybackReset:
                            epoch = self.buffer.epoch
                            if started:
                                stream.abort()
                            started = False
                            prefill = True
                            self._update(playing=False, level=0.)
                            continue
                        if not chunk:
                            if self.buffer.finished and self.buffer.empty():
                                if started:
                                    stream.stop()  # Drain the final hardware buffer before opening the mic.
                                started = False
                                prefill = True
                                self._update(playing=False, level=0.)
                            elif started:
                                prefill = True
                                if not buffering:
                                    self._event('AUDIO: Buffering narration; speech is retained in order.')
                                    buffering = True
                            continue
                        if epoch != self.buffer.epoch:
                            continue
                        if not started:
                            # Gate the microphone before the hardware stream
                            # starts, so its first speaker packet cannot be
                            # sent back as a new Live input/interruption.
                            self._update(playing=True, level=pcm16_level(chunk))
                            stream.start()
                            started = True
                        else:
                            self._update(level=pcm16_level(chunk))
                        underflow = stream.write(chunk)
                        buffering = False
                        prefill = bool(underflow)
                        if underflow:
                            count = self.snapshot()['underflows'] + 1
                            prefill_bytes = min(MAX_PREFILL_BYTES, prefill_bytes + WRITE_BYTES)
                            self._update(underflows=count, prefill_bytes=prefill_bytes)
                            if count == 1 or count % 20 == 0:
                                self._event(
                                    f'AUDIO: Output underrun detected ({count}); '
                                    f'increasing prebuffer to {round(prefill_bytes / BYTES_PER_SECOND * 1000)} ms, '
                                    'no chunk replay.'
                                )
                except EOFError:
                    break
                except Exception as exc:
                    self._update(ready=False, playing=False, level=0.)
                    self.buffer.clear()
                    if not unavailable:
                        self._event(f'AUDIO: Speaker unavailable ({type(exc).__name__}); text and remote controls remain available; retrying.')
                    unavailable = True
                finally:
                    self._update(ready=False, playing=False, level=0.)
                    if stream is not None:
                        try:
                            if started:
                                stream.abort()
                        except Exception:
                            pass
                        try:
                            stream.close()
                        except Exception:
                            pass
                if unavailable:
                    self.stopping.wait(self.retry_seconds)
        finally:
            self.stopped.set()

