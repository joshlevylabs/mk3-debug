"""Network discovery module for finding MK3 amplifiers."""

import socket
import subprocess
import platform
import re
import threading
from typing import List, Dict, Optional, Callable, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import ipaddress

from ..utils import get_logger

logger = get_logger(__name__)


@dataclass
class DiscoveredDevice:
    """Represents a discovered network device."""
    ip_address: str
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    vendor: Optional[str] = None
    open_ports: List[int] = None
    response_time_ms: Optional[float] = None
    is_mk3_candidate: bool = False

    def __post_init__(self):
        if self.open_ports is None:
            self.open_ports = []


class NetworkDiscovery:
    """
    Discovers devices on the network using various methods.
    """

    # Known Sonance MAC prefixes (if any - placeholder)
    SONANCE_MAC_PREFIXES = [
        # Add known Sonance OUI prefixes here
    ]

    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout
        self._cancel_flag = threading.Event()

    def cancel(self) -> None:
        """Cancel any running discovery operation."""
        self._cancel_flag.set()

    def reset_cancel(self) -> None:
        """Reset the cancel flag."""
        self._cancel_flag.clear()

    def get_local_ip(self) -> str:
        """Get the local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logger.error(f"Failed to get local IP: {e}")
            return "127.0.0.1"

    def get_subnet(self, ip: str, prefix_length: int = 24) -> str:
        """Get the subnet for an IP address."""
        network = ipaddress.ip_network(f"{ip}/{prefix_length}", strict=False)
        return str(network)

    def ping(self, ip: str, count: int = 1) -> Tuple[bool, Optional[float]]:
        """
        Ping an IP address.

        Returns:
            Tuple of (success, response_time_ms)
        """
        try:
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
            timeout_val = str(int(self.timeout * 1000)) if platform.system().lower() == 'windows' else str(int(self.timeout))

            cmd = ['ping', param, str(count), timeout_param, timeout_val, ip]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout + 2
            )

            if result.returncode == 0:
                # Parse response time
                output = result.stdout
                if platform.system().lower() == 'windows':
                    match = re.search(r'Average = (\d+)ms', output)
                    if not match:
                        match = re.search(r'time[=<](\d+)ms', output)
                else:
                    match = re.search(r'time=(\d+\.?\d*)', output)

                if match:
                    return True, float(match.group(1))
                return True, None

            return False, None

        except subprocess.TimeoutExpired:
            logger.debug(f"Ping timeout for {ip}")
            return False, None
        except Exception as e:
            logger.error(f"Ping error for {ip}: {e}")
            return False, None

    def scan_subnet(
        self,
        subnet: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        max_workers: int = 50
    ) -> List[DiscoveredDevice]:
        """
        Scan a subnet for active devices.

        Args:
            subnet: Subnet to scan (e.g., "192.168.1.0/24"). If None, uses local subnet.
            progress_callback: Callback(current, total, ip) for progress updates.
            max_workers: Maximum concurrent ping operations.

        Returns:
            List of discovered devices.
        """
        self.reset_cancel()

        if subnet is None:
            local_ip = self.get_local_ip()
            subnet = self.get_subnet(local_ip)

        logger.info(f"Scanning subnet: {subnet}")

        network = ipaddress.ip_network(subnet, strict=False)
        hosts = list(network.hosts())
        total = len(hosts)

        devices: List[DiscoveredDevice] = []
        completed = 0

        def ping_host(ip: str) -> Optional[DiscoveredDevice]:
            if self._cancel_flag.is_set():
                return None

            ip_str = str(ip)
            success, response_time = self.ping(ip_str)

            if success:
                device = DiscoveredDevice(
                    ip_address=ip_str,
                    response_time_ms=response_time
                )
                logger.debug(f"Found device: {ip_str} ({response_time}ms)")
                return device
            return None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(ping_host, ip): ip for ip in hosts}

            for future in as_completed(futures):
                if self._cancel_flag.is_set():
                    break

                completed += 1
                ip = futures[future]

                if progress_callback:
                    progress_callback(completed, total, str(ip))

                try:
                    device = future.result()
                    if device:
                        devices.append(device)
                except Exception as e:
                    logger.error(f"Error scanning {ip}: {e}")

        logger.info(f"Subnet scan complete. Found {len(devices)} devices.")
        return devices

    def get_arp_table(self) -> List[Dict[str, str]]:
        """
        Get the ARP table from the system.

        Returns:
            List of dicts with 'ip' and 'mac' keys.
        """
        entries = []

        try:
            if platform.system().lower() == 'windows':
                result = subprocess.run(
                    ['arp', '-a'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                # Parse Windows ARP output
                for line in result.stdout.splitlines():
                    match = re.search(
                        r'(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})',
                        line
                    )
                    if match:
                        entries.append({
                            'ip': match.group(1),
                            'mac': match.group(2).replace('-', ':').lower()
                        })
            else:
                result = subprocess.run(
                    ['arp', '-a'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                # Parse Unix ARP output
                for line in result.stdout.splitlines():
                    match = re.search(
                        r'\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F:]{17})',
                        line
                    )
                    if match:
                        entries.append({
                            'ip': match.group(1),
                            'mac': match.group(2).lower()
                        })

            logger.info(f"Found {len(entries)} ARP entries")

        except Exception as e:
            logger.error(f"Failed to get ARP table: {e}")

        return entries

    def resolve_hostname(self, ip: str) -> Optional[str]:
        """Resolve hostname for an IP address using DNS."""
        try:
            hostname, _, _ = socket.gethostbyaddr(ip)
            return hostname
        except socket.herror:
            return None
        except Exception as e:
            logger.debug(f"Hostname resolution failed for {ip}: {e}")
            return None

    def enrich_device(self, device: DiscoveredDevice) -> DiscoveredDevice:
        """
        Enrich a device with additional information (hostname, MAC, etc.).
        """
        # Try to resolve hostname
        if not device.hostname:
            device.hostname = self.resolve_hostname(device.ip_address)

        # Try to get MAC from ARP table
        if not device.mac_address:
            arp_table = self.get_arp_table()
            for entry in arp_table:
                if entry['ip'] == device.ip_address:
                    device.mac_address = entry['mac']
                    break

        # Check if it's a potential MK3 based on various heuristics
        device.is_mk3_candidate = self._check_mk3_candidate(device)

        return device

    def _check_mk3_candidate(self, device: DiscoveredDevice) -> bool:
        """Check if a device is a potential MK3 amplifier."""
        # Check hostname patterns
        if device.hostname:
            hostname_lower = device.hostname.lower()
            if any(pattern in hostname_lower for pattern in ['dsp', 'sonance', 'mk3', 'amp']):
                return True

        # Check MAC prefix (if known Sonance prefixes are added)
        if device.mac_address:
            mac_prefix = device.mac_address[:8].upper().replace(':', '-')
            if mac_prefix in self.SONANCE_MAC_PREFIXES:
                return True

        # Check for common ports
        if 80 in device.open_ports or 23 in device.open_ports:
            return True

        return False

    def quick_scan(
        self,
        ip: str,
        ports: Optional[List[int]] = None
    ) -> DiscoveredDevice:
        """
        Perform a quick scan of a single IP address.

        Args:
            ip: IP address to scan
            ports: List of ports to check. If None, uses common ports.

        Returns:
            DiscoveredDevice with available information.
        """
        if ports is None:
            ports = [80, 23, 443, 8080, 10000, 10001]

        logger.info(f"Quick scan of {ip}")

        # Ping first
        success, response_time = self.ping(ip)

        device = DiscoveredDevice(
            ip_address=ip,
            response_time_ms=response_time if success else None
        )

        if success:
            # Check ports
            for port in ports:
                if self._check_port(ip, port):
                    device.open_ports.append(port)

            # Enrich with hostname and MAC
            device = self.enrich_device(device)

        logger.info(f"Quick scan complete: {device}")
        return device

    def _check_port(self, ip: str, port: int) -> bool:
        """Check if a port is open."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False
