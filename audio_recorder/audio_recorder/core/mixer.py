"""Audio mixing functionality.

This module combines multiple audio streams into a single output,
applying volume scaling and soft clipping to prevent distortion.
"""

import logging
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


@dataclass
class MixerInput:
    """Configuration for a mixer input channel.

    Attributes:
        name: Identifier for this input (for logging).
        volume: Volume multiplier (0.0 to 1.0).
    """

    name: str
    volume: float = 1.0


class AudioMixer:
    """Mixes multiple audio streams with volume control and soft clipping.

    The mixer averages input streams (to prevent clipping), applies
    per-channel volume multipliers, and uses tanh soft clipping for
    the final output.

    Args:
        channels: Number of audio channels (must match input data).

    Example:
        mixer = AudioMixer(channels=2)
        mixed = mixer.mix([
            (mic_data, MixerInput("mic", volume=0.8)),
            (monitor_data, MixerInput("monitor", volume=0.5)),
        ])
    """

    def __init__(self, channels: int = 2) -> None:
        self._channels = channels

    def mix(
        self,
        inputs: list[tuple[NDArray[np.float32] | None, MixerInput]],
    ) -> NDArray[np.float32] | None:
        """Mix multiple audio streams into one.

        Args:
            inputs: List of (audio_data, mixer_input) tuples.
                    Audio data can be None (treated as silence).

        Returns:
            Mixed audio data, or None if all inputs are None/empty.
        """
        # Filter out None inputs and apply volume
        weighted_chunks = []
        for data, config in inputs:
            if data is None or len(data) == 0:
                continue
            weighted_chunks.append((data * config.volume, config.name))

        if not weighted_chunks:
            return None

        # Find the minimum length (align to shortest chunk)
        min_frames = min(chunk.shape[0] for chunk, _ in weighted_chunks)

        # Trim all chunks to minimum length
        trimmed = [chunk[:min_frames] for chunk, _ in weighted_chunks]

        # Average the streams (dividing prevents clipping)
        mixed = np.mean(trimmed, axis=0).astype(np.float32)

        # Apply soft clipping using tanh
        return self._soft_clip(mixed)

    def mix_with_padding(
        self,
        inputs: list[tuple[NDArray[np.float32] | None, MixerInput]],
    ) -> NDArray[np.float32] | None:
        """Mix streams with zero-padding for shorter chunks.

        Unlike mix(), this preserves all audio by padding shorter
        streams with silence rather than trimming.

        Args:
            inputs: List of (audio_data, mixer_input) tuples.

        Returns:
            Mixed audio data, or None if all inputs are None/empty.
        """
        weighted_chunks = []
        for data, config in inputs:
            if data is None or len(data) == 0:
                continue
            weighted_chunks.append((data * config.volume, config.name))

        if not weighted_chunks:
            return None

        # Find maximum length
        max_frames = max(chunk.shape[0] for chunk, _ in weighted_chunks)

        # Pad all chunks to maximum length
        padded = []
        for chunk, name in weighted_chunks:
            if chunk.shape[0] < max_frames:
                padding = np.zeros(
                    (max_frames - chunk.shape[0], self._channels),
                    dtype=np.float32,
                )
                padded.append(np.concatenate([chunk, padding], axis=0))
            else:
                padded.append(chunk)

        # Average the streams
        mixed = np.mean(padded, axis=0).astype(np.float32)

        return self._soft_clip(mixed)

    def _soft_clip(self, data: NDArray[np.float32]) -> NDArray[np.float32]:
        """Apply soft clipping using tanh to prevent harsh distortion.

        This maps the input range to approximately [-1, 1] with a
        smooth saturation curve.

        Args:
            data: Audio data to clip.

        Returns:
            Soft-clipped audio data.
        """
        return np.tanh(data).astype(np.float32)
