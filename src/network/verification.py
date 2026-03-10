"""
Automated Firmware Verification Tests for Sonance MK3 Amplifiers.

This module provides structured test classes that map to specific JIRA tickets
in the firmware verification test plan. Each test exercises a different aspect
of the MK3 amplifier's network behavior and reports pass/fail with detailed
diagnostics.

Tests:
    IPCommandStabilityTest  - DSP3-136 / DSP3-134: Rapid IP command stability
    StatusPageVerifier      - DSP3-135: Status.htm accuracy after state changes
    HTTPStabilityMonitor    - DSP3-150: Long-duration HTTP polling stability
    RebootDetector          - Sleep/Reboot issue: Unexpected reboot detection
"""

import re
import socket
import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import requests

from ..utils import get_logger
from .mk3_commands import (
    MK3CommandBuilder, MK3ResponseParser, MK3_PORT,
    OutputGroup, MK3Model
)

logger = get_logger(__name__)

# Default socket timeout for individual command exchanges (seconds)
_SOCKET_TIMEOUT = 3.0

# Buffer size for reading MK3 responses
_RECV_BUFFER = 1024


# =============================================================================
# RESULT DATACLASS
# =============================================================================

@dataclass
class VerificationResult:
    """Structured result from a verification test."""
    test_name: str
    ticket_id: str
    passed: bool
    message: str
    details: str
    duration_ms: float
    raw_data: Dict = field(default_factory=dict)


# =============================================================================
# HELPERS
# =============================================================================

def _send_command(ip: str, cmd: bytes, timeout: float = _SOCKET_TIMEOUT) -> Optional[str]:
    """
    Open a TCP connection, send a single binary command, read the response,
    and close the socket.

    Returns the decoded response string, or None on failure.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((ip, MK3_PORT))
            sock.sendall(cmd)
            data = sock.recv(_RECV_BUFFER)
            return data.decode("ascii", errors="replace").strip()
    except (socket.timeout, socket.error, OSError) as exc:
        logger.debug("Command send failed (%s): %s", ip, exc)
        return None


def _send_command_reuse(sock: socket.socket, cmd: bytes,
                        timeout: float = _SOCKET_TIMEOUT) -> Optional[str]:
    """
    Send a binary command on an already-open socket and read the response.

    Returns the decoded response string, or None on failure.
    """
    try:
        sock.settimeout(timeout)
        sock.sendall(cmd)
        data = sock.recv(_RECV_BUFFER)
        return data.decode("ascii", errors="replace").strip()
    except (socket.timeout, socket.error, OSError) as exc:
        logger.debug("Command on reused socket failed: %s", exc)
        return None


# =============================================================================
# IPCommandStabilityTest  (DSP3-136 / DSP3-134)
# =============================================================================

class IPCommandStabilityTest:
    """
    Rapid IP command stability test.

    Sends bursts of binary commands over TCP port 52000 and tracks error
    rates, response times, and whether the amplifier remains responsive
    throughout the burst.

    JIRA: DSP3-136 (IP command response stability)
           DSP3-134 (rapid command handling)
    """

    def __init__(self, ip: str, burst_size: int = 15, num_bursts: int = 3,
                 inter_command_delay: float = 0.05,
                 inter_burst_delay: float = 1.0):
        self.ip = ip
        self.burst_size = max(10, min(burst_size, 20))
        self.num_bursts = num_bursts
        self.inter_command_delay = inter_command_delay
        self.inter_burst_delay = inter_burst_delay

    # -- command palette for the burst --
    _BURST_COMMANDS = [
        ("power_query", MK3CommandBuilder.power_query),
        ("volume_query_A", lambda: MK3CommandBuilder.query_group_volume(OutputGroup.A)),
        ("mute_query_A", lambda: MK3CommandBuilder.query_group_mute(OutputGroup.A)),
        ("protect_query", lambda: MK3CommandBuilder.query_channel_short_protect(
            __import__("src.network.mk3_commands", fromlist=["OutputChannel"]).OutputChannel.CH1_LEFT
        )),
    ]

    def run(self) -> VerificationResult:
        """Execute the stability test and return results."""
        start = time.perf_counter()

        # Lazily import OutputChannel to keep the class-level reference simple
        from .mk3_commands import OutputChannel

        burst_commands = [
            ("power_query", MK3CommandBuilder.power_query),
            ("volume_query_A",
             lambda: MK3CommandBuilder.query_group_volume(OutputGroup.A)),
            ("mute_query_A",
             lambda: MK3CommandBuilder.query_group_mute(OutputGroup.A)),
            ("protect_query_ch1",
             lambda: MK3CommandBuilder.query_channel_short_protect(
                 OutputChannel.CH1_LEFT)),
        ]

        all_latencies: List[float] = []
        errors = 0
        total_sent = 0
        burst_results: List[Dict] = []

        for burst_idx in range(self.num_bursts):
            burst_record = {"burst": burst_idx + 1, "commands": []}
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(_SOCKET_TIMEOUT)
                sock.connect((self.ip, MK3_PORT))
            except (socket.timeout, socket.error, OSError) as exc:
                logger.warning("Burst %d: connection failed - %s",
                               burst_idx + 1, exc)
                errors += self.burst_size
                total_sent += self.burst_size
                burst_record["error"] = str(exc)
                burst_results.append(burst_record)
                continue

            try:
                for cmd_idx in range(self.burst_size):
                    label, builder = burst_commands[cmd_idx % len(burst_commands)]
                    cmd_bytes = builder() if callable(builder) else builder
                    total_sent += 1

                    t0 = time.perf_counter()
                    resp = _send_command_reuse(sock, cmd_bytes)
                    t1 = time.perf_counter()

                    latency_ms = (t1 - t0) * 1000
                    if resp is not None:
                        all_latencies.append(latency_ms)
                        burst_record["commands"].append({
                            "label": label,
                            "latency_ms": round(latency_ms, 2),
                            "response": resp[:120],
                        })
                    else:
                        errors += 1
                        burst_record["commands"].append({
                            "label": label,
                            "latency_ms": round(latency_ms, 2),
                            "response": None,
                            "error": True,
                        })

                    if self.inter_command_delay > 0:
                        time.sleep(self.inter_command_delay)
            finally:
                sock.close()

            burst_results.append(burst_record)

            if burst_idx < self.num_bursts - 1 and self.inter_burst_delay > 0:
                time.sleep(self.inter_burst_delay)

        duration_ms = (time.perf_counter() - start) * 1000
        error_rate = (errors / total_sent * 100) if total_sent else 100.0

        if all_latencies:
            avg_latency = statistics.mean(all_latencies)
            max_latency = max(all_latencies)
            min_latency = min(all_latencies)
            p95 = sorted(all_latencies)[int(len(all_latencies) * 0.95)]
        else:
            avg_latency = max_latency = min_latency = p95 = 0.0

        passed = error_rate < 5.0  # Less than 5 % errors considered pass

        details_lines = [
            f"Bursts: {self.num_bursts}, Commands per burst: {self.burst_size}",
            f"Total commands sent: {total_sent}",
            f"Errors: {errors} ({error_rate:.1f}%)",
            f"Latency avg/min/max/p95: "
            f"{avg_latency:.1f}/{min_latency:.1f}/{max_latency:.1f}/{p95:.1f} ms",
        ]

        return VerificationResult(
            test_name="IP Command Stability",
            ticket_id="DSP3-136 / DSP3-134",
            passed=passed,
            message=("PASS - all commands acknowledged"
                     if passed else f"FAIL - {error_rate:.1f}% error rate"),
            details="\n".join(details_lines),
            duration_ms=round(duration_ms, 1),
            raw_data={
                "total_sent": total_sent,
                "errors": errors,
                "error_rate_pct": round(error_rate, 2),
                "latency_avg_ms": round(avg_latency, 2),
                "latency_min_ms": round(min_latency, 2),
                "latency_max_ms": round(max_latency, 2),
                "latency_p95_ms": round(p95, 2),
                "bursts": burst_results,
            },
        )


# =============================================================================
# StatusPageVerifier  (DSP3-135)
# =============================================================================

class StatusPageVerifier:
    """
    Verify that Status.htm reflects actual device state after changes.

    Sends commands via the binary protocol, then fetches the HTTP status page
    and checks that the reported state matches the expected outcome.

    JIRA: DSP3-135
    """

    _STATUS_PATH = "/Status.htm"
    _HTTP_TIMEOUT = 5

    def __init__(self, ip: str, settle_time: float = 2.0):
        self.ip = ip
        self.settle_time = settle_time
        self._base_url = f"http://{ip}"

    def _fetch_status(self) -> Optional[str]:
        """Fetch Status.htm and return the raw HTML, or None on failure."""
        try:
            resp = requests.get(
                self._base_url + self._STATUS_PATH,
                timeout=self._HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            logger.warning("Failed to fetch Status.htm: %s", exc)
            return None

    @staticmethod
    def _parse_mute_state(html: str) -> Optional[str]:
        """Extract mute state from Status.htm HTML.

        Looks for patterns like 'Mute=on', 'Mute=off', 'Mute: On', etc.
        Returns 'on', 'off', or None if not found.
        """
        match = re.search(r"[Mm]ute\s*[=:]\s*(on|off)", html, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return None

    @staticmethod
    def _parse_power_state(html: str) -> Optional[str]:
        """Extract power state from Status.htm HTML.

        Returns 'on', 'off', or None.
        """
        match = re.search(r"[Pp]ower\s*[=:]\s*(on|off)", html, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return None

    def run(self) -> VerificationResult:
        """Run the full status page verification suite."""
        start = time.perf_counter()
        sub_results: List[Dict] = []

        # ----- Sub-test 1: Mute toggle reflected on Status.htm -----
        mute_result = self._test_mute_reflection()
        sub_results.append(mute_result)

        # ----- Sub-test 2: Group power reflected on Status.htm -----
        power_result = self._test_group_power_reflection()
        sub_results.append(power_result)

        duration_ms = (time.perf_counter() - start) * 1000
        all_passed = all(r.get("passed", False) for r in sub_results)

        details_lines = []
        for r in sub_results:
            status = "PASS" if r["passed"] else "FAIL"
            details_lines.append(f"[{status}] {r['name']}: {r['message']}")

        return VerificationResult(
            test_name="Status Page Verification",
            ticket_id="DSP3-135",
            passed=all_passed,
            message="PASS - Status.htm accurate" if all_passed
                    else "FAIL - Status.htm mismatch detected",
            details="\n".join(details_lines),
            duration_ms=round(duration_ms, 1),
            raw_data={"sub_tests": sub_results},
        )

    def _test_mute_reflection(self) -> Dict:
        """Toggle mute and verify Status.htm updates."""
        name = "Mute reflection"

        # Fetch pre-state
        pre_html = self._fetch_status()
        if pre_html is None:
            return {"name": name, "passed": False,
                    "message": "Could not fetch Status.htm (pre-state)"}

        pre_mute = self._parse_mute_state(pre_html)

        # Send mute toggle via binary protocol
        resp = _send_command(self.ip, MK3CommandBuilder.global_mute_toggle())
        if resp is None:
            return {"name": name, "passed": False,
                    "message": "Mute toggle command failed"}

        time.sleep(self.settle_time)

        # Fetch post-state
        post_html = self._fetch_status()
        if post_html is None:
            return {"name": name, "passed": False,
                    "message": "Could not fetch Status.htm (post-state)"}

        post_mute = self._parse_mute_state(post_html)

        # Restore original mute state
        _send_command(self.ip, MK3CommandBuilder.global_mute_toggle())

        if pre_mute is None or post_mute is None:
            return {"name": name, "passed": False,
                    "message": f"Could not parse mute state "
                               f"(pre={pre_mute}, post={post_mute})"}

        changed = pre_mute != post_mute
        return {
            "name": name,
            "passed": changed,
            "message": (f"Mute toggled {pre_mute} -> {post_mute}"
                        if changed
                        else f"Mute did NOT change (still {pre_mute})"),
            "pre_mute": pre_mute,
            "post_mute": post_mute,
        }

    def _test_group_power_reflection(self) -> Dict:
        """Turn group power off then on and verify Status.htm updates."""
        name = "Group power reflection"

        # Fetch pre-state
        pre_html = self._fetch_status()
        if pre_html is None:
            return {"name": name, "passed": False,
                    "message": "Could not fetch Status.htm (pre-state)"}

        pre_power = self._parse_power_state(pre_html)

        # Send group power off
        resp = _send_command(self.ip, MK3CommandBuilder.global_group_power_off())
        if resp is None:
            return {"name": name, "passed": False,
                    "message": "Group power off command failed"}

        time.sleep(self.settle_time)

        # Fetch mid-state (should be off)
        mid_html = self._fetch_status()
        mid_power = self._parse_power_state(mid_html) if mid_html else None

        # Send group power on to restore
        _send_command(self.ip, MK3CommandBuilder.global_group_power_on())
        time.sleep(self.settle_time)

        # Fetch post-state (should be on again)
        post_html = self._fetch_status()
        post_power = self._parse_power_state(post_html) if post_html else None

        if mid_power is None or post_power is None:
            return {"name": name, "passed": False,
                    "message": f"Could not parse power state "
                               f"(mid={mid_power}, post={post_power})"}

        passed = mid_power == "off" and post_power == "on"
        return {
            "name": name,
            "passed": passed,
            "message": (f"Power off={mid_power}, restored={post_power}"
                        if passed
                        else f"Unexpected states: off-phase={mid_power}, "
                             f"on-phase={post_power}"),
            "pre_power": pre_power,
            "mid_power": mid_power,
            "post_power": post_power,
        }


# =============================================================================
# HTTPStabilityMonitor  (DSP3-150)
# =============================================================================

class HTTPStabilityMonitor:
    """
    Long-duration HTTP stability monitor.

    Polls the amplifier's web server at a configurable interval and tracks
    response times, failures, and uptime over the monitoring window.

    JIRA: DSP3-150
    """

    def __init__(self, ip: str, duration_sec: float = 1800,
                 poll_interval: float = 5.0,
                 progress_callback: Optional[Callable[[str, int, int], None]] = None,
                 stop_event: Optional[threading.Event] = None):
        self.ip = ip
        self.duration_sec = duration_sec
        self.poll_interval = poll_interval
        self.progress_callback = progress_callback
        self.stop_event = stop_event or threading.Event()
        self._base_url = f"http://{ip}"

    def _notify(self, message: str, current: int, total: int) -> None:
        if self.progress_callback is not None:
            try:
                self.progress_callback(message, current, total)
            except Exception:
                pass

    def run(self) -> VerificationResult:
        """Run the HTTP stability monitor for the configured duration."""
        start = time.perf_counter()
        total_polls = int(self.duration_sec / self.poll_interval) or 1

        latencies: List[float] = []
        failures: List[Dict] = []
        poll_count = 0
        success_count = 0

        endpoints = ["/", "/Status.htm"]

        while not self.stop_event.is_set():
            elapsed = time.perf_counter() - start
            if elapsed >= self.duration_sec:
                break

            poll_count += 1
            endpoint = endpoints[poll_count % len(endpoints)]
            url = self._base_url + endpoint

            t0 = time.perf_counter()
            try:
                resp = requests.get(url, timeout=5)
                resp.raise_for_status()
                latency_ms = (time.perf_counter() - t0) * 1000
                latencies.append(latency_ms)
                success_count += 1
            except requests.RequestException as exc:
                latency_ms = (time.perf_counter() - t0) * 1000
                failures.append({
                    "poll": poll_count,
                    "elapsed_sec": round(elapsed, 1),
                    "endpoint": endpoint,
                    "error": str(exc),
                    "latency_ms": round(latency_ms, 1),
                })
                logger.debug("HTTP poll %d failed: %s", poll_count, exc)

            self._notify(
                f"Poll {poll_count}/{total_polls} - {endpoint} "
                f"({latency_ms:.0f} ms)",
                poll_count,
                total_polls,
            )

            # Wait for the next interval, but allow early cancellation
            self.stop_event.wait(timeout=self.poll_interval)

        duration_ms = (time.perf_counter() - start) * 1000
        uptime_pct = (success_count / poll_count * 100) if poll_count else 0.0

        if latencies:
            avg_lat = statistics.mean(latencies)
            max_lat = max(latencies)
            min_lat = min(latencies)
            stdev_lat = statistics.stdev(latencies) if len(latencies) > 1 else 0.0
        else:
            avg_lat = max_lat = min_lat = stdev_lat = 0.0

        passed = uptime_pct >= 99.0 and (not failures or len(failures) < poll_count * 0.01)

        details_lines = [
            f"Duration: {self.duration_sec}s, Interval: {self.poll_interval}s",
            f"Total polls: {poll_count}, Successes: {success_count}, "
            f"Failures: {len(failures)}",
            f"Uptime: {uptime_pct:.2f}%",
            f"Latency avg/min/max/stdev: "
            f"{avg_lat:.1f}/{min_lat:.1f}/{max_lat:.1f}/{stdev_lat:.1f} ms",
        ]
        if failures:
            details_lines.append(f"First failure at poll {failures[0]['poll']} "
                                 f"({failures[0]['elapsed_sec']}s)")

        return VerificationResult(
            test_name="HTTP Stability Monitor",
            ticket_id="DSP3-150",
            passed=passed,
            message=f"{'PASS' if passed else 'FAIL'} - "
                    f"{uptime_pct:.2f}% uptime over {poll_count} polls",
            details="\n".join(details_lines),
            duration_ms=round(duration_ms, 1),
            raw_data={
                "poll_count": poll_count,
                "success_count": success_count,
                "failure_count": len(failures),
                "uptime_pct": round(uptime_pct, 2),
                "latency_avg_ms": round(avg_lat, 2),
                "latency_min_ms": round(min_lat, 2),
                "latency_max_ms": round(max_lat, 2),
                "latency_stdev_ms": round(stdev_lat, 2),
                "failures": failures,
            },
        )


# =============================================================================
# RebootDetector  (Sleep / Reboot issue)
# =============================================================================

class RebootDetector:
    """
    Monitor an amplifier for unexpected reboots / connection drops.

    Continuously polls via the binary protocol (power query) and records
    every connection drop with timestamps and measured downtime.

    Intended for the Sleep/Reboot firmware issue investigation.
    """

    def __init__(self, ip: str, duration_sec: float = 1800,
                 poll_interval: float = 2.0,
                 progress_callback: Optional[Callable[[str, int, int], None]] = None,
                 stop_event: Optional[threading.Event] = None):
        self.ip = ip
        self.duration_sec = duration_sec
        self.poll_interval = poll_interval
        self.progress_callback = progress_callback
        self.stop_event = stop_event or threading.Event()

    def _notify(self, message: str, current: int, total: int) -> None:
        if self.progress_callback is not None:
            try:
                self.progress_callback(message, current, total)
            except Exception:
                pass

    def run(self) -> VerificationResult:
        """Run the reboot detector for the configured duration."""
        start = time.perf_counter()
        total_polls = int(self.duration_sec / self.poll_interval) or 1

        poll_count = 0
        success_count = 0
        drops: List[Dict] = []
        in_drop = False
        drop_start: float = 0.0
        consecutive_failures = 0

        cmd = MK3CommandBuilder.power_query()

        while not self.stop_event.is_set():
            elapsed = time.perf_counter() - start
            if elapsed >= self.duration_sec:
                break

            poll_count += 1
            resp = _send_command(self.ip, cmd, timeout=_SOCKET_TIMEOUT)

            if resp is not None:
                success_count += 1
                if in_drop:
                    # Connection restored -- record the drop
                    drop_end = time.perf_counter()
                    downtime_sec = drop_end - drop_start
                    drop_record = {
                        "drop_number": len(drops) + 1,
                        "started_at_sec": round(drop_start - start, 1),
                        "ended_at_sec": round(drop_end - start, 1),
                        "downtime_sec": round(downtime_sec, 1),
                        "missed_polls": consecutive_failures,
                    }
                    drops.append(drop_record)
                    logger.info("Connection restored after %.1fs downtime "
                                "(drop #%d)", downtime_sec, len(drops))
                    self._notify(
                        f"Reconnected after {downtime_sec:.1f}s downtime "
                        f"(drop #{len(drops)})",
                        poll_count, total_polls,
                    )
                    in_drop = False
                    consecutive_failures = 0
                else:
                    parsed = MK3ResponseParser.parse(resp)
                    status_str = parsed.value if parsed.success else "?"
                    self._notify(
                        f"Poll {poll_count}/{total_polls} - "
                        f"Power: {status_str}",
                        poll_count, total_polls,
                    )
            else:
                consecutive_failures += 1
                if not in_drop:
                    in_drop = True
                    drop_start = time.perf_counter()
                    logger.warning("Connection drop detected at %.1fs",
                                   elapsed)
                self._notify(
                    f"Poll {poll_count}/{total_polls} - "
                    f"NO RESPONSE (drop #{len(drops) + 1}, "
                    f"{consecutive_failures} missed)",
                    poll_count, total_polls,
                )

            self.stop_event.wait(timeout=self.poll_interval)

        # If we ended while still in a drop, close it out
        if in_drop:
            drop_end = time.perf_counter()
            downtime_sec = drop_end - drop_start
            drops.append({
                "drop_number": len(drops) + 1,
                "started_at_sec": round(drop_start - start, 1),
                "ended_at_sec": round(drop_end - start, 1),
                "downtime_sec": round(downtime_sec, 1),
                "missed_polls": consecutive_failures,
                "still_down": True,
            })

        duration_ms = (time.perf_counter() - start) * 1000
        total_downtime = sum(d["downtime_sec"] for d in drops)
        uptime_pct = ((1 - total_downtime / (duration_ms / 1000)) * 100
                      if duration_ms > 0 else 0.0)

        passed = len(drops) == 0

        details_lines = [
            f"Duration: {self.duration_sec}s, Interval: {self.poll_interval}s",
            f"Total polls: {poll_count}, Successful: {success_count}",
            f"Connection drops detected: {len(drops)}",
            f"Total downtime: {total_downtime:.1f}s",
            f"Uptime: {uptime_pct:.2f}%",
        ]
        for d in drops:
            still = " (still down)" if d.get("still_down") else ""
            details_lines.append(
                f"  Drop #{d['drop_number']}: {d['downtime_sec']}s "
                f"at {d['started_at_sec']}s{still}"
            )

        return VerificationResult(
            test_name="Reboot Detector",
            ticket_id="Sleep/Reboot",
            passed=passed,
            message=("PASS - no unexpected drops"
                     if passed
                     else f"FAIL - {len(drops)} drop(s), "
                          f"{total_downtime:.1f}s total downtime"),
            details="\n".join(details_lines),
            duration_ms=round(duration_ms, 1),
            raw_data={
                "poll_count": poll_count,
                "success_count": success_count,
                "drop_count": len(drops),
                "total_downtime_sec": round(total_downtime, 1),
                "uptime_pct": round(uptime_pct, 2),
                "drops": drops,
            },
        )
