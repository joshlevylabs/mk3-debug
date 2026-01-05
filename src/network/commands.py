"""TCP command testing module for MK3 amplifiers."""

import socket
import time
import threading
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import statistics

from ..utils import get_logger

logger = get_logger(__name__)


@dataclass
class CommandResult:
    """Result of a single command execution."""
    command: str
    success: bool
    response: Optional[str] = None
    error: Optional[str] = None
    send_time_ms: Optional[float] = None
    response_time_ms: Optional[float] = None
    total_time_ms: Optional[float] = None


@dataclass
class BurstTestResult:
    """Result of a burst command test."""
    total_commands: int
    successful_commands: int
    failed_commands: int
    delay_between_ms: float
    min_response_ms: Optional[float] = None
    avg_response_ms: Optional[float] = None
    max_response_ms: Optional[float] = None
    stddev_response_ms: Optional[float] = None
    error_rate_percent: float = 0.0
    errors: List[str] = field(default_factory=list)
    individual_results: List[CommandResult] = field(default_factory=list)


import socket as socket_module


@dataclass
class CommandConnection:
    """Represents a command connection to an MK3 amplifier."""
    ip_address: str
    port: int
    sock: Optional[socket_module.socket] = None
    is_connected: bool = False
    last_error: Optional[str] = None


class CommandTester:
    """
    Tests TCP command protocol for MK3 amplifiers.

    This class helps diagnose issues with command errors when
    multiple commands are sent rapidly.
    """

    # Common line terminators
    TERMINATORS = {
        'cr': b'\r',
        'lf': b'\n',
        'crlf': b'\r\n',
        'none': b''
    }

    def __init__(
        self,
        timeout: float = 5.0,
        recv_timeout: float = 2.0,
        terminator: str = 'crlf'
    ):
        self.timeout = timeout
        self.recv_timeout = recv_timeout
        self.terminator = self.TERMINATORS.get(terminator, b'\r\n')
        self._cancel_flag = threading.Event()

    def cancel(self) -> None:
        """Cancel ongoing operations."""
        self._cancel_flag.set()

    def reset_cancel(self) -> None:
        """Reset cancel flag."""
        self._cancel_flag.clear()

    def connect(
        self,
        ip_address: str,
        port: int
    ) -> CommandConnection:
        """
        Establish a TCP connection to the amplifier.

        Args:
            ip_address: Device IP address
            port: TCP port number

        Returns:
            CommandConnection object
        """
        logger.info(f"Connecting to {ip_address}:{port}")

        conn = CommandConnection(ip_address=ip_address, port=port)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((ip_address, port))

            conn.sock = sock
            conn.is_connected = True
            logger.info(f"Connected to {ip_address}:{port}")

        except socket.timeout:
            conn.last_error = "Connection timeout"
            logger.error(f"Connection timeout: {ip_address}:{port}")
        except ConnectionRefusedError:
            conn.last_error = "Connection refused"
            logger.error(f"Connection refused: {ip_address}:{port}")
        except Exception as e:
            conn.last_error = str(e)
            logger.error(f"Connection error: {ip_address}:{port} - {e}")

        return conn

    def disconnect(self, conn: CommandConnection) -> None:
        """Close a connection."""
        if conn.sock:
            try:
                conn.sock.close()
            except Exception:
                pass
            conn.sock = None
            conn.is_connected = False
            logger.debug(f"Disconnected from {conn.ip_address}:{conn.port}")

    def send_command(
        self,
        conn: CommandConnection,
        command: str,
        wait_for_response: bool = True,
        response_terminator: Optional[bytes] = None
    ) -> CommandResult:
        """
        Send a command and optionally wait for response.

        Args:
            conn: CommandConnection object
            command: Command string to send
            wait_for_response: Whether to wait for a response
            response_terminator: Expected response terminator

        Returns:
            CommandResult
        """
        result = CommandResult(command=command, success=False)

        if not conn.is_connected or not conn.sock:
            result.error = "Not connected"
            return result

        try:
            # Prepare command with terminator
            cmd_bytes = command.encode('utf-8') + self.terminator

            # Send command
            start_send = time.perf_counter()
            conn.sock.sendall(cmd_bytes)
            result.send_time_ms = (time.perf_counter() - start_send) * 1000

            logger.debug(f"Sent: {repr(command)}")

            if wait_for_response:
                # Wait for response
                conn.sock.settimeout(self.recv_timeout)
                start_recv = time.perf_counter()

                response_data = b''
                try:
                    while True:
                        chunk = conn.sock.recv(1024)
                        if not chunk:
                            break
                        response_data += chunk

                        # Check for terminator
                        term = response_terminator or self.terminator
                        if term and response_data.endswith(term):
                            break

                        # Also check if we've been waiting too long
                        if time.perf_counter() - start_recv > self.recv_timeout:
                            break

                except socket.timeout:
                    pass

                result.response_time_ms = (time.perf_counter() - start_recv) * 1000
                result.total_time_ms = result.send_time_ms + result.response_time_ms

                if response_data:
                    result.response = response_data.decode('utf-8', errors='ignore').strip()
                    result.success = True
                    logger.debug(f"Received: {repr(result.response)}")

                    # Check for error responses
                    if 'error' in result.response.lower():
                        result.error = f"Command error: {result.response}"
                        result.success = False
                else:
                    result.error = "No response received"

            else:
                result.success = True
                result.total_time_ms = result.send_time_ms

            # Reset socket timeout
            conn.sock.settimeout(self.timeout)

        except socket.timeout:
            result.error = "Timeout waiting for response"
            logger.warning(f"Command timeout: {command}")
        except Exception as e:
            result.error = str(e)
            logger.error(f"Command error: {command} - {e}")
            conn.is_connected = False

        return result

    def send_command_simple(
        self,
        ip_address: str,
        port: int,
        command: str
    ) -> CommandResult:
        """
        Send a single command (connects, sends, disconnects).

        Args:
            ip_address: Device IP
            port: TCP port
            command: Command to send

        Returns:
            CommandResult
        """
        conn = self.connect(ip_address, port)
        if not conn.is_connected:
            return CommandResult(
                command=command,
                success=False,
                error=conn.last_error
            )

        result = self.send_command(conn, command)
        self.disconnect(conn)
        return result

    def burst_test(
        self,
        ip_address: str,
        port: int,
        command: str,
        count: int = 10,
        delay_ms: float = 0,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> BurstTestResult:
        """
        Send multiple commands rapidly to test rate limiting/queueing.

        Args:
            ip_address: Device IP
            port: TCP port
            command: Command to send repeatedly
            count: Number of commands to send
            delay_ms: Delay between commands in milliseconds
            progress_callback: Callback(current, total) for progress

        Returns:
            BurstTestResult with statistics
        """
        self.reset_cancel()

        logger.info(f"Burst test: {count} commands, {delay_ms}ms delay")

        result = BurstTestResult(
            total_commands=count,
            successful_commands=0,
            failed_commands=0,
            delay_between_ms=delay_ms
        )

        # Connect once for all commands
        conn = self.connect(ip_address, port)
        if not conn.is_connected:
            result.failed_commands = count
            result.error_rate_percent = 100.0
            result.errors.append(f"Failed to connect: {conn.last_error}")
            return result

        response_times = []

        for i in range(count):
            if self._cancel_flag.is_set():
                break

            cmd_result = self.send_command(conn, command)
            result.individual_results.append(cmd_result)

            if cmd_result.success:
                result.successful_commands += 1
                if cmd_result.total_time_ms:
                    response_times.append(cmd_result.total_time_ms)
            else:
                result.failed_commands += 1
                if cmd_result.error:
                    result.errors.append(f"Command {i+1}: {cmd_result.error}")

            if progress_callback:
                progress_callback(i + 1, count)

            # Delay between commands
            if delay_ms > 0 and i < count - 1:
                time.sleep(delay_ms / 1000.0)

            # Reconnect if connection was lost
            if not conn.is_connected:
                logger.warning("Connection lost, reconnecting...")
                self.disconnect(conn)
                conn = self.connect(ip_address, port)
                if not conn.is_connected:
                    result.errors.append("Reconnection failed")
                    break

        self.disconnect(conn)

        # Calculate statistics
        if response_times:
            result.min_response_ms = min(response_times)
            result.avg_response_ms = statistics.mean(response_times)
            result.max_response_ms = max(response_times)
            if len(response_times) > 1:
                result.stddev_response_ms = statistics.stdev(response_times)

        result.error_rate_percent = (result.failed_commands / count) * 100

        logger.info(
            f"Burst test complete: {result.successful_commands}/{count} successful, "
            f"{result.error_rate_percent:.1f}% error rate"
        )

        return result

    def find_optimal_delay(
        self,
        ip_address: str,
        port: int,
        command: str,
        delays_to_test: List[float] = None,
        commands_per_test: int = 10,
        max_acceptable_error_rate: float = 5.0,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> Dict:
        """
        Find the minimum delay needed for reliable command execution.

        Args:
            ip_address: Device IP
            port: TCP port
            command: Command to test with
            delays_to_test: List of delays (ms) to test
            commands_per_test: Commands to send per delay test
            max_acceptable_error_rate: Maximum acceptable error rate %
            progress_callback: Callback(phase, current, total)

        Returns:
            Dict with test results and recommendation
        """
        if delays_to_test is None:
            delays_to_test = [0, 10, 25, 50, 100, 250, 500]

        logger.info(f"Finding optimal delay: testing {delays_to_test}")

        results = {
            'tests': [],
            'recommended_delay_ms': None,
            'all_passed': False
        }

        for i, delay in enumerate(delays_to_test):
            if self._cancel_flag.is_set():
                break

            if progress_callback:
                progress_callback(f"Testing {delay}ms delay", i + 1, len(delays_to_test))

            test_result = self.burst_test(
                ip_address, port, command,
                count=commands_per_test,
                delay_ms=delay
            )

            results['tests'].append({
                'delay_ms': delay,
                'error_rate_percent': test_result.error_rate_percent,
                'avg_response_ms': test_result.avg_response_ms,
                'successful': test_result.successful_commands,
                'failed': test_result.failed_commands
            })

            # Check if this delay is acceptable
            if test_result.error_rate_percent <= max_acceptable_error_rate:
                if results['recommended_delay_ms'] is None:
                    results['recommended_delay_ms'] = delay

        # Check if all tests passed at zero delay
        if results['tests'] and results['tests'][0]['error_rate_percent'] <= max_acceptable_error_rate:
            results['all_passed'] = True
            results['recommended_delay_ms'] = 0

        logger.info(f"Optimal delay analysis complete. Recommended: {results['recommended_delay_ms']}ms")
        return results

    def concurrent_connection_test(
        self,
        ip_address: str,
        port: int,
        num_connections: int = 5,
        command: str = ""
    ) -> Dict:
        """
        Test multiple simultaneous connections.

        Args:
            ip_address: Device IP
            port: TCP port
            num_connections: Number of concurrent connections to test
            command: Optional command to send on each connection

        Returns:
            Dict with test results
        """
        logger.info(f"Testing {num_connections} concurrent connections")

        results = {
            'requested_connections': num_connections,
            'successful_connections': 0,
            'failed_connections': 0,
            'errors': []
        }

        connections = []

        # Try to establish all connections
        for i in range(num_connections):
            conn = self.connect(ip_address, port)
            if conn.is_connected:
                connections.append(conn)
                results['successful_connections'] += 1
            else:
                results['failed_connections'] += 1
                results['errors'].append(f"Connection {i+1}: {conn.last_error}")

        # If command provided, send on all connections
        if command and connections:
            for i, conn in enumerate(connections):
                cmd_result = self.send_command(conn, command)
                if not cmd_result.success:
                    results['errors'].append(
                        f"Command on connection {i+1}: {cmd_result.error}"
                    )

        # Close all connections
        for conn in connections:
            self.disconnect(conn)

        logger.info(
            f"Concurrent test: {results['successful_connections']}/{num_connections} connections"
        )
        return results

    def discover_protocol(
        self,
        ip_address: str,
        port: int,
        test_commands: Optional[List[str]] = None
    ) -> Dict:
        """
        Attempt to discover the command protocol.

        Args:
            ip_address: Device IP
            port: TCP port
            test_commands: Optional list of commands to try

        Returns:
            Dict with discovery results
        """
        if test_commands is None:
            # Common control system commands to try
            test_commands = [
                "",            # Empty (might trigger help)
                "?",           # Help
                "help",        # Help
                "status",      # Status query
                "ver",         # Version
                "version",     # Version
                "*idn?",       # SCPI identification
                "identify",    # Identify
                "info",        # Info
                "get status",  # Get status
                "GET /",       # HTTP-ish
            ]

        logger.info(f"Discovering protocol on {ip_address}:{port}")

        results = {
            'responses': [],
            'likely_protocol': 'unknown',
            'suggested_commands': []
        }

        conn = self.connect(ip_address, port)
        if not conn.is_connected:
            results['error'] = conn.last_error
            return results

        for cmd in test_commands:
            if self._cancel_flag.is_set():
                break

            cmd_result = self.send_command(conn, cmd)
            if cmd_result.response:
                results['responses'].append({
                    'command': cmd,
                    'response': cmd_result.response
                })

            # Small delay between commands
            time.sleep(0.1)

        self.disconnect(conn)

        # Analyze responses to guess protocol
        if results['responses']:
            all_responses = ' '.join(r['response'] for r in results['responses']).lower()

            if 'http' in all_responses or '<html' in all_responses:
                results['likely_protocol'] = 'HTTP'
            elif 'error' in all_responses or 'ok' in all_responses:
                results['likely_protocol'] = 'Text-based command'
            elif any(c in all_responses for c in ['crestron', 'control4', 'amx']):
                results['likely_protocol'] = 'Control system'

        logger.info(f"Protocol discovery complete: {results['likely_protocol']}")
        return results
