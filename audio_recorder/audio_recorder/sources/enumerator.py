"""Device enumeration using sounddevice and PulseAudio/PipeWire.

This module discovers available audio devices through sounddevice (PortAudio)
and uses pulsectl to identify monitor sources for system audio capture.
"""

from dataclasses import dataclass

import pulsectl
import sounddevice as sd

from audio_recorder.exceptions import DeviceNotFoundError, NoDevicesAvailableError


@dataclass(frozen=True)
class AudioDevice:
    """Represents an audio device.

    Attributes:
        index: Sounddevice device index.
        name: Device name as seen by sounddevice.
        description: Human-readable description.
        is_monitor: Whether this is a monitor source (for system audio capture).
        is_default: Whether this is the default device.
        input_channels: Number of input channels.
    """

    index: int
    name: str
    description: str
    is_monitor: bool = False
    is_default: bool = False
    input_channels: int = 2

    def __str__(self) -> str:
        markers = []
        if self.is_default:
            markers.append("default")
        if self.is_monitor:
            markers.append("monitor")
        suffix = f" [{', '.join(markers)}]" if markers else ""
        return f"{self.description}{suffix}"


class DeviceEnumerator:
    """Enumerates and selects audio devices.

    Uses sounddevice for device enumeration (PortAudio) and pulsectl
    to identify which devices are monitor sources.

    Example:
        with DeviceEnumerator() as enumerator:
            mics = enumerator.list_microphones()
            monitors = enumerator.list_monitors()
    """

    def __init__(self) -> None:
        self._pulse: pulsectl.Pulse | None = None
        self._monitor_names: set[str] = set()

    def __enter__(self) -> "DeviceEnumerator":
        self._pulse = pulsectl.Pulse("audio-recorder-enumerator")
        self._load_monitor_names()
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> None:
        if self._pulse is not None:
            self._pulse.close()
            self._pulse = None

    def _load_monitor_names(self) -> None:
        """Load monitor source names from PulseAudio for identification."""
        if self._pulse is None:
            return

        # Get sink descriptions to identify monitors
        for sink in self._pulse.sink_list():
            # Store the description part that would appear in sounddevice
            desc = sink.description or sink.name
            self._monitor_names.add(desc)

    def _is_monitor_device(self, device_name: str) -> bool:
        """Check if a sounddevice device is a monitor source.

        Monitor sources in PipeWire/JACK have both input and output channels
        and match a sink's description.
        """
        # Check if the device name matches any known sink description
        for monitor_desc in self._monitor_names:
            if monitor_desc in device_name:
                return True
        return False

    def _get_default_device_index(self, kind: str) -> int | None:
        """Get the default device index for input or output."""
        try:
            default = sd.query_devices(kind=kind)
            if isinstance(default, dict):
                return default.get("index")
        except sd.PortAudioError:
            pass
        return None

    def _query_input_devices(self) -> list[dict]:
        """Get all devices with input capability."""
        devices = sd.query_devices()
        if isinstance(devices, dict):
            devices = [devices]

        return [
            {**d, "index": i}
            for i, d in enumerate(devices)
            if d.get("max_input_channels", 0) > 0
        ]

    def list_microphones(self) -> list[AudioDevice]:
        """List available microphone sources (non-monitor inputs).

        Returns:
            List of AudioDevice objects representing microphones.

        Raises:
            NoDevicesAvailableError: If no microphones are available.
        """
        default_idx = self._get_default_device_index("input")
        devices = []

        for d in self._query_input_devices():
            name = d["name"]
            idx = d["index"]

            # Skip generic/virtual devices that aren't real microphones
            if name in ("sysdefault", "pipewire", "default", "spdif"):
                continue

            # Skip devices that are monitors (have both in and out, and match a sink)
            is_monitor = (
                d.get("max_output_channels", 0) > 0 and self._is_monitor_device(name)
            )
            if is_monitor:
                continue

            devices.append(
                AudioDevice(
                    index=idx,
                    name=name,
                    description=name,
                    is_monitor=False,
                    is_default=(idx == default_idx),
                    input_channels=d.get("max_input_channels", 2),
                )
            )

        if not devices:
            raise NoDevicesAvailableError("microphone")

        return devices

    def list_monitors(self) -> list[AudioDevice]:
        """List available monitor sources (for capturing system audio).

        Monitor sources capture audio output from sinks (speakers/headphones).
        In PipeWire, these appear as devices with both input and output channels.

        Returns:
            List of AudioDevice objects representing monitor sources.

        Raises:
            NoDevicesAvailableError: If no monitors are available.
        """
        devices = []
        default_sink_desc = None

        # Get default sink description from PulseAudio
        if self._pulse:
            try:
                default_sink_name = self._pulse.server_info().default_sink_name
                for sink in self._pulse.sink_list():
                    if sink.name == default_sink_name:
                        default_sink_desc = sink.description
                        break
            except pulsectl.PulseError:
                pass

        for d in self._query_input_devices():
            name = d["name"]
            idx = d["index"]

            # Skip generic/virtual devices
            if name in ("sysdefault", "pipewire", "default", "spdif"):
                continue

            # Monitors have both input and output channels and match a sink
            has_output = d.get("max_output_channels", 0) > 0
            matches_sink = self._is_monitor_device(name)

            if has_output and matches_sink:
                is_default = default_sink_desc is not None and default_sink_desc in name

                devices.append(
                    AudioDevice(
                        index=idx,
                        name=name,
                        description=f"{name} (Monitor)",
                        is_monitor=True,
                        is_default=is_default,
                        input_channels=d.get("max_input_channels", 2),
                    )
                )

        if not devices:
            raise NoDevicesAvailableError("monitor")

        return devices

    def get_default_microphone(self) -> AudioDevice:
        """Get the default microphone device.

        Returns:
            The default microphone AudioDevice.

        Raises:
            NoDevicesAvailableError: If no microphones are available.
        """
        mics = self.list_microphones()
        for mic in mics:
            if mic.is_default:
                return mic
        return mics[0]

    def get_default_monitor(self) -> AudioDevice:
        """Get the default monitor source (for system audio).

        Returns:
            The default monitor AudioDevice.

        Raises:
            NoDevicesAvailableError: If no monitors are available.
        """
        monitors = self.list_monitors()
        for monitor in monitors:
            if monitor.is_default:
                return monitor
        return monitors[0]

    def find_microphone(self, name_or_desc: str) -> AudioDevice:
        """Find a microphone by name or description substring.

        Args:
            name_or_desc: Full or partial device name/description to match.

        Returns:
            Matching AudioDevice.

        Raises:
            DeviceNotFoundError: If no matching microphone is found.
        """
        search = name_or_desc.lower()
        for mic in self.list_microphones():
            if search in mic.name.lower() or search in mic.description.lower():
                return mic
        raise DeviceNotFoundError(name_or_desc, "microphone")

    def find_monitor(self, name_or_desc: str) -> AudioDevice:
        """Find a monitor source by name or description substring.

        Args:
            name_or_desc: Full or partial device name/description to match.

        Returns:
            Matching AudioDevice.

        Raises:
            DeviceNotFoundError: If no matching monitor is found.
        """
        search = name_or_desc.lower()
        for monitor in self.list_monitors():
            if search in monitor.name.lower() or search in monitor.description.lower():
                return monitor
        raise DeviceNotFoundError(name_or_desc, "monitor")
