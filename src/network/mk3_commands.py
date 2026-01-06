"""
MK3 DSP Amplifier IP Command Database

This module defines all IP control commands for Sonance MK3 DSP amplifiers.
Based on Sonance IP Codes documentation V1.3 (Feb 2016).

Protocol: TCP port 52000
Format: All commands start with header FF 55
- 1-byte payload: FF 55 01 <cmd> - Global commands
- 2-byte payload: FF 55 02 <cmd> <index> - Per-group/channel commands

Models supported:
- DSP8-130: 8 channels (4 stereo pairs), 8 output groups (A-H)
- DSP2-150: 2 channels (1 stereo pair), 2 output groups (A-B)
- DSP2-750: 2 channels (1 stereo pair), 2 output groups (A-B)
"""

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Dict, List, Optional, Tuple
import struct


# =============================================================================
# CONSTANTS
# =============================================================================

MK3_PORT = 52000
HEADER = bytes([0xFF, 0x55])


# =============================================================================
# ENUMS
# =============================================================================

class MK3Model(Enum):
    """MK3 DSP amplifier models."""
    DSP8_130 = "DSP8-130"
    DSP2_150 = "DSP2-150"
    DSP2_750 = "DSP2-750"
    UNKNOWN = "Unknown"


class OutputGroup(IntEnum):
    """Output group indices (0-7 for 8-channel, 0-1 for 2-channel)."""
    A = 0
    B = 1
    C = 2
    D = 3
    E = 4
    F = 5
    G = 6
    H = 7


class OutputChannel(IntEnum):
    """Physical output channel indices for protection/DSP queries."""
    CH1_LEFT = 0x08
    CH1_RIGHT = 0x09
    CH2_LEFT = 0x0A
    CH2_RIGHT = 0x0B
    CH3_LEFT = 0x0C
    CH3_RIGHT = 0x0D
    CH4_LEFT = 0x0E
    CH4_RIGHT = 0x0F


class InputSource(IntEnum):
    """Input source selection."""
    SOURCE_1 = 1
    SOURCE_2 = 2
    SOURCE_3 = 3
    SOURCE_4 = 4


class ThermalState(Enum):
    """Amplifier thermal states."""
    NORMAL = "Normal Temp"
    OVERTEMP = "Over Temp"
    UNKNOWN = "Unknown"


class ProtectState(Enum):
    """Short circuit protection states."""
    NO_SHORT = "No short"
    SHORT_DETECTED = "Short"
    UNKNOWN = "Unknown"


# =============================================================================
# COMMAND CODES
# =============================================================================

class PowerCmd:
    """Power control command codes."""
    ON = 0x01
    OFF = 0x02
    TOGGLE = 0x03
    QUERY = 0x70


class GlobalCmd:
    """Global (all groups) command codes."""
    VOLUME_UP = 0x04
    VOLUME_DOWN = 0x05
    MUTE_TOGGLE = 0x06
    MUTE_ON = 0x07
    MUTE_OFF = 0x08
    SOURCE_1 = 0x09
    SOURCE_2 = 0x0A
    SOURCE_3 = 0x0B
    SOURCE_4 = 0x0C
    RETURN_TO_TURN_ON_VOL = 0x0D
    VOLUME_UP_3DB = 0x0E
    VOLUME_DOWN_3DB = 0x0F
    GROUP_POWER_ON = 0x65
    GROUP_POWER_OFF = 0x66
    GROUP_POWER_TOGGLE = 0x67


class GroupCmd:
    """Per-group command codes (add group index as 2nd byte)."""
    VOLUME_UP = 0x04
    VOLUME_DOWN = 0x05
    MUTE_TOGGLE = 0x06
    MUTE_ON = 0x07
    MUTE_OFF = 0x08
    SOURCE_1 = 0x09
    SOURCE_2 = 0x0A
    SOURCE_3 = 0x0B
    SOURCE_4 = 0x0C
    RETURN_TO_TURN_ON_VOL = 0x0D
    VOLUME_UP_3DB = 0x0E
    VOLUME_DOWN_3DB = 0x0F
    POWER_ON = 0x65
    POWER_OFF = 0x66
    POWER_TOGGLE = 0x67


class QueryCmd:
    """Query command codes."""
    # Global
    POWER_STATUS = 0x70

    # Per-group (add group index)
    VOLUME = 0x10
    SOURCE = 0x11
    MUTE_STATE = 0x12

    # Per-channel (add channel index 0x08-0x0F)
    DSP_PRESET = 0x16
    SHORT_PROTECT = 0x17
    OVERTEMP = 0x18


# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

@dataclass
class ModelConfig:
    """Configuration for a specific MK3 model."""
    name: str
    channels: int
    groups: List[str]
    stereo_pairs: int

    @property
    def group_indices(self) -> List[OutputGroup]:
        """Get list of valid group indices for this model."""
        return [OutputGroup(i) for i in range(len(self.groups))]

    @property
    def channel_indices(self) -> List[OutputChannel]:
        """Get list of valid channel indices for this model."""
        channels = []
        for i in range(self.stereo_pairs):
            channels.append(OutputChannel(0x08 + i * 2))      # Left
            channels.append(OutputChannel(0x08 + i * 2 + 1))  # Right
        return channels


MODEL_CONFIGS: Dict[MK3Model, ModelConfig] = {
    MK3Model.DSP8_130: ModelConfig(
        name="DSP8-130",
        channels=8,
        groups=['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],
        stereo_pairs=4
    ),
    MK3Model.DSP2_150: ModelConfig(
        name="DSP2-150",
        channels=2,
        groups=['A', 'B'],
        stereo_pairs=1
    ),
    MK3Model.DSP2_750: ModelConfig(
        name="DSP2-750",
        channels=2,
        groups=['A', 'B'],
        stereo_pairs=1
    ),
}


# =============================================================================
# VOLUME CONVERSION
# =============================================================================

def volume_db_to_hex(db: int) -> int:
    """
    Convert volume in dB to hex command byte.

    Volume range: -70dB to 0dB
    Hex range: 0x71 (-70dB) to 0xB6 (0dB)

    Formula: hex = 0x71 + (db + 70)
    """
    if db < -70:
        db = -70
    elif db > 0:
        db = 0
    return 0x71 + (db + 70)


def volume_hex_to_db(hex_val: int) -> int:
    """
    Convert hex volume byte back to dB.

    Formula: db = (hex - 0x71) - 70
    """
    return (hex_val - 0x71) - 70


# =============================================================================
# COMMAND BUILDERS
# =============================================================================

class MK3CommandBuilder:
    """Builder for MK3 binary commands."""

    @staticmethod
    def _build_global(cmd: int) -> bytes:
        """Build a global (1-byte payload) command."""
        return HEADER + bytes([0x01, cmd])

    @staticmethod
    def _build_group(cmd: int, group: OutputGroup) -> bytes:
        """Build a per-group (2-byte payload) command."""
        return HEADER + bytes([0x02, cmd, group])

    @staticmethod
    def _build_channel(cmd: int, channel: OutputChannel) -> bytes:
        """Build a per-channel (2-byte payload) command."""
        return HEADER + bytes([0x02, cmd, channel])

    # -------------------------------------------------------------------------
    # Power Commands
    # -------------------------------------------------------------------------

    @classmethod
    def power_on(cls) -> bytes:
        """Turn amplifier on."""
        return cls._build_global(PowerCmd.ON)

    @classmethod
    def power_off(cls) -> bytes:
        """Turn amplifier off (standby)."""
        return cls._build_global(PowerCmd.OFF)

    @classmethod
    def power_toggle(cls) -> bytes:
        """Toggle amplifier power."""
        return cls._build_global(PowerCmd.TOGGLE)

    @classmethod
    def power_query(cls) -> bytes:
        """Query amplifier power status."""
        return cls._build_global(PowerCmd.QUERY)

    # -------------------------------------------------------------------------
    # Global Commands (All Groups)
    # -------------------------------------------------------------------------

    @classmethod
    def global_volume_up(cls) -> bytes:
        """Increase volume on all groups."""
        return cls._build_global(GlobalCmd.VOLUME_UP)

    @classmethod
    def global_volume_down(cls) -> bytes:
        """Decrease volume on all groups."""
        return cls._build_global(GlobalCmd.VOLUME_DOWN)

    @classmethod
    def global_volume_up_3db(cls) -> bytes:
        """Increase volume by 3dB on all groups."""
        return cls._build_global(GlobalCmd.VOLUME_UP_3DB)

    @classmethod
    def global_volume_down_3db(cls) -> bytes:
        """Decrease volume by 3dB on all groups."""
        return cls._build_global(GlobalCmd.VOLUME_DOWN_3DB)

    @classmethod
    def global_mute_toggle(cls) -> bytes:
        """Toggle mute on all groups."""
        return cls._build_global(GlobalCmd.MUTE_TOGGLE)

    @classmethod
    def global_mute_on(cls) -> bytes:
        """Mute all groups."""
        return cls._build_global(GlobalCmd.MUTE_ON)

    @classmethod
    def global_mute_off(cls) -> bytes:
        """Unmute all groups."""
        return cls._build_global(GlobalCmd.MUTE_OFF)

    @classmethod
    def global_source(cls, source: InputSource) -> bytes:
        """Set input source for all groups."""
        cmd = GlobalCmd.SOURCE_1 + (source - 1)
        return cls._build_global(cmd)

    @classmethod
    def global_return_to_turn_on_volume(cls) -> bytes:
        """Return all groups to turn-on volume."""
        return cls._build_global(GlobalCmd.RETURN_TO_TURN_ON_VOL)

    @classmethod
    def global_group_power_on(cls) -> bytes:
        """Turn on all groups."""
        return cls._build_global(GlobalCmd.GROUP_POWER_ON)

    @classmethod
    def global_group_power_off(cls) -> bytes:
        """Turn off all groups."""
        return cls._build_global(GlobalCmd.GROUP_POWER_OFF)

    @classmethod
    def global_volume_set(cls, db: int) -> bytes:
        """Set volume level (dB) for all groups. Range: -70 to 0."""
        vol_cmd = volume_db_to_hex(db)
        return cls._build_global(vol_cmd)

    # -------------------------------------------------------------------------
    # Per-Group Commands
    # -------------------------------------------------------------------------

    @classmethod
    def group_power_on(cls, group: OutputGroup) -> bytes:
        """Turn on a specific group."""
        return cls._build_group(GroupCmd.POWER_ON, group)

    @classmethod
    def group_power_off(cls, group: OutputGroup) -> bytes:
        """Turn off a specific group."""
        return cls._build_group(GroupCmd.POWER_OFF, group)

    @classmethod
    def group_power_toggle(cls, group: OutputGroup) -> bytes:
        """Toggle power for a specific group."""
        return cls._build_group(GroupCmd.POWER_TOGGLE, group)

    @classmethod
    def group_volume_up(cls, group: OutputGroup) -> bytes:
        """Increase volume on a specific group."""
        return cls._build_group(GroupCmd.VOLUME_UP, group)

    @classmethod
    def group_volume_down(cls, group: OutputGroup) -> bytes:
        """Decrease volume on a specific group."""
        return cls._build_group(GroupCmd.VOLUME_DOWN, group)

    @classmethod
    def group_volume_up_3db(cls, group: OutputGroup) -> bytes:
        """Increase volume by 3dB on a specific group."""
        return cls._build_group(GroupCmd.VOLUME_UP_3DB, group)

    @classmethod
    def group_volume_down_3db(cls, group: OutputGroup) -> bytes:
        """Decrease volume by 3dB on a specific group."""
        return cls._build_group(GroupCmd.VOLUME_DOWN_3DB, group)

    @classmethod
    def group_volume_set(cls, group: OutputGroup, db: int) -> bytes:
        """Set volume level (dB) for a specific group. Range: -70 to 0."""
        vol_cmd = volume_db_to_hex(db)
        return cls._build_group(vol_cmd, group)

    @classmethod
    def group_mute_toggle(cls, group: OutputGroup) -> bytes:
        """Toggle mute on a specific group."""
        return cls._build_group(GroupCmd.MUTE_TOGGLE, group)

    @classmethod
    def group_mute_on(cls, group: OutputGroup) -> bytes:
        """Mute a specific group."""
        return cls._build_group(GroupCmd.MUTE_ON, group)

    @classmethod
    def group_mute_off(cls, group: OutputGroup) -> bytes:
        """Unmute a specific group."""
        return cls._build_group(GroupCmd.MUTE_OFF, group)

    @classmethod
    def group_source(cls, group: OutputGroup, source: InputSource) -> bytes:
        """Set input source for a specific group."""
        cmd = GroupCmd.SOURCE_1 + (source - 1)
        return cls._build_group(cmd, group)

    @classmethod
    def group_return_to_turn_on_volume(cls, group: OutputGroup) -> bytes:
        """Return a specific group to turn-on volume."""
        return cls._build_group(GroupCmd.RETURN_TO_TURN_ON_VOL, group)

    # -------------------------------------------------------------------------
    # Query Commands
    # -------------------------------------------------------------------------

    @classmethod
    def query_group_volume(cls, group: OutputGroup) -> bytes:
        """Query volume level of a specific group."""
        return cls._build_group(QueryCmd.VOLUME, group)

    @classmethod
    def query_group_source(cls, group: OutputGroup) -> bytes:
        """Query input source of a specific group."""
        return cls._build_group(QueryCmd.SOURCE, group)

    @classmethod
    def query_group_mute(cls, group: OutputGroup) -> bytes:
        """Query mute state of a specific group."""
        return cls._build_group(QueryCmd.MUTE_STATE, group)

    @classmethod
    def query_channel_dsp_preset(cls, channel: OutputChannel) -> bytes:
        """Query DSP preset for a specific output channel."""
        return cls._build_channel(QueryCmd.DSP_PRESET, channel)

    @classmethod
    def query_channel_short_protect(cls, channel: OutputChannel) -> bytes:
        """Query short circuit protection status for a channel."""
        return cls._build_channel(QueryCmd.SHORT_PROTECT, channel)

    @classmethod
    def query_channel_overtemp(cls, channel: OutputChannel) -> bytes:
        """Query over-temperature status for a channel."""
        return cls._build_channel(QueryCmd.OVERTEMP, channel)


# =============================================================================
# RESPONSE PARSER
# =============================================================================

@dataclass
class MK3Response:
    """Parsed response from MK3 amplifier."""
    raw: str
    command_type: str
    success: bool
    value: Optional[str] = None
    group: Optional[str] = None
    channel: Optional[str] = None
    error: Optional[str] = None


class MK3ResponseParser:
    """Parser for MK3 amplifier responses."""

    @staticmethod
    def parse(response: str) -> MK3Response:
        """
        Parse a response string from the MK3 amplifier.

        Response formats:
        - Power status: "Power status :On" or "Power status :Off"
        - Volume: "Cmd:Volume,Group:A Vol=-30 d"
        - Source: "Cmd:Source1,Group:A Src1=Input 1L"
        - Mute: "Cmd:MuteState,Group:A Mute=off"
        - DSP Preset: "Cmd:DSP_Preset:FLAT,Channel Output 1L"
        - Short protect: "Cmd:AmpShortCir:No short,Channel Output 1L"
        - Overtemp: "Cmd:AmpOverTemp:Normal Temp,Channel Output 1L"
        """
        response = response.strip()

        # Power status
        if "Power status" in response:
            is_on = ":On" in response or ": On" in response
            return MK3Response(
                raw=response,
                command_type="power_status",
                success=True,
                value="On" if is_on else "Off"
            )

        # Volume query response
        if "Cmd:Volume" in response:
            try:
                # Extract group
                group = None
                if "Group:" in response:
                    group_part = response.split("Group:")[1]
                    group = group_part[0]  # First character is group letter

                # Extract volume
                vol = None
                if "Vol=" in response:
                    vol_part = response.split("Vol=")[1]
                    vol = vol_part.split()[0]  # Get number before space

                return MK3Response(
                    raw=response,
                    command_type="volume",
                    success=True,
                    value=vol,
                    group=group
                )
            except Exception as e:
                return MK3Response(
                    raw=response,
                    command_type="volume",
                    success=False,
                    error=str(e)
                )

        # Mute state response
        if "MuteState" in response:
            try:
                group = None
                if "Group:" in response:
                    group_part = response.split("Group:")[1]
                    group = group_part[0]

                mute_state = "on" if "Mute=on" in response.lower() else "off"

                return MK3Response(
                    raw=response,
                    command_type="mute_state",
                    success=True,
                    value=mute_state,
                    group=group
                )
            except Exception as e:
                return MK3Response(
                    raw=response,
                    command_type="mute_state",
                    success=False,
                    error=str(e)
                )

        # Source response
        if "Cmd:Source" in response:
            try:
                group = None
                if "Group:" in response:
                    group_part = response.split("Group:")[1]
                    group = group_part[0]

                source = None
                if "Src1=" in response:
                    source_part = response.split("Src1=")[1]
                    source = source_part.strip()

                return MK3Response(
                    raw=response,
                    command_type="source",
                    success=True,
                    value=source,
                    group=group
                )
            except Exception as e:
                return MK3Response(
                    raw=response,
                    command_type="source",
                    success=False,
                    error=str(e)
                )

        # Short circuit protection response
        if "AmpShortCir" in response:
            try:
                channel = None
                if "Channel Output" in response:
                    channel = response.split("Channel Output")[1].strip()

                has_short = "short" in response.lower() and "no short" not in response.lower()

                return MK3Response(
                    raw=response,
                    command_type="short_protect",
                    success=True,
                    value="Short detected" if has_short else "No short",
                    channel=channel
                )
            except Exception as e:
                return MK3Response(
                    raw=response,
                    command_type="short_protect",
                    success=False,
                    error=str(e)
                )

        # Over-temperature response
        if "AmpOverTemp" in response:
            try:
                channel = None
                if "Channel Output" in response:
                    channel = response.split("Channel Output")[1].strip()

                is_overtemp = "over temp" in response.lower() or "overtemp" in response.lower()
                is_normal = "normal" in response.lower()

                if is_normal:
                    state = "Normal"
                elif is_overtemp:
                    state = "Over Temp"
                else:
                    state = "Unknown"

                return MK3Response(
                    raw=response,
                    command_type="overtemp",
                    success=True,
                    value=state,
                    channel=channel
                )
            except Exception as e:
                return MK3Response(
                    raw=response,
                    command_type="overtemp",
                    success=False,
                    error=str(e)
                )

        # DSP Preset response
        if "DSP_Preset" in response:
            try:
                channel = None
                if "Channel Output" in response:
                    channel = response.split("Channel Output")[1].strip()

                preset = None
                if ":" in response:
                    parts = response.split(":")
                    if len(parts) >= 2:
                        preset = parts[1].split(",")[0].strip()

                return MK3Response(
                    raw=response,
                    command_type="dsp_preset",
                    success=True,
                    value=preset,
                    channel=channel
                )
            except Exception as e:
                return MK3Response(
                    raw=response,
                    command_type="dsp_preset",
                    success=False,
                    error=str(e)
                )

        # Generic/unknown response
        return MK3Response(
            raw=response,
            command_type="unknown",
            success=True,
            value=response
        )


# =============================================================================
# COMMAND PRESETS FOR GUI
# =============================================================================

# Organized command presets for the GUI dropdown menus
COMMAND_PRESETS = {
    "Power": [
        ("Power On", MK3CommandBuilder.power_on),
        ("Power Off", MK3CommandBuilder.power_off),
        ("Power Toggle", MK3CommandBuilder.power_toggle),
        ("Query Power Status", MK3CommandBuilder.power_query),
    ],
    "Global Volume": [
        ("Volume Up", MK3CommandBuilder.global_volume_up),
        ("Volume Down", MK3CommandBuilder.global_volume_down),
        ("Volume +3dB", MK3CommandBuilder.global_volume_up_3db),
        ("Volume -3dB", MK3CommandBuilder.global_volume_down_3db),
        ("Return to Turn-On Volume", MK3CommandBuilder.global_return_to_turn_on_volume),
    ],
    "Global Mute": [
        ("Mute Toggle", MK3CommandBuilder.global_mute_toggle),
        ("Mute On", MK3CommandBuilder.global_mute_on),
        ("Mute Off", MK3CommandBuilder.global_mute_off),
    ],
    "Global Source": [
        ("Source 1", lambda: MK3CommandBuilder.global_source(InputSource.SOURCE_1)),
        ("Source 2", lambda: MK3CommandBuilder.global_source(InputSource.SOURCE_2)),
        ("Source 3", lambda: MK3CommandBuilder.global_source(InputSource.SOURCE_3)),
        ("Source 4", lambda: MK3CommandBuilder.global_source(InputSource.SOURCE_4)),
    ],
    "All Groups Power": [
        ("All Groups On", MK3CommandBuilder.global_group_power_on),
        ("All Groups Off", MK3CommandBuilder.global_group_power_off),
    ],
}


def get_hex_string(cmd_bytes: bytes) -> str:
    """Convert command bytes to readable hex string like 'FF 55 01 01'."""
    return ' '.join(f'{b:02X}' for b in cmd_bytes)


def hex_string_to_bytes(hex_str: str) -> bytes:
    """Convert hex string like 'FF 55 01 01' to bytes."""
    hex_str = hex_str.replace(' ', '').replace('0x', '').replace('\\x', '')
    return bytes.fromhex(hex_str)
