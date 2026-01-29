"""Audio processors for real-time transcription and analysis.

This module provides processors that can be attached to recording sessions
to perform operations like transcription and speaker diarization.
"""

from audio_recorder.processors.speaker_diarizer import SimpleSpeakerDiarizer
from audio_recorder.processors.whisper_transcriber import WhisperTranscriber

__all__ = ["WhisperTranscriber", "SimpleSpeakerDiarizer"]
