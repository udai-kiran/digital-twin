"""Command-line interface for the audio recorder.

This module provides the main entry point and argument parsing
for the audio recorder CLI tool.
"""

import argparse
import logging
import sys
from pathlib import Path

from audio_recorder import __version__
from audio_recorder.config import AudioConfig, RecordingConfig, SourceConfig, TranscriptionConfig
from audio_recorder.core.protocols import AudioProcessor
from audio_recorder.core.session import RecordingSession
from audio_recorder.exceptions import AudioRecorderError
from audio_recorder.sources.enumerator import DeviceEnumerator


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity setting."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def list_devices() -> None:
    """List all available audio devices."""
    print("Available Audio Devices")
    print("=" * 50)

    with DeviceEnumerator() as enumerator:
        print("\nMicrophones:")
        print("-" * 30)
        try:
            for mic in enumerator.list_microphones():
                print(f"  {mic}")
                print(f"    Index: {mic.index}, Name: {mic.name}")
        except AudioRecorderError as e:
            print(f"  Error: {e}")

        print("\nMonitor Sources (System Audio):")
        print("-" * 30)
        try:
            for monitor in enumerator.list_monitors():
                print(f"  {monitor}")
                print(f"    Index: {monitor.index}, Name: {monitor.name}")
        except AudioRecorderError as e:
            print(f"  Error: {e}")


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="audio-recorder",
        description="Record microphone and system audio simultaneously.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic recording (uses default devices)
  audio-recorder -o output.wav

  # List available devices
  audio-recorder --list-devices

  # Record with specific devices
  audio-recorder -o output.wav --mic "Built-in" --monitor "Built-in"

  # Timed recording with volume adjustment
  audio-recorder -o output.wav --duration 60 --mic-volume 0.8 --monitor-volume 0.5

  # Record only system audio (no microphone)
  audio-recorder -o output.wav --no-mic

  # Recording with transcription
  audio-recorder -o output.wav --transcribe

  # Transcription with speaker labels
  audio-recorder -o output.wav --transcribe --speaker-labels

  # Custom Whisper model size
  audio-recorder -o output.wav --transcribe --model-size small
""",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("recording.wav"),
        help="Output WAV file path (default: recording.wav)",
    )

    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio devices and exit",
    )

    # Device selection
    device_group = parser.add_argument_group("Device Selection")
    device_group.add_argument(
        "--mic",
        type=str,
        default=None,
        metavar="DEVICE",
        help="Microphone device name or description (default: system default)",
    )
    device_group.add_argument(
        "--monitor",
        type=str,
        default=None,
        metavar="DEVICE",
        help="Monitor source name or description (default: system default)",
    )
    device_group.add_argument(
        "--no-mic",
        action="store_true",
        help="Disable microphone recording",
    )
    device_group.add_argument(
        "--no-monitor",
        action="store_true",
        help="Disable system audio recording",
    )

    # Volume controls
    volume_group = parser.add_argument_group("Volume Controls")
    volume_group.add_argument(
        "--mic-volume",
        type=float,
        default=1.0,
        metavar="VOL",
        help="Microphone volume multiplier 0.0-1.0 (default: 1.0)",
    )
    volume_group.add_argument(
        "--monitor-volume",
        type=float,
        default=1.0,
        metavar="VOL",
        help="System audio volume multiplier 0.0-1.0 (default: 1.0)",
    )

    # Recording options
    recording_group = parser.add_argument_group("Recording Options")
    recording_group.add_argument(
        "--duration",
        type=float,
        default=None,
        metavar="SECS",
        help="Recording duration in seconds (default: until Ctrl+C)",
    )
    recording_group.add_argument(
        "--sample-rate",
        type=int,
        default=48000,
        metavar="HZ",
        help="Sample rate in Hz (default: 48000)",
    )

    # Transcription options
    transcription_group = parser.add_argument_group("Transcription Options")
    transcription_group.add_argument(
        "--transcribe",
        action="store_true",
        help="Enable real-time transcription with Whisper",
    )
    transcription_group.add_argument(
        "--model-size",
        type=str,
        choices=["tiny", "base", "small", "medium", "large"],
        default="base",
        metavar="SIZE",
        help="Whisper model size (default: base)",
    )
    transcription_group.add_argument(
        "--buffer-seconds",
        type=float,
        default=10.0,
        metavar="SECS",
        help="Audio buffer size in seconds for transcription (default: 10.0)",
    )
    transcription_group.add_argument(
        "--speaker-labels",
        action="store_true",
        help="Include speaker labels (User/System) in transcripts",
    )

    # Output options
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser


def validate_args(args: argparse.Namespace) -> None:
    """Validate command-line arguments.

    Raises:
        ValueError: If arguments are invalid.
    """
    if args.no_mic and args.no_monitor:
        raise ValueError("Cannot disable both microphone and monitor")

    if not 0.0 <= args.mic_volume <= 1.0:
        raise ValueError(f"Microphone volume must be 0.0-1.0, got {args.mic_volume}")

    if not 0.0 <= args.monitor_volume <= 1.0:
        raise ValueError(f"Monitor volume must be 0.0-1.0, got {args.monitor_volume}")

    if args.duration is not None and args.duration <= 0:
        raise ValueError(f"Duration must be positive, got {args.duration}")

    if args.buffer_seconds <= 0:
        raise ValueError(f"Buffer seconds must be positive, got {args.buffer_seconds}")


def build_config(args: argparse.Namespace) -> RecordingConfig:
    """Build recording configuration from arguments."""
    audio_config = AudioConfig(
        sample_rate=args.sample_rate,
        channels=2,
        block_size=1024,
        dtype="float32",
    )

    mic_config = SourceConfig(
        device_name=args.mic,
        volume=args.mic_volume,
        enabled=not args.no_mic,
    )

    monitor_config = SourceConfig(
        device_name=args.monitor,
        volume=args.monitor_volume,
        enabled=not args.no_monitor,
    )

    # Build transcription config if enabled
    transcription_config = None
    if args.transcribe:
        # Auto-generate transcript filename from output path
        transcript_path = args.output.with_suffix(".txt")

        transcription_config = TranscriptionConfig(
            enabled=True,
            model_size=args.model_size,
            buffer_seconds=args.buffer_seconds,
            output_path=transcript_path,
            speaker_labels=args.speaker_labels,
        )

    return RecordingConfig(
        output_path=args.output,
        audio=audio_config,
        mic=mic_config,
        monitor=monitor_config,
        duration=args.duration,
        transcription=transcription_config,
        verbose=args.verbose,
    )


def main() -> int:
    """Main entry point for the CLI.

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    parser = create_parser()
    args = parser.parse_args()

    # List devices and exit
    if args.list_devices:
        try:
            list_devices()
            return 0
        except AudioRecorderError as e:
            print(f"Error listing devices: {e}", file=sys.stderr)
            return 1

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Validate arguments
    try:
        validate_args(args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Build configuration
    config = build_config(args)

    # Create processors
    processors: list[AudioProcessor] = []
    diarizer = None

    if config.transcription and config.transcription.enabled:
        try:
            from audio_recorder.processors import SimpleSpeakerDiarizer, WhisperTranscriber

            # Create diarizer if speaker labels are enabled
            if config.transcription.speaker_labels:
                diarizer = SimpleSpeakerDiarizer(energy_threshold=0.01, ratio_threshold=2.0)
                logger.info("Speaker diarization enabled")

            transcriber = WhisperTranscriber(
                output_path=config.transcription.output_path,  # type: ignore
                audio_config=config.audio,
                model_size=config.transcription.model_size,
                buffer_seconds=config.transcription.buffer_seconds,
            )
            processors.append(transcriber)
            logger.info("Transcription enabled (model: %s)", config.transcription.model_size)
        except ImportError as e:
            logger.error("Failed to import transcription dependencies: %s", e)
            return 1

    # Run recording session
    try:
        session = RecordingSession(config, processors=processors, diarizer=diarizer)
        session.run()
        return 0
    except AudioRecorderError as e:
        logger.error("Recording failed: %s", e)
        return 1
    except KeyboardInterrupt:
        # This shouldn't happen as we handle SIGINT, but just in case
        logger.info("Interrupted")
        return 0


if __name__ == "__main__":
    sys.exit(main())
