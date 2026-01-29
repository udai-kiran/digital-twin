"""Recording session orchestration.

This module provides the main RecordingSession class that coordinates
audio capture from multiple sources, mixing, and file output.
"""

import logging
import signal
import time
from types import FrameType
from typing import Any

import numpy as np
from numpy.typing import NDArray

from audio_recorder.config import RecordingConfig
from audio_recorder.core.mixer import AudioMixer, MixerInput
from audio_recorder.core.protocols import AudioProcessor
from audio_recorder.exceptions import SessionError
from audio_recorder.sources.enumerator import AudioDevice, DeviceEnumerator
from audio_recorder.sources.sounddevice_source import SoundDeviceSource
from audio_recorder.writers.wav_writer import WavFileWriter

logger = logging.getLogger(__name__)


class RecordingSession:
    """Orchestrates a complete recording session.

    Manages the lifecycle of audio sources, mixing, and file writing.
    Handles graceful shutdown on SIGINT/SIGTERM.

    Args:
        config: Recording configuration.
        processors: List of audio processors (transcription, effects, etc.).
        diarizer: Optional speaker diarizer for identifying speakers.

    Example:
        config = RecordingConfig(
            output_path=Path("output.wav"),
            mic=SourceConfig(volume=0.8),
            monitor=SourceConfig(volume=0.5),
            duration=60,
        )
        session = RecordingSession(config)
        session.run()
    """

    def __init__(
        self,
        config: RecordingConfig,
        processors: list[AudioProcessor] | None = None,
        diarizer: Any = None,
    ) -> None:
        self._config = config
        self._mic_source: SoundDeviceSource | None = None
        self._monitor_source: SoundDeviceSource | None = None
        self._mixer: AudioMixer | None = None
        self._writer: WavFileWriter | None = None
        self._processors = processors or []
        self._diarizer = diarizer
        self._running = False
        self._original_sigint: Any = None
        self._original_sigterm: Any = None

    def _setup_signal_handlers(self) -> None:
        """Install signal handlers for graceful shutdown."""

        def handler(signum: int, frame: FrameType | None) -> None:
            sig_name = signal.Signals(signum).name
            logger.info("Received %s, stopping recording...", sig_name)
            self._running = False

        self._original_sigint = signal.signal(signal.SIGINT, handler)
        self._original_sigterm = signal.signal(signal.SIGTERM, handler)

    def _restore_signal_handlers(self) -> None:
        """Restore original signal handlers."""
        if self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)
        if self._original_sigterm is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm)

    def _resolve_devices(self) -> tuple[AudioDevice | None, AudioDevice | None]:
        """Resolve devices using the enumerator.

        Returns:
            Tuple of (mic_device, monitor_device).
        """
        mic_device = None
        monitor_device = None

        with DeviceEnumerator() as enumerator:
            # Resolve microphone
            if self._config.mic.enabled:
                if self._config.mic.device_name:
                    mic_device = enumerator.find_microphone(self._config.mic.device_name)
                else:
                    mic_device = enumerator.get_default_microphone()
                logger.info("Using microphone: %s", mic_device.description)

            # Resolve monitor
            if self._config.monitor.enabled:
                if self._config.monitor.device_name:
                    monitor_device = enumerator.find_monitor(self._config.monitor.device_name)
                else:
                    monitor_device = enumerator.get_default_monitor()
                logger.info("Using monitor: %s", monitor_device.description)

        return mic_device, monitor_device

    def _create_sources(
        self, mic_device: AudioDevice | None, monitor_device: AudioDevice | None
    ) -> None:
        """Create audio source instances."""
        if mic_device:
            self._mic_source = SoundDeviceSource(
                device_index=mic_device.index,
                device_name=mic_device.name,
                config=self._config.audio,
                buffer_size=self._config.buffer_size,
            )

        if monitor_device:
            self._monitor_source = SoundDeviceSource(
                device_index=monitor_device.index,
                device_name=monitor_device.name,
                config=self._config.audio,
                buffer_size=self._config.buffer_size,
            )

    def _start_sources(self) -> None:
        """Start all audio sources."""
        if self._mic_source:
            self._mic_source.start()
        if self._monitor_source:
            self._monitor_source.start()

    def _stop_sources(self) -> None:
        """Stop all audio sources."""
        if self._mic_source:
            self._mic_source.stop()
        if self._monitor_source:
            self._monitor_source.stop()

    def _start_processors(self) -> None:
        """Start all audio processors."""
        for processor in self._processors:
            try:
                processor.start()
            except Exception as e:
                logger.error("Failed to start processor: %s", e)
                raise

    def _stop_processors(self) -> None:
        """Stop all audio processors."""
        for processor in self._processors:
            try:
                processor.stop()
            except Exception as e:
                logger.error("Error stopping processor: %s", e)

    def _close_processors(self) -> None:
        """Close all audio processors."""
        for processor in self._processors:
            try:
                processor.close()
            except Exception as e:
                logger.error("Error closing processor: %s", e)

    def _recording_loop(self) -> None:
        """Main recording loop - read, mix, write."""
        if self._writer is None or self._mixer is None:
            raise SessionError("Session not properly initialized")

        start_time = time.monotonic()
        loop_interval = self._config.audio.block_size / self._config.audio.sample_rate

        while self._running:
            # Check duration limit
            if self._config.duration is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= self._config.duration:
                    logger.info("Duration limit reached (%.1f seconds)", elapsed)
                    break

            # Read from sources
            mic_data = self._mic_source.read() if self._mic_source else None
            monitor_data = self._monitor_source.read() if self._monitor_source else None

            # Determine speaker (before mixing)
            speaker = None
            timestamp = time.monotonic() - start_time
            if self._diarizer and (mic_data is not None or monitor_data is not None):
                try:
                    speaker = self._diarizer.process_streams(mic_data, monitor_data, timestamp)
                except Exception as e:
                    logger.error("Diarization error: %s", e)

            # Mix sources
            inputs: list[tuple[NDArray[np.float32] | None, MixerInput]] = []
            if mic_data is not None:
                inputs.append((mic_data, MixerInput("mic", self._config.mic.volume)))
            if monitor_data is not None:
                inputs.append((monitor_data, MixerInput("monitor", self._config.monitor.volume)))

            if inputs:
                mixed = self._mixer.mix(inputs)
                if mixed is not None:
                    self._writer.write(mixed)

                    # Process with processors
                    for processor in self._processors:
                        try:
                            # Check if processor has speaker-aware method
                            if hasattr(processor, "process_with_speaker"):
                                processor.process_with_speaker(mixed, timestamp, speaker)
                            else:
                                processor.process(mixed, timestamp)
                        except Exception as e:
                            logger.error("Processor error: %s", e)
                            # Continue recording despite processor errors

            # Small sleep to prevent busy-waiting
            time.sleep(loop_interval / 2)

    def run(self) -> None:
        """Run the recording session.

        This method blocks until recording is complete (either by duration
        limit or user interrupt).

        Raises:
            SessionError: If the session cannot be started.
        """
        logger.info("Starting recording session")
        logger.info("Output: %s", self._config.output_path)

        # Resolve devices
        mic_device, monitor_device = self._resolve_devices()

        if not mic_device and not monitor_device:
            raise SessionError("No audio sources enabled")

        # Create components
        self._create_sources(mic_device, monitor_device)
        self._mixer = AudioMixer(channels=self._config.audio.channels)

        # Setup signal handlers
        self._setup_signal_handlers()
        self._running = True

        try:
            # Start sources and open writer
            self._start_sources()

            # Start processors after sources
            self._start_processors()

            with WavFileWriter(self._config.output_path, self._config.audio) as writer:
                self._writer = writer
                logger.info("Recording... Press Ctrl+C to stop")
                self._recording_loop()

        finally:
            self._running = False

            # Stop processors before closing sources
            self._stop_processors()
            self._close_processors()

            self._stop_sources()
            self._restore_signal_handlers()
            self._writer = None

        logger.info("Recording complete")
