# Implementation Tasks: Real-time Whisper Transcription + Speaker Diarization

## Phase 1: Protocol and Base Structure

### Task 1.1: Add AudioProcessor Protocol
**Priority**: High
**Dependencies**: None
**Estimated Effort**: 30 minutes

- [ ] Add `AudioProcessor` protocol to `audio_recorder/core/protocols.py`
- [ ] Define methods: `start()`, `process(data, timestamp)`, `stop()`, `close()`
- [ ] Add comprehensive docstrings
- [ ] Add type hints using `Protocol` from typing

**Acceptance Criteria**:
- Protocol follows same pattern as `AudioSource` and `AudioWriter`
- Type checking passes with mypy

### Task 1.2: Create Processors Module
**Priority**: High
**Dependencies**: Task 1.1
**Estimated Effort**: 15 minutes

- [ ] Create `audio_recorder/processors/` directory
- [ ] Create `audio_recorder/processors/__init__.py` with exports
- [ ] Add module docstring

**Acceptance Criteria**:
- Module importable: `from audio_recorder.processors import ...`
- No circular import issues

### Task 1.3: Add Transcription Configuration
**Priority**: High
**Dependencies**: None
**Estimated Effort**: 20 minutes

- [ ] Add `TranscriptionConfig` dataclass to `audio_recorder/config.py`
- [ ] Fields: `enabled`, `model_size`, `buffer_seconds`, `output_path`, `speaker_labels`
- [ ] Add to `RecordingConfig` as optional field
- [ ] Update type hints

**Acceptance Criteria**:
- Configuration validates correctly
- Default values are sensible
- Type checking passes

---

## Phase 2: Simple Transcription (No Diarization)

### Task 2.1: Add faster-whisper Dependency
**Priority**: High
**Dependencies**: None
**Estimated Effort**: 10 minutes

- [ ] Add `faster-whisper>=1.0.0` to `pyproject.toml` dependencies
- [ ] Run `uv sync` to install
- [ ] Verify import works: `from faster_whisper import WhisperModel`

**Acceptance Criteria**:
- Dependency installs without errors
- No version conflicts
- Can import successfully

### Task 2.2: Implement WhisperTranscriber
**Priority**: High
**Dependencies**: Task 1.1, Task 1.2, Task 2.1
**Estimated Effort**: 2 hours

- [ ] Create `audio_recorder/processors/whisper_transcriber.py`
- [ ] Implement `WhisperTranscriber` class implementing `AudioProcessor`
- [ ] Add audio buffering logic (accumulate N seconds)
- [ ] Create worker thread for async transcription
- [ ] Implement thread-safe queue for audio chunks
- [ ] Add transcription result writing to text file
- [ ] Handle audio format conversion (stereo → mono, resampling if needed)
- [ ] Add proper error handling for model loading and transcription

**Key Methods**:
```python
def __init__(self, model_size: str, output_path: Path, buffer_seconds: float = 5.0)
def start(self) -> None  # Load model, start worker thread
def process(self, data: NDArray[np.float32], timestamp: float) -> None  # Buffer audio
def stop(self) -> None  # Process remaining buffer, stop worker
def close(self) -> None  # Clean up resources
def _transcribe_worker(self) -> None  # Worker thread main loop
```

**Acceptance Criteria**:
- Implements `AudioProcessor` protocol correctly
- Non-blocking: `process()` returns quickly
- Thread-safe queue handling
- Handles model download on first run
- Writes formatted transcripts with timestamps
- No memory leaks

### Task 2.3: Add Transcription Exceptions
**Priority**: Medium
**Dependencies**: None
**Estimated Effort**: 10 minutes

- [ ] Add `TranscriptionError` exception to `audio_recorder/exceptions.py`
- [ ] Add `ModelLoadError` exception
- [ ] Add proper error messages and docstrings

**Acceptance Criteria**:
- Exceptions inherit from `AudioRecorderError`
- Clear, actionable error messages

### Task 2.4: Integrate Transcriber into RecordingSession
**Priority**: High
**Dependencies**: Task 2.2
**Estimated Effort**: 1 hour

- [ ] Modify `RecordingSession.__init__()` to accept `processors: list[AudioProcessor]`
- [ ] Add processor lifecycle to `run()`: start before recording, stop after
- [ ] Modify `_recording_loop()` to call `processor.process()` for each processor
- [ ] Track elapsed time for accurate timestamps
- [ ] Add error handling for processor failures (log but continue recording)

**Changes**:
- `audio_recorder/core/session.py` line 42: Add `processors` parameter
- `audio_recorder/core/session.py` line 195-200: Add processor.start() calls
- `audio_recorder/core/session.py` line 132-165: Add processor.process() in loop
- `audio_recorder/core/session.py` line 202-206: Add processor.stop() calls

**Acceptance Criteria**:
- Recording works without processors (backward compatible)
- Recording works with 1+ processors
- Processor errors don't crash recording
- Timestamps are accurate

### Task 2.5: Add CLI Flags for Transcription
**Priority**: High
**Dependencies**: Task 2.4
**Estimated Effort**: 30 minutes

- [ ] Add `--transcribe` flag to `audio_recorder/cli/app.py`
- [ ] Add `--model-size` option (choices: tiny, base, small, medium, large)
- [ ] Create `WhisperTranscriber` when `--transcribe` is enabled
- [ ] Auto-generate transcript filename from output path (change .wav to .txt)
- [ ] Update help text

**Acceptance Criteria**:
- `audio-recorder output.wav --transcribe` creates output.txt
- `--model-size` option works correctly
- Help text is clear

### Task 2.6: Test Basic Transcription
**Priority**: High
**Dependencies**: Task 2.5
**Estimated Effort**: 1 hour

- [ ] Create `tests/processors/test_whisper_transcriber.py`
- [ ] Test audio buffering logic (without real model)
- [ ] Test queue handling
- [ ] Test file writing
- [ ] Manual integration test: record 30s with transcription
- [ ] Verify transcript accuracy on test audio
- [ ] Verify timestamps are correct

**Acceptance Criteria**:
- All unit tests pass
- Integration test produces valid transcript
- No performance regression in recording

---

## Phase 3: Speaker Diarization

### Task 3.1: Implement SimpleSpeakerDiarizer
**Priority**: Medium
**Dependencies**: Task 1.1, Task 1.2
**Estimated Effort**: 1.5 hours

- [ ] Create `audio_recorder/processors/speaker_diarizer.py`
- [ ] Implement energy-based speaker identification
- [ ] Calculate RMS energy for mic and monitor streams
- [ ] Determine active speaker based on energy ratio
- [ ] Store speaker events with timestamps
- [ ] Support labels: "User", "System", "Both", "None"

**Key Methods**:
```python
def __init__(self, threshold_ratio: float = 2.0)
def process_streams(
    mic_data: NDArray[np.float32] | None,
    monitor_data: NDArray[np.float32] | None,
    timestamp: float
) -> str  # Returns speaker label
def get_speaker_at_time(self, timestamp: float) -> str
```

**Acceptance Criteria**:
- Correctly identifies dominant speaker
- Handles missing streams (None values)
- Reasonable threshold for speaker switching
- Efficient (< 1ms processing time)

### Task 3.2: Modify Recording Loop for Unmixed Streams
**Priority**: High
**Dependencies**: Task 3.1
**Estimated Effort**: 45 minutes

- [ ] Modify `RecordingSession._recording_loop()` to pass unmixed streams to diarizer
- [ ] Keep mixed audio for transcriber (existing behavior)
- [ ] Add optional `speaker_diarizer` field to `RecordingSession`
- [ ] Call diarizer before mixing, transcriber after mixing

**Changes**:
```python
# In _recording_loop():
speaker = None
if self._diarizer:
    speaker = self._diarizer.process_streams(mic_data, monitor_data, timestamp)

# Mix audio (existing)
mixed = self._mixer.mix(inputs)
self._writer.write(mixed)

# Transcribe with speaker label
for processor in self._processors:
    if isinstance(processor, WhisperTranscriber):
        processor.process(mixed, timestamp, speaker_label=speaker)
    else:
        processor.process(mixed, timestamp)
```

**Acceptance Criteria**:
- Diarizer receives unmixed streams
- Transcriber receives mixed audio + speaker label
- No performance degradation

### Task 3.3: Integrate Speaker Labels into Transcripts
**Priority**: Medium
**Dependencies**: Task 3.2
**Estimated Effort**: 30 minutes

- [ ] Modify `WhisperTranscriber.process()` to accept optional `speaker_label`
- [ ] Store speaker labels with audio chunks
- [ ] Include speaker in transcript output format: `[timestamp - Speaker] text`
- [ ] Handle missing speaker labels gracefully

**Output Format**:
```
[0.00s - User] Hello, this is a test.
[3.45s - System] Audio playback from system.
[7.23s - Both] Overlapping speech.
```

**Acceptance Criteria**:
- Transcript includes speaker labels when available
- Works without speaker labels (backward compatible)
- Format is readable and consistent

### Task 3.4: Add CLI Flag for Speaker Labels
**Priority**: Medium
**Dependencies**: Task 3.3
**Estimated Effort**: 20 minutes

- [ ] Add `--speaker-labels` flag to `audio_recorder/cli/app.py`
- [ ] Create `SimpleSpeakerDiarizer` when flag is enabled
- [ ] Pass to `RecordingSession`
- [ ] Update help text

**Acceptance Criteria**:
- `--speaker-labels` works with or without `--transcribe`
- If used without `--transcribe`, speaker info is logged but not saved

### Task 3.5: Test Speaker Diarization
**Priority**: Medium
**Dependencies**: Task 3.4
**Estimated Effort**: 45 minutes

- [ ] Create `tests/processors/test_speaker_diarizer.py`
- [ ] Test energy calculation with mock audio
- [ ] Test speaker identification logic
- [ ] Manual test: record with mic + system audio, verify speaker labels
- [ ] Test edge cases (silence, both speaking, only one source)

**Acceptance Criteria**:
- Unit tests pass
- Integration test correctly identifies speakers > 80% of time
- No false positives with silence

---

## Phase 4: Polish and Optimization

### Task 4.1: Add Progress Indicators
**Priority**: Low
**Dependencies**: Task 2.5
**Estimated Effort**: 30 minutes

- [ ] Add transcription progress to CLI output
- [ ] Show model loading progress (first run)
- [ ] Show chunks processed vs recorded
- [ ] Update recording status display

**Acceptance Criteria**:
- User can see transcription is working
- No spam in console output
- Clean formatting

### Task 4.2: Optimize Buffering Parameters
**Priority**: Low
**Dependencies**: Task 2.6
**Estimated Effort**: 1 hour

- [ ] Profile transcription latency with different buffer sizes
- [ ] Test model sizes (tiny vs base vs small)
- [ ] Find optimal balance: accuracy vs latency vs CPU
- [ ] Document recommended settings in README
- [ ] Add `--buffer-seconds` CLI option

**Acceptance Criteria**:
- Transcription keeps up with realtime on target hardware
- Latency < 10 seconds behind realtime
- CPU usage < 80% on one core

### Task 4.3: Add Error Handling and Recovery
**Priority**: Medium
**Dependencies**: Task 2.4
**Estimated Effort**: 45 minutes

- [ ] Handle model download failures (no internet)
- [ ] Handle out-of-memory errors
- [ ] Handle slow transcription (queue overflow)
- [ ] Handle file write errors (disk full)
- [ ] Add retry logic where appropriate
- [ ] Log errors clearly

**Acceptance Criteria**:
- Recording never crashes due to transcription errors
- Errors are logged with actionable messages
- Partial transcripts saved even if errors occur

### Task 4.4: Write Documentation
**Priority**: Medium
**Dependencies**: Task 3.4
**Estimated Effort**: 1 hour

- [ ] Update README with transcription features
- [ ] Add usage examples for `--transcribe` and `--speaker-labels`
- [ ] Document model sizes and performance characteristics
- [ ] Add troubleshooting section (model download, performance)
- [ ] Document output format
- [ ] Add limitations section (accuracy, real-time requirements)

**Acceptance Criteria**:
- New users can enable transcription from README
- Troubleshooting covers common issues
- Examples are clear and tested

### Task 4.5: Add Integration Tests
**Priority**: Medium
**Dependencies**: Task 3.5
**Estimated Effort**: 1.5 hours

- [ ] Create `tests/test_transcription_integration.py`
- [ ] Test full recording with transcription
- [ ] Test recording with transcription + speaker labels
- [ ] Test error cases (invalid model size, disk full)
- [ ] Test performance (no frame drops)
- [ ] Verify all existing tests still pass

**Acceptance Criteria**:
- Integration tests cover happy path
- Integration tests cover error cases
- All tests pass consistently
- No flaky tests

---

## Summary

**Total Tasks**: 20
**Estimated Total Effort**: ~14 hours

**Critical Path**:
1. Task 1.1 → 1.2 → 2.1 → 2.2 → 2.4 → 2.5 → 2.6 (Basic transcription)
2. Task 3.1 → 3.2 → 3.3 → 3.4 → 3.5 (Speaker diarization)
3. Task 4.* (Polish and finalize)

**High-Priority Tasks**: 11
**Medium-Priority Tasks**: 7
**Low-Priority Tasks**: 2

**Risks**:
- Whisper performance on target hardware (Task 4.2 mitigates)
- Speaker diarization accuracy (Task 3.5 validates)
- Integration complexity (Task 2.4, 3.2 - careful testing needed)

**Next Steps**:
1. Create PostgreSQL tasks table schema
2. Import these tasks into database
3. Begin implementation with Phase 1
