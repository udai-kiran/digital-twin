# Implementation Plan: Real-time Whisper Transcription + Speaker Diarization

## Overview
Add real-time speech-to-text transcription using local Whisper and speaker diarization to identify who is speaking (mic user vs system audio sources).

## Requirements
- Real-time transcription as audio is captured
- Speaker identification (mic = "User", monitor = "System")
- Output: Plain text file with timestamps, speaker labels, and transcribed text
- Non-blocking: transcription must not interfere with audio recording
- Local processing only (no cloud APIs)

## Architecture Design

### 1. New Protocol: AudioProcessor

Create `audio_recorder/core/protocols.py::AudioProcessor`:

```python
class AudioProcessor(Protocol):
    """Protocol for processing audio chunks in real-time.

    Processors receive mixed audio data with timestamps and can perform
    analysis, transcription, or other operations without blocking recording.
    """

    def start(self) -> None:
        """Start the processor (initialize models, threads, etc.)."""
        ...

    def process(self, data: NDArray[np.float32], timestamp: float) -> None:
        """Process an audio chunk.

        Args:
            data: Audio data as float32 array (frames, channels)
            timestamp: Recording timestamp in seconds
        """
        ...

    def stop(self) -> None:
        """Stop the processor and finalize output."""
        ...

    def close(self) -> None:
        """Clean up resources."""
        ...
```

**Rationale**: Follows Dependency Inversion Principle. Session orchestrator depends on abstraction, not concrete implementations.

### 2. New Module: processors/

Create new directory `audio_recorder/processors/` with:

#### 2.1 `processors/whisper_transcriber.py`

**Responsibility**: Convert audio chunks to text using Whisper

**Key Design Points**:
- Uses `faster-whisper` for optimized local inference
- Runs in separate thread to avoid blocking recording
- Accumulates audio chunks (e.g., 5-10 seconds) before transcribing
- Thread-safe queue for audio chunks
- Outputs timestamped segments

**Implementation Strategy**:
```python
class WhisperTranscriber:
    def __init__(self, model_size="base", output_path: Path):
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self.audio_queue = Queue()
        self.worker_thread = Thread(target=self._transcribe_worker, daemon=True)
        self.output_path = output_path
        self.buffer = []  # Accumulate chunks
        self.buffer_duration = 0.0
        self.target_buffer_seconds = 5.0

    def process(self, data: NDArray[np.float32], timestamp: float):
        # Convert to mono, accumulate
        mono = data.mean(axis=1) if data.ndim > 1 else data
        self.buffer.append(mono)
        self.buffer_duration += len(mono) / 48000  # sample rate

        # Once buffer hits target, send to transcription thread
        if self.buffer_duration >= self.target_buffer_seconds:
            audio_chunk = np.concatenate(self.buffer)
            self.audio_queue.put((audio_chunk, timestamp - self.buffer_duration))
            self.buffer.clear()
            self.buffer_duration = 0.0

    def _transcribe_worker(self):
        # Worker thread: transcribe chunks and write to file
        with open(self.output_path, "w") as f:
            while True:
                audio, start_time = self.audio_queue.get()
                segments, info = self.model.transcribe(audio)
                for segment in segments:
                    timestamp = start_time + segment.start
                    f.write(f"[{timestamp:.2f}s] {segment.text}\n")
                    f.flush()
```

#### 2.2 `processors/speaker_diarizer.py`

**Responsibility**: Identify which speaker is talking at each moment

**Key Design Points**:
- Leverages that mic and monitor are separate streams
- Simple approach: Track which stream has dominant audio energy
- Advanced option: Use pyannote.audio for ML-based diarization
- Outputs speaker labels: "User" (mic) or "System" (monitor)

**Implementation Strategy** (Simple Energy-Based):
```python
class SimpleSpeakerDiarizer:
    """Energy-based speaker identification.

    Analyzes mic and monitor streams separately to determine
    which speaker is active at each moment.
    """

    def __init__(self, threshold_ratio=2.0):
        self.threshold_ratio = threshold_ratio
        self.mic_buffer = []
        self.monitor_buffer = []
        self.speaker_events = []  # (timestamp, speaker)

    def process_streams(
        self,
        mic_data: NDArray[np.float32] | None,
        monitor_data: NDArray[np.float32] | None,
        timestamp: float
    ):
        # Calculate RMS energy for each stream
        mic_energy = np.sqrt(np.mean(mic_data**2)) if mic_data is not None else 0.0
        monitor_energy = np.sqrt(np.mean(monitor_data**2)) if monitor_data is not None else 0.0

        # Determine active speaker
        if mic_energy > monitor_energy * self.threshold_ratio:
            speaker = "User"
        elif monitor_energy > mic_energy * self.threshold_ratio:
            speaker = "System"
        else:
            speaker = "Both"

        self.speaker_events.append((timestamp, speaker))
        return speaker
```

**Integration Point**: Diarizer needs access to UNMIXED streams (mic and monitor separately), not the mixed output.

#### 2.3 `processors/transcript_writer.py`

**Responsibility**: Combine transcription + speaker labels into output file

**Key Design Points**:
- Receives transcripts from Whisper
- Receives speaker labels from diarizer
- Merges based on timestamps
- Writes formatted output

**Output Format**:
```
[0.00s - User] Hello, this is a test recording.
[3.45s - System] Audio playback from system.
[7.23s - User] I'm speaking again.
```

### 3. Integration with RecordingSession

**Modification Strategy** (minimize changes to existing code):

1. Add `processors: list[AudioProcessor]` to `RecordingSession.__init__`
2. Modify `_recording_loop()` to call processors after mixing:
   ```python
   while self._running:
       mic_data = self._mic_source.read()
       monitor_data = self._monitor_source.read()

       # Existing mixing logic
       inputs = []
       if mic_data: inputs.append((mic_data, MixerInput("mic", ...)))
       if monitor_data: inputs.append((monitor_data, MixerInput("monitor", ...)))

       if inputs:
           mixed = self._mixer.mix(inputs)
           self._writer.write(mixed)

           # NEW: Process with each processor
           for processor in self._processors:
               processor.process(mixed, self._elapsed_time)
   ```

3. Add lifecycle methods:
   ```python
   def run(self):
       # ... existing setup ...

       # Start processors
       for processor in self._processors:
           processor.start()

       # ... recording loop ...

       # Stop processors
       for processor in self._processors:
           processor.stop()
           processor.close()
   ```

**Challenge**: Diarizer needs UNMIXED streams, not mixed audio.

**Solution**: Pass mic/monitor separately to diarizer:
```python
# In recording loop
if self._diarizer:
    speaker = self._diarizer.process_streams(mic_data, monitor_data, timestamp)

if self._transcriber:
    self._transcriber.process(mixed, timestamp, speaker_label=speaker)
```

### 4. CLI Integration

Add new arguments to `audio_recorder/cli/app.py`:

```python
@click.option("--transcribe", is_flag=True, help="Enable real-time transcription")
@click.option("--model-size",
              type=click.Choice(["tiny", "base", "small", "medium", "large"]),
              default="base",
              help="Whisper model size (default: base)")
@click.option("--speaker-labels", is_flag=True, help="Enable speaker diarization")
def record(
    output: Path,
    # ... existing options ...
    transcribe: bool,
    model_size: str,
    speaker_labels: bool
):
    # Create processors if enabled
    processors = []

    if transcribe:
        transcript_path = output.with_suffix(".txt")
        transcriber = WhisperTranscriber(
            model_size=model_size,
            output_path=transcript_path
        )
        processors.append(transcriber)

    if speaker_labels:
        diarizer = SimpleSpeakerDiarizer()
        processors.append(diarizer)

    session = RecordingSession(config, processors=processors)
    session.run()
```

### 5. Configuration Updates

Add to `audio_recorder/config.py`:

```python
@dataclass
class TranscriptionConfig:
    """Transcription settings."""
    enabled: bool = False
    model_size: str = "base"  # tiny, base, small, medium, large
    buffer_seconds: float = 5.0  # Accumulate N seconds before transcribing
    output_path: Path | None = None
    speaker_labels: bool = False
```

Add to `RecordingConfig`:
```python
@dataclass
class RecordingConfig:
    # ... existing fields ...
    transcription: TranscriptionConfig | None = None
```

### 6. Dependencies to Add

Add to `pyproject.toml`:

```toml
dependencies = [
    "sounddevice>=0.4.6",
    "soundfile>=0.12.0",
    "pulsectl>=23.5.0",
    "numpy>=1.24.0",
    "faster-whisper>=1.0.0",  # NEW: Optimized Whisper
]
```

Optional advanced diarization:
```toml
[project.optional-dependencies]
diarization = [
    "pyannote.audio>=3.1.0",
    "torch>=2.0.0",
]
```

### 7. Threading and Performance Considerations

**Thread Architecture**:
```
Main Thread:
  - Audio capture callbacks (PortAudio)
  - Mixing
  - WAV writing
  - Quick processor.process() calls (just queue audio)

Transcription Thread (WhisperTranscriber):
  - Blocking Whisper inference
  - Writing transcript file

Diarization Thread (if using pyannote):
  - Blocking ML inference
  - Speaker segmentation
```

**Performance Targets**:
- Whisper "base" model: ~1-2x realtime on modern CPU
- Buffer 5-10 seconds before transcribing to batch work
- Main recording loop should stay under 10ms per iteration

**Memory Management**:
- Limit queue sizes (max 100 chunks)
- Clear buffers after transcription
- Use int8 quantization for Whisper model

### 8. Error Handling

Add new exception types in `audio_recorder/exceptions.py`:

```python
class TranscriptionError(AudioRecorderError):
    """Raised when transcription fails."""

class ModelLoadError(TranscriptionError):
    """Raised when Whisper model cannot be loaded."""
```

Handle gracefully:
- Model download failures (first run)
- Out of memory errors
- Slow transcription (falling behind realtime)
- File write errors

### 9. Testing Strategy

**Unit Tests**:
- `tests/processors/test_whisper_transcriber.py`
  - Test audio buffering logic
  - Test queue handling
  - Mock Whisper model
- `tests/processors/test_speaker_diarizer.py`
  - Test energy calculation
  - Test speaker identification logic

**Integration Tests**:
- `tests/test_transcription_integration.py`
  - Record 10 seconds with transcription enabled
  - Verify transcript file created
  - Verify timestamps are reasonable

**Manual Verification**:
1. Record with `--transcribe --speaker-labels`
2. Verify .txt file has correct format
3. Check transcript accuracy
4. Verify speaker labels are correct

### 10. Implementation Steps (In Order)

**Phase 1: Protocol and Base Structure**
1. Add `AudioProcessor` protocol to `core/protocols.py`
2. Create `processors/__init__.py` module
3. Add configuration classes to `config.py`

**Phase 2: Simple Transcription (No Diarization)**
4. Implement `WhisperTranscriber` with buffering
5. Add `faster-whisper` dependency
6. Integrate into `RecordingSession._recording_loop()`
7. Add `--transcribe` CLI flag
8. Test basic transcription

**Phase 3: Speaker Diarization**
9. Implement `SimpleSpeakerDiarizer` (energy-based)
10. Modify recording loop to pass unmixed streams
11. Integrate speaker labels into transcript output
12. Add `--speaker-labels` CLI flag
13. Test speaker identification

**Phase 4: Polish and Optimization**
14. Add progress indicators for transcription
15. Optimize buffering parameters
16. Add error handling and recovery
17. Write documentation
18. Add tests

### 11. File Structure After Implementation

```
audio_recorder/
├── core/
│   ├── protocols.py          # ADD: AudioProcessor protocol
│   ├── session.py            # MODIFY: Add processor integration
│   ├── mixer.py              # No changes
├── processors/               # NEW MODULE
│   ├── __init__.py
│   ├── whisper_transcriber.py
│   ├── speaker_diarizer.py
│   └── transcript_writer.py
├── sources/                  # No changes
├── writers/                  # No changes
├── cli/
│   └── app.py               # MODIFY: Add CLI flags
├── config.py                # MODIFY: Add TranscriptionConfig
├── exceptions.py            # ADD: Transcription exceptions
└── __main__.py              # No changes

tests/
├── processors/              # NEW TEST MODULE
│   ├── test_whisper_transcriber.py
│   └── test_speaker_diarizer.py
└── test_transcription_integration.py
```

### 12. SOLID Principles Adherence

**Single Responsibility**:
- `WhisperTranscriber`: Only transcribes audio
- `SpeakerDiarizer`: Only identifies speakers
- `TranscriptWriter`: Only formats and writes output
- `RecordingSession`: Orchestrates (doesn't do transcription itself)

**Open/Closed**:
- New processors can be added without modifying existing code
- Just implement `AudioProcessor` protocol

**Liskov Substitution**:
- All `AudioProcessor` implementations are interchangeable
- Session doesn't care about specific processor types

**Interface Segregation**:
- `AudioProcessor` is focused (start, process, stop, close)
- No fat interfaces

**Dependency Inversion**:
- `RecordingSession` depends on `AudioProcessor` protocol
- Not coupled to concrete transcriber implementation

### 13. Verification Steps

After implementation, verify:

1. **Recording still works without transcription**:
   ```bash
   audio-recorder output.wav --duration 10
   # Should produce output.wav as before
   ```

2. **Transcription works**:
   ```bash
   audio-recorder output.wav --transcribe --duration 30
   # Should produce output.wav + output.txt
   ```

3. **Speaker labels work**:
   ```bash
   audio-recorder output.wav --transcribe --speaker-labels --duration 30
   # output.txt should have speaker labels
   ```

4. **Model selection works**:
   ```bash
   audio-recorder output.wav --transcribe --model-size small
   # Should use small model (faster, less accurate)
   ```

5. **Performance check**:
   - Recording should not stutter or drop frames
   - Transcription thread should not block recording
   - CPU usage reasonable (< 80% on one core)

6. **Error handling**:
   - Test with no internet (first run, model download)
   - Test with low disk space
   - Test with invalid model size

## Risk Assessment

**High Risk**:
- Whisper model size/performance on target hardware
- Real-time performance (falling behind realtime)

**Medium Risk**:
- Model download on first run (needs internet)
- Speaker diarization accuracy with energy-based approach

**Low Risk**:
- Integration with existing code (minimal changes)
- Threading correctness (using existing queue pattern)

## Success Criteria

1. Recording quality unchanged (no dropped frames)
2. Transcription accuracy > 90% for clear speech
3. Speaker labels correct > 80% of the time
4. Performance: < 100ms latency added to recording loop
5. Zero crashes or hangs during 1-hour recording
6. All existing tests still pass
7. New features documented in README

## Notes

- Start with simple energy-based diarization; can upgrade to pyannote later
- Consider adding `--no-realtime` flag for offline transcription (process WAV after recording)
- Future: Add support for multiple speakers beyond User/System
- Future: Add support for exporting to SRT/VTT subtitle formats
