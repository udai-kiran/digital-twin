"""Real-time Whisper transcription processor.

This module provides WhisperTranscriber, which transcribes audio in real-time
using the faster-whisper library. It accumulates audio chunks in a buffer,
runs inference on a worker thread, and writes timestamped transcripts to a file.
"""

import logging
import queue
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

import numpy as np
from numpy.typing import NDArray

from audio_recorder.config import AudioConfig
from audio_recorder.exceptions import ModelLoadError, TranscriptionError

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


class WhisperTranscriber:
    """Real-time Whisper transcription processor.

    Accumulates audio chunks and transcribes them using Whisper on a worker thread.
    The process() method is non-blocking (<1ms) to avoid affecting recording.

    Args:
        output_path: Path to the transcript output file.
        audio_config: Audio configuration (sample rate, channels).
        model_size: Whisper model size (tiny, base, small, medium, large).
        buffer_seconds: Audio buffer size in seconds before transcription.
        speaker_label: Optional speaker label to include in transcripts.

    Example:
        transcriber = WhisperTranscriber(
            output_path=Path("transcript.txt"),
            audio_config=AudioConfig(sample_rate=48000, channels=2),
            model_size="base",
            buffer_seconds=5.0,
        )
        transcriber.start()
        transcriber.process(audio_data, timestamp=0.0)
        transcriber.stop()
        transcriber.close()
    """

    def __init__(
        self,
        output_path: Path,
        audio_config: AudioConfig,
        model_size: str = "base",
        buffer_seconds: float = 5.0,
        speaker_label: str | None = None,
    ) -> None:
        self._output_path = output_path
        self._audio_config = audio_config
        self._model_size = model_size
        self._buffer_seconds = buffer_seconds
        self._default_speaker_label = speaker_label

        # Audio buffer
        self._buffer: list[NDArray[np.float32]] = []
        self._buffer_size = int(buffer_seconds * audio_config.sample_rate)
        self._total_frames = 0

        # Worker thread for transcription
        # Larger queue to handle temporary slowdowns
        self._queue: queue.Queue[tuple[NDArray[np.float32], float, str | None] | None] = (
            queue.Queue(maxsize=500)
        )
        self._worker_thread: threading.Thread | None = None
        self._running = False
        self._dropped_chunks = 0
        self._last_warning_time = 0.0

        # Whisper model (loaded in start())
        self._model: Any = None
        self._file_handle: TextIO | None = None

    def start(self) -> None:
        """Initialize the transcriber.

        Loads the Whisper model and starts the worker thread.

        Raises:
            ModelLoadError: If the Whisper model cannot be loaded.
        """
        logger.info("Initializing Whisper transcriber (model: %s)", self._model_size)

        try:
            from faster_whisper import WhisperModel

            # Load model (downloads on first use)
            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
            logger.info("Whisper model loaded successfully")

        except Exception as e:
            raise ModelLoadError(f"Failed to load Whisper model '{self._model_size}': {e}") from e

        # Open output file
        try:
            self._file_handle = open(self._output_path, "w", encoding="utf-8")
            logger.info("Transcript output: %s", self._output_path)
        except OSError as e:
            raise TranscriptionError(f"Failed to open transcript file: {e}") from e

        # Start worker thread
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        logger.info("Transcription worker thread started")

    def process(self, data: NDArray[np.float32], timestamp: float) -> None:
        """Process an audio chunk (non-blocking).

        Queues the audio data for transcription on the worker thread.

        Args:
            data: Audio data as float32 array with shape (frames, channels).
            timestamp: Recording timestamp in seconds.
        """
        if not self._running:
            return

        try:
            # Non-blocking queue put
            self._queue.put_nowait((data.copy(), timestamp, self._default_speaker_label))
        except queue.Full:
            self._dropped_chunks += 1
            # Rate-limit warnings to avoid log spam
            import time
            now = time.time()
            if now - self._last_warning_time > 5.0:
                logger.warning(
                    "Transcription queue full (dropped %d chunks). Consider using a faster model "
                    "(--model-size tiny) or larger buffer (--buffer-seconds 10)",
                    self._dropped_chunks
                )
                self._last_warning_time = now

    def process_with_speaker(
        self, data: NDArray[np.float32], timestamp: float, speaker: str | None
    ) -> None:
        """Process an audio chunk with speaker label (non-blocking).

        Args:
            data: Audio data as float32 array with shape (frames, channels).
            timestamp: Recording timestamp in seconds.
            speaker: Speaker label (e.g., "User", "System", "Both").
        """
        if not self._running:
            return

        try:
            self._queue.put_nowait((data.copy(), timestamp, speaker))
        except queue.Full:
            self._dropped_chunks += 1
            # Rate-limit warnings to avoid log spam
            import time
            now = time.time()
            if now - self._last_warning_time > 5.0:
                logger.warning(
                    "Transcription queue full (dropped %d chunks). Consider using a faster model "
                    "(--model-size tiny) or larger buffer (--buffer-seconds 10)",
                    self._dropped_chunks
                )
                self._last_warning_time = now

    def stop(self) -> None:
        """Finalize transcription.

        Signals the worker thread to process remaining buffers and stop.
        """
        if not self._running:
            return

        logger.info("Stopping transcription...")
        if self._dropped_chunks > 0:
            logger.warning("Total dropped chunks during recording: %d", self._dropped_chunks)

        self._running = False

        # Signal worker to stop (sentinel value)
        try:
            self._queue.put(None, timeout=5.0)
        except queue.Full:
            logger.warning("Failed to signal worker thread (queue full)")

    def close(self) -> None:
        """Clean up resources.

        Waits for the worker thread to finish and closes the output file.
        """
        # Wait for worker thread
        if self._worker_thread and self._worker_thread.is_alive():
            logger.info("Waiting for transcription worker to finish...")
            self._worker_thread.join(timeout=30.0)
            if self._worker_thread.is_alive():
                logger.warning("Worker thread did not finish in time")

        # Close output file
        if self._file_handle:
            try:
                self._file_handle.close()
            except Exception as e:
                logger.error("Error closing transcript file: %s", e)
            finally:
                self._file_handle = None

        self._model = None
        logger.info("Transcription resources cleaned up")

    def _worker_loop(self) -> None:
        """Worker thread main loop.

        Accumulates audio chunks, runs Whisper inference, and writes transcripts.
        """
        logger.debug("Worker thread started")

        while True:
            try:
                # Block until data available
                item = self._queue.get(timeout=1.0)

                # Check for sentinel (stop signal)
                if item is None:
                    logger.debug("Received stop signal")
                    break

                data, timestamp, speaker = item

                # Accumulate in buffer
                self._buffer.append(data)
                self._total_frames += len(data)

                # Check if buffer is full
                if self._total_frames >= self._buffer_size:
                    self._transcribe_buffer(timestamp, speaker)

            except queue.Empty:
                # No data available, check if we should stop
                if not self._running and self._queue.empty():
                    break
                continue

            except Exception as e:
                logger.error("Error in transcription worker: %s", e, exc_info=True)

        # Process remaining buffer
        if self._buffer:
            logger.info("Processing remaining audio buffer...")
            self._transcribe_buffer(0.0, None)

        logger.debug("Worker thread stopped")

    def _transcribe_buffer(self, timestamp: float, speaker: str | None) -> None:
        """Transcribe accumulated audio buffer.

        Args:
            timestamp: Timestamp of the last chunk in the buffer.
            speaker: Speaker label for this segment.
        """
        if not self._buffer or not self._model:
            return

        try:
            # Concatenate buffer
            audio = np.concatenate(self._buffer, axis=0)

            # Convert to mono (average channels)
            if audio.shape[1] > 1:
                audio = audio.mean(axis=1)
            else:
                audio = audio.squeeze()

            # Resample if needed (Whisper expects 16kHz)
            if self._audio_config.sample_rate != 16000:
                audio = self._resample(audio, self._audio_config.sample_rate, 16000)

            # Run Whisper inference with optimized settings
            # beam_size=1 is faster, vad_filter helps skip silence
            segments, info = self._model.transcribe(
                audio,
                beam_size=1,  # Faster than beam_size=5
                language=None,  # Auto-detect
                vad_filter=True,  # Skip silence
                condition_on_previous_text=False  # Faster, independent segments
            )

            # Write transcripts
            for segment in segments:
                text = segment.text.strip()
                if text:
                    if speaker:
                        line = f"[{timestamp:.2f}s - {speaker}] {text}\n"
                    else:
                        line = f"[{timestamp:.2f}s] {text}\n"

                    if self._file_handle:
                        self._file_handle.write(line)
                        self._file_handle.flush()

            # Clear buffer
            self._buffer.clear()
            self._total_frames = 0

        except Exception as e:
            logger.error("Transcription failed: %s", e, exc_info=True)
            # Clear buffer even on error to avoid memory buildup
            self._buffer.clear()
            self._total_frames = 0

    def _resample(self, audio: NDArray[np.float32], orig_sr: int, target_sr: int) -> NDArray[np.float32]:
        """Resample audio to target sample rate.

        Args:
            audio: Input audio array (1D).
            orig_sr: Original sample rate.
            target_sr: Target sample rate.

        Returns:
            Resampled audio array.
        """
        from scipy import signal as scipy_signal  # type: ignore[import-untyped]

        # Calculate resampling ratio
        num_samples = int(len(audio) * target_sr / orig_sr)
        resampled: NDArray[np.float32] = scipy_signal.resample(audio, num_samples)
        return resampled.astype(np.float32)
