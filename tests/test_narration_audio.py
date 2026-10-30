"""Narration must retain PCM exactly across bursts, jitter and tool execution."""
import asyncio
import threading
import time
import unittest
from types import SimpleNamespace

from core.narration_audio import (
    SpeechBuffer, SpeechPlayer, PlaybackReset, WRITE_BYTES, PREFILL_BYTES,
    MAX_PREFILL_BYTES,
)
from test_response_status import method


class SpeechBufferTests(unittest.TestCase):
    def test_long_burst_preserves_every_byte_including_odd_packet_boundaries(self):
        data = bytes(range(256)) * 2000  # 10.67 seconds; exceeded the old six-second queue.
        buffer = SpeechBuffer()
        for start in range(0, len(data), 1703):
            buffer.put_nowait(data[start:start + 1703])
        buffer.finish_turn()
        chunks = []
        while not buffer.empty():
            chunks.append(buffer.read(buffer.epoch, timeout=0))
        self.assertEqual(b''.join(chunks), data)
        self.assertTrue(all(len(chunk) % 2 == 0 and len(chunk) <= WRITE_BYTES for chunk in chunks))

    def test_prefill_waits_for_jitter_but_a_short_finished_tail_is_not_lost(self):
        buffer = SpeechBuffer()
        buffer.put_nowait(b'12' * 100)
        self.assertEqual(buffer.read(0, prefill=True, timeout=.001), b'')
        buffer.finish_turn()
        self.assertEqual(buffer.read(0, prefill=True, timeout=0), b'12' * 100)
        buffer.put_nowait(b'34' * (PREFILL_BYTES // 2))
        self.assertEqual(len(buffer.read(0, prefill=True, timeout=0)), WRITE_BYTES)

    def test_custom_prefill_only_delays_an_unfinished_jittery_turn(self):
        buffer = SpeechBuffer()
        tail = b'12' * 100
        buffer.put_nowait(tail)
        self.assertEqual(
            buffer.read(0, prefill=True, prefill_bytes=PREFILL_BYTES * 2, timeout=.001), b''
        )
        buffer.finish_turn()
        self.assertEqual(
            buffer.read(0, prefill=True, prefill_bytes=MAX_PREFILL_BYTES, timeout=0),
            tail,
        )

    def test_overflow_is_explicit_and_does_not_replace_earlier_words(self):
        buffer = SpeechBuffer(max_bytes=8)
        buffer.put_nowait(b'original')
        with self.assertRaises(BufferError):
            buffer.put_nowait(b'new words')
        buffer.finish_turn()
        self.assertEqual(buffer.read(0), b'original')

    def test_interrupt_invalidates_old_reader_and_new_turn_can_play(self):
        buffer = SpeechBuffer()
        buffer.put_nowait(b'old speech')
        buffer.clear()
        with self.assertRaises(PlaybackReset):
            buffer.read(0)
        buffer.put_nowait(b'new speech')
        buffer.finish_turn()
        self.assertEqual(buffer.read(1), b'new speech')
        buffer.close()
        with self.assertRaises(EOFError):
            buffer.read(1)
        with self.assertRaises(RuntimeError):
            buffer.put_nowait(b'12')

    def test_incomplete_final_sample_reports_bad_pcm(self):
        buffer = SpeechBuffer()
        buffer.put_nowait(b'1')
        with self.assertRaises(ValueError):
            buffer.finish_turn()


class FakeStream:
    def __init__(self, *, underflow=False):
        self.written = []
        self.underflow = underflow
        self.drained = threading.Event()
        self.closed = threading.Event()
        self.aborted = threading.Event()

    def start(self): pass
    def write(self, data):
        self.written.append(data)
        result, self.underflow = self.underflow, False
        return result
    def stop(self): self.drained.set()
    def abort(self): self.aborted.set()
    def close(self): self.closed.set()


class SpeechPlayerTests(unittest.TestCase):
    def run_player(self, buffer, stream, **kwargs):
        self.kwargs = None
        def factory(**options):
            self.kwargs = options
            return stream
        player = SpeechPlayer(buffer, factory, **kwargs)
        self.addCleanup(lambda: self.stop_player(player))
        player.start()
        return player

    @staticmethod
    def stop_player(player):
        player.stop()
        if not player.stopped.wait(1):
            raise AssertionError('Audio writer did not terminate')

    def test_driver_without_low_latency_mode_falls_back_to_default_without_losing_speech(self):
        data = b"fallback speech" * 1000
        buffer = SpeechBuffer()
        buffer.put_nowait(data)
        buffer.finish_turn()
        stream = FakeStream()
        calls = []
        def factory(**options):
            calls.append(dict(options))
            if "latency" in options:
                raise ValueError("low latency unsupported")
            return stream
        player = SpeechPlayer(buffer, factory, retry_seconds=.01)
        self.addCleanup(lambda: self.stop_player(player))
        player.start()
        self.assertTrue(stream.drained.wait(1))
        self.assertEqual(b"".join(stream.written), data)
        self.assertEqual(calls[0]["latency"], "low")
        self.assertNotIn("latency", calls[1])
        messages = []
        while not player.events.empty():
            messages.append(player.events.get_nowait())
        self.assertTrue(any("default buffer" in message for message in messages))

    def test_long_turn_and_underflow_never_skip_or_replay_pcm(self):
        data = bytes(range(256)) * 2000
        buffer = SpeechBuffer()
        buffer.put_nowait(data)
        buffer.finish_turn()
        stream = FakeStream(underflow=True)
        player = self.run_player(buffer, stream)
        self.assertTrue(stream.drained.wait(1))
        self.assertEqual(b''.join(stream.written), data)
        self.assertEqual(player.snapshot()['underflows'], 1)
        self.assertGreater(player.snapshot()['prefill_bytes'], PREFILL_BYTES)
        self.assertEqual(self.kwargs['samplerate'], 24000)
        self.assertEqual(self.kwargs['blocksize'], 0)
        self.assertEqual(self.kwargs['latency'], 'low')
        self.assertEqual(PREFILL_BYTES, 2880)  # 60 ms at 24 kHz mono PCM16
        self.assertEqual(MAX_PREFILL_BYTES, 14400)  # 300 ms hard ceiling

    def test_jitter_keeps_pending_tail_and_playback_state_until_turn_finishes(self):
        buffer = SpeechBuffer()
        stream = FakeStream()
        player = self.run_player(buffer, stream)
        first = b'12' * (PREFILL_BYTES // 2)
        buffer.put_nowait(first)
        deadline = time.monotonic() + 1
        while len(stream.written) < 3 and time.monotonic() < deadline:
            time.sleep(.005)
        # The producer pauses for longer than the normal write period.
        time.sleep(.12)
        self.assertTrue(player.snapshot()['playing'])
        tail = b'34' * 35
        buffer.put_nowait(tail)
        buffer.finish_turn()
        self.assertTrue(stream.drained.wait(1))
        self.assertEqual(b''.join(stream.written), first + tail)

    def test_interrupt_aborts_native_buffer_and_discards_only_cancelled_turn(self):
        buffer = SpeechBuffer()
        stream = FakeStream()
        player = self.run_player(buffer, stream)
        buffer.put_nowait(b'12' * (PREFILL_BYTES // 2))
        deadline = time.monotonic() + 1
        while not stream.written and time.monotonic() < deadline:
            time.sleep(.005)
        buffer.clear()
        self.assertTrue(stream.aborted.wait(1))
        count = len(stream.written)
        buffer.put_nowait(b'new turn')
        buffer.finish_turn()
        self.assertTrue(stream.drained.wait(1))
        self.assertEqual(b''.join(stream.written[count:]), b'new turn')

    def test_device_recovery_does_not_replay_speech_from_outage(self):
        buffer = SpeechBuffer()
        failed = threading.Event()
        stream = FakeStream()
        attempts = []
        def factory(**options):
            attempts.append(options)
            if len(attempts) == 1:
                failed.set()
                raise OSError('disconnected')
            return stream
        player = SpeechPlayer(buffer, factory, retry_seconds=.03)
        self.addCleanup(lambda: self.stop_player(player))
        player.start()
        self.assertTrue(failed.wait(1))
        buffer.put_nowait(b'stale speech')
        deadline = time.monotonic() + 1
        while not player.snapshot()['ready'] and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertTrue(player.snapshot()['ready'])
        buffer.put_nowait(b'fresh speech')
        buffer.finish_turn()
        self.assertTrue(stream.drained.wait(1))
        self.assertEqual(b''.join(stream.written), b'fresh speech')


class ReceiveDuringToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_narration_boundary_waits_for_generation_queue_and_hardware(self):
        buffer = SpeechBuffer()
        state = {'playing': True}
        done = asyncio.Event()
        buffer.put_nowait(b'last words')
        buffer.finish_turn()
        obj = SimpleNamespace(audio_in_queue=buffer, session=object(), _interrupted=False,
            _turn_done_event=done, _speech_player=SimpleNamespace(snapshot=lambda: state.copy()))
        task = asyncio.create_task(method('_wait_for_narration_end')(obj, timeout=1))
        try:
            done.set()  # Generation is done, but the audio queue has not drained.
            await asyncio.sleep(.03)
            self.assertFalse(task.done())
            buffer.read(buffer.epoch)
            await asyncio.sleep(.03)
            self.assertFalse(task.done())  # Native device is still playing.
            state['playing'] = False
            self.assertTrue(await asyncio.wait_for(task, 1))
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_interrupted_or_reconnected_briefing_does_not_resume_old_news(self):
        buffer = SpeechBuffer()
        obj = SimpleNamespace(audio_in_queue=buffer, session=object(), _interrupted=True,
            _turn_done_event=asyncio.Event(), _speech_player=None)
        self.assertFalse(await method('_wait_for_narration_end')(obj))
        obj._interrupted = False
        task = asyncio.create_task(method('_wait_for_narration_end')(obj, timeout=1))
        await asyncio.sleep(.03)
        obj.audio_in_queue = SpeechBuffer()
        self.assertFalse(await asyncio.wait_for(task, 1))

    async def test_receive_continues_during_slow_tool_and_batches_remain_ordered(self):
        started, release, received, sent = (asyncio.Event() for _ in range(4))
        executed, responses = [], []
        batches = [['first'], ['second']]
        pcm = b'12' * 180000  # 7.5 seconds, before any playback device is ready.
        async def execute(calls):
            executed.append(calls)
            if calls == batches[0]:
                started.set()
                await release.wait()
            return calls
        async def send_tool_response(**kwargs):
            responses.append(kwargs['function_responses'])
            if len(responses) == 2:
                sent.set()
        async def receive():
            yield SimpleNamespace(data=None, server_content=None,
                                  tool_call=SimpleNamespace(function_calls=batches[0]))
            await started.wait()
            yield SimpleNamespace(data=pcm, server_content=None, tool_call=None)
            yield SimpleNamespace(data=None, tool_call=None, server_content=SimpleNamespace(
                output_transcription=None, input_transcription=None, turn_complete=True))
            yield SimpleNamespace(data=None, server_content=None,
                                  tool_call=SimpleNamespace(function_calls=batches[1]))
            received.set()
            await asyncio.Event().wait()
        obj = SimpleNamespace(session=SimpleNamespace(receive=receive, send_tool_response=send_tool_response),
            _execute_tool_batch=execute, _tool_call_queue=asyncio.Queue(maxsize=16),
            audio_in_queue=SpeechBuffer(), _audio_output_ready=False, _interrupted=False,
            _pending_text_started_at=None, _response_pending=False, _is_speaking=False,
            _turn_done_event=asyncio.Event(), _dashboard=None, _pending_vision=None,
            _vision_close_pending=False, _reconfigure_reason=None, _reconfigure_event=None,
            ui=SimpleNamespace(set_state=lambda state: None, write_log=lambda line: None))
        tasks = [asyncio.create_task(method('_receive_audio')(obj)),
                 asyncio.create_task(method('_process_tool_calls')(obj))]
        try:
            await asyncio.wait_for(received.wait(), 1)
            self.assertEqual(executed, [batches[0]])
            chunks = []
            while not obj.audio_in_queue.empty():
                chunks.append(obj.audio_in_queue.read(0))
            self.assertEqual(b''.join(chunks), pcm)
            release.set()
            await asyncio.wait_for(sent.wait(), 1)
            self.assertEqual(executed, batches)
            self.assertEqual(responses, batches)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_server_interruption_flushes_stale_pcm_but_accepts_next_turn(self):
        buffer = SpeechBuffer()
        buffer.put_nowait(b'old audio!')
        async def receive():
            yield SimpleNamespace(data=b'discard me', tool_call=None, server_content=SimpleNamespace(
                interrupted=True, input_transcription=None, output_transcription=None, turn_complete=False))
            yield SimpleNamespace(data=b'new audio!', tool_call=None, server_content=SimpleNamespace(
                interrupted=False, input_transcription=None, output_transcription=None, turn_complete=True))
            raise asyncio.CancelledError()
        obj = SimpleNamespace(audio_in_queue=buffer, _interrupted=False, _response_pending=True,
            _pending_text_started_at=None, _turn_done_event=asyncio.Event(), _is_speaking=False,
            _pending_vision=None, _vision_close_pending=False, _dashboard=None,
            session=SimpleNamespace(receive=receive), set_speaking=lambda value: None,
            ui=SimpleNamespace(set_state=lambda state: None, write_log=lambda line: None))
        with self.assertRaises(asyncio.CancelledError):
            await method('_receive_audio')(obj)
        self.assertEqual(buffer.read(buffer.epoch), b'new audio!')

    async def test_stale_microphone_packets_are_not_sent_during_playback(self):
        packets, sent = asyncio.Queue(), []
        packets.put_nowait({'data': b'echo'})
        obj = SimpleNamespace(out_queue=packets, _is_speaking=False,
            _speech_player=SimpleNamespace(snapshot=lambda: {'playing': True}))
        async def send(**kwargs): sent.append(kwargs)
        obj.session = SimpleNamespace(send_realtime_input=send)
        task = asyncio.create_task(method('_send_realtime')(obj))
        try:
            await asyncio.sleep(.01)
            self.assertEqual(sent, [])
            obj._speech_player = None
            packets.put_nowait({'data': b'question'})
            await asyncio.sleep(.01)
            self.assertEqual(sent, [{'media': {'data': b'question'}}])
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
