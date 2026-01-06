"""
MK3 Amplifier Binary Protocol Handler.

Sonance DSP MKIII amplifiers (DSP 2-150/2-750/8-130 MKIII) use a binary protocol
over TCP port 52000. Commands are 4-5 bytes starting with FF 55.

Protocol Format:
- Global commands: FF 55 01 <cmd>
- Group commands:  FF 55 02 <cmd> <group>
  where group: 00=A, 01=B, 02=C, etc.
"""

import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any
from enum import Enum

from ..utils import get_logger

logger = get_logger(__name__)


class MK3Command(Enum):
    """MK3 Binary Protocol Commands."""
    # Global Power Commands (FF 55 01 XX)
    POWER_ON = bytes([0xFF, 0x55, 0x01, 0x01])
    POWER_OFF = bytes([0xFF, 0x55, 0x01, 0x02])
    POWER_TOGGLE = bytes([0xFF, 0x55, 0x01, 0x03])
    POWER_QUERY = bytes([0xFF, 0x55, 0x01, 0x70])

    # Global Volume/Mute Commands (FF 55 01 XX)
    VOLUME_UP = bytes([0xFF, 0x55, 0x01, 0x04])
    VOLUME_DOWN = bytes([0xFF, 0x55, 0x01, 0x05])
    MUTE_TOGGLE = bytes([0xFF, 0x55, 0x01, 0x06])
    MUTE_ON = bytes([0xFF, 0x55, 0x01, 0x07])
    MUTE_OFF = bytes([0xFF, 0x55, 0x01, 0x08])

    # Global Input Selection (FF 55 01 XX)
    INPUT_1 = bytes([0xFF, 0x55, 0x01, 0x09])
    INPUT_2 = bytes([0xFF, 0x55, 0x01, 0x0A])
    INPUT_3 = bytes([0xFF, 0x55, 0x01, 0x0B])
    INPUT_4 = bytes([0xFF, 0x55, 0x01, 0x0C])

    # Fault/Protect Status Queries (FF 55 01 XX)
    # These return status bytes with fault/protect information
    PROTECT_STATUS_GLOBAL = bytes([0xFF, 0x55, 0x01, 0x71])  # Global protect summary
    THERMAL_STATE = bytes([0xFF, 0x55, 0x01, 0x72])          # Thermal state (may not work on all FW)


# Group command base codes (requires 5th byte for group index)
class MK3GroupCommand(Enum):
    """MK3 Per-Group Commands (append group index 00-07)."""
    POWER_ON = bytes([0xFF, 0x55, 0x02, 0x65])
    POWER_OFF = bytes([0xFF, 0x55, 0x02, 0x66])
    POWER_TOGGLE = bytes([0xFF, 0x55, 0x02, 0x67])
    VOLUME_UP = bytes([0xFF, 0x55, 0x02, 0x04])
    VOLUME_DOWN = bytes([0xFF, 0x55, 0x02, 0x05])
    MUTE_TOGGLE = bytes([0xFF, 0x55, 0x02, 0x06])
    MUTE_ON = bytes([0xFF, 0x55, 0x02, 0x07])
    MUTE_OFF = bytes([0xFF, 0x55, 0x02, 0x08])
    SOURCE_1 = bytes([0xFF, 0x55, 0x02, 0x09])
    SOURCE_2 = bytes([0xFF, 0x55, 0x02, 0x0A])
    SOURCE_3 = bytes([0xFF, 0x55, 0x02, 0x0B])
    SOURCE_4 = bytes([0xFF, 0x55, 0x02, 0x0C])
    RETURN_TO_TURN_ON_VOL = bytes([0xFF, 0x55, 0x02, 0x0D])
    VOLUME_UP_3DB = bytes([0xFF, 0x55, 0x02, 0x0E])
    VOLUME_DOWN_3DB = bytes([0xFF, 0x55, 0x02, 0x0F])

    # Query commands (per-group)
    QUERY_VOLUME = bytes([0xFF, 0x55, 0x02, 0x10])
    QUERY_SOURCE = bytes([0xFF, 0x55, 0x02, 0x11])
    QUERY_MUTE = bytes([0xFF, 0x55, 0x02, 0x12])
    QUERY_PROTECT = bytes([0xFF, 0x55, 0x02, 0x13])  # Per-group protect status


class MK3ChannelCommand(Enum):
    """
    MK3 Per-Channel Commands (append channel index).

    Channel indices (for DSP8-130):
    0x08 = Channel 1L    0x09 = Channel 1R
    0x0A = Channel 2L    0x0B = Channel 2R
    0x0C = Channel 3L    0x0D = Channel 3R
    0x0E = Channel 4L    0x0F = Channel 4R
    """
    QUERY_DSP_PRESET = bytes([0xFF, 0x55, 0x02, 0x16])     # DSP EQ preset
    QUERY_SHORT_PROTECT = bytes([0xFF, 0x55, 0x02, 0x17])  # Short circuit protect status
    QUERY_OVERTEMP = bytes([0xFF, 0x55, 0x02, 0x18])       # Over-temperature status


# Channel index constants
class ChannelIndex:
    """Physical output channel indices for per-channel queries."""
    CH1_LEFT = 0x08
    CH1_RIGHT = 0x09
    CH2_LEFT = 0x0A
    CH2_RIGHT = 0x0B
    CH3_LEFT = 0x0C
    CH3_RIGHT = 0x0D
    CH4_LEFT = 0x0E
    CH4_RIGHT = 0x0F

    # Map for iteration
    ALL_8CH = [0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F]
    ALL_2CH = [0x08, 0x09]  # For 2-channel models

    NAMES = {
        0x08: "1L", 0x09: "1R",
        0x0A: "2L", 0x0B: "2R",
        0x0C: "3L", 0x0D: "3R",
        0x0E: "4L", 0x0F: "4R"
    }


# ============================================================================
# Fault/Protect Status Bit Decoders
# These are reverse-engineered meanings - not officially documented by Sonance
# ============================================================================

class GlobalProtectBits:
    """
    Bit meanings for global protect status (FF 55 01 71 response).
    WARNING: These are inferred from behavior, not formally documented.
    """
    PROTECTION_ACTIVE = 0x01   # Bit 0: Protection active (any channel)
    THERMAL_WARNING = 0x02     # Bit 1: Thermal warning / thermal protect
    POWER_SUPPLY_FAULT = 0x04  # Bit 2: Power supply fault
    AMPLIFIER_FAULT = 0x08     # Bit 3: Amplifier fault (generic)
    # Bits 4-7: Reserved / model-specific

    @classmethod
    def decode(cls, status_byte: int) -> Dict[str, bool]:
        """Decode global protect status byte into named flags."""
        return {
            'protection_active': bool(status_byte & cls.PROTECTION_ACTIVE),
            'thermal_warning': bool(status_byte & cls.THERMAL_WARNING),
            'power_supply_fault': bool(status_byte & cls.POWER_SUPPLY_FAULT),
            'amplifier_fault': bool(status_byte & cls.AMPLIFIER_FAULT),
            'reserved_bits': (status_byte >> 4) & 0x0F,  # Upper 4 bits
            'raw_value': status_byte,
            'has_any_fault': status_byte != 0
        }


class GroupProtectBits:
    """
    Bit meanings for per-group protect status (FF 55 02 13 XX response).
    WARNING: These are inferred from behavior, not formally documented.
    """
    MUTED_DUE_TO_PROTECT = 0x01  # Bit 0: Group muted due to protect
    THERMAL_PROTECT = 0x02       # Bit 1: Thermal protect (group output stage)
    OVER_CURRENT = 0x04          # Bit 2: Over-current / short
    LOAD_FAULT = 0x08            # Bit 3: Load fault
    DC_FAULT = 0x10              # Bit 4: DC fault
    # Bits 5-7: Reserved

    @classmethod
    def decode(cls, status_byte: int) -> Dict[str, Any]:
        """Decode per-group protect status byte into named flags."""
        return {
            'muted_due_to_protect': bool(status_byte & cls.MUTED_DUE_TO_PROTECT),
            'thermal_protect': bool(status_byte & cls.THERMAL_PROTECT),
            'over_current': bool(status_byte & cls.OVER_CURRENT),
            'load_fault': bool(status_byte & cls.LOAD_FAULT),
            'dc_fault': bool(status_byte & cls.DC_FAULT),
            'reserved_bits': (status_byte >> 5) & 0x07,  # Upper 3 bits
            'raw_value': status_byte,
            'has_any_fault': status_byte != 0
        }


class ThermalState:
    """
    Thermal state codes (FF 55 01 72 response).
    WARNING: This command may not work on all firmware versions.
    """
    NORMAL = 0x00
    WARM = 0x01
    HOT = 0x02
    THERMAL_PROTECT = 0x03

    DESCRIPTIONS = {
        0x00: "Normal",
        0x01: "Warm",
        0x02: "Hot",
        0x03: "Thermal Protect"
    }

    @classmethod
    def decode(cls, state_byte: int) -> Dict[str, Any]:
        """Decode thermal state byte."""
        return {
            'state_code': state_byte,
            'state_name': cls.DESCRIPTIONS.get(state_byte, f"Unknown (0x{state_byte:02X})"),
            'is_normal': state_byte == cls.NORMAL,
            'is_warning': state_byte in (cls.WARM, cls.HOT),
            'is_critical': state_byte == cls.THERMAL_PROTECT
        }


@dataclass
class MK3Response:
    """Response from MK3 amplifier."""
    success: bool
    raw_data: bytes = field(default_factory=bytes)
    error: Optional[str] = None
    response_time_ms: float = 0.0
    parsed_value: Any = None


@dataclass
class MK3PowerStatus:
    """Power status information."""
    is_on: bool
    raw_response: bytes


@dataclass
class MK3GroupStatus:
    """Status of a single output group."""
    group_index: int
    group_name: str  # A, B, C, etc.
    volume: Optional[int] = None  # dB or raw value
    mute: Optional[bool] = None
    source: Optional[int] = None  # Input number 1-4
    # Protect status
    protect_status: Optional[Dict[str, Any]] = None  # Decoded from GroupProtectBits
    raw_volume: Optional[bytes] = None
    raw_mute: Optional[bytes] = None
    raw_source: Optional[bytes] = None
    raw_protect: Optional[bytes] = None


@dataclass
class MK3GlobalProtectStatus:
    """Global protection/fault status."""
    protection_active: bool = False
    thermal_warning: bool = False
    power_supply_fault: bool = False
    amplifier_fault: bool = False
    has_any_fault: bool = False
    raw_value: int = 0
    raw_response: bytes = field(default_factory=bytes)


@dataclass
class MK3ThermalStatus:
    """Thermal state information."""
    state_code: int = 0
    state_name: str = "Unknown"
    is_normal: bool = True
    is_warning: bool = False
    is_critical: bool = False
    raw_response: bytes = field(default_factory=bytes)
    query_supported: bool = True  # False if firmware doesn't support this query


@dataclass
class MK3ChannelStatus:
    """Status of a single output channel (for per-channel protection queries)."""
    channel_index: int
    channel_name: str  # "1L", "1R", "2L", etc.
    dsp_preset: Optional[str] = None
    has_short: bool = False
    short_status: str = "Unknown"
    has_overtemp: bool = False
    overtemp_status: str = "Unknown"
    raw_dsp_preset: Optional[bytes] = None
    raw_short_protect: Optional[bytes] = None
    raw_overtemp: Optional[bytes] = None


@dataclass
class MK3DeviceStatus:
    """Complete device status."""
    ip: str
    port: int
    is_reachable: bool
    power_status: Optional[MK3PowerStatus] = None
    global_protect: Optional[MK3GlobalProtectStatus] = None
    thermal_status: Optional[MK3ThermalStatus] = None
    groups: List[MK3GroupStatus] = field(default_factory=list)
    channels: List[MK3ChannelStatus] = field(default_factory=list)  # Per-channel protection status
    protocol_version: Optional[str] = None
    response_times: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    raw_responses: Dict[str, bytes] = field(default_factory=dict)
    # Summary flags for quick status check
    has_any_fault: bool = False
    fault_summary: List[str] = field(default_factory=list)  # Human-readable fault descriptions


class MK3ProtocolTester:
    """
    Handler for MK3 binary protocol communication.

    Provides diagnostic capabilities for testing MK3 amplifier
    connectivity and querying device status.
    """

    PORT = 52000
    HEADER = bytes([0xFF, 0x55])
    GROUP_NAMES = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']

    def __init__(self, timeout: float = 2.0):
        """
        Initialize MK3 protocol tester.

        Args:
            timeout: Socket timeout in seconds
        """
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None

    def _connect(self, ip: str, port: int = None) -> Tuple[bool, Optional[str]]:
        """
        Establish TCP connection to MK3 amplifier.

        Returns:
            Tuple of (success, error_message)
        """
        port = port or self.PORT
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((ip, port))
            logger.debug(f"Connected to MK3 at {ip}:{port}")
            return True, None
        except socket.timeout:
            return False, "Connection timed out"
        except ConnectionRefusedError:
            return False, "Connection refused"
        except OSError as e:
            return False, f"Connection error: {e}"

    def _disconnect(self) -> None:
        """Close the connection."""
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def _send_command(self, command: bytes, expect_response: bool = True) -> MK3Response:
        """
        Send a binary command and optionally read response.

        Args:
            command: Raw bytes to send
            expect_response: Whether to wait for response

        Returns:
            MK3Response with results
        """
        if not self._socket:
            return MK3Response(success=False, error="Not connected")

        start_time = time.perf_counter()

        try:
            # Send command
            self._socket.sendall(command)
            logger.debug(f"Sent: {command.hex().upper()}")

            if expect_response:
                # Read response (most responses are small, 1-4 bytes)
                response = self._socket.recv(64)
                elapsed = (time.perf_counter() - start_time) * 1000

                logger.debug(f"Received: {response.hex().upper()} ({elapsed:.1f}ms)")

                return MK3Response(
                    success=True,
                    raw_data=response,
                    response_time_ms=elapsed
                )
            else:
                elapsed = (time.perf_counter() - start_time) * 1000
                return MK3Response(success=True, response_time_ms=elapsed)

        except socket.timeout:
            elapsed = (time.perf_counter() - start_time) * 1000
            return MK3Response(
                success=False,
                error="Response timeout",
                response_time_ms=elapsed
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return MK3Response(
                success=False,
                error=str(e),
                response_time_ms=elapsed
            )

    def send_command_simple(
        self,
        ip: str,
        command: bytes,
        port: int = None
    ) -> MK3Response:
        """
        Send a single command (connect, send, disconnect).

        Args:
            ip: Target IP address
            command: Raw bytes to send
            port: Target port (default 52000)

        Returns:
            MK3Response with results
        """
        port = port or self.PORT

        connected, error = self._connect(ip, port)
        if not connected:
            return MK3Response(success=False, error=error)

        try:
            return self._send_command(command)
        finally:
            self._disconnect()

    def test_connectivity(self, ip: str, port: int = None) -> MK3Response:
        """
        Test if MK3 protocol port is reachable and responding.

        Args:
            ip: Target IP address
            port: Target port (default 52000)

        Returns:
            MK3Response indicating connectivity status
        """
        port = port or self.PORT
        start_time = time.perf_counter()

        connected, error = self._connect(ip, port)
        elapsed = (time.perf_counter() - start_time) * 1000

        if not connected:
            return MK3Response(
                success=False,
                error=error,
                response_time_ms=elapsed
            )

        self._disconnect()
        return MK3Response(
            success=True,
            response_time_ms=elapsed
        )

    def query_power_status(self, ip: str, port: int = None) -> MK3Response:
        """
        Query the power status of the amplifier.

        Args:
            ip: Target IP address
            port: Target port (default 52000)

        Returns:
            MK3Response with power status
        """
        response = self.send_command_simple(ip, MK3Command.POWER_QUERY.value, port)

        if response.success and response.raw_data:
            # Parse power status from response
            # Typically: 01 = ON, 02 = OFF (or similar)
            response.parsed_value = MK3PowerStatus(
                is_on=response.raw_data[0] == 0x01 if response.raw_data else False,
                raw_response=response.raw_data
            )

        return response

    def query_group_volume(self, ip: str, group: int, port: int = None) -> MK3Response:
        """
        Query volume level for a specific group.

        Args:
            ip: Target IP address
            group: Group index (0=A, 1=B, etc.)
            port: Target port (default 52000)

        Returns:
            MK3Response with volume information
        """
        command = MK3GroupCommand.QUERY_VOLUME.value + bytes([group])
        return self.send_command_simple(ip, command, port)

    def query_group_source(self, ip: str, group: int, port: int = None) -> MK3Response:
        """
        Query input source for a specific group.

        Args:
            ip: Target IP address
            group: Group index (0=A, 1=B, etc.)
            port: Target port (default 52000)

        Returns:
            MK3Response with source information
        """
        command = MK3GroupCommand.QUERY_SOURCE.value + bytes([group])
        return self.send_command_simple(ip, command, port)

    def query_group_mute(self, ip: str, group: int, port: int = None) -> MK3Response:
        """
        Query mute status for a specific group.

        Args:
            ip: Target IP address
            group: Group index (0=A, 1=B, etc.)
            port: Target port (default 52000)

        Returns:
            MK3Response with mute status
        """
        command = MK3GroupCommand.QUERY_MUTE.value + bytes([group])
        return self.send_command_simple(ip, command, port)

    def query_global_protect_status(self, ip: str, port: int = None) -> MK3Response:
        """
        Query global protection/fault status.

        Command: FF 55 01 71
        Returns status byte with protection/thermal/fault flags.

        WARNING: Bit meanings are reverse-engineered, not officially documented.

        Args:
            ip: Target IP address
            port: Target port (default 52000)

        Returns:
            MK3Response with parsed MK3GlobalProtectStatus
        """
        response = self.send_command_simple(ip, MK3Command.PROTECT_STATUS_GLOBAL.value, port)

        if response.success and response.raw_data:
            status_byte = response.raw_data[0] if response.raw_data else 0
            decoded = GlobalProtectBits.decode(status_byte)

            response.parsed_value = MK3GlobalProtectStatus(
                protection_active=decoded['protection_active'],
                thermal_warning=decoded['thermal_warning'],
                power_supply_fault=decoded['power_supply_fault'],
                amplifier_fault=decoded['amplifier_fault'],
                has_any_fault=decoded['has_any_fault'],
                raw_value=status_byte,
                raw_response=response.raw_data
            )

        return response

    def query_thermal_state(self, ip: str, port: int = None) -> MK3Response:
        """
        Query thermal state of the amplifier.

        Command: FF 55 01 72
        WARNING: This command may not work on all firmware versions.

        Args:
            ip: Target IP address
            port: Target port (default 52000)

        Returns:
            MK3Response with parsed MK3ThermalStatus
        """
        response = self.send_command_simple(ip, MK3Command.THERMAL_STATE.value, port)

        if response.success and response.raw_data:
            state_byte = response.raw_data[0] if response.raw_data else 0
            decoded = ThermalState.decode(state_byte)

            response.parsed_value = MK3ThermalStatus(
                state_code=decoded['state_code'],
                state_name=decoded['state_name'],
                is_normal=decoded['is_normal'],
                is_warning=decoded['is_warning'],
                is_critical=decoded['is_critical'],
                raw_response=response.raw_data,
                query_supported=True
            )
        elif response.error:
            # Query might not be supported on this firmware
            response.parsed_value = MK3ThermalStatus(
                state_name="Query not supported",
                query_supported=False
            )

        return response

    def query_group_protect_status(self, ip: str, group: int, port: int = None) -> MK3Response:
        """
        Query protection status for a specific group.

        Command: FF 55 02 13 <group>
        Returns status byte with group-specific fault flags.

        WARNING: Bit meanings are reverse-engineered, not officially documented.

        Args:
            ip: Target IP address
            group: Group index (0=A, 1=B, etc.)
            port: Target port (default 52000)

        Returns:
            MK3Response with decoded protect status dict
        """
        command = MK3GroupCommand.QUERY_PROTECT.value + bytes([group])
        response = self.send_command_simple(ip, command, port)

        if response.success and response.raw_data:
            status_byte = response.raw_data[0] if response.raw_data else 0
            response.parsed_value = GroupProtectBits.decode(status_byte)

        return response

    def query_all_group_status(self, ip: str, num_groups: int = 8, port: int = None) -> List[MK3GroupStatus]:
        """
        Query status of all output groups.

        Args:
            ip: Target IP address
            num_groups: Number of groups to query (default 8 for DSP 8-130)
            port: Target port (default 52000)

        Returns:
            List of MK3GroupStatus for each group
        """
        port = port or self.PORT
        groups = []

        connected, error = self._connect(ip, port)
        if not connected:
            logger.error(f"Failed to connect for group status: {error}")
            return groups

        try:
            for i in range(min(num_groups, 8)):
                group_status = MK3GroupStatus(
                    group_index=i,
                    group_name=self.GROUP_NAMES[i]
                )

                # Query volume
                vol_cmd = MK3GroupCommand.QUERY_VOLUME.value + bytes([i])
                vol_resp = self._send_command(vol_cmd)
                if vol_resp.success:
                    group_status.raw_volume = vol_resp.raw_data
                    if vol_resp.raw_data:
                        # Volume is typically returned as a single byte or dB value
                        group_status.volume = vol_resp.raw_data[0] if vol_resp.raw_data else None

                # Query mute
                mute_cmd = MK3GroupCommand.QUERY_MUTE.value + bytes([i])
                mute_resp = self._send_command(mute_cmd)
                if mute_resp.success:
                    group_status.raw_mute = mute_resp.raw_data
                    if mute_resp.raw_data:
                        group_status.mute = mute_resp.raw_data[0] == 0x01

                # Query source
                src_cmd = MK3GroupCommand.QUERY_SOURCE.value + bytes([i])
                src_resp = self._send_command(src_cmd)
                if src_resp.success:
                    group_status.raw_source = src_resp.raw_data
                    if src_resp.raw_data:
                        group_status.source = src_resp.raw_data[0]

                # Query protect status for this group
                protect_cmd = MK3GroupCommand.QUERY_PROTECT.value + bytes([i])
                protect_resp = self._send_command(protect_cmd)
                if protect_resp.success:
                    group_status.raw_protect = protect_resp.raw_data
                    if protect_resp.raw_data:
                        status_byte = protect_resp.raw_data[0]
                        group_status.protect_status = GroupProtectBits.decode(status_byte)

                groups.append(group_status)
                protect_info = group_status.protect_status.get('has_any_fault', False) if group_status.protect_status else False
                logger.debug(f"Group {self.GROUP_NAMES[i]}: vol={group_status.volume}, mute={group_status.mute}, src={group_status.source}, fault={protect_info}")

        finally:
            self._disconnect()

        return groups

    def run_full_diagnostic(self, ip: str, num_groups: int = 8, port: int = None) -> MK3DeviceStatus:
        """
        Run comprehensive diagnostic on MK3 amplifier.

        Queries all available status information from the device.

        Args:
            ip: Target IP address
            num_groups: Number of groups to query
            port: Target port (default 52000)

        Returns:
            MK3DeviceStatus with complete device information
        """
        port = port or self.PORT
        status = MK3DeviceStatus(
            ip=ip,
            port=port,
            is_reachable=False
        )

        logger.info(f"Running MK3 protocol diagnostic on {ip}:{port}")

        # Test connectivity
        conn_result = self.test_connectivity(ip, port)
        status.is_reachable = conn_result.success
        status.response_times['connectivity'] = conn_result.response_time_ms

        if not conn_result.success:
            status.errors.append(f"Connection failed: {conn_result.error}")
            logger.warning(f"MK3 protocol not reachable on {ip}:{port}")
            return status

        logger.info(f"MK3 protocol reachable on {ip}:{port} ({conn_result.response_time_ms:.1f}ms)")

        # Query power status
        power_result = self.query_power_status(ip, port)
        status.response_times['power_query'] = power_result.response_time_ms
        if power_result.success:
            status.power_status = power_result.parsed_value
            status.raw_responses['power'] = power_result.raw_data
            logger.info(f"Power status: {power_result.raw_data.hex().upper() if power_result.raw_data else 'N/A'}")
        else:
            status.errors.append(f"Power query failed: {power_result.error}")

        # Query global protect status (FF 55 01 71)
        protect_result = self.query_global_protect_status(ip, port)
        status.response_times['global_protect_query'] = protect_result.response_time_ms
        if protect_result.success and protect_result.parsed_value:
            status.global_protect = protect_result.parsed_value
            status.raw_responses['global_protect'] = protect_result.raw_data
            logger.info(f"Global protect status: {protect_result.raw_data.hex().upper() if protect_result.raw_data else 'N/A'}")

            # Check for faults
            if status.global_protect.has_any_fault:
                status.has_any_fault = True
                if status.global_protect.protection_active:
                    status.fault_summary.append("PROTECTION ACTIVE - Amplifier in protection mode")
                if status.global_protect.thermal_warning:
                    status.fault_summary.append("THERMAL WARNING - Amplifier is overheating")
                if status.global_protect.power_supply_fault:
                    status.fault_summary.append("POWER SUPPLY FAULT - PSU issue detected")
                if status.global_protect.amplifier_fault:
                    status.fault_summary.append("AMPLIFIER FAULT - Generic amp fault")
        else:
            logger.debug(f"Global protect query: {protect_result.error or 'no response'}")

        # Query thermal state (FF 55 01 72) - may not work on all firmware
        thermal_result = self.query_thermal_state(ip, port)
        status.response_times['thermal_query'] = thermal_result.response_time_ms
        if thermal_result.success and thermal_result.parsed_value:
            status.thermal_status = thermal_result.parsed_value
            status.raw_responses['thermal'] = thermal_result.raw_data
            logger.info(f"Thermal state: {status.thermal_status.state_name}")

            if status.thermal_status.is_critical:
                status.has_any_fault = True
                status.fault_summary.append(f"THERMAL CRITICAL - {status.thermal_status.state_name}")
            elif status.thermal_status.is_warning:
                status.fault_summary.append(f"THERMAL WARNING - {status.thermal_status.state_name}")
        else:
            logger.debug(f"Thermal query: {thermal_result.error or 'not supported on this firmware'}")

        # Query all groups (including per-group protect status)
        status.groups = self.query_all_group_status(ip, num_groups, port)
        if status.groups:
            logger.info(f"Queried {len(status.groups)} output groups")
            for g in status.groups:
                status.raw_responses[f'group_{g.group_name}_volume'] = g.raw_volume or b''
                status.raw_responses[f'group_{g.group_name}_mute'] = g.raw_mute or b''
                status.raw_responses[f'group_{g.group_name}_source'] = g.raw_source or b''
                status.raw_responses[f'group_{g.group_name}_protect'] = g.raw_protect or b''

                # Check for per-group faults
                if g.protect_status and g.protect_status.get('has_any_fault'):
                    status.has_any_fault = True
                    fault_types = []
                    if g.protect_status.get('muted_due_to_protect'):
                        fault_types.append("auto-muted")
                    if g.protect_status.get('thermal_protect'):
                        fault_types.append("thermal")
                    if g.protect_status.get('over_current'):
                        fault_types.append("over-current/short")
                    if g.protect_status.get('load_fault'):
                        fault_types.append("load fault")
                    if g.protect_status.get('dc_fault'):
                        fault_types.append("DC fault")

                    status.fault_summary.append(f"GROUP {g.group_name} FAULT: {', '.join(fault_types)}")

        # Log fault summary
        if status.has_any_fault:
            logger.warning(f"FAULTS DETECTED on {ip}: {status.fault_summary}")
        else:
            logger.info(f"No faults detected on {ip}")

        return status

    def burst_test(
        self,
        ip: str,
        command: bytes = None,
        count: int = 10,
        delay_ms: float = 0,
        port: int = None
    ) -> Dict[str, Any]:
        """
        Send multiple commands rapidly to test reliability.

        Args:
            ip: Target IP address
            command: Command to send (default: power query)
            count: Number of commands to send
            delay_ms: Delay between commands in milliseconds
            port: Target port (default 52000)

        Returns:
            Dict with test results
        """
        port = port or self.PORT
        command = command or MK3Command.POWER_QUERY.value

        results = {
            'total': count,
            'successful': 0,
            'failed': 0,
            'response_times': [],
            'errors': [],
            'error_rate_percent': 0.0
        }

        connected, error = self._connect(ip, port)
        if not connected:
            results['errors'].append(f"Connection failed: {error}")
            results['failed'] = count
            results['error_rate_percent'] = 100.0
            return results

        try:
            for i in range(count):
                response = self._send_command(command)

                if response.success:
                    results['successful'] += 1
                    results['response_times'].append(response.response_time_ms)
                else:
                    results['failed'] += 1
                    results['errors'].append(response.error)

                if delay_ms > 0 and i < count - 1:
                    time.sleep(delay_ms / 1000.0)

        finally:
            self._disconnect()

        results['error_rate_percent'] = (results['failed'] / count) * 100
        if results['response_times']:
            results['avg_response_ms'] = sum(results['response_times']) / len(results['response_times'])
            results['min_response_ms'] = min(results['response_times'])
            results['max_response_ms'] = max(results['response_times'])

        return results

    def query_channel_short_protect(self, ip: str, channel: int, port: int = None) -> MK3Response:
        """
        Query short circuit protection status for a specific output channel.

        Command: FF 55 02 17 <channel>
        Response: Text like "Cmd:AmpShortCir :No short,Channel Output 1L"

        Args:
            ip: Target IP address
            channel: Channel index (0x08-0x0F for channels 1L-4R)
            port: Target port (default 52000)

        Returns:
            MK3Response with short circuit status
        """
        command = MK3ChannelCommand.QUERY_SHORT_PROTECT.value + bytes([channel])
        response = self.send_command_simple(ip, command, port)

        if response.success and response.raw_data:
            # Try to parse text response
            try:
                text = response.raw_data.decode('utf-8', errors='ignore').strip()
                has_short = "short" in text.lower() and "no short" not in text.lower()
                response.parsed_value = {
                    'has_short': has_short,
                    'status_text': text,
                    'channel': ChannelIndex.NAMES.get(channel, f"0x{channel:02X}")
                }
            except Exception:
                response.parsed_value = {
                    'has_short': False,
                    'status_text': f"Raw: {response.raw_data.hex().upper()}",
                    'channel': ChannelIndex.NAMES.get(channel, f"0x{channel:02X}")
                }

        return response

    def query_channel_overtemp(self, ip: str, channel: int, port: int = None) -> MK3Response:
        """
        Query over-temperature status for a specific output channel.

        Command: FF 55 02 18 <channel>
        Response: Text like "Cmd:AmpOverTemp :Normal Temp,Channel Output 1L"

        Args:
            ip: Target IP address
            channel: Channel index (0x08-0x0F for channels 1L-4R)
            port: Target port (default 52000)

        Returns:
            MK3Response with thermal status
        """
        command = MK3ChannelCommand.QUERY_OVERTEMP.value + bytes([channel])
        response = self.send_command_simple(ip, command, port)

        if response.success and response.raw_data:
            try:
                text = response.raw_data.decode('utf-8', errors='ignore').strip()
                is_overtemp = "over temp" in text.lower() or "overtemp" in text.lower()
                is_normal = "normal" in text.lower()
                response.parsed_value = {
                    'has_overtemp': is_overtemp and not is_normal,
                    'is_normal': is_normal,
                    'status_text': text,
                    'channel': ChannelIndex.NAMES.get(channel, f"0x{channel:02X}")
                }
            except Exception:
                response.parsed_value = {
                    'has_overtemp': False,
                    'is_normal': True,
                    'status_text': f"Raw: {response.raw_data.hex().upper()}",
                    'channel': ChannelIndex.NAMES.get(channel, f"0x{channel:02X}")
                }

        return response

    def query_channel_dsp_preset(self, ip: str, channel: int, port: int = None) -> MK3Response:
        """
        Query DSP EQ preset for a specific output channel.

        Command: FF 55 02 16 <channel>
        Response: Text like "Cmd:DSP_Preset:FLAT,Channel Output 1L"

        Args:
            ip: Target IP address
            channel: Channel index (0x08-0x0F for channels 1L-4R)
            port: Target port (default 52000)

        Returns:
            MK3Response with DSP preset information
        """
        command = MK3ChannelCommand.QUERY_DSP_PRESET.value + bytes([channel])
        response = self.send_command_simple(ip, command, port)

        if response.success and response.raw_data:
            try:
                text = response.raw_data.decode('utf-8', errors='ignore').strip()
                # Extract preset name from response like "Cmd:DSP_Preset:FLAT,Channel..."
                preset = "Unknown"
                if ":" in text:
                    parts = text.split(":")
                    if len(parts) >= 2:
                        preset_part = parts[-1].split(",")[0].strip()
                        if preset_part:
                            preset = preset_part
                response.parsed_value = {
                    'preset': preset,
                    'status_text': text,
                    'channel': ChannelIndex.NAMES.get(channel, f"0x{channel:02X}")
                }
            except Exception:
                response.parsed_value = {
                    'preset': "Unknown",
                    'status_text': f"Raw: {response.raw_data.hex().upper()}",
                    'channel': ChannelIndex.NAMES.get(channel, f"0x{channel:02X}")
                }

        return response

    def query_all_channel_status(self, ip: str, num_channels: int = 8, port: int = None) -> List[MK3ChannelStatus]:
        """
        Query protection status for all output channels.

        Args:
            ip: Target IP address
            num_channels: Number of channels to query (8 for DSP8-130, 2 for DSP2-xxx)
            port: Target port (default 52000)

        Returns:
            List of MK3ChannelStatus for each channel
        """
        port = port or self.PORT
        channels = []

        channel_indices = ChannelIndex.ALL_8CH[:num_channels]

        connected, error = self._connect(ip, port)
        if not connected:
            logger.error(f"Failed to connect for channel status: {error}")
            return channels

        try:
            for ch_idx in channel_indices:
                ch_name = ChannelIndex.NAMES.get(ch_idx, f"0x{ch_idx:02X}")
                channel_status = MK3ChannelStatus(
                    channel_index=ch_idx,
                    channel_name=ch_name
                )

                # Query short protect
                short_cmd = MK3ChannelCommand.QUERY_SHORT_PROTECT.value + bytes([ch_idx])
                short_resp = self._send_command(short_cmd)
                if short_resp.success and short_resp.raw_data:
                    channel_status.raw_short_protect = short_resp.raw_data
                    try:
                        text = short_resp.raw_data.decode('utf-8', errors='ignore').strip()
                        channel_status.has_short = "short" in text.lower() and "no short" not in text.lower()
                        channel_status.short_status = "Short detected" if channel_status.has_short else "No short"
                    except Exception:
                        channel_status.short_status = f"Raw: {short_resp.raw_data.hex().upper()}"

                # Query overtemp
                temp_cmd = MK3ChannelCommand.QUERY_OVERTEMP.value + bytes([ch_idx])
                temp_resp = self._send_command(temp_cmd)
                if temp_resp.success and temp_resp.raw_data:
                    channel_status.raw_overtemp = temp_resp.raw_data
                    try:
                        text = temp_resp.raw_data.decode('utf-8', errors='ignore').strip()
                        channel_status.has_overtemp = "over temp" in text.lower() and "normal" not in text.lower()
                        channel_status.overtemp_status = "Over Temp" if channel_status.has_overtemp else "Normal"
                    except Exception:
                        channel_status.overtemp_status = f"Raw: {temp_resp.raw_data.hex().upper()}"

                # Query DSP preset
                dsp_cmd = MK3ChannelCommand.QUERY_DSP_PRESET.value + bytes([ch_idx])
                dsp_resp = self._send_command(dsp_cmd)
                if dsp_resp.success and dsp_resp.raw_data:
                    channel_status.raw_dsp_preset = dsp_resp.raw_data
                    try:
                        text = dsp_resp.raw_data.decode('utf-8', errors='ignore').strip()
                        if ":" in text:
                            parts = text.split(":")
                            if len(parts) >= 2:
                                channel_status.dsp_preset = parts[-1].split(",")[0].strip()
                    except Exception:
                        pass

                channels.append(channel_status)
                logger.debug(f"Channel {ch_name}: short={channel_status.short_status}, temp={channel_status.overtemp_status}, dsp={channel_status.dsp_preset}")

        finally:
            self._disconnect()

        return channels

    def send_group_command(self, ip: str, command: MK3GroupCommand, group: int, port: int = None) -> MK3Response:
        """
        Send a per-group command.

        Args:
            ip: Target IP address
            command: MK3GroupCommand enum value
            group: Group index (0=A, 1=B, etc.)
            port: Target port (default 52000)

        Returns:
            MK3Response with results
        """
        cmd_bytes = command.value + bytes([group])
        return self.send_command_simple(ip, cmd_bytes, port)

    def send_global_command(self, ip: str, command: MK3Command, port: int = None) -> MK3Response:
        """
        Send a global command.

        Args:
            ip: Target IP address
            command: MK3Command enum value
            port: Target port (default 52000)

        Returns:
            MK3Response with results
        """
        return self.send_command_simple(ip, command.value, port)

    def set_group_volume_direct(self, ip: str, group: int, db: int, port: int = None) -> MK3Response:
        """
        Set volume directly to a specific dB level for a group.

        Volume range: -70dB to 0dB
        Command format: FF 55 02 <vol_byte> <group>
        where vol_byte = 0x71 (-70dB) to 0xB6 (0dB)

        Args:
            ip: Target IP address
            group: Group index (0=A, 1=B, etc.)
            db: Volume level in dB (-70 to 0)
            port: Target port (default 52000)

        Returns:
            MK3Response with results
        """
        # Clamp dB to valid range
        db = max(-70, min(0, db))
        # Convert dB to command byte: -70dB = 0x71, 0dB = 0xB6
        vol_byte = 0x71 + (db + 70)
        command = bytes([0xFF, 0x55, 0x02, vol_byte, group])
        return self.send_command_simple(ip, command, port)

    def set_global_volume_direct(self, ip: str, db: int, port: int = None) -> MK3Response:
        """
        Set volume directly to a specific dB level for all groups.

        Volume range: -70dB to 0dB
        Command format: FF 55 01 <vol_byte>
        where vol_byte = 0x71 (-70dB) to 0xB6 (0dB)

        Args:
            ip: Target IP address
            db: Volume level in dB (-70 to 0)
            port: Target port (default 52000)

        Returns:
            MK3Response with results
        """
        # Clamp dB to valid range
        db = max(-70, min(0, db))
        # Convert dB to command byte
        vol_byte = 0x71 + (db + 70)
        command = bytes([0xFF, 0x55, 0x01, vol_byte])
        return self.send_command_simple(ip, command, port)
