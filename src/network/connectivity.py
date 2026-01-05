"""Connectivity testing module for MK3 amplifiers."""

import socket
import time
import threading
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.exceptions import RequestException

from ..utils import get_logger

logger = get_logger(__name__)


@dataclass
class PortScanResult:
    """Result of a port scan."""
    port: int
    is_open: bool
    service_name: Optional[str] = None
    banner: Optional[str] = None
    response_time_ms: Optional[float] = None


@dataclass
class HTTPEndpointResult:
    """Result of an HTTP endpoint test."""
    url: str
    is_accessible: bool
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    error: Optional[str] = None
    title: Optional[str] = None


@dataclass
class PingResult:
    """Result of a ping test."""
    ip_address: str
    is_reachable: bool
    packets_sent: int = 0
    packets_received: int = 0
    min_ms: Optional[float] = None
    avg_ms: Optional[float] = None
    max_ms: Optional[float] = None
    packet_loss_percent: float = 0.0


@dataclass
class ConnectivityReport:
    """Full connectivity test report."""
    ip_address: str
    timestamp: str
    ping_result: Optional[PingResult] = None
    open_ports: List[PortScanResult] = field(default_factory=list)
    http_endpoints: List[HTTPEndpointResult] = field(default_factory=list)
    overall_status: str = "unknown"


class ConnectivityTester:
    """
    Tests network connectivity to MK3 amplifiers.
    """

    # Well-known port services
    PORT_SERVICES = {
        21: "FTP",
        22: "SSH",
        23: "Telnet",
        80: "HTTP",
        443: "HTTPS",
        8080: "HTTP-Alt",
        8000: "HTTP-Alt",
        10000: "Control",
        10001: "Control",
        10002: "Control",
        4998: "Crestron",
        4999: "Crestron",
        5000: "Crestron",
        41794: "Crestron-CIP",
        41795: "Crestron-CTP",
    }

    def __init__(
        self,
        timeout: float = 5.0,
        http_timeout: float = 10.0
    ):
        self.timeout = timeout
        self.http_timeout = http_timeout
        self._cancel_flag = threading.Event()

    def cancel(self) -> None:
        """Cancel ongoing tests."""
        self._cancel_flag.set()

    def reset_cancel(self) -> None:
        """Reset cancel flag."""
        self._cancel_flag.clear()

    def ping_extended(
        self,
        ip: str,
        count: int = 10,
        interval: float = 0.5,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> PingResult:
        """
        Extended ping test with statistics.

        Args:
            ip: IP address to ping
            count: Number of pings
            interval: Interval between pings in seconds
            progress_callback: Callback(current, total) for progress

        Returns:
            PingResult with statistics
        """
        logger.info(f"Extended ping to {ip} ({count} packets)")

        response_times = []
        received = 0

        for i in range(count):
            if self._cancel_flag.is_set():
                break

            success, response_time = self._single_ping(ip)

            if success:
                received += 1
                if response_time is not None:
                    response_times.append(response_time)

            if progress_callback:
                progress_callback(i + 1, count)

            if i < count - 1:
                time.sleep(interval)

        packet_loss = ((count - received) / count) * 100

        result = PingResult(
            ip_address=ip,
            is_reachable=received > 0,
            packets_sent=count,
            packets_received=received,
            packet_loss_percent=packet_loss
        )

        if response_times:
            result.min_ms = min(response_times)
            result.avg_ms = sum(response_times) / len(response_times)
            result.max_ms = max(response_times)

        logger.info(f"Ping complete: {received}/{count} received, {packet_loss:.1f}% loss")
        return result

    def _single_ping(self, ip: str) -> Tuple[bool, Optional[float]]:
        """Perform a single ping (TCP-based for reliability)."""
        # Use TCP connect to port 80 as a proxy for ping
        # This works even when ICMP is blocked
        try:
            start = time.perf_counter()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)

            # Try to connect to common ports
            for port in [80, 443, 23]:
                result = sock.connect_ex((ip, port))
                if result == 0:
                    elapsed = (time.perf_counter() - start) * 1000
                    sock.close()
                    return True, elapsed

            sock.close()

            # Fall back to raw socket if no ports respond
            import subprocess
            import platform

            param = '-n' if platform.system().lower() == 'windows' else '-c'
            timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
            timeout_val = str(int(self.timeout * 1000)) if platform.system().lower() == 'windows' else str(int(self.timeout))

            start = time.perf_counter()
            result = subprocess.run(
                ['ping', param, '1', timeout_param, timeout_val, ip],
                capture_output=True,
                text=True,
                timeout=self.timeout + 1
            )
            elapsed = (time.perf_counter() - start) * 1000

            return result.returncode == 0, elapsed

        except Exception as e:
            logger.debug(f"Ping error: {e}")
            return False, None

    def scan_ports(
        self,
        ip: str,
        ports: List[int],
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
        max_workers: int = 20
    ) -> List[PortScanResult]:
        """
        Scan multiple ports on an IP address.

        Args:
            ip: IP address to scan
            ports: List of ports to scan
            progress_callback: Callback(current, total, port) for progress
            max_workers: Maximum concurrent scans

        Returns:
            List of PortScanResult for each port
        """
        self.reset_cancel()
        logger.info(f"Scanning {len(ports)} ports on {ip}")

        results: List[PortScanResult] = []
        completed = 0

        def scan_port(port: int) -> PortScanResult:
            if self._cancel_flag.is_set():
                return PortScanResult(port=port, is_open=False)

            start = time.perf_counter()
            is_open = False
            banner = None

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                result = sock.connect_ex((ip, port))

                if result == 0:
                    is_open = True
                    # Try to grab banner
                    try:
                        sock.settimeout(1.0)
                        sock.send(b'\r\n')
                        banner = sock.recv(1024).decode('utf-8', errors='ignore').strip()
                    except Exception:
                        pass

                sock.close()

            except Exception as e:
                logger.debug(f"Port scan error on {port}: {e}")

            elapsed = (time.perf_counter() - start) * 1000

            return PortScanResult(
                port=port,
                is_open=is_open,
                service_name=self.PORT_SERVICES.get(port),
                banner=banner if banner else None,
                response_time_ms=elapsed if is_open else None
            )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(scan_port, port): port for port in ports}

            for future in as_completed(futures):
                if self._cancel_flag.is_set():
                    break

                completed += 1
                port = futures[future]

                if progress_callback:
                    progress_callback(completed, len(ports), port)

                try:
                    result = future.result()
                    results.append(result)
                    if result.is_open:
                        logger.info(f"Port {port} is OPEN ({result.service_name or 'unknown'})")
                except Exception as e:
                    logger.error(f"Error scanning port {port}: {e}")
                    results.append(PortScanResult(port=port, is_open=False))

        # Sort by port number
        results.sort(key=lambda r: r.port)

        open_count = sum(1 for r in results if r.is_open)
        logger.info(f"Port scan complete: {open_count}/{len(ports)} ports open")

        return results

    def test_http_endpoint(
        self,
        ip: str,
        endpoint: str,
        port: int = 80,
        use_https: bool = False
    ) -> HTTPEndpointResult:
        """
        Test an HTTP endpoint.

        Args:
            ip: IP address
            endpoint: Endpoint path (e.g., "/Landing.htm")
            port: Port number
            use_https: Use HTTPS instead of HTTP

        Returns:
            HTTPEndpointResult
        """
        protocol = "https" if use_https else "http"
        port_str = "" if (port == 80 and not use_https) or (port == 443 and use_https) else f":{port}"
        url = f"{protocol}://{ip}{port_str}{endpoint}"

        logger.info(f"Testing HTTP endpoint: {url}")

        result = HTTPEndpointResult(url=url, is_accessible=False)

        try:
            start = time.perf_counter()
            response = requests.get(
                url,
                timeout=self.http_timeout,
                verify=False,  # Allow self-signed certs
                allow_redirects=True
            )
            elapsed = (time.perf_counter() - start) * 1000

            result.is_accessible = True
            result.status_code = response.status_code
            result.response_time_ms = elapsed
            result.content_type = response.headers.get('Content-Type')
            result.content_length = len(response.content)

            # Try to extract page title
            if 'text/html' in (result.content_type or ''):
                import re
                title_match = re.search(r'<title>(.*?)</title>', response.text, re.IGNORECASE)
                if title_match:
                    result.title = title_match.group(1).strip()

            logger.info(f"HTTP {result.status_code}: {url} ({elapsed:.1f}ms)")

        except requests.exceptions.ConnectTimeout:
            result.error = "Connection timeout"
            logger.warning(f"HTTP timeout: {url}")
        except requests.exceptions.ConnectionError as e:
            result.error = f"Connection error: {str(e)}"
            logger.warning(f"HTTP connection error: {url}")
        except RequestException as e:
            result.error = f"Request error: {str(e)}"
            logger.error(f"HTTP request error: {url} - {e}")

        return result

    def test_http_endpoints(
        self,
        ip: str,
        endpoints: List[str],
        port: int = 80,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[HTTPEndpointResult]:
        """
        Test multiple HTTP endpoints.

        Args:
            ip: IP address
            endpoints: List of endpoint paths
            port: Port number
            progress_callback: Callback(current, total, endpoint) for progress

        Returns:
            List of HTTPEndpointResult
        """
        results = []

        for i, endpoint in enumerate(endpoints):
            if self._cancel_flag.is_set():
                break

            result = self.test_http_endpoint(ip, endpoint, port)
            results.append(result)

            if progress_callback:
                progress_callback(i + 1, len(endpoints), endpoint)

        return results

    def test_tcp_connection(
        self,
        ip: str,
        port: int,
        timeout: Optional[float] = None
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """
        Test a TCP connection and return details.

        Returns:
            Tuple of (success, response_time_ms, error_message)
        """
        timeout = timeout or self.timeout

        try:
            start = time.perf_counter()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            elapsed = (time.perf_counter() - start) * 1000
            sock.close()

            if result == 0:
                return True, elapsed, None
            else:
                return False, elapsed, f"Connection refused (errno {result})"

        except socket.timeout:
            return False, None, "Connection timeout"
        except Exception as e:
            return False, None, str(e)

    def run_full_test(
        self,
        ip: str,
        ports: List[int],
        http_endpoints: List[str],
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> ConnectivityReport:
        """
        Run a full connectivity test suite.

        Args:
            ip: IP address to test
            ports: Ports to scan
            http_endpoints: HTTP endpoints to test
            progress_callback: Callback(phase, current, total)

        Returns:
            ConnectivityReport with all results
        """
        from datetime import datetime

        logger.info(f"Starting full connectivity test for {ip}")

        report = ConnectivityReport(
            ip_address=ip,
            timestamp=datetime.now().isoformat()
        )

        # Phase 1: Extended ping
        if progress_callback:
            progress_callback("ping", 0, 10)

        report.ping_result = self.ping_extended(
            ip, count=10,
            progress_callback=lambda c, t: progress_callback("ping", c, t) if progress_callback else None
        )

        # Phase 2: Port scan
        if progress_callback:
            progress_callback("ports", 0, len(ports))

        report.open_ports = self.scan_ports(
            ip, ports,
            progress_callback=lambda c, t, p: progress_callback("ports", c, t) if progress_callback else None
        )

        # Phase 3: HTTP endpoints
        if progress_callback:
            progress_callback("http", 0, len(http_endpoints))

        report.http_endpoints = self.test_http_endpoints(
            ip, http_endpoints,
            progress_callback=lambda c, t, e: progress_callback("http", c, t) if progress_callback else None
        )

        # Determine overall status
        has_ping = report.ping_result and report.ping_result.is_reachable
        has_open_ports = any(p.is_open for p in report.open_ports)
        has_http = any(e.is_accessible for e in report.http_endpoints)

        if has_ping and has_http:
            report.overall_status = "healthy"
        elif has_ping and has_open_ports:
            report.overall_status = "partial"
        elif has_ping:
            report.overall_status = "reachable"
        else:
            report.overall_status = "unreachable"

        logger.info(f"Full test complete. Status: {report.overall_status}")
        return report
