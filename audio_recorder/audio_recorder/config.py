"""Configuration dataclasses for audio recording."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class AudioConfig:
    """Configuration for audio capture parameters.

    Attributes:
        sample_rate: Sample rate in Hz (default: 48000 for PipeWire compatibility).
        channels: Number of audio channels (default: 2 for stereo).
        block_size: Number of frames per audio block (default: 1024).
        dtype: NumPy dtype string for audio samples.
    """

    sample_rate: int = 48000
    channels: int = 2
    block_size: int = 1024
    dtype: str = "float32"


@dataclass(frozen=True)
class SourceConfig:
    """Configuration for an individual audio source.

    Attributes:
        device_name: Name or identifier of the audio device.
        volume: Volume multiplier (0.0 to 1.0).
        enabled: Whether this source is enabled for recording.
    """

    device_name: str | None = None
    volume: float = 1.0
    enabled: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.volume <= 1.0:
            raise ValueError(f"Volume must be between 0.0 and 1.0, got {self.volume}")


@dataclass(frozen=True)
class TranscriptionConfig:
    """Configuration for real-time transcription.

    Attributes:
        enabled: Whether transcription is enabled.
        model_size: Whisper model size (tiny, base, small, medium, large).
        buffer_seconds: Audio buffer size in seconds before transcription.
        output_path: Path to the transcript file (None for auto-generated).
        speaker_labels: Whether to include speaker labels (User/System).
    """

    enabled: bool = False
    model_size: Literal["tiny", "base", "small", "medium", "large"] = "base"
    buffer_seconds: float = 10.0
    output_path: Path | None = None
    speaker_labels: bool = False

    def __post_init__(self) -> None:
        if self.buffer_seconds <= 0:
            raise ValueError(f"buffer_seconds must be positive, got {self.buffer_seconds}")
        if isinstance(self.output_path, str):
            object.__setattr__(self, "output_path", Path(self.output_path))


@dataclass
class RecordingConfig:
    """Configuration for a recording session.

    Attributes:
        output_path: Path to the output WAV file.
        audio: Audio parameters configuration.
        mic: Microphone source configuration.
        monitor: Monitor source configuration (for system audio).
        duration: Recording duration in seconds (None for indefinite).
        buffer_size: Maximum number of audio chunks to buffer per source.
        transcription: Transcription configuration (None to disable).
        verbose: Enable verbose logging.
    """

    output_path: Path
    audio: AudioConfig = field(default_factory=AudioConfig)
    mic: SourceConfig = field(default_factory=SourceConfig)
    monitor: SourceConfig = field(default_factory=SourceConfig)
    duration: float | None = None
    buffer_size: int = 100
    transcription: TranscriptionConfig | None = None
    verbose: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.output_path, str):
            object.__setattr__(self, "output_path", Path(self.output_path))
