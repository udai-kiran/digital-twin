"""Custom exceptions for the audio recorder."""


class AudioRecorderError(Exception):
    """Base exception for all audio recorder errors."""


class DeviceNotFoundError(AudioRecorderError):
    """Raised when a requested audio device cannot be found."""

    def __init__(self, device_name: str, device_type: str = "device") -> None:
        self.device_name = device_name
        self.device_type = device_type
        super().__init__(f"{device_type.capitalize()} not found: '{device_name}'")


class NoDevicesAvailableError(AudioRecorderError):
    """Raised when no audio devices of the required type are available."""

    def __init__(self, device_type: str) -> None:
        self.device_type = device_type
        super().__init__(f"No {device_type} devices available")


class AudioCaptureError(AudioRecorderError):
    """Raised when audio capture fails."""


class AudioWriteError(AudioRecorderError):
    """Raised when writing audio data fails."""


class SessionError(AudioRecorderError):
    """Raised when the recording session encounters an error."""


class MixerError(AudioRecorderError):
    """Raised when audio mixing fails."""


class TranscriptionError(AudioRecorderError):
    """Raised when transcription processing fails."""


class ModelLoadError(AudioRecorderError):
    """Raised when loading a transcription model fails."""
