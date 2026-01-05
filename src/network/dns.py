"""DNS testing module for MK3 amplifiers."""

import socket
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import dns.resolver
import dns.reversename
import dns.exception

from ..utils import get_logger

logger = get_logger(__name__)


@dataclass
class DNSLookupResult:
    """Result of a DNS lookup."""
    query: str
    query_type: str
    success: bool
    answers: List[str] = field(default_factory=list)
    response_time_ms: Optional[float] = None
    error: Optional[str] = None
    nameserver: Optional[str] = None


@dataclass
class DNSServerTest:
    """Result of testing a DNS server."""
    server_ip: str
    is_reachable: bool
    can_resolve: bool
    response_time_ms: Optional[float] = None
    error: Optional[str] = None


class DNSTester:
    """
    Tests DNS resolution and server connectivity.
    """

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def forward_lookup(
        self,
        hostname: str,
        record_type: str = 'A',
        nameserver: Optional[str] = None
    ) -> DNSLookupResult:
        """
        Perform a forward DNS lookup.

        Args:
            hostname: Hostname to resolve
            record_type: DNS record type (A, AAAA, CNAME, etc.)
            nameserver: Optional specific nameserver to use

        Returns:
            DNSLookupResult
        """
        logger.info(f"Forward DNS lookup: {hostname} ({record_type})")

        result = DNSLookupResult(
            query=hostname,
            query_type=record_type,
            success=False,
            nameserver=nameserver
        )

        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = self.timeout
            resolver.lifetime = self.timeout

            if nameserver:
                resolver.nameservers = [nameserver]

            start = time.perf_counter()
            answers = resolver.resolve(hostname, record_type)
            elapsed = (time.perf_counter() - start) * 1000

            result.success = True
            result.response_time_ms = elapsed
            result.answers = [str(rdata) for rdata in answers]

            logger.info(f"DNS resolved: {hostname} -> {result.answers}")

        except dns.resolver.NXDOMAIN:
            result.error = "Domain does not exist (NXDOMAIN)"
            logger.warning(f"DNS NXDOMAIN: {hostname}")
        except dns.resolver.NoAnswer:
            result.error = f"No {record_type} record found"
            logger.warning(f"DNS no answer: {hostname}")
        except dns.resolver.NoNameservers:
            result.error = "No nameservers available"
            logger.error(f"DNS no nameservers for: {hostname}")
        except dns.exception.Timeout:
            result.error = "DNS query timeout"
            logger.warning(f"DNS timeout: {hostname}")
        except Exception as e:
            result.error = str(e)
            logger.error(f"DNS error: {hostname} - {e}")

        return result

    def reverse_lookup(
        self,
        ip_address: str,
        nameserver: Optional[str] = None
    ) -> DNSLookupResult:
        """
        Perform a reverse DNS lookup (PTR record).

        Args:
            ip_address: IP address to resolve
            nameserver: Optional specific nameserver to use

        Returns:
            DNSLookupResult
        """
        logger.info(f"Reverse DNS lookup: {ip_address}")

        result = DNSLookupResult(
            query=ip_address,
            query_type='PTR',
            success=False,
            nameserver=nameserver
        )

        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = self.timeout
            resolver.lifetime = self.timeout

            if nameserver:
                resolver.nameservers = [nameserver]

            # Convert IP to reverse DNS format
            rev_name = dns.reversename.from_address(ip_address)

            start = time.perf_counter()
            answers = resolver.resolve(rev_name, 'PTR')
            elapsed = (time.perf_counter() - start) * 1000

            result.success = True
            result.response_time_ms = elapsed
            result.answers = [str(rdata).rstrip('.') for rdata in answers]

            logger.info(f"Reverse DNS resolved: {ip_address} -> {result.answers}")

        except dns.resolver.NXDOMAIN:
            result.error = "No PTR record found"
            logger.debug(f"Reverse DNS NXDOMAIN: {ip_address}")
        except dns.resolver.NoAnswer:
            result.error = "No PTR record found"
            logger.debug(f"Reverse DNS no answer: {ip_address}")
        except dns.exception.Timeout:
            result.error = "DNS query timeout"
            logger.warning(f"Reverse DNS timeout: {ip_address}")
        except Exception as e:
            result.error = str(e)
            logger.error(f"Reverse DNS error: {ip_address} - {e}")

        return result

    def test_dns_server(
        self,
        server_ip: str,
        test_domain: str = "google.com"
    ) -> DNSServerTest:
        """
        Test if a DNS server is reachable and functioning.

        Args:
            server_ip: DNS server IP address
            test_domain: Domain to use for testing resolution

        Returns:
            DNSServerTest result
        """
        logger.info(f"Testing DNS server: {server_ip}")

        result = DNSServerTest(
            server_ip=server_ip,
            is_reachable=False,
            can_resolve=False
        )

        # First, check if the server is reachable on port 53
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            sock.connect((server_ip, 53))
            sock.close()
            result.is_reachable = True
        except Exception as e:
            result.error = f"Cannot connect to port 53: {e}"
            logger.warning(f"DNS server unreachable: {server_ip}")
            return result

        # Try to resolve a test domain
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = self.timeout
            resolver.lifetime = self.timeout
            resolver.nameservers = [server_ip]

            start = time.perf_counter()
            answers = resolver.resolve(test_domain, 'A')
            elapsed = (time.perf_counter() - start) * 1000

            result.can_resolve = True
            result.response_time_ms = elapsed

            logger.info(f"DNS server {server_ip} working ({elapsed:.1f}ms)")

        except Exception as e:
            result.error = f"Resolution failed: {e}"
            logger.warning(f"DNS server {server_ip} cannot resolve: {e}")

        return result

    def test_multiple_dns_servers(
        self,
        servers: List[str],
        test_domain: str = "google.com"
    ) -> List[DNSServerTest]:
        """
        Test multiple DNS servers.

        Args:
            servers: List of DNS server IPs
            test_domain: Domain to use for testing

        Returns:
            List of DNSServerTest results
        """
        results = []
        for server in servers:
            result = self.test_dns_server(server, test_domain)
            results.append(result)
        return results

    def get_system_dns_servers(self) -> List[str]:
        """Get the system's configured DNS servers."""
        try:
            resolver = dns.resolver.Resolver()
            return resolver.nameservers
        except Exception as e:
            logger.error(f"Failed to get system DNS servers: {e}")
            return []

    def compare_dns_resolution(
        self,
        hostname: str,
        nameservers: List[str]
    ) -> Dict[str, DNSLookupResult]:
        """
        Compare DNS resolution across multiple nameservers.

        Args:
            hostname: Hostname to resolve
            nameservers: List of nameserver IPs to test

        Returns:
            Dict mapping nameserver IP to DNSLookupResult
        """
        results = {}

        for ns in nameservers:
            result = self.forward_lookup(hostname, 'A', nameserver=ns)
            results[ns] = result

        return results

    def full_dns_diagnostic(
        self,
        ip_address: str,
        hostname: Optional[str] = None,
        extra_nameservers: Optional[List[str]] = None
    ) -> Dict:
        """
        Run a full DNS diagnostic for a device.

        Args:
            ip_address: Device IP address
            hostname: Optional expected hostname
            extra_nameservers: Additional nameservers to test

        Returns:
            Dict with all diagnostic results
        """
        logger.info(f"Running full DNS diagnostic for {ip_address}")

        diagnostic = {
            'ip_address': ip_address,
            'expected_hostname': hostname,
            'reverse_lookup': None,
            'forward_lookup': None,
            'system_dns_servers': [],
            'dns_server_tests': [],
            'issues': []
        }

        # Get system DNS servers
        diagnostic['system_dns_servers'] = self.get_system_dns_servers()

        # Reverse lookup
        rev_result = self.reverse_lookup(ip_address)
        diagnostic['reverse_lookup'] = rev_result

        if not rev_result.success:
            diagnostic['issues'].append(
                f"Reverse DNS lookup failed: {rev_result.error}"
            )

        # Forward lookup if we have a hostname
        resolved_hostname = None
        if hostname:
            fwd_result = self.forward_lookup(hostname)
            diagnostic['forward_lookup'] = fwd_result

            if fwd_result.success:
                if ip_address not in fwd_result.answers:
                    diagnostic['issues'].append(
                        f"Forward lookup mismatch: {hostname} resolves to {fwd_result.answers}, not {ip_address}"
                    )
            else:
                diagnostic['issues'].append(
                    f"Forward DNS lookup failed: {fwd_result.error}"
                )
        elif rev_result.success and rev_result.answers:
            # If we got a hostname from reverse lookup, verify it
            resolved_hostname = rev_result.answers[0]
            fwd_result = self.forward_lookup(resolved_hostname)
            diagnostic['forward_lookup'] = fwd_result

            if fwd_result.success and ip_address not in fwd_result.answers:
                diagnostic['issues'].append(
                    f"DNS mismatch: {resolved_hostname} doesn't resolve back to {ip_address}"
                )

        # Test DNS servers
        all_servers = list(set(
            diagnostic['system_dns_servers'] +
            (extra_nameservers or [])
        ))

        for server in all_servers:
            test_result = self.test_dns_server(server)
            diagnostic['dns_server_tests'].append(test_result)

            if not test_result.can_resolve:
                diagnostic['issues'].append(
                    f"DNS server {server} is not functioning: {test_result.error}"
                )

        logger.info(f"DNS diagnostic complete. {len(diagnostic['issues'])} issues found.")
        return diagnostic
