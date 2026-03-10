"""GUI frame modules for each tab."""

from .discovery import DiscoveryFrame
from .connectivity import ConnectivityFrame
from .dns_hostname import DNSHostnameFrame
from .commands import CommandsFrame
from .diagnostics import DiagnosticsFrame
from .logs import LogsFrame
from .verification import VerificationFrame

__all__ = [
    "DiscoveryFrame",
    "ConnectivityFrame",
    "DNSHostnameFrame",
    "CommandsFrame",
    "DiagnosticsFrame",
    "LogsFrame",
    "VerificationFrame",
]
