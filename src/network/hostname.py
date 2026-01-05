"""Hostname resolution testing for MK3 amplifiers."""

import socket
import struct
import time
import threading
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, field

from ..utils import get_logger

logger = get_logger(__name__)


@dataclass
class HostnameResult:
    """Result of a hostname resolution attempt."""
    ip_address: str
    method: str  # 'dns', 'netbios', 'mdns', 'socket'
    success: bool
    hostname: Optional[str] = None
    response_time_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass
class mDNSService:
    """Represents an mDNS service discovered."""
    name: str
    service_type: str
    host: str
    port: int
    properties: Dict[str, str] = field(default_factory=dict)


class HostnameTester:
    """
    Tests hostname resolution using various methods.
    """

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def resolve_via_socket(self, ip_address: str) -> HostnameResult:
        """
        Resolve hostname using socket.gethostbyaddr (system resolver).

        This uses the system's DNS configuration.
        """
        logger.debug(f"Socket hostname lookup: {ip_address}")

        result = HostnameResult(
            ip_address=ip_address,
            method='socket',
            success=False
        )

        try:
            start = time.perf_counter()
            hostname, aliases, _ = socket.gethostbyaddr(ip_address)
            elapsed = (time.perf_counter() - start) * 1000

            result.success = True
            result.hostname = hostname
            result.response_time_ms = elapsed

            logger.info(f"Socket resolved: {ip_address} -> {hostname}")

        except socket.herror as e:
            result.error = f"Host not found: {e}"
            logger.debug(f"Socket resolution failed: {ip_address}")
        except socket.timeout:
            result.error = "Timeout"
            logger.debug(f"Socket resolution timeout: {ip_address}")
        except Exception as e:
            result.error = str(e)
            logger.error(f"Socket resolution error: {ip_address} - {e}")

        return result

    def resolve_via_netbios(self, ip_address: str) -> HostnameResult:
        """
        Resolve hostname using NetBIOS Name Service (UDP port 137).

        This is the method Windows uses for local network name resolution.
        """
        logger.debug(f"NetBIOS hostname lookup: {ip_address}")

        result = HostnameResult(
            ip_address=ip_address,
            method='netbios',
            success=False
        )

        try:
            # NetBIOS Name Service query
            # Transaction ID (2 bytes) + Flags (2 bytes) + Questions (2 bytes) +
            # Answer RRs (2 bytes) + Authority RRs (2 bytes) + Additional RRs (2 bytes)
            # + Query for * (wildcard) name

            transaction_id = 0x1234
            flags = 0x0000  # Standard query
            questions = 1

            # Encode the query name "*" (wildcard for status query)
            # NetBIOS names are 16 bytes, padded with spaces
            name = b'*' + b'\x00' * 15  # Wildcard name

            # First-level encoding of NetBIOS name
            encoded_name = b'\x20'  # Length
            for byte in name:
                encoded_name += bytes([((byte >> 4) & 0x0f) + ord('A')])
                encoded_name += bytes([(byte & 0x0f) + ord('A')])
            encoded_name += b'\x00'  # Null terminator

            # Build the query packet
            query = struct.pack(
                '>HHHHHH',
                transaction_id,
                flags,
                questions,
                0,  # Answer RRs
                0,  # Authority RRs
                0   # Additional RRs
            )
            query += encoded_name
            query += struct.pack('>HH', 0x0021, 0x0001)  # Type: NBSTAT, Class: IN

            # Send the query
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)

            start = time.perf_counter()
            sock.sendto(query, (ip_address, 137))

            try:
                response, _ = sock.recvfrom(1024)
                elapsed = (time.perf_counter() - start) * 1000

                # Parse the response to extract names
                if len(response) > 56:
                    # Skip header and query, find the name table
                    num_names = response[56]
                    names = []

                    offset = 57
                    for i in range(num_names):
                        if offset + 18 <= len(response):
                            name_bytes = response[offset:offset + 15]
                            name_type = response[offset + 15]
                            name_flags = struct.unpack('>H', response[offset + 16:offset + 18])[0]

                            # Decode the name
                            name = name_bytes.decode('ascii', errors='ignore').strip()
                            if name and name_type == 0x00:  # Workstation name
                                names.append(name)

                            offset += 18

                    if names:
                        result.success = True
                        result.hostname = names[0]
                        result.response_time_ms = elapsed
                        logger.info(f"NetBIOS resolved: {ip_address} -> {result.hostname}")

            except socket.timeout:
                result.error = "No NetBIOS response"
                logger.debug(f"NetBIOS timeout: {ip_address}")

            sock.close()

        except Exception as e:
            result.error = str(e)
            logger.error(f"NetBIOS error: {ip_address} - {e}")

        return result

    def resolve_via_mdns(
        self,
        ip_address: str,
        browse_timeout: float = 3.0
    ) -> HostnameResult:
        """
        Resolve hostname using mDNS/Bonjour.

        This discovers the device's .local hostname.
        """
        logger.debug(f"mDNS hostname lookup: {ip_address}")

        result = HostnameResult(
            ip_address=ip_address,
            method='mdns',
            success=False
        )

        try:
            from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
            import threading

            class Listener(ServiceListener):
                def __init__(self):
                    self.found = None
                    self.event = threading.Event()

                def add_service(self, zc, type_, name):
                    info = zc.get_service_info(type_, name)
                    if info:
                        # Check if this service's IP matches
                        for addr in info.addresses:
                            addr_str = socket.inet_ntoa(addr)
                            if addr_str == ip_address:
                                self.found = info.server.rstrip('.')
                                self.event.set()
                                break

                def remove_service(self, zc, type_, name):
                    pass

                def update_service(self, zc, type_, name):
                    pass

            zeroconf = Zeroconf()
            listener = Listener()

            # Browse for HTTP services
            browser = ServiceBrowser(zeroconf, "_http._tcp.local.", listener)

            start = time.perf_counter()

            # Wait for discovery
            listener.event.wait(timeout=browse_timeout)

            elapsed = (time.perf_counter() - start) * 1000

            zeroconf.close()

            if listener.found:
                result.success = True
                result.hostname = listener.found
                result.response_time_ms = elapsed
                logger.info(f"mDNS resolved: {ip_address} -> {result.hostname}")
            else:
                result.error = "No mDNS service found"
                logger.debug(f"mDNS: No service found for {ip_address}")

        except ImportError:
            result.error = "zeroconf library not available"
            logger.warning("mDNS not available: zeroconf not installed")
        except Exception as e:
            result.error = str(e)
            logger.error(f"mDNS error: {ip_address} - {e}")

        return result

    def discover_mdns_services(
        self,
        service_types: List[str],
        browse_timeout: float = 5.0,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> List[mDNSService]:
        """
        Discover mDNS services on the network.

        Args:
            service_types: List of service types to discover (e.g., ["_http._tcp.local."])
            browse_timeout: Time to browse in seconds
            progress_callback: Called when a service is found

        Returns:
            List of discovered services
        """
        logger.info(f"Discovering mDNS services: {service_types}")

        services: List[mDNSService] = []

        try:
            from zeroconf import Zeroconf, ServiceBrowser, ServiceListener

            class Listener(ServiceListener):
                def __init__(self):
                    self.lock = threading.Lock()

                def add_service(self, zc, type_, name):
                    info = zc.get_service_info(type_, name)
                    if info:
                        props = {}
                        if info.properties:
                            for k, v in info.properties.items():
                                try:
                                    props[k.decode()] = v.decode() if isinstance(v, bytes) else str(v)
                                except Exception:
                                    pass

                        service = mDNSService(
                            name=name,
                            service_type=type_,
                            host=info.server.rstrip('.'),
                            port=info.port,
                            properties=props
                        )

                        with self.lock:
                            services.append(service)

                        if progress_callback:
                            progress_callback(name)

                        logger.debug(f"mDNS service found: {name} at {service.host}:{service.port}")

                def remove_service(self, zc, type_, name):
                    pass

                def update_service(self, zc, type_, name):
                    pass

            zeroconf = Zeroconf()
            listener = Listener()

            browsers = [
                ServiceBrowser(zeroconf, stype, listener)
                for stype in service_types
            ]

            # Wait for discovery
            time.sleep(browse_timeout)

            zeroconf.close()

            logger.info(f"mDNS discovery complete. Found {len(services)} services.")

        except ImportError:
            logger.warning("mDNS not available: zeroconf not installed")
        except Exception as e:
            logger.error(f"mDNS discovery error: {e}")

        return services

    def resolve_all_methods(
        self,
        ip_address: str,
        expected_hostname: Optional[str] = None
    ) -> Dict[str, HostnameResult]:
        """
        Try all hostname resolution methods.

        Args:
            ip_address: IP address to resolve
            expected_hostname: Optional expected hostname for comparison

        Returns:
            Dict mapping method name to result
        """
        logger.info(f"Resolving hostname for {ip_address} using all methods")

        results = {}

        # Socket/DNS resolution
        results['socket'] = self.resolve_via_socket(ip_address)

        # NetBIOS resolution
        results['netbios'] = self.resolve_via_netbios(ip_address)

        # mDNS resolution
        results['mdns'] = self.resolve_via_mdns(ip_address)

        # Log summary
        successful = [m for m, r in results.items() if r.success]
        if successful:
            logger.info(f"Hostname resolved via: {', '.join(successful)}")
        else:
            logger.warning(f"No hostname resolution method succeeded for {ip_address}")

        # Check against expected hostname if provided
        if expected_hostname:
            for method, result in results.items():
                if result.success and result.hostname:
                    if result.hostname.lower() != expected_hostname.lower():
                        logger.warning(
                            f"Hostname mismatch ({method}): expected '{expected_hostname}', "
                            f"got '{result.hostname}'"
                        )

        return results

    def diagnose_hostname_issue(
        self,
        ip_address: str,
        expected_hostname: str = "DSP"
    ) -> Dict:
        """
        Diagnose why a hostname might not be appearing.

        This is specifically for the issue where AngryIP shows blank hostname.

        Args:
            ip_address: Device IP address
            expected_hostname: Expected hostname (default "DSP" for MK3)

        Returns:
            Diagnostic report dict
        """
        logger.info(f"Diagnosing hostname issue for {ip_address}")

        diagnostic = {
            'ip_address': ip_address,
            'expected_hostname': expected_hostname,
            'resolution_results': {},
            'issues': [],
            'recommendations': []
        }

        # Try all resolution methods
        results = self.resolve_all_methods(ip_address, expected_hostname)
        diagnostic['resolution_results'] = {
            method: {
                'success': r.success,
                'hostname': r.hostname,
                'error': r.error,
                'response_time_ms': r.response_time_ms
            }
            for method, r in results.items()
        }

        # Analyze results
        any_success = any(r.success for r in results.values())
        hostname_matches = False

        for method, result in results.items():
            if result.success:
                if result.hostname and result.hostname.upper() == expected_hostname.upper():
                    hostname_matches = True
                    break
                elif result.hostname:
                    diagnostic['issues'].append(
                        f"Hostname mismatch via {method}: got '{result.hostname}', "
                        f"expected '{expected_hostname}'"
                    )

        if not any_success:
            diagnostic['issues'].append(
                "No hostname resolution method succeeded"
            )
            diagnostic['recommendations'].extend([
                "Check if the device is configured to broadcast its hostname",
                "Verify NetBIOS name service is enabled on the device",
                "Check if mDNS/Bonjour is enabled on the device",
                "Verify there's a PTR record in DNS for reverse lookup"
            ])

        if not results['netbios'].success:
            diagnostic['issues'].append(
                f"NetBIOS resolution failed: {results['netbios'].error}"
            )
            diagnostic['recommendations'].append(
                "NetBIOS name service may be disabled on the device or blocked by firewall"
            )

        if not results['mdns'].success:
            diagnostic['issues'].append(
                f"mDNS resolution failed: {results['mdns'].error}"
            )
            diagnostic['recommendations'].append(
                "mDNS/Bonjour may be disabled or not advertising any services"
            )

        if not results['socket'].success:
            diagnostic['issues'].append(
                f"DNS reverse lookup failed: {results['socket'].error}"
            )
            diagnostic['recommendations'].append(
                "No PTR record in DNS for this IP address"
            )

        if not diagnostic['issues']:
            diagnostic['issues'].append("No issues found - hostname resolves correctly")

        logger.info(f"Hostname diagnosis complete. {len(diagnostic['issues'])} issues found.")
        return diagnostic
