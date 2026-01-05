"""Application configuration for MK3 Diagnostic Tool."""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional


@dataclass
class Config:
    """Application configuration settings."""

    # Network settings
    default_timeout: float = 5.0  # seconds
    ping_count: int = 4
    ping_timeout: float = 2.0
    port_scan_timeout: float = 1.0
    http_timeout: float = 5.0

    # Common ports to scan on MK3 amplifiers
    common_ports: List[int] = field(default_factory=lambda: [
        52000,  # MK3 Binary Control Protocol (PRIMARY)
        80,     # HTTP Web Interface
        443,    # HTTPS
        23,     # Telnet (legacy)
        21,     # FTP
        22,     # SSH
        8080,   # Alt HTTP
        8000,   # Alt HTTP
        10000,  # Common control port
        10001,  # Common control port
        10002,  # Common control port
        4998,   # Crestron
        4999,   # Crestron
        5000,   # Crestron
        41794,  # Crestron CIP
        41795,  # Crestron CTP
        41796,  # Crestron
        41797,  # Crestron
        9090,   # Control4
        5020,   # Control4
        5021,   # Control4
    ])

    # MK3 Binary Protocol Settings
    mk3_control_port: int = 52000
    mk3_protocol_timeout: float = 2.0
    mk3_num_groups: int = 8  # DSP 8-130 has 8 output groups (A-H)

    # HTTP endpoints to check on MK3
    http_endpoints: List[str] = field(default_factory=lambda: [
        "/",
        "/Landing.htm",
        "/index.html",
        "/index.htm",
        "/status",
        "/api/status",
        "/info",
        "/config",
    ])

    # Command testing
    command_test_delays_ms: List[int] = field(default_factory=lambda: [
        0, 10, 25, 50, 100, 250, 500, 1000
    ])
    command_burst_count: int = 10

    # DNS settings
    common_dns_servers: List[str] = field(default_factory=lambda: [
        "8.8.8.8",       # Google
        "8.8.4.4",       # Google
        "1.1.1.1",       # Cloudflare
        "1.0.0.1",       # Cloudflare
        "208.67.222.222", # OpenDNS
        "208.67.220.220", # OpenDNS
    ])

    # mDNS/Bonjour settings
    mdns_service_types: List[str] = field(default_factory=lambda: [
        "_http._tcp.local.",
        "_https._tcp.local.",
        "_sonance._tcp.local.",
        "_sonos._tcp.local.",
        "_raop._tcp.local.",
        "_airplay._tcp.local.",
        "_googlecast._tcp.local.",
    ])

    # UI settings
    dark_mode: bool = True
    font_size: int = 12
    window_width: int = 1200
    window_height: int = 800

    # Logging
    log_level: str = "DEBUG"
    max_log_entries: int = 10000

    # Last used values (persisted)
    last_ip_address: str = ""
    recent_ip_addresses: List[str] = field(default_factory=list)

    @classmethod
    def load(cls, filepath: Optional[Path] = None) -> "Config":
        """Load configuration from file."""
        if filepath is None:
            filepath = cls._default_config_path()

        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return cls(**data)
            except (json.JSONDecodeError, TypeError):
                pass

        return cls()

    def save(self, filepath: Optional[Path] = None) -> None:
        """Save configuration to file."""
        if filepath is None:
            filepath = self._default_config_path()

        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, indent=2)

    @staticmethod
    def _default_config_path() -> Path:
        """Get the default configuration file path."""
        return Path.home() / ".mk3-debug" / "config.json"

    def add_recent_ip(self, ip: str) -> None:
        """Add an IP to the recent list."""
        if ip in self.recent_ip_addresses:
            self.recent_ip_addresses.remove(ip)
        self.recent_ip_addresses.insert(0, ip)
        self.recent_ip_addresses = self.recent_ip_addresses[:10]  # Keep last 10
        self.last_ip_address = ip
