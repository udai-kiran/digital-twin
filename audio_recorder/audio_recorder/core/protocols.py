"""Protocol definitions for audio recording components.

These protocols define the contracts that audio sources and writers must implement,
following the Dependency Inversion Principle.
"""

from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class AudioSource(Protocol):
    """Protocol for audio capture sources.

    Implementations must provide methods to start/stop capture and read audio data.
    Audio data is returned as NumPy arrays with shape (frames, channels).
    """

    @property
    def name(self) -> str:
        """Human-readable name of the audio source."""
        ...

    @property
    def is_active(self) -> bool:
        """Whether the source is currently capturing audio."""
        ...

    def start(self) -> None:
        """Start capturing audio from this source.

        Raises:
            AudioCaptureError: If capture cannot be started.
        """
        ...

    def stop(self) -> None:
        """Stop capturing audio from this source."""
        ...

    def read(self) -> NDArray[np.float32] | None:
        """Read available audio data from the buffer.

        Returns:
            Audio data as float32 array with shape (frames, channels),
            or None if no data is available.
        """
        ...

    def clear_buffer(self) -> None:
        """Clear any buffered audio data."""
        ...


class AudioWriter(Protocol):
    """Protocol for audio file writers.

    Implementations must support context manager protocol for safe resource handling.
    """

    def write(self, data: NDArray[np.float32]) -> None:
        """Write audio data to the output.

        Args:
            data: Audio data as float32 array with shape (frames, channels).

        Raises:
            AudioWriteError: If writing fails.
        """
        ...

    def close(self) -> None:
        """Close the writer and finalize the output file."""
        ...

    def __enter__(self) -> "AudioWriter":
        """Enter context manager."""
        ...

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        """Exit context manager, ensuring resources are released."""
        ...


class AudioProcessor(Protocol):
    """Protocol for audio processors (transcription, effects, analysis, etc.).

    Processors receive audio chunks during recording and perform operations
    like transcription, speaker diarization, or real-time effects.
    The process() method must be non-blocking (complete in <1ms).
    """

    def start(self) -> None:
        """Initialize the processor.

        This is called before recording starts. Use this to load models,
        start worker threads, or allocate resources.

        Raises:
            AudioRecorderError: If initialization fails.
        """
        ...

    def process(self, data: NDArray[np.float32], timestamp: float) -> None:
        """Process an audio chunk (must be non-blocking).

        This method is called from the main recording loop and must complete
        in <1ms to avoid recording dropouts. Use a worker thread for any
        heavy processing.

        Args:
            data: Audio data as float32 array with shape (frames, channels).
            timestamp: Recording timestamp in seconds since recording started.
        """
        ...

    def stop(self) -> None:
        """Finalize processing.

        This is called when recording stops. Use this to flush buffers,
        finalize output files, or perform cleanup that requires processing
        remaining data.
        """
        ...

    def close(self) -> None:
        """Clean up resources.

        This is called after stop(). Use this to release resources like
        worker threads, file handles, or loaded models.
        """
        ...
