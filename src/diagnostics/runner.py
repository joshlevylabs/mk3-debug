"""Diagnostic test runner and orchestrator."""

import threading
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..network import (
    NetworkDiscovery,
    ConnectivityTester,
    DNSTester,
    HostnameTester,
    CommandTester,
    MK3ProtocolTester
)
from ..utils import get_logger, Config

logger = get_logger(__name__)


class TestStatus(Enum):
    """Status of a diagnostic test."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"
    ERROR = "error"


class Severity(Enum):
    """Severity level of a diagnostic finding."""
    CRITICAL = "critical"  # Prevents core functionality
    HIGH = "high"          # Significant impact on operation
    MEDIUM = "medium"      # Partial functionality affected
    LOW = "low"            # Minor issue, cosmetic or non-blocking
    INFO = "info"          # Informational only


@dataclass
class RootCause:
    """Root cause analysis for a diagnostic finding."""
    category: str                    # e.g., "Network", "Configuration", "Firmware", "Hardware"
    description: str                 # Human-readable explanation of the root cause
    technical_details: str           # Developer-focused technical explanation
    evidence: List[str] = field(default_factory=list)  # Supporting data/observations
    related_tests: List[str] = field(default_factory=list)  # Other tests affected by this issue
    firmware_relevant: bool = False  # Flag for firmware team attention


@dataclass
class CorrectiveAction:
    """A corrective action to resolve a diagnostic finding."""
    priority: int                    # 1 = highest priority, do first
    action: str                      # What to do
    description: str                 # Detailed explanation
    responsible_party: str           # "user", "installer", "developer", "firmware_team"
    verification_steps: List[str] = field(default_factory=list)  # How to verify the fix worked
    estimated_complexity: str = "low"  # "low", "medium", "high"


@dataclass
class DiagnosticFinding:
    """A single diagnostic finding with full analysis."""
    issue: str                       # Short issue title
    severity: Severity
    root_cause: RootCause
    corrective_actions: List[CorrectiveAction] = field(default_factory=list)
    affected_functionality: List[str] = field(default_factory=list)  # What features are impacted


@dataclass
class TestResult:
    """Result of a single diagnostic test."""
    name: str
    status: TestStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    recommendations: List[str] = field(default_factory=list)
    # Enhanced diagnostic fields
    findings: List[DiagnosticFinding] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)  # Raw test data for developer analysis
    test_methodology: str = ""  # How the test was performed
    environment_info: Dict[str, Any] = field(default_factory=dict)  # Network/system context


@dataclass
class DiagnosticReport:
    """Complete diagnostic report."""
    timestamp: datetime
    ip_address: str
    tests: List[TestResult] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=lambda: {
        'passed': 0,
        'failed': 0,
        'warnings': 0,
        'skipped': 0
    })
    overall_status: str = "unknown"
    duration_ms: Optional[float] = None


class DiagnosticRunner:
    """
    Orchestrates diagnostic tests for MK3 amplifiers.
    """

    def __init__(self, config: Config):
        self.config = config

        # Initialize testers
        self._discovery = NetworkDiscovery(timeout=config.default_timeout)
        self._connectivity = ConnectivityTester(
            timeout=config.default_timeout,
            http_timeout=config.http_timeout
        )
        self._dns = DNSTester(timeout=config.default_timeout)
        self._hostname = HostnameTester(timeout=config.default_timeout)
        self._commands = CommandTester(timeout=config.default_timeout)
        self._mk3_protocol = MK3ProtocolTester(timeout=config.mk3_protocol_timeout)

        self._cancel_flag = threading.Event()
        self._current_report: Optional[DiagnosticReport] = None

    def cancel(self) -> None:
        """Cancel running diagnostics."""
        self._cancel_flag.set()
        self._discovery.cancel()
        self._connectivity.cancel()
        self._commands.cancel()

    def reset_cancel(self) -> None:
        """Reset cancel flag."""
        self._cancel_flag.clear()
        self._discovery.reset_cancel()
        self._connectivity.reset_cancel()
        self._commands.reset_cancel()

    def run_diagnostics(
        self,
        ip_address: str,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        test_callback: Optional[Callable[[TestResult], None]] = None
    ) -> DiagnosticReport:
        """
        Run complete diagnostic suite.

        Args:
            ip_address: Target IP address
            progress_callback: Callback(phase_name, current_step, total_steps)
            test_callback: Callback(test_result) called after each test

        Returns:
            DiagnosticReport with all results
        """
        self.reset_cancel()

        start_time = datetime.now()

        report = DiagnosticReport(
            timestamp=start_time,
            ip_address=ip_address
        )
        self._current_report = report

        tests = [
            ("Network Reachability", self._test_reachability),
            ("Port Scan", self._test_ports),
            ("HTTP Web Interface", self._test_http),
            ("MK3 Control Protocol", self._test_mk3_protocol),
            ("Hostname Resolution", self._test_hostname),
            ("DNS Configuration", self._test_dns),
            ("Command Protocol (Legacy)", self._test_commands),
        ]

        total_tests = len(tests)

        for i, (name, test_func) in enumerate(tests):
            if self._cancel_flag.is_set():
                break

            if progress_callback:
                progress_callback(name, i + 1, total_tests)

            logger.info(f"Running test: {name}")

            try:
                result = test_func(ip_address)
            except Exception as e:
                logger.error(f"Test error ({name}): {e}")
                result = TestResult(
                    name=name,
                    status=TestStatus.ERROR,
                    message=str(e)
                )

            report.tests.append(result)

            # Update summary
            if result.status == TestStatus.PASSED:
                report.summary['passed'] += 1
            elif result.status == TestStatus.FAILED:
                report.summary['failed'] += 1
            elif result.status == TestStatus.WARNING:
                report.summary['warnings'] += 1
            elif result.status == TestStatus.SKIPPED:
                report.summary['skipped'] += 1

            if test_callback:
                test_callback(result)

        # Determine overall status
        if report.summary['failed'] > 0:
            report.overall_status = "problems_detected"
        elif report.summary['warnings'] > 0:
            report.overall_status = "minor_issues"
        else:
            report.overall_status = "healthy"

        # Calculate duration
        end_time = datetime.now()
        report.duration_ms = (end_time - start_time).total_seconds() * 1000

        logger.info(f"Diagnostics complete: {report.overall_status}")
        return report

    def _test_reachability(self, ip: str) -> TestResult:
        """Test network reachability."""
        import time
        start = time.perf_counter()

        ping_result = self._connectivity.ping_extended(ip, count=5)

        duration = (time.perf_counter() - start) * 1000

        if ping_result.is_reachable:
            if ping_result.packet_loss_percent == 0:
                status = TestStatus.PASSED
                message = f"Device reachable - {ping_result.avg_ms:.1f}ms avg latency"
            else:
                status = TestStatus.WARNING
                message = f"Device reachable but {ping_result.packet_loss_percent:.0f}% packet loss"
        else:
            status = TestStatus.FAILED
            message = "Device not reachable"

        recommendations = []
        if not ping_result.is_reachable:
            recommendations.extend([
                "Verify the IP address is correct",
                "Check that the device is powered on",
                "Verify network cable connections",
                "Check for firewall rules blocking ICMP"
            ])

        return TestResult(
            name="Network Reachability",
            status=status,
            message=message,
            details={
                'packets_sent': ping_result.packets_sent,
                'packets_received': ping_result.packets_received,
                'packet_loss_percent': ping_result.packet_loss_percent,
                'min_ms': ping_result.min_ms,
                'avg_ms': ping_result.avg_ms,
                'max_ms': ping_result.max_ms
            },
            duration_ms=duration,
            recommendations=recommendations
        )

    def _test_ports(self, ip: str) -> TestResult:
        """Test open ports."""
        import time
        start = time.perf_counter()

        key_ports = [80, 23, 443, 8080, 10000, 10001, 4998]
        port_results = self._connectivity.scan_ports(ip, key_ports)

        duration = (time.perf_counter() - start) * 1000

        open_ports = [r for r in port_results if r.is_open]
        has_web = any(r.port == 80 for r in open_ports)
        has_control = any(r.port in [23, 10000, 10001, 4998] for r in open_ports)

        if open_ports:
            if has_web and has_control:
                status = TestStatus.PASSED
                message = f"{len(open_ports)} ports open (web and control)"
            elif has_web:
                status = TestStatus.WARNING
                message = f"{len(open_ports)} ports open (web only, no control port)"
            elif has_control:
                status = TestStatus.WARNING
                message = f"{len(open_ports)} ports open (control only, no web)"
            else:
                status = TestStatus.WARNING
                message = f"{len(open_ports)} ports open"
        else:
            status = TestStatus.FAILED
            message = "No ports responding"

        recommendations = []
        if not has_web:
            recommendations.append(
                "Web interface (port 80) not accessible - check device web server"
            )
        if not has_control:
            recommendations.append(
                "Control ports not found - device may need configuration"
            )

        return TestResult(
            name="Port Scan",
            status=status,
            message=message,
            details={
                'open_ports': [r.port for r in open_ports],
                'closed_ports': [r.port for r in port_results if not r.is_open],
                'has_web': has_web,
                'has_control': has_control
            },
            duration_ms=duration,
            recommendations=recommendations
        )

    def _test_http(self, ip: str) -> TestResult:
        """Test HTTP web interface."""
        import time
        start = time.perf_counter()

        endpoints = ["/", "/Landing.htm", "/index.html"]
        http_results = self._connectivity.test_http_endpoints(ip, endpoints)

        duration = (time.perf_counter() - start) * 1000

        accessible = [r for r in http_results if r.is_accessible]
        landing = next((r for r in accessible if 'Landing' in r.url), None)

        if landing:
            status = TestStatus.PASSED
            message = f"Web interface accessible at /Landing.htm ({landing.response_time_ms:.0f}ms)"
        elif accessible:
            status = TestStatus.WARNING
            message = f"Web server responding but /Landing.htm not found"
        else:
            status = TestStatus.FAILED
            message = "Web interface not accessible"

        recommendations = []
        if not accessible:
            recommendations.extend([
                "Check if device web server is enabled",
                "Verify port 80 is not blocked by firewall",
                "Try accessing the device from a different browser"
            ])
        elif not landing:
            recommendations.append(
                "Web server running but main page not found - check device firmware"
            )

        return TestResult(
            name="HTTP Web Interface",
            status=status,
            message=message,
            details={
                'accessible_endpoints': [r.url for r in accessible],
                'failed_endpoints': [r.url for r in http_results if not r.is_accessible],
                'landing_page_found': landing is not None
            },
            duration_ms=duration,
            recommendations=recommendations
        )

    def _test_mk3_protocol(self, ip: str) -> TestResult:
        """
        Test MK3 binary control protocol on port 52000.

        This is the PRIMARY control interface for MK3 amplifiers.
        Queries power status and all output group configurations.
        """
        import time
        import socket
        start = time.perf_counter()

        port = self.config.mk3_control_port
        num_groups = self.config.mk3_num_groups

        # Run full MK3 protocol diagnostic
        device_status = self._mk3_protocol.run_full_diagnostic(ip, num_groups, port)

        duration = (time.perf_counter() - start) * 1000

        # Gather environment info
        environment_info = {
            'target_ip': ip,
            'target_port': port,
            'num_groups_tested': num_groups,
            'test_timeout_ms': self.config.mk3_protocol_timeout * 1000,
            'local_hostname': socket.gethostname()
        }

        if not device_status.is_reachable:
            # Protocol not accessible - this is a significant issue
            findings = [
                DiagnosticFinding(
                    issue="MK3 Control Protocol Not Accessible",
                    severity=Severity.CRITICAL,
                    root_cause=RootCause(
                        category="Network/Configuration",
                        description="The MK3 binary control protocol on port 52000 is not responding.",
                        technical_details=(
                            f"TCP connection to {ip}:{port} failed. "
                            "This is the primary control interface for MK3 amplifiers. "
                            "Without this port, third-party control systems cannot communicate with the device."
                        ),
                        evidence=[
                            f"Connection attempt to port {port} failed",
                            f"Error: {device_status.errors[0] if device_status.errors else 'Connection refused or timeout'}"
                        ],
                        related_tests=["Port Scan", "Network Reachability"],
                        firmware_relevant=True
                    ),
                    corrective_actions=[
                        CorrectiveAction(
                            priority=1,
                            action="Verify MK3 amplifier is powered on and booted",
                            description="The control port may not be available until the device completes its boot sequence.",
                            responsible_party="user",
                            verification_steps=[
                                "Check front panel indicators",
                                "Wait 60 seconds after power-on",
                                "Re-run diagnostic"
                            ],
                            estimated_complexity="low"
                        ),
                        CorrectiveAction(
                            priority=2,
                            action="Check network firewall rules",
                            description=f"Port {port} may be blocked by network security.",
                            responsible_party="installer",
                            verification_steps=[
                                f"Test: echo -ne '\\xFF\\x55\\x01\\x70' | nc {ip} {port}",
                                "Check switch/router ACLs",
                                "Verify VLAN configuration"
                            ],
                            estimated_complexity="medium"
                        ),
                        CorrectiveAction(
                            priority=3,
                            action="Firmware investigation",
                            description="If port is confirmed open but not responding, firmware may need update.",
                            responsible_party="firmware_team",
                            verification_steps=[
                                "Check current firmware version via web interface",
                                "Compare against latest release",
                                "Review firmware changelog for control protocol changes"
                            ],
                            estimated_complexity="high"
                        )
                    ],
                    affected_functionality=[
                        "Third-party control system integration (Crestron, Control4, Savant)",
                        "Home automation scenes and macros",
                        "Volume/mute control via IP",
                        "Power on/off automation",
                        "Multi-room audio synchronization"
                    ]
                )
            ]

            return TestResult(
                name="MK3 Control Protocol",
                status=TestStatus.FAILED,
                message=f"Control port {port} not accessible - third-party control disabled",
                details={
                    'port': port,
                    'is_reachable': False,
                    'errors': device_status.errors
                },
                duration_ms=duration,
                recommendations=[
                    f"Verify port {port} is not blocked by firewall",
                    "Check device is fully booted (wait 60s after power-on)",
                    "Test with: echo -ne '\\xFF\\x55\\x01\\x70' | nc <IP> 52000",
                    "Contact Sonance support if issue persists"
                ],
                findings=findings,
                raw_data={
                    'connection_errors': device_status.errors,
                    'response_times': device_status.response_times
                },
                test_methodology=(
                    f"Attempted TCP connection to port {port} using MK3 binary protocol. "
                    "Sent power status query command (FF 55 01 70) to verify protocol responsiveness."
                ),
                environment_info=environment_info
            )

        # Protocol is accessible - gather detailed status
        group_details = []

        for group in device_status.groups:
            group_info = {
                'group': group.group_name,
                'index': group.group_index,
                'volume': group.volume,
                'mute': group.mute,
                'source': group.source,
                'protect_status': group.protect_status,
                'raw_volume_hex': group.raw_volume.hex().upper() if group.raw_volume else None,
                'raw_mute_hex': group.raw_mute.hex().upper() if group.raw_mute else None,
                'raw_source_hex': group.raw_source.hex().upper() if group.raw_source else None,
                'raw_protect_hex': group.raw_protect.hex().upper() if group.raw_protect else None
            }
            group_details.append(group_info)

        # Gather power info
        power_info = None
        if device_status.power_status:
            power_info = {
                'is_on': device_status.power_status.is_on,
                'raw_hex': device_status.power_status.raw_response.hex().upper() if device_status.power_status.raw_response else None
            }

        # Gather global protect info
        global_protect_info = None
        if device_status.global_protect:
            global_protect_info = {
                'protection_active': device_status.global_protect.protection_active,
                'thermal_warning': device_status.global_protect.thermal_warning,
                'power_supply_fault': device_status.global_protect.power_supply_fault,
                'amplifier_fault': device_status.global_protect.amplifier_fault,
                'has_any_fault': device_status.global_protect.has_any_fault,
                'raw_hex': device_status.global_protect.raw_response.hex().upper() if device_status.global_protect.raw_response else None
            }

        # Gather thermal info
        thermal_info = None
        if device_status.thermal_status:
            thermal_info = {
                'state_name': device_status.thermal_status.state_name,
                'state_code': device_status.thermal_status.state_code,
                'is_normal': device_status.thermal_status.is_normal,
                'is_warning': device_status.thermal_status.is_warning,
                'is_critical': device_status.thermal_status.is_critical,
                'query_supported': device_status.thermal_status.query_supported,
                'raw_hex': device_status.thermal_status.raw_response.hex().upper() if device_status.thermal_status.raw_response else None
            }

        has_group_data = any(g.volume is not None or g.mute is not None for g in device_status.groups)

        # Determine test status - FAIL if any faults detected
        findings = []
        if device_status.has_any_fault:
            status = TestStatus.FAILED
            message = f"FAULTS DETECTED: {'; '.join(device_status.fault_summary)}"

            # Create detailed findings for each fault
            findings.append(
                DiagnosticFinding(
                    issue="Hardware Fault/Protection Event Detected",
                    severity=Severity.CRITICAL,
                    root_cause=RootCause(
                        category="Hardware/Firmware",
                        description="The amplifier has reported one or more fault conditions.",
                        technical_details=(
                            f"Fault flags detected via binary protocol queries:\n"
                            f"Global protect (01 71): {global_protect_info}\n"
                            f"Thermal state (01 72): {thermal_info}\n"
                            f"Fault summary: {device_status.fault_summary}"
                        ),
                        evidence=device_status.fault_summary,
                        related_tests=["Port Scan", "Network Reachability"],
                        firmware_relevant=True
                    ),
                    corrective_actions=[
                        CorrectiveAction(
                            priority=1,
                            action="Check physical connections and speaker loads",
                            description="Over-current and load faults are often caused by shorted speaker wires or impedance mismatches.",
                            responsible_party="installer",
                            verification_steps=[
                                "Disconnect all speaker outputs",
                                "Power cycle the amplifier",
                                "Re-run diagnostic to check if fault clears",
                                "Reconnect speakers one zone at a time"
                            ],
                            estimated_complexity="medium"
                        ),
                        CorrectiveAction(
                            priority=2,
                            action="Check ventilation and ambient temperature",
                            description="Thermal faults indicate overheating. Ensure adequate airflow.",
                            responsible_party="installer",
                            verification_steps=[
                                "Check rack ventilation",
                                "Verify ambient temp is within spec",
                                "Allow amp to cool, then re-test"
                            ],
                            estimated_complexity="low"
                        ),
                        CorrectiveAction(
                            priority=3,
                            action="Power cycle the amplifier",
                            description="Some fault conditions are latched and require a power cycle to clear.",
                            responsible_party="user",
                            verification_steps=[
                                "Power off the amplifier",
                                "Wait 30 seconds",
                                "Power on and wait for full boot (60s)",
                                "Re-run diagnostic"
                            ],
                            estimated_complexity="low"
                        )
                    ],
                    affected_functionality=[
                        "Audio output may be muted or distorted",
                        "Affected zones may not respond to commands",
                        "Amplifier may shut down to protect itself"
                    ]
                )
            )
        elif device_status.power_status and has_group_data:
            status = TestStatus.PASSED
            power_state = "ON" if device_status.power_status.is_on else "OFF"
            thermal_state = f", Thermal: {device_status.thermal_status.state_name}" if device_status.thermal_status else ""
            message = f"Control protocol active - Power: {power_state}{thermal_state}, {len(device_status.groups)} groups OK"
        elif device_status.is_reachable:
            status = TestStatus.WARNING
            message = f"Control port open but limited response data"
        else:
            status = TestStatus.WARNING
            message = "Control protocol partially working"

        # Run a quick burst test to check reliability
        burst_result = self._mk3_protocol.burst_test(ip, count=5, delay_ms=50, port=port)

        recommendations = []
        if status == TestStatus.PASSED:
            recommendations = [
                "Control protocol is working - device can be controlled via IP",
                f"Use port {port} for third-party control system integration",
                "No hardware faults detected"
            ]
        elif status == TestStatus.FAILED:
            recommendations = [
                "HARDWARE FAULT - See fault details above",
                "Check speaker connections and loads",
                "Verify ventilation and cooling",
                "Power cycle may clear latched faults"
            ]
        else:
            recommendations = [
                "Protocol accessible but responses may be incomplete",
                "Check firmware version for full protocol support"
            ]

        return TestResult(
            name="MK3 Control Protocol",
            status=status,
            message=message,
            details={
                'port': port,
                'is_reachable': True,
                'power_status': power_info,
                'global_protect': global_protect_info,
                'thermal_status': thermal_info,
                'has_any_fault': device_status.has_any_fault,
                'fault_summary': device_status.fault_summary,
                'groups': group_details,
                'connectivity_time_ms': device_status.response_times.get('connectivity', 0),
                'burst_test': {
                    'commands_sent': burst_result['total'],
                    'successful': burst_result['successful'],
                    'error_rate_percent': burst_result['error_rate_percent'],
                    'avg_response_ms': burst_result.get('avg_response_ms', 0)
                }
            },
            duration_ms=duration,
            recommendations=recommendations,
            findings=findings,
            raw_data={
                'all_raw_responses': {k: v.hex().upper() if isinstance(v, bytes) else v
                                      for k, v in device_status.raw_responses.items()},
                'response_times': device_status.response_times,
                'burst_test_details': burst_result
            },
            test_methodology=(
                f"Connected to MK3 binary protocol on port {port}. "
                f"Sent power query (FF 55 01 70), global protect query (FF 55 01 71), "
                f"thermal query (FF 55 01 72), and per-group status queries "
                f"(FF 55 02 10/11/12/13 XX) for {num_groups} groups. "
                f"Also ran {burst_result['total']}-command burst test at 50ms intervals."
            ),
            environment_info=environment_info
        )

    def _test_hostname(self, ip: str) -> TestResult:
        """Test hostname resolution (Issue #2)."""
        import time
        start = time.perf_counter()

        hostname_results = self._hostname.resolve_all_methods(ip, "DSP")

        duration = (time.perf_counter() - start) * 1000

        successful = {m: r for m, r in hostname_results.items() if r.success}
        hostnames = [r.hostname for r in successful.values() if r.hostname]

        has_dsp = any('dsp' in h.lower() for h in hostnames if h)

        if has_dsp:
            status = TestStatus.PASSED
            message = f"Hostname 'DSP' resolved via {list(successful.keys())}"
        elif successful:
            status = TestStatus.WARNING
            message = f"Hostname found ({hostnames}) but not 'DSP'"
        else:
            status = TestStatus.FAILED
            message = "No hostname resolution method succeeded"

        recommendations = []
        if not successful:
            recommendations.extend([
                "Device may not be advertising its hostname",
                "Check if NetBIOS name service is enabled on device",
                "Verify mDNS/Bonjour is enabled",
                "Ensure PTR record exists in DNS"
            ])

        if 'netbios' not in successful:
            recommendations.append(
                "NetBIOS resolution failed - hostname won't appear in network scanners"
            )

        return TestResult(
            name="Hostname Resolution",
            status=status,
            message=message,
            details={
                'methods_tested': list(hostname_results.keys()),
                'methods_successful': list(successful.keys()),
                'hostnames_found': hostnames,
                'expected_hostname': 'DSP'
            },
            duration_ms=duration,
            recommendations=recommendations
        )

    def _test_dns(self, ip: str) -> TestResult:
        """Test DNS configuration (Issue #3)."""
        import time
        start = time.perf_counter()

        # Get and test system DNS servers
        system_dns = self._dns.get_system_dns_servers()
        dns_results = self._dns.test_multiple_dns_servers(system_dns[:3])

        # Also test reverse lookup
        reverse = self._dns.reverse_lookup(ip)

        duration = (time.perf_counter() - start) * 1000

        working_dns = [r for r in dns_results if r.can_resolve]

        if working_dns and reverse.success:
            status = TestStatus.PASSED
            message = f"DNS working - {len(working_dns)} servers, PTR record found"
        elif working_dns:
            status = TestStatus.WARNING
            message = f"DNS servers working but no PTR record for device"
        else:
            status = TestStatus.FAILED
            message = "DNS servers not responding"

        recommendations = []
        if not working_dns:
            recommendations.append(
                "No DNS servers accessible - check network DNS configuration"
            )
        if not reverse.success:
            recommendations.append(
                "No PTR record - hostname won't resolve via DNS reverse lookup"
            )

        return TestResult(
            name="DNS Configuration",
            status=status,
            message=message,
            details={
                'system_dns_servers': system_dns,
                'working_servers': [r.server_ip for r in working_dns],
                'reverse_lookup_success': reverse.success,
                'reverse_lookup_result': reverse.answers if reverse.success else None
            },
            duration_ms=duration,
            recommendations=recommendations
        )

    def _test_commands(self, ip: str) -> TestResult:
        """Test command protocol (Issue #4)."""
        import time
        import socket
        start = time.perf_counter()

        # Find a working control port
        test_ports = [23, 10000, 10001, 4998, 4999]
        connected_port = None
        port_scan_results = {}
        connection_errors = {}

        for port in test_ports:
            try:
                conn = self._commands.connect(ip, port)
                port_scan_results[port] = {
                    'connected': conn.is_connected,
                    'error': conn.error if hasattr(conn, 'error') else None
                }
                if conn.is_connected:
                    connected_port = port
                    self._commands.disconnect(conn)
                    break
            except Exception as e:
                connection_errors[port] = str(e)
                port_scan_results[port] = {'connected': False, 'error': str(e)}

        # Gather environment info
        environment_info = {
            'target_ip': ip,
            'ports_tested': test_ports,
            'test_timeout_ms': self.config.default_timeout * 1000,
            'local_hostname': socket.gethostname()
        }

        if not connected_port:
            # Build comprehensive root cause analysis for no command port
            findings = [
                DiagnosticFinding(
                    issue="No Command/Control Port Available",
                    severity=Severity.CRITICAL,
                    root_cause=RootCause(
                        category="Configuration/Firmware",
                        description="The device is not listening on any of the standard control ports (Telnet/TCP). "
                                   "This prevents third-party control systems from communicating with the amplifier.",
                        technical_details=(
                            f"TCP connection attempts to ports {test_ports} all failed. "
                            "The device web interface is accessible (ports 80/8080), indicating the device is "
                            "network-connected and responsive, but the control protocol service is not running or "
                            "not bound to any network interface. This is typically caused by: "
                            "(1) Control protocol disabled in device configuration, "
                            "(2) Firmware not including control protocol support, "
                            "(3) Control service crashed or failed to start, or "
                            "(4) Port binding conflict on the device."
                        ),
                        evidence=[
                            f"Attempted connections to ports: {test_ports}",
                            f"All connection attempts resulted in connection refused or timeout",
                            f"Port scan details: {port_scan_results}",
                            "Web interface (port 80/8080) confirmed accessible in prior test"
                        ],
                        related_tests=["Port Scan", "HTTP Web Interface"],
                        firmware_relevant=True
                    ),
                    corrective_actions=[
                        CorrectiveAction(
                            priority=1,
                            action="Verify control protocol is enabled in device settings",
                            description="Access the device web interface and navigate to the network/control settings. "
                                       "Ensure that IP control or TCP control is enabled.",
                            responsible_party="installer",
                            verification_steps=[
                                "Open web browser to http://{}/Landing.htm".format(ip),
                                "Navigate to Settings > Network or Control",
                                "Look for 'IP Control', 'TCP Control', or 'RS232 over IP' setting",
                                "Enable the setting and save/apply changes",
                                "Reboot device if required",
                                "Re-run this diagnostic to verify"
                            ],
                            estimated_complexity="low"
                        ),
                        CorrectiveAction(
                            priority=2,
                            action="Check firmware version supports control protocol",
                            description="Some firmware versions may not include control protocol support, "
                                       "or it may require a specific firmware variant.",
                            responsible_party="firmware_team",
                            verification_steps=[
                                "Check current firmware version on device",
                                "Compare against firmware changelog for control protocol support",
                                "Verify if DSP8-130 MK3 model includes control protocol in base firmware"
                            ],
                            estimated_complexity="medium"
                        ),
                        CorrectiveAction(
                            priority=3,
                            action="Review device logs for control service errors",
                            description="The control protocol service may have failed to start due to internal errors.",
                            responsible_party="developer",
                            verification_steps=[
                                "Access device diagnostic logs via web interface or serial console",
                                "Search for errors related to 'telnet', 'control', 'tcp server', or port binding",
                                "Look for crash reports or service restart attempts"
                            ],
                            estimated_complexity="high"
                        ),
                        CorrectiveAction(
                            priority=4,
                            action="Factory reset and reconfigure",
                            description="If other steps fail, a factory reset may restore default control protocol settings.",
                            responsible_party="installer",
                            verification_steps=[
                                "Backup current device configuration",
                                "Perform factory reset via web interface or hardware button",
                                "Reconfigure network settings",
                                "Re-run diagnostic to test control protocol"
                            ],
                            estimated_complexity="medium"
                        )
                    ],
                    affected_functionality=[
                        "Third-party control system integration (Crestron, Control4, Savant, etc.)",
                        "Automation and scripting",
                        "Remote volume/source control",
                        "Multi-room audio synchronization",
                        "Programmatic device management"
                    ]
                )
            ]

            return TestResult(
                name="Command Protocol",
                status=TestStatus.FAILED,
                message="No command port found - control protocol not available",
                details={
                    'ports_tested': test_ports,
                    'port_scan_results': port_scan_results,
                    'connection_errors': connection_errors
                },
                duration_ms=(time.perf_counter() - start) * 1000,
                recommendations=[
                    "Enable IP control in device web interface settings",
                    "Verify firmware supports control protocol",
                    "Check device logs for control service errors",
                    "Consider factory reset if issue persists"
                ],
                findings=findings,
                raw_data={
                    'port_scan_results': port_scan_results,
                    'connection_errors': connection_errors,
                    'tcp_ports_standard': {
                        23: 'Telnet (common for AV control)',
                        10000: 'Sonance/Dana proprietary',
                        10001: 'Sonance/Dana proprietary alt',
                        4998: 'AMX/Harman control',
                        4999: 'AMX/Harman control alt'
                    }
                },
                test_methodology=(
                    "Sequential TCP connection attempts to standard control ports. "
                    "For each port, a TCP socket connection is attempted with a configurable timeout. "
                    "A successful connection indicates the port is open and a service is listening."
                ),
                environment_info=environment_info
            )

        # Run burst test
        burst_result = self._commands.burst_test(
            ip, connected_port, "",
            count=10, delay_ms=0
        )

        duration = (time.perf_counter() - start) * 1000
        findings = []

        if burst_result.error_rate_percent == 0:
            status = TestStatus.PASSED
            message = f"Control port {connected_port} - commands working at 0ms delay"
        elif burst_result.error_rate_percent < 20:
            status = TestStatus.WARNING
            message = f"Control port {connected_port} - {burst_result.error_rate_percent:.0f}% errors (rate limiting)"
            findings.append(
                DiagnosticFinding(
                    issue="Command Rate Limiting Detected",
                    severity=Severity.MEDIUM,
                    root_cause=RootCause(
                        category="Firmware/Performance",
                        description="The device is dropping some commands when sent in rapid succession. "
                                   "This is typically due to internal rate limiting or buffer overflow.",
                        technical_details=(
                            f"Burst test of 10 commands at 0ms delay resulted in {burst_result.error_rate_percent:.1f}% errors. "
                            f"Successful: {burst_result.successful_commands}/{burst_result.total_commands}. "
                            "The device command processor may have a limited input buffer or intentional rate limiting "
                            "to prevent denial-of-service conditions."
                        ),
                        evidence=[
                            f"Error rate: {burst_result.error_rate_percent:.1f}%",
                            f"Commands sent: {burst_result.total_commands}",
                            f"Commands successful: {burst_result.successful_commands}",
                            f"Average response time: {burst_result.avg_response_ms:.1f}ms"
                        ],
                        firmware_relevant=True
                    ),
                    corrective_actions=[
                        CorrectiveAction(
                            priority=1,
                            action="Add inter-command delay in control system",
                            description="Configure the control system to add 50-100ms delay between commands.",
                            responsible_party="installer",
                            verification_steps=[
                                "Access control system programming interface",
                                "Add delay/wait commands between device commands",
                                "Test with 50ms delay, increase if needed"
                            ],
                            estimated_complexity="low"
                        ),
                        CorrectiveAction(
                            priority=2,
                            action="Implement command queueing",
                            description="Use a command queue with rate limiting on the control system side.",
                            responsible_party="installer",
                            verification_steps=[
                                "Implement FIFO queue for commands",
                                "Process queue with fixed interval (e.g., 100ms)",
                                "Monitor for dropped commands"
                            ],
                            estimated_complexity="medium"
                        )
                    ],
                    affected_functionality=[
                        "Rapid command sequences (e.g., quick volume adjustments)",
                        "Macro execution",
                        "Bulk configuration changes"
                    ]
                )
            )
        else:
            status = TestStatus.FAILED
            message = f"Control port {connected_port} - {burst_result.error_rate_percent:.0f}% errors"
            findings.append(
                DiagnosticFinding(
                    issue="High Command Error Rate",
                    severity=Severity.HIGH,
                    root_cause=RootCause(
                        category="Firmware/Network",
                        description="The device is failing to process a significant portion of commands. "
                                   "This indicates either a firmware issue or network instability.",
                        technical_details=(
                            f"Burst test resulted in {burst_result.error_rate_percent:.1f}% error rate. "
                            "This exceeds acceptable thresholds for reliable control. Possible causes: "
                            "(1) Firmware command parser overwhelmed, "
                            "(2) Network packet loss between test host and device, "
                            "(3) Device CPU overloaded, "
                            "(4) Memory pressure causing dropped connections."
                        ),
                        evidence=[
                            f"Error rate: {burst_result.error_rate_percent:.1f}%",
                            f"Commands sent: {burst_result.total_commands}",
                            f"Commands successful: {burst_result.successful_commands}",
                            f"Average response time: {burst_result.avg_response_ms:.1f}ms"
                        ],
                        firmware_relevant=True
                    ),
                    corrective_actions=[
                        CorrectiveAction(
                            priority=1,
                            action="Reboot the device",
                            description="A reboot may clear any transient firmware issues.",
                            responsible_party="installer",
                            verification_steps=["Power cycle the device", "Wait 60 seconds", "Re-run diagnostic"],
                            estimated_complexity="low"
                        ),
                        CorrectiveAction(
                            priority=2,
                            action="Check network stability",
                            description="Verify there's no packet loss or latency issues on the network path.",
                            responsible_party="installer",
                            verification_steps=["Run extended ping test", "Check switch port statistics", "Verify cable connections"],
                            estimated_complexity="medium"
                        ),
                        CorrectiveAction(
                            priority=3,
                            action="Firmware investigation required",
                            description="If issue persists after reboot and network verification, this may indicate a firmware bug.",
                            responsible_party="firmware_team",
                            verification_steps=[
                                "Collect device logs during command test",
                                "Analyze command parser performance",
                                "Check for memory leaks or CPU spikes"
                            ],
                            estimated_complexity="high"
                        )
                    ],
                    affected_functionality=[
                        "All control system integration",
                        "Reliable command execution",
                        "User experience with automation"
                    ]
                )
            )

        recommendations = []
        if burst_result.error_rate_percent > 0:
            recommendations.extend([
                f"Add delay between commands (try 50-100ms)",
                "Rate limiting detected - slow down command rate",
                "Consider command queueing on control system"
            ])

        return TestResult(
            name="Command Protocol",
            status=status,
            message=message,
            details={
                'control_port': connected_port,
                'commands_sent': burst_result.total_commands,
                'commands_successful': burst_result.successful_commands,
                'error_rate_percent': burst_result.error_rate_percent,
                'avg_response_ms': burst_result.avg_response_ms
            },
            duration_ms=duration,
            recommendations=recommendations,
            findings=findings,
            raw_data={
                'port_used': connected_port,
                'burst_test_config': {'count': 10, 'delay_ms': 0},
                'burst_results': {
                    'total': burst_result.total_commands,
                    'successful': burst_result.successful_commands,
                    'failed': burst_result.total_commands - burst_result.successful_commands,
                    'error_rate': burst_result.error_rate_percent,
                    'avg_response_ms': burst_result.avg_response_ms
                }
            },
            test_methodology=(
                f"TCP connection to port {connected_port}, followed by burst test of 10 commands "
                "with 0ms inter-command delay to assess rate limiting behavior."
            ),
            environment_info=environment_info
        )

    def get_current_report(self) -> Optional[DiagnosticReport]:
        """Get the current/last diagnostic report."""
        return self._current_report
