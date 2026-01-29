"""Simple energy-based speaker diarization.

This module provides SimpleSpeakerDiarizer, which identifies speakers
(User vs System) based on RMS energy comparison between microphone
and monitor audio streams.
"""

import logging

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class SimpleSpeakerDiarizer:
    """Simple energy-based speaker diarization.

    Identifies who's speaking by comparing energy levels between
    microphone (User) and monitor (System) audio streams.

    Algorithm:
        1. Calculate RMS energy for each stream
        2. Compare energy ratio
        3. If one stream is significantly louder (threshold ratio),
           it's the dominant speaker
        4. If both are similar, return "Both"
        5. If both are quiet, return "None"

    Args:
        energy_threshold: Minimum RMS energy to consider as speech (default: 0.01).
        ratio_threshold: Energy ratio to determine dominant speaker (default: 2.0).

    Example:
        diarizer = SimpleSpeakerDiarizer(energy_threshold=0.01, ratio_threshold=2.0)
        speaker = diarizer.process_streams(mic_data, monitor_data, timestamp=0.0)
        # Returns: "User", "System", "Both", or "None"
    """

    def __init__(self, energy_threshold: float = 0.01, ratio_threshold: float = 2.0) -> None:
        self._energy_threshold = energy_threshold
        self._ratio_threshold = ratio_threshold

    def process_streams(
        self,
        mic_data: NDArray[np.float32] | None,
        monitor_data: NDArray[np.float32] | None,
        timestamp: float,
    ) -> str:
        """Identify the speaker from audio streams.

        Args:
            mic_data: Microphone audio data with shape (frames, channels).
            monitor_data: Monitor audio data with shape (frames, channels).
            timestamp: Recording timestamp in seconds (for logging).

        Returns:
            Speaker label: "User", "System", "Both", or "None".
        """
        # Calculate RMS energy for each stream
        mic_energy = self._calculate_rms(mic_data) if mic_data is not None else 0.0
        monitor_energy = self._calculate_rms(monitor_data) if monitor_data is not None else 0.0

        # Check if both streams are quiet
        if mic_energy < self._energy_threshold and monitor_energy < self._energy_threshold:
            return "None"

        # Check if only one stream has audio
        if mic_energy < self._energy_threshold:
            return "System"
        if monitor_energy < self._energy_threshold:
            return "User"

        # Compare energy ratio
        ratio = mic_energy / monitor_energy if monitor_energy > 0 else float("inf")

        if ratio > self._ratio_threshold:
            # Microphone is significantly louder
            return "User"
        elif ratio < (1.0 / self._ratio_threshold):
            # Monitor is significantly louder
            return "System"
        else:
            # Both streams have similar energy
            return "Both"

    def _calculate_rms(self, data: NDArray[np.float32]) -> float:
        """Calculate RMS (Root Mean Square) energy of audio data.

        Args:
            data: Audio data with shape (frames, channels).

        Returns:
            RMS energy as a float.
        """
        if data is None or len(data) == 0:
            return 0.0

        # Calculate RMS: sqrt(mean(signal^2))
        rms = np.sqrt(np.mean(data**2))
        return float(rms)
