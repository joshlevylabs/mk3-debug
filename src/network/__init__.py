"""Network testing and discovery modules."""

from .discovery import NetworkDiscovery
from .connectivity import ConnectivityTester
from .dns import DNSTester
from .hostname import HostnameTester
from .commands import CommandTester
from .mk3_protocol import (
    MK3ProtocolTester,
    MK3DeviceStatus,
    MK3GroupStatus,
    MK3ChannelStatus,
    MK3GlobalProtectStatus,
    MK3ThermalStatus,
    MK3Command,
    MK3GroupCommand,
    MK3ChannelCommand,
    ChannelIndex,
    GlobalProtectBits,
    GroupProtectBits,
    ThermalState,
)
from .mk3_commands import (
    MK3CommandBuilder,
    MK3ResponseParser,
    MK3Model,
    OutputGroup,
    OutputChannel,
    InputSource,
    MODEL_CONFIGS,
    MK3_PORT,
    COMMAND_PRESETS,
    get_hex_string,
    hex_string_to_bytes,
    volume_db_to_hex,
    volume_hex_to_db,
)

__all__ = [
    # Discovery and testing
    "NetworkDiscovery",
    "ConnectivityTester",
    "DNSTester",
    "HostnameTester",
    "CommandTester",
    # MK3 Protocol
    "MK3ProtocolTester",
    "MK3DeviceStatus",
    "MK3GroupStatus",
    "MK3ChannelStatus",
    "MK3GlobalProtectStatus",
    "MK3ThermalStatus",
    "MK3Command",
    "MK3GroupCommand",
    "MK3ChannelCommand",
    "ChannelIndex",
    "GlobalProtectBits",
    "GroupProtectBits",
    "ThermalState",
    # MK3 Command Builder
    "MK3CommandBuilder",
    "MK3ResponseParser",
    "MK3Model",
    "OutputGroup",
    "OutputChannel",
    "InputSource",
    "MODEL_CONFIGS",
    "MK3_PORT",
    "COMMAND_PRESETS",
    "get_hex_string",
    "hex_string_to_bytes",
    "volume_db_to_hex",
    "volume_hex_to_db",
]
