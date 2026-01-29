"""WAV file writer using soundfile library.

This module provides safe, context-managed WAV file writing
with proper resource cleanup.
"""

import logging
from pathlib import Path
from typing import Self

import numpy as np
import soundfile as sf
from numpy.typing import NDArray

from audio_recorder.config import AudioConfig
from audio_recorder.exceptions import AudioWriteError

logger = logging.getLogger(__name__)


class WavFileWriter:
    """Writes audio data to a WAV file.

    Uses soundfile for high-quality WAV output with float32 samples.
    Supports context manager protocol for safe resource handling.

    Args:
        path: Output file path.
        config: Audio configuration (sample rate, channels).

    Example:
        with WavFileWriter(Path("output.wav"), config) as writer:
            writer.write(audio_chunk)
            writer.write(another_chunk)
        # File is automatically closed and finalized
    """

    def __init__(self, path: Path, config: AudioConfig) -> None:
        self._path = path
        self._config = config
        self._file: sf.SoundFile | None = None
        self._frames_written = 0

    @property
    def path(self) -> Path:
        """Path to the output file."""
        return self._path

    @property
    def frames_written(self) -> int:
        """Total number of frames written."""
        return self._frames_written

    @property
    def duration(self) -> float:
        """Duration of audio written in seconds."""
        return self._frames_written / self._config.sample_rate

    def __enter__(self) -> Self:
        """Open the file for writing."""
        try:
            self._file = sf.SoundFile(
                self._path,
                mode="w",
                samplerate=self._config.sample_rate,
                channels=self._config.channels,
                subtype="FLOAT",
                format="WAV",
            )
            logger.info("Opened %s for writing", self._path)
        except sf.SoundFileError as e:
            raise AudioWriteError(f"Failed to open {self._path}: {e}")
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: object,
    ) -> None:
        """Close the file, ensuring it's finalized."""
        self.close()

    def write(self, data: NDArray[np.float32]) -> None:
        """Write audio data to the file.

        Args:
            data: Audio data as float32 array with shape (frames, channels).

        Raises:
            AudioWriteError: If writing fails or file is not open.
        """
        if self._file is None:
            raise AudioWriteError("Writer not opened - use as context manager")

        if data.size == 0:
            return

        try:
            self._file.write(data)
            self._frames_written += data.shape[0]
        except sf.SoundFileError as e:
            raise AudioWriteError(f"Failed to write audio data: {e}")

    def close(self) -> None:
        """Close the writer and finalize the output file."""
        if self._file is not None:
            try:
                self._file.close()
                logger.info(
                    "Closed %s (%.2f seconds, %d frames)",
                    self._path,
                    self.duration,
                    self._frames_written,
                )
            except sf.SoundFileError as e:
                logger.error("Error closing %s: %s", self._path, e)
            finally:
                self._file = None
