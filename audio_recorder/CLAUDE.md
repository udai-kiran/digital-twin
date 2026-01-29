# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Linux CLI tool that records microphone and system audio simultaneously, mixing them into a single WAV file. Uses PipeWire/PulseAudio for device discovery and sounddevice for audio capture.

## Development Commands

```bash
# Setup
uv sync                          # Install dependencies
uv sync --dev                    # Include dev dependencies

# Run the application
uv run audio-recorder --help
uv run audio-recorder --list-devices
uv run audio-recorder -o output.wav

# Development with venv
.venv/bin/python -m audio_recorder --help

# Linting and type checking
uv run ruff check audio_recorder/
uv run ruff format audio_recorder/
uv run mypy audio_recorder/

# Testing
uv run pytest                    # Run all tests
uv run pytest tests/path/to/test.py  # Run specific test
uv run pytest --cov=audio_recorder   # With coverage

# Build AppImage
./build-appimage.sh              # Creates audio-recorder-x86_64.AppImage
```

## Architecture Overview

### SOLID Design Principles

The codebase follows strict SOLID principles:

**Protocol-Based Abstractions (DIP)**
- `AudioSource` protocol - any audio capture source (microphone, monitor)
- `AudioWriter` protocol - any audio output format
- Implementations depend on abstractions, not concretions

**Single Responsibility**
- `DeviceEnumerator` - device discovery only (using pulsectl)
- `SoundDeviceSource` - audio capture only (using sounddevice callbacks)
- `AudioMixer` - stream mixing only (volume control, soft clipping)
- `WavFileWriter` - file output only
- `RecordingSession` - orchestration only

**Core Data Flow**

```
CLI (cli/app.py)
  ↓ creates RecordingConfig
RecordingSession (core/session.py) ← orchestrator/facade
  ↓ resolves devices via
DeviceEnumerator (sources/enumerator.py)
  ↓ creates
SoundDeviceSource instances (microphone, monitor)
  ↓ captures to Queue (thread-safe)
Recording Loop reads → AudioMixer → WavFileWriter
```

### Critical Architecture Patterns

**Thread Safety**
- `SoundDeviceSource` uses `queue.Queue` for thread-safe audio buffering
- Audio callbacks run in separate PortAudio threads
- `put_nowait()`/`get_nowait()` for lock-free queue access
- Buffer overflow tracking with periodic logging

**Device Discovery Strategy**
- Microphones: sounddevice devices with input channels, excluding monitors
- Monitors (system audio): devices with BOTH input and output channels that match PulseAudio sink descriptions
- PipeWire/JACK monitors appear as duplex devices in PortAudio

**Audio Mixing**
- Average streams (prevents clipping) with per-source volume multipliers
- Apply tanh soft clipping to final output
- Align chunks by trimming to shortest (or pad with zeros)

**Configuration Pattern**
- Immutable frozen dataclasses for audio parameters (`AudioConfig`)
- Mutable dataclass for session config (`RecordingConfig`)
- Validation in `__post_init__` methods

**Lifecycle Management**
- Context managers for resource cleanup (`DeviceEnumerator`, `WavFileWriter`)
- Signal handlers (SIGINT/SIGTERM) for graceful shutdown
- Start/stop methods follow consistent pattern across components

### Key Files and Responsibilities

**core/protocols.py**
- Defines `AudioSource` and `AudioWriter` protocols
- All components depend on these abstractions

**core/session.py**
- `RecordingSession` orchestrates the entire recording flow
- `_recording_loop()` is where audio capture happens:
  1. Read from sources
  2. Mix streams
  3. Write to file
  4. Check duration limits

**sources/enumerator.py**
- `DeviceEnumerator` discovers devices via pulsectl + sounddevice
- Critical: understands how PipeWire/PulseAudio monitor sources work
- Monitor detection: matches sounddevice devices to PulseAudio sinks

**sources/sounddevice_source.py**
- `SoundDeviceSource` implements thread-safe audio capture
- `_audio_callback()` runs in PortAudio thread - must be fast
- Uses `Queue` for communication between threads

**core/mixer.py**
- `AudioMixer` combines multiple audio streams
- `mix()` aligns by trimming, `mix_with_padding()` preserves all audio
- Soft clipping via `np.tanh()` prevents distortion

**cli/app.py**
- Argument parsing and validation
- Creates `RecordingConfig` from CLI args
- Device listing mode vs recording mode

### Audio Technical Details

**Sample Format**
- 48000 Hz (PipeWire default)
- 2 channels (stereo)
- float32 dtype
- 1024 frames per block

**Monitor Sources**
- System audio captured via PulseAudio/PipeWire monitor sources
- Each sink (output device) has a corresponding monitor source
- In PipeWire/JACK, monitors appear as duplex devices (both input and output channels)

**Buffer Management**
- Default 100 chunks per source (configurable)
- Overflow logged every 10 occurrences to avoid spam
- Queue.Full exceptions caught in audio callback thread

## Adding New Components

**New Audio Source**
- Implement `AudioSource` protocol from `core/protocols.py`
- Must provide: `name`, `is_active`, `start()`, `stop()`, `read()`, `clear_buffer()`
- Return audio as `NDArray[np.float32]` with shape `(frames, channels)`

**New Audio Processor** (future feature)
- Define new protocol in `core/protocols.py` following existing patterns
- Implement with thread-safe processing
- Integrate into `RecordingSession._recording_loop()`
- Add configuration to `config.py` dataclass

**New Output Format**
- Implement `AudioWriter` protocol
- Support context manager (`__enter__`, `__exit__`)
- Add format selection to CLI

## Type Checking

- Strict mypy enabled (`strict = true` in pyproject.toml)
- Use Python 3.11+ union syntax: `str | None` not `Optional[str]`
- Protocol types for dependency inversion
- NumPy array types: `NDArray[np.float32]`

## Testing Environment

- Requires PulseAudio/PipeWire on Linux
- Tests need audio devices available (microphone/monitor)
- Mock `sounddevice` and `pulsectl` for unit tests
- Integration tests require real audio hardware
