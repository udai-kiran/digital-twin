"""Audio capture source using sounddevice library.

This module provides thread-safe audio capture from any PulseAudio/PipeWire source
using callback-based streaming.
"""

import logging
from queue import Empty, Full, Queue
from typing import Any

import numpy as np
import sounddevice as sd
from numpy.typing import NDArray

from audio_recorder.config import AudioConfig
from audio_recorder.exceptions import AudioCaptureError

logger = logging.getLogger(__name__)


class SoundDeviceSource:
    """Captures audio from a device using sounddevice.

    Uses callback-based capture with a thread-safe queue for buffering.
    The callback runs in a separate thread managed by sounddevice/PortAudio.

    Args:
        device_index: Sounddevice device index.
        device_name: Human-readable device name for logging.
        config: Audio configuration parameters.
        buffer_size: Maximum number of audio chunks to buffer.

    Example:
        source = SoundDeviceSource(device_index=11, device_name="Mic", config=config)
        source.start()
        try:
            while recording:
                chunk = source.read()
                if chunk is not None:
                    process(chunk)
        finally:
            source.stop()
    """

    def __init__(
        self,
        device_index: int,
        device_name: str,
        config: AudioConfig,
        buffer_size: int = 100,
    ) -> None:
        self._device_index = device_index
        self._device_name = device_name
        self._config = config
        self._buffer_size = buffer_size
        self._buffer: Queue[NDArray[np.float32]] = Queue(maxsize=buffer_size)
        self._stream: sd.InputStream | None = None
        self._overflow_count = 0

    @property
    def name(self) -> str:
        """Human-readable name of the audio source."""
        return self._device_name

    @property
    def is_active(self) -> bool:
        """Whether the source is currently capturing audio."""
        return self._stream is not None and self._stream.active

    def _audio_callback(
        self,
        indata: NDArray[np.float32],
        frames: int,
        time_info: Any,
        status: sd.CallbackFlags,
    ) -> None:
        """Callback invoked by sounddevice when audio data is available.

        This runs in a separate thread - must be thread-safe and fast.
        """
        if status.input_overflow:
            logger.warning("Input overflow on %s", self._device_name)

        # Copy data since sounddevice may reuse the buffer
        try:
            self._buffer.put_nowait(indata.copy())
        except Full:
            self._overflow_count += 1
            if self._overflow_count % 10 == 1:  # Log every 10th overflow
                logger.warning(
                    "Buffer overflow on %s (count: %d)", self._device_name, self._overflow_count
                )

    def start(self) -> None:
        """Start capturing audio from this source.

        Raises:
            AudioCaptureError: If the stream cannot be opened.
        """
        if self._stream is not None:
            logger.warning("Source %s already started", self._device_name)
            return

        try:
            self._stream = sd.InputStream(
                device=self._device_index,
                samplerate=self._config.sample_rate,
                channels=self._config.channels,
                dtype=self._config.dtype,
                blocksize=self._config.block_size,
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.info("Started capture from %s (index %d)", self._device_name, self._device_index)
        except sd.PortAudioError as e:
            raise AudioCaptureError(f"Failed to start capture from {self._device_name}: {e}")

    def stop(self) -> None:
        """Stop capturing audio from this source."""
        if self._stream is None:
            return

        try:
            self._stream.stop()
            self._stream.close()
        except sd.PortAudioError as e:
            logger.error("Error stopping stream %s: %s", self._device_name, e)
        finally:
            self._stream = None
            logger.info("Stopped capture from %s", self._device_name)

    def read(self) -> NDArray[np.float32] | None:
        """Read available audio data from the buffer.

        Returns:
            Audio data as float32 array with shape (frames, channels),
            or None if no data is available.
        """
        try:
            return self._buffer.get_nowait()
        except Empty:
            return None

    def read_all(self) -> NDArray[np.float32] | None:
        """Read all available audio data from the buffer.

        Concatenates all buffered chunks into a single array.

        Returns:
            Combined audio data, or None if buffer is empty.
        """
        chunks = []
        while True:
            chunk = self.read()
            if chunk is None:
                break
            chunks.append(chunk)

        if not chunks:
            return None

        return np.concatenate(chunks, axis=0)

    def clear_buffer(self) -> None:
        """Clear any buffered audio data."""
        while not self._buffer.empty():
            try:
                self._buffer.get_nowait()
            except Empty:
                break
        self._overflow_count = 0
