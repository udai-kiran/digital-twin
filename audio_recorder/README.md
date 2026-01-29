# Audio Recorder

A CLI tool to record microphone and system audio (speaker/earphone) simultaneously, mixing them into a single WAV file.

## Features

- Record microphone and system audio together
- Automatic device detection via PulseAudio/PipeWire
- Per-source volume control
- Soft clipping to prevent distortion
- Timed recording option
- Clean WAV output (float32)

## Requirements

- Linux with PulseAudio or PipeWire (with PulseAudio compatibility)
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

### Using uv (Recommended)

```bash
# Clone and sync
uv sync

# Run the recorder
uv run audio-recorder --help
```

### Using pip

```bash
pip install -e .
```

### AppImage

Download the AppImage from releases, make it executable, and run:

```bash
chmod +x audio-recorder-*.AppImage
./audio-recorder-*.AppImage --help
```

## Usage

### Basic Recording

```bash
# Record with default devices
audio-recorder -o output.wav

# Press Ctrl+C to stop recording
```

### List Available Devices

```bash
audio-recorder --list-devices
```

### Custom Devices

```bash
audio-recorder -o output.wav --mic "Built-in Microphone" --monitor "Built-in Audio"
```

### Timed Recording

```bash
# Record for 60 seconds
audio-recorder -o output.wav --duration 60
```

### Volume Adjustment

```bash
# Reduce microphone volume, boost system audio
audio-recorder -o output.wav --mic-volume 0.5 --monitor-volume 0.8
```

### Record Only System Audio

```bash
audio-recorder -o output.wav --no-mic
```

### Record Only Microphone

```bash
audio-recorder -o output.wav --no-monitor
```

## CLI Options

```
usage: audio-recorder [-h] [--version] [-o OUTPUT] [--list-devices]
                      [--mic DEVICE] [--monitor DEVICE] [--no-mic] [--no-monitor]
                      [--mic-volume VOL] [--monitor-volume VOL]
                      [--duration SECS] [--sample-rate HZ] [-v]

Options:
  -h, --help            Show help message and exit
  --version             Show version and exit
  -o, --output OUTPUT   Output WAV file path (default: recording.wav)
  --list-devices        List available audio devices and exit
  -v, --verbose         Enable verbose logging

Device Selection:
  --mic DEVICE          Microphone device name or description
  --monitor DEVICE      Monitor source name or description
  --no-mic              Disable microphone recording
  --no-monitor          Disable system audio recording

Volume Controls:
  --mic-volume VOL      Microphone volume 0.0-1.0 (default: 1.0)
  --monitor-volume VOL  System audio volume 0.0-1.0 (default: 1.0)

Recording Options:
  --duration SECS       Recording duration in seconds
  --sample-rate HZ      Sample rate in Hz (default: 48000)
```

## How It Works

1. **Device Discovery**: Uses `pulsectl` to enumerate PulseAudio/PipeWire sources
2. **Audio Capture**: Uses `sounddevice` with callback-based streaming for low-latency capture
3. **Mixing**: Averages streams with per-source volume, applies tanh soft clipping
4. **Output**: Writes WAV file using `soundfile` library

### Monitor Sources

System audio is captured via monitor sources. For each audio output (sink) like speakers or headphones, PulseAudio/PipeWire provides a corresponding monitor source that captures whatever is playing.

## Building AppImage

```bash
# Install appimage-builder
pip install appimage-builder

# Build
./build-appimage.sh
```

## License

MIT
