"""Full diagnostics tab frame - Enhanced Corporate Design."""

import customtkinter as ctk
import threading
import json
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime
from pathlib import Path

from ...network import (
    NetworkDiscovery,
    ConnectivityTester,
    DNSTester,
    HostnameTester,
    CommandTester
)
from ...utils import get_logger, Config
from ..components import ResultCard
from ..components.result_card import ResultStatus, EnhancedIssueCard

logger = get_logger(__name__)


# Modern Corporate Color Palette
COLORS = {
    "bg_primary": "#0a0a0f",
    "bg_secondary": "#111827",
    "bg_card": "#1f2937",
    "bg_elevated": "#374151",
    "border_subtle": "#374151",
    "border_accent": "#3b82f6",
    "text_primary": "#f9fafb",
    "text_secondary": "#9ca3af",
    "text_muted": "#6b7280",
    "success": "#10b981",
    "success_bg": "#064e3b",
    "warning": "#f59e0b",
    "warning_bg": "#451a03",
    "error": "#ef4444",
    "error_bg": "#450a0a",
    "info": "#3b82f6",
    "info_bg": "#1e3a5f",
}


class DiagnosticsFrame(ctk.CTkFrame):
    """
    Frame for running comprehensive diagnostics.
    """

    def __init__(
        self,
        master,
        config: Config,
        get_target_ip: Callable[[], Optional[str]],
        **kwargs
    ):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.config = config
        self._get_target_ip = get_target_ip

        # Testers
        self._discovery = NetworkDiscovery()
        self._connectivity = ConnectivityTester()
        self._dns = DNSTester()
        self._hostname = HostnameTester()
        self._commands = CommandTester()

        self._is_running = False
        self._results = {}

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the UI."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Controls
        self._build_controls()

        # Results
        self._build_results()

    def _build_controls(self) -> None:
        """Build modern controls section with corporate styling."""
        # Header container with gradient-like appearance
        header_container = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_secondary"],
            corner_radius=0
        )
        header_container.grid(row=0, column=0, sticky="ew", padx=0, pady=0)

        # Inner controls with padding
        controls = ctk.CTkFrame(header_container, fg_color="transparent")
        controls.pack(fill="x", padx=20, pady=16)

        # Left side - Run button and progress
        left_section = ctk.CTkFrame(controls, fg_color="transparent")
        left_section.pack(side="left", fill="x", expand=True)

        # Modern run button with icon
        self.run_btn = ctk.CTkButton(
            left_section,
            text="▶  Run Diagnostics",
            command=self._run_full_diagnostic,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#10b981",
            hover_color="#059669",
            text_color="white",
            width=200,
            height=44,
            corner_radius=10
        )
        self.run_btn.pack(side="left")

        # Progress section
        progress_section = ctk.CTkFrame(left_section, fg_color="transparent")
        progress_section.pack(side="left", padx=(24, 0), fill="x", expand=True)

        # Progress label (above bar)
        self.progress_label = ctk.CTkLabel(
            progress_section,
            text="Ready to diagnose",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"],
            anchor="w"
        )
        self.progress_label.pack(anchor="w")

        # Modern progress bar
        self.progress_bar = ctk.CTkProgressBar(
            progress_section,
            width=400,
            height=8,
            corner_radius=4,
            fg_color=COLORS["bg_elevated"],
            progress_color=COLORS["info"]
        )
        self.progress_bar.pack(anchor="w", pady=(4, 0))
        self.progress_bar.set(0)

        # Right side - Export buttons
        right_section = ctk.CTkFrame(controls, fg_color="transparent")
        right_section.pack(side="right")

        # Export All button
        self.export_btn = ctk.CTkButton(
            right_section,
            text="Export All",
            command=self._export_report,
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["bg_elevated"],
            hover_color="#4b5563",
            text_color=COLORS["text_primary"],
            width=100,
            height=36,
            corner_radius=8,
            state="disabled"
        )
        self.export_btn.pack(side="left", padx=(0, 8))

        # Clear button
        self.clear_btn = ctk.CTkButton(
            right_section,
            text="Clear All Results",
            command=self._clear_results,
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            hover_color=COLORS["bg_elevated"],
            text_color=COLORS["text_secondary"],
            width=120,
            height=36,
            corner_radius=8,
            border_width=1,
            border_color=COLORS["border_subtle"]
        )
        self.clear_btn.pack(side="left")

    def _build_results(self) -> None:
        """Build modern results section."""
        # Results container with subtle background
        self.results_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_primary"],
            corner_radius=0
        )
        self.results_scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.results_scroll.grid_columnconfigure(0, weight=1)

        # Build placeholder
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        """Show the modern placeholder message."""
        # Placeholder container
        self.placeholder_frame = ctk.CTkFrame(
            self.results_scroll,
            fg_color=COLORS["bg_card"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border_subtle"]
        )
        self.placeholder_frame.pack(pady=40, padx=20)

        inner = ctk.CTkFrame(self.placeholder_frame, fg_color="transparent")
        inner.pack(padx=48, pady=40)

        # Icon
        ctk.CTkLabel(
            inner,
            text="🔍",
            font=ctk.CTkFont(size=48)
        ).pack()

        # Title
        ctk.CTkLabel(
            inner,
            text="Network Diagnostics",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(pady=(16, 8))

        # Description
        ctk.CTkLabel(
            inner,
            text="Run a comprehensive diagnostic suite to analyze your MK3 amplifier's\nnetwork connectivity, control protocols, and configuration.",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_secondary"],
            justify="center"
        ).pack(pady=(0, 24))

        # Test list in a modern card style
        tests_card = ctk.CTkFrame(inner, fg_color=COLORS["bg_secondary"], corner_radius=12)
        tests_card.pack(fill="x")

        tests_inner = ctk.CTkFrame(tests_card, fg_color="transparent")
        tests_inner.pack(padx=24, pady=20)

        ctk.CTkLabel(
            tests_inner,
            text="Diagnostic Tests Include:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLORS["text_primary"],
            anchor="w"
        ).pack(anchor="w", pady=(0, 12))

        tests = [
            ("📡", "Network Reachability", "Ping, latency, packet loss analysis"),
            ("🔌", "Port Scanning", "Web and control port availability"),
            ("🌐", "HTTP Endpoints", "Web interface accessibility"),
            ("🏷️", "Hostname Resolution", "NetBIOS, mDNS, reverse DNS"),
            ("📋", "DNS Configuration", "Server availability and PTR records"),
            ("⚡", "Command Protocol", "Control port testing and rate limiting"),
        ]

        for icon, name, desc in tests:
            row = ctk.CTkFrame(tests_inner, fg_color="transparent")
            row.pack(fill="x", pady=4)

            ctk.CTkLabel(row, text=icon, font=ctk.CTkFont(size=14)).pack(side="left")
            ctk.CTkLabel(
                row,
                text=name,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=COLORS["text_primary"]
            ).pack(side="left", padx=(8, 0))
            ctk.CTkLabel(
                row,
                text=f"— {desc}",
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_muted"]
            ).pack(side="left", padx=(8, 0))

    def _clear_results(self) -> None:
        """Clear all results and show placeholder."""
        for widget in self.results_scroll.winfo_children():
            widget.destroy()
        self._show_placeholder()
        self.export_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Ready to diagnose")

    def _check_ip(self) -> Optional[str]:
        """Check if target IP is set."""
        ip = self._get_target_ip()
        if not ip:
            self.progress_label.configure(text="No target IP set!", text_color="red")
            return None
        return ip

    def _run_full_diagnostic(self) -> None:
        """Run full diagnostic suite."""
        ip = self._check_ip()
        if not ip:
            return

        if self._is_running:
            return

        self._is_running = True
        self.run_btn.configure(state="disabled", text="Running...")
        self.export_btn.configure(state="disabled")

        # Clear previous results
        for widget in self.results_scroll.winfo_children():
            widget.destroy()

        # Initialize results
        self._results = {
            'timestamp': datetime.now().isoformat(),
            'ip_address': ip,
            'tests': {},
            'summary': {
                'passed': 0,
                'failed': 0,
                'warnings': 0
            }
        }

        def run():
            try:
                total_steps = 6
                current_step = 0

                # Step 1: Quick network check
                current_step += 1
                self._update_progress(current_step, total_steps, "Checking network reachability...")
                self._run_reachability_test(ip)

                # Step 2: Port scan
                current_step += 1
                self._update_progress(current_step, total_steps, "Scanning ports...")
                self._run_port_scan(ip)

                # Step 3: HTTP endpoints
                current_step += 1
                self._update_progress(current_step, total_steps, "Testing HTTP endpoints...")
                self._run_http_test(ip)

                # Step 4: Hostname resolution
                current_step += 1
                self._update_progress(current_step, total_steps, "Testing hostname resolution...")
                self._run_hostname_test(ip)

                # Step 5: DNS tests
                current_step += 1
                self._update_progress(current_step, total_steps, "Testing DNS...")
                self._run_dns_test(ip)

                # Step 6: Command testing
                current_step += 1
                self._update_progress(current_step, total_steps, "Testing command interface...")
                self._run_command_test(ip)

                # Final summary
                self.after(0, self._display_summary)

            except Exception as e:
                logger.error(f"Diagnostic error: {e}")
                self.after(0, lambda: self.progress_label.configure(
                    text=f"Error: {e}", text_color="red"
                ))
            finally:
                self._is_running = False
                self.after(0, lambda: self.run_btn.configure(
                    state="normal", text="Run Full Diagnostic"
                ))
                self.after(0, lambda: self.export_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _update_progress(self, current: int, total: int, message: str) -> None:
        """Update progress display."""
        progress = current / total
        self.after(0, lambda: self.progress_bar.set(progress))
        self.after(0, lambda: self.progress_label.configure(text=message))

    def _run_reachability_test(self, ip: str) -> None:
        """Run reachability test."""
        result = self._connectivity.ping_extended(ip, count=5)

        test_data = {
            'name': 'Network Reachability',
            'passed': result.is_reachable,
            'details': {
                'packets_sent': result.packets_sent,
                'packets_received': result.packets_received,
                'packet_loss': result.packet_loss_percent,
                'avg_latency_ms': result.avg_ms
            }
        }
        self._results['tests']['reachability'] = test_data

        if result.is_reachable:
            status = ResultStatus.PASSED
            msg = f"Device reachable - {result.avg_ms:.1f}ms avg latency"
            self._results['summary']['passed'] += 1
        else:
            status = ResultStatus.FAILED
            msg = "Device NOT reachable"
            self._results['summary']['failed'] += 1

        self.after(0, lambda: self._add_result_card(
            "Network Reachability", status, msg,
            f"Packets: {result.packets_received}/{result.packets_sent}\n"
            f"Packet Loss: {result.packet_loss_percent:.1f}%"
        ))

    def _run_port_scan(self, ip: str) -> None:
        """Run port scan."""
        # Test key ports
        key_ports = [80, 23, 443, 8080, 10000, 10001]
        results = self._connectivity.scan_ports(ip, key_ports)

        open_ports = [r for r in results if r.is_open]

        test_data = {
            'name': 'Port Scan',
            'passed': len(open_ports) > 0,
            'open_ports': [r.port for r in open_ports]
        }
        self._results['tests']['ports'] = test_data

        if open_ports:
            # Check for web port
            has_web = any(r.port == 80 for r in open_ports)
            if has_web:
                status = ResultStatus.PASSED
                msg = f"{len(open_ports)} ports open including web (80)"
                self._results['summary']['passed'] += 1
            else:
                status = ResultStatus.WARNING
                msg = f"{len(open_ports)} ports open but web port (80) closed"
                self._results['summary']['warnings'] += 1
        else:
            status = ResultStatus.FAILED
            msg = "No ports responding"
            self._results['summary']['failed'] += 1

        port_list = ", ".join(str(r.port) for r in open_ports)
        self.after(0, lambda: self._add_result_card(
            "Port Scan", status, msg,
            f"Open ports: {port_list if port_list else 'None'}"
        ))

    def _run_http_test(self, ip: str) -> None:
        """Run HTTP endpoint test."""
        endpoints = ["/", "/Landing.htm", "/index.html"]
        results = self._connectivity.test_http_endpoints(ip, endpoints)

        accessible = [r for r in results if r.is_accessible]

        test_data = {
            'name': 'HTTP Endpoints',
            'passed': len(accessible) > 0,
            'accessible_endpoints': [r.url for r in accessible]
        }
        self._results['tests']['http'] = test_data

        if accessible:
            landing = next((r for r in accessible if 'Landing' in r.url), None)
            if landing:
                status = ResultStatus.PASSED
                msg = f"Web interface accessible ({landing.response_time_ms:.0f}ms)"
                self._results['summary']['passed'] += 1
            else:
                status = ResultStatus.WARNING
                msg = f"{len(accessible)} endpoints accessible, but not Landing.htm"
                self._results['summary']['warnings'] += 1
        else:
            status = ResultStatus.FAILED
            msg = "Web interface NOT accessible"
            self._results['summary']['failed'] += 1

        self.after(0, lambda: self._add_result_card(
            "HTTP Web Interface", status, msg,
            "\n".join(f"• {r.url}: {r.status_code or r.error}" for r in results)
        ))

    def _run_hostname_test(self, ip: str) -> None:
        """Run hostname resolution test."""
        results = self._hostname.resolve_all_methods(ip, "DSP")

        successful = {m: r for m, r in results.items() if r.success}
        hostnames = [r.hostname for r in successful.values() if r.hostname]

        test_data = {
            'name': 'Hostname Resolution',
            'passed': len(successful) > 0,
            'methods_successful': list(successful.keys()),
            'hostnames_found': hostnames
        }
        self._results['tests']['hostname'] = test_data

        if successful:
            # Check if hostname is DSP
            has_dsp = any('dsp' in h.lower() for h in hostnames if h)
            if has_dsp:
                status = ResultStatus.PASSED
                msg = f"Hostname 'DSP' resolved via {list(successful.keys())}"
                self._results['summary']['passed'] += 1
            else:
                status = ResultStatus.WARNING
                msg = f"Hostname found but not 'DSP': {hostnames}"
                self._results['summary']['warnings'] += 1
        else:
            status = ResultStatus.FAILED
            msg = "No hostname resolution method succeeded"
            self._results['summary']['failed'] += 1

        details = "\n".join(
            f"• {m}: {r.hostname if r.success else r.error}"
            for m, r in results.items()
        )
        self.after(0, lambda: self._add_result_card(
            "Hostname Resolution (Issue #2)", status, msg, details
        ))

    def _run_dns_test(self, ip: str) -> None:
        """Run DNS test."""
        # Get system DNS and test them
        system_dns = self._dns.get_system_dns_servers()
        dns_results = self._dns.test_multiple_dns_servers(system_dns[:2])

        working_dns = [r for r in dns_results if r.can_resolve]

        test_data = {
            'name': 'DNS Servers',
            'passed': len(working_dns) > 0,
            'working_servers': [r.server_ip for r in working_dns]
        }
        self._results['tests']['dns'] = test_data

        if working_dns:
            status = ResultStatus.PASSED
            msg = f"{len(working_dns)}/{len(dns_results)} DNS servers working"
            self._results['summary']['passed'] += 1
        else:
            status = ResultStatus.FAILED
            msg = "No DNS servers responding"
            self._results['summary']['failed'] += 1

        details = "\n".join(
            f"• {r.server_ip}: {'Working' if r.can_resolve else r.error}"
            for r in dns_results
        )
        self.after(0, lambda: self._add_result_card(
            "DNS Configuration (Issue #3)", status, msg, details
        ))

    def _run_command_test(self, ip: str) -> None:
        """Run command protocol test."""
        # Try common control ports
        test_ports = [23, 10000, 4998]
        connected_port = None

        for port in test_ports:
            conn = self._commands.connect(ip, port)
            if conn.is_connected:
                connected_port = port
                self._commands.disconnect(conn)
                break

        if connected_port:
            # Run burst test
            burst_result = self._commands.burst_test(
                ip, connected_port, "status",
                count=5, delay_ms=0
            )

            test_data = {
                'name': 'Command Protocol',
                'passed': burst_result.error_rate_percent < 10,
                'port': connected_port,
                'error_rate': burst_result.error_rate_percent
            }
            self._results['tests']['commands'] = test_data

            if burst_result.error_rate_percent == 0:
                status = ResultStatus.PASSED
                msg = f"Command port {connected_port} - no errors at 0ms delay"
                self._results['summary']['passed'] += 1
            elif burst_result.error_rate_percent < 50:
                status = ResultStatus.WARNING
                msg = f"Command port {connected_port} - {burst_result.error_rate_percent:.0f}% error rate (rate limiting detected)"
                self._results['summary']['warnings'] += 1
            else:
                status = ResultStatus.FAILED
                msg = f"Command port {connected_port} - {burst_result.error_rate_percent:.0f}% error rate (severe issues)"
                self._results['summary']['failed'] += 1

            details = f"Port: {connected_port}\n" \
                     f"Commands sent: {burst_result.total_commands}\n" \
                     f"Successful: {burst_result.successful_commands}\n" \
                     f"Error rate: {burst_result.error_rate_percent:.1f}%"
        else:
            test_data = {
                'name': 'Command Protocol',
                'passed': False,
                'error': 'No command port found'
            }
            self._results['tests']['commands'] = test_data
            self._results['summary']['failed'] += 1

            status = ResultStatus.FAILED
            msg = "No command port found"
            details = f"Tested ports: {test_ports}"

        self.after(0, lambda: self._add_result_card(
            "Command Protocol (Issue #4)", status, msg, details
        ))

    def _add_result_card(self, name: str, status: ResultStatus,
                         message: str, details: str = "") -> None:
        """Add a result card to the display."""
        card = ResultCard(self.results_scroll, name, status, message, details)
        card.pack(fill="x", padx=16, pady=4)

    def _display_summary(self) -> None:
        """Display enhanced corporate-style summary with modern design."""
        summary = self._results['summary']
        tests = self._results.get('tests', {})
        ip = self._results.get('ip_address', 'Unknown')
        timestamp = self._results.get('timestamp', '')

        # Determine overall status
        if summary['failed'] == 0 and summary['warnings'] == 0:
            overall = "ALL SYSTEMS OPERATIONAL"
            overall_icon = "✓"
            overall_color = COLORS["success"]
            overall_bg = COLORS["success_bg"]
            status_type = "healthy"
        elif summary['failed'] == 0:
            overall = "MINOR ISSUES DETECTED"
            overall_icon = "!"
            overall_color = COLORS["warning"]
            overall_bg = COLORS["warning_bg"]
            status_type = "warning"
        else:
            overall = "ISSUES FOUND"
            overall_icon = "✗"
            overall_color = COLORS["error"]
            overall_bg = COLORS["error_bg"]
            status_type = "error"

        # ========== DEVICE INFO HEADER ==========
        device_header = ctk.CTkFrame(
            self.results_scroll,
            fg_color=COLORS["bg_card"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border_subtle"]
        )
        device_header.pack(fill="x", padx=16, pady=(16, 8))

        header_inner = ctk.CTkFrame(device_header, fg_color="transparent")
        header_inner.pack(fill="x", padx=24, pady=20)

        # Device info row
        info_row = ctk.CTkFrame(header_inner, fg_color="transparent")
        info_row.pack(fill="x")

        # Left: Device info
        left_info = ctk.CTkFrame(info_row, fg_color="transparent")
        left_info.pack(side="left")

        ctk.CTkLabel(
            left_info,
            text="Target Device",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w")

        ctk.CTkLabel(
            left_info,
            text=ip,
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w")

        # Right: Timestamp
        right_info = ctk.CTkFrame(info_row, fg_color="transparent")
        right_info.pack(side="right")

        ctk.CTkLabel(
            right_info,
            text="Tested",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"],
            anchor="e"
        ).pack(anchor="e")

        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            time_str = timestamp

        ctk.CTkLabel(
            right_info,
            text=time_str,
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_secondary"],
            anchor="e"
        ).pack(anchor="e")

        # ========== STATUS BANNER ==========
        status_banner = ctk.CTkFrame(
            self.results_scroll,
            fg_color=overall_bg,
            corner_radius=16,
            border_width=2,
            border_color=overall_color
        )
        status_banner.pack(fill="x", padx=16, pady=8)

        banner_inner = ctk.CTkFrame(status_banner, fg_color="transparent")
        banner_inner.pack(fill="x", padx=24, pady=24)

        # Status row with icon
        status_row = ctk.CTkFrame(banner_inner, fg_color="transparent")
        status_row.pack(fill="x")

        # Status icon circle
        icon_circle = ctk.CTkFrame(
            status_row,
            width=56,
            height=56,
            corner_radius=28,
            fg_color=overall_color
        )
        icon_circle.pack(side="left")
        icon_circle.pack_propagate(False)

        ctk.CTkLabel(
            icon_circle,
            text=overall_icon,
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="white"
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Status text
        status_text = ctk.CTkFrame(status_row, fg_color="transparent")
        status_text.pack(side="left", padx=(20, 0))

        ctk.CTkLabel(
            status_text,
            text=overall,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=overall_color
        ).pack(anchor="w")

        status_msg = {
            "healthy": "All diagnostic tests completed successfully.",
            "warning": "Some non-critical issues were detected.",
            "error": "Critical issues require attention."
        }

        ctk.CTkLabel(
            status_text,
            text=status_msg.get(status_type, ""),
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w", pady=(4, 0))

        # Stats pills
        stats_row = ctk.CTkFrame(banner_inner, fg_color="transparent")
        stats_row.pack(fill="x", pady=(20, 0))

        # Create stat pills
        stats = [
            (summary['passed'], "Passed", COLORS["success"]),
            (summary['warnings'], "Warnings", COLORS["warning"]),
            (summary['failed'], "Failed", COLORS["error"]),
        ]

        for count, label, color in stats:
            pill = ctk.CTkFrame(stats_row, fg_color=COLORS["bg_card"], corner_radius=8)
            pill.pack(side="left", padx=(0, 12))

            pill_inner = ctk.CTkFrame(pill, fg_color="transparent")
            pill_inner.pack(padx=16, pady=8)

            ctk.CTkLabel(
                pill_inner,
                text=str(count),
                font=ctk.CTkFont(size=24, weight="bold"),
                text_color=color
            ).pack(side="left")

            ctk.CTkLabel(
                pill_inner,
                text=label,
                font=ctk.CTkFont(size=12),
                text_color=COLORS["text_secondary"]
            ).pack(side="left", padx=(8, 0))

        # ========== ISSUES SECTION ==========
        if summary['failed'] > 0 or summary['warnings'] > 0:
            issues_section = ctk.CTkFrame(
                self.results_scroll,
                fg_color=COLORS["bg_card"],
                corner_radius=16,
                border_width=1,
                border_color=COLORS["error"]
            )
            issues_section.pack(fill="x", padx=16, pady=8)

            issues_inner = ctk.CTkFrame(issues_section, fg_color="transparent")
            issues_inner.pack(fill="x", padx=24, pady=20)

            # Section header
            header_row = ctk.CTkFrame(issues_inner, fg_color="transparent")
            header_row.pack(fill="x", pady=(0, 16))

            ctk.CTkLabel(
                header_row,
                text="⚠",
                font=ctk.CTkFont(size=20),
                text_color=COLORS["error"]
            ).pack(side="left")

            ctk.CTkLabel(
                header_row,
                text="Issues Requiring Attention",
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color=COLORS["text_primary"]
            ).pack(side="left", padx=(12, 0))

            # Display issues with enhanced cards
            self._display_enhanced_issues(issues_inner, tests)

        # ========== WORKING SECTION ==========
        working_section = ctk.CTkFrame(
            self.results_scroll,
            fg_color=COLORS["bg_card"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["success"]
        )
        working_section.pack(fill="x", padx=16, pady=8)

        working_inner = ctk.CTkFrame(working_section, fg_color="transparent")
        working_inner.pack(fill="x", padx=24, pady=20)

        # Section header
        header_row = ctk.CTkFrame(working_inner, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(
            header_row,
            text="✓",
            font=ctk.CTkFont(size=20),
            text_color=COLORS["success"]
        ).pack(side="left")

        ctk.CTkLabel(
            header_row,
            text="Operational Systems",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(side="left", padx=(12, 0))

        # Working items
        working_items = []

        if tests.get('reachability', {}).get('passed'):
            details = tests['reachability'].get('details', {})
            working_items.append({
                "name": "Network Reachability",
                "status": f"{details.get('avg_latency_ms', 0):.1f}ms latency",
                "detail": f"{details.get('packet_loss', 0):.0f}% packet loss"
            })

        if tests.get('ports', {}).get('passed'):
            ports = tests['ports'].get('open_ports', [])
            working_items.append({
                "name": "Port Availability",
                "status": f"{len(ports)} ports open",
                "detail": ", ".join(map(str, ports))
            })

        if tests.get('http', {}).get('passed'):
            working_items.append({
                "name": "Web Interface",
                "status": "Accessible",
                "detail": "/Landing.htm responding"
            })

        if tests.get('dns', {}).get('passed'):
            servers = tests['dns'].get('working_servers', [])
            working_items.append({
                "name": "DNS Configuration",
                "status": f"{len(servers)} server(s) working",
                "detail": ", ".join(servers)
            })

        if tests.get('hostname', {}).get('passed'):
            hostnames = tests['hostname'].get('hostnames_found', [])
            working_items.append({
                "name": "Hostname Resolution",
                "status": "Resolved",
                "detail": ", ".join(hostnames) if hostnames else "Found"
            })

        if tests.get('commands', {}).get('passed'):
            port = tests['commands'].get('port', 'Unknown')
            working_items.append({
                "name": "Command Protocol",
                "status": f"Port {port} active",
                "detail": "Accepting commands"
            })

        # Grid layout for working items
        if working_items:
            items_grid = ctk.CTkFrame(working_inner, fg_color="transparent")
            items_grid.pack(fill="x")

            for item in working_items:
                item_card = ctk.CTkFrame(
                    items_grid,
                    fg_color=COLORS["success_bg"],
                    corner_radius=8
                )
                item_card.pack(fill="x", pady=4)

                item_inner = ctk.CTkFrame(item_card, fg_color="transparent")
                item_inner.pack(fill="x", padx=16, pady=12)

                # Left side
                left = ctk.CTkFrame(item_inner, fg_color="transparent")
                left.pack(side="left")

                ctk.CTkLabel(
                    left,
                    text=item["name"],
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=COLORS["success"]
                ).pack(anchor="w")

                ctk.CTkLabel(
                    left,
                    text=item["detail"],
                    font=ctk.CTkFont(size=12),
                    text_color=COLORS["text_secondary"]
                ).pack(anchor="w")

                # Right side - status badge
                status_badge = ctk.CTkFrame(
                    item_inner,
                    fg_color=COLORS["success"],
                    corner_radius=6
                )
                status_badge.pack(side="right")

                ctk.CTkLabel(
                    status_badge,
                    text=item["status"],
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="white"
                ).pack(padx=10, pady=4)
        else:
            ctk.CTkLabel(
                working_inner,
                text="No tests passed - device may be offline or unreachable",
                font=ctk.CTkFont(size=13),
                text_color=COLORS["text_muted"]
            ).pack(anchor="w")

        # Complete
        self.progress_bar.set(1.0)
        self.progress_label.configure(text="Diagnostic complete", text_color=COLORS["success"])

    def _display_enhanced_issues(self, parent, tests: Dict[str, Any]) -> None:
        """Display issues using enhanced issue cards."""
        # Hostname Resolution Issue
        hostname_test = tests.get('hostname', {})
        if not hostname_test.get('passed', True):
            EnhancedIssueCard(
                parent,
                title="Hostname Not Broadcasting",
                severity="medium",
                description="Device won't appear by name in network scanners like AngryIP. This may be a firmware limitation.",
                root_cause={
                    "category": "Configuration/Firmware",
                    "technical_details": "The MK3 is not responding to NetBIOS name queries, not advertising mDNS/Bonjour services, and no reverse DNS (PTR) record exists for this IP.",
                    "evidence": [
                        "NetBIOS name resolution failed",
                        "mDNS/Bonjour discovery returned no results",
                        "Reverse DNS lookup returned no PTR record"
                    ]
                },
                corrective_actions=[
                    {
                        "priority": 1,
                        "action": "Check hostname configuration in amp settings",
                        "description": "Navigate to the device web interface and look for hostname or network name settings.",
                        "responsible_party": "installer",
                        "verification_steps": ["Access web interface", "Find network settings", "Check for hostname field"],
                        "estimated_complexity": "low"
                    },
                    {
                        "priority": 2,
                        "action": "Contact Sonance support for firmware guidance",
                        "description": "This may require a firmware update to enable hostname broadcasting.",
                        "responsible_party": "firmware_team",
                        "verification_steps": ["Check current firmware version", "Inquire about hostname support"],
                        "estimated_complexity": "medium"
                    }
                ],
                affected_functionality=["Network discovery tools", "Hostname-based addressing"],
                firmware_relevant=True
            ).pack(fill="x", pady=(0, 12))

        # Command Protocol Issue
        cmd_test = tests.get('commands', {})
        if not cmd_test.get('passed', True):
            if cmd_test.get('error') == 'No command port found':
                EnhancedIssueCard(
                    parent,
                    title="No Control Port Found",
                    severity="critical",
                    description="No TCP control ports are responding. Control systems (Crestron, Control4, Savant) cannot send commands to this amplifier.",
                    root_cause={
                        "category": "Configuration/Firmware",
                        "technical_details": "TCP connection attempts to standard control ports (23, 10000, 4998) all failed. The device web interface is accessible, indicating the device is network-connected, but the control protocol service is not running or not bound to any network interface.",
                        "evidence": [
                            "Port 23 (Telnet) - Connection refused/timeout",
                            "Port 10000 (Control) - Connection refused/timeout",
                            "Port 4998 (Crestron) - Connection refused/timeout",
                            "Web interface (port 80) is accessible"
                        ]
                    },
                    corrective_actions=[
                        {
                            "priority": 1,
                            "action": "Verify IP Control is enabled in device settings",
                            "description": "Access the device web interface and navigate to network/control settings. Ensure IP Control or TCP Control is enabled.",
                            "responsible_party": "installer",
                            "verification_steps": [
                                "Open web browser to device Landing.htm",
                                "Navigate to Settings > Network or Control",
                                "Look for 'IP Control' or 'TCP Control' setting",
                                "Enable and save changes",
                                "Reboot device if required"
                            ],
                            "estimated_complexity": "low"
                        },
                        {
                            "priority": 2,
                            "action": "Check firmware supports control protocol",
                            "description": "Some firmware versions may not include control protocol support or require a specific firmware variant.",
                            "responsible_party": "firmware_team",
                            "verification_steps": [
                                "Check current firmware version",
                                "Compare against changelog for control protocol support"
                            ],
                            "estimated_complexity": "medium"
                        },
                        {
                            "priority": 3,
                            "action": "Factory reset if issue persists",
                            "description": "A factory reset may restore default control protocol settings.",
                            "responsible_party": "installer",
                            "verification_steps": [
                                "Backup current configuration",
                                "Perform factory reset",
                                "Reconfigure and test"
                            ],
                            "estimated_complexity": "medium"
                        }
                    ],
                    affected_functionality=[
                        "Third-party control system integration",
                        "Automation and scripting",
                        "Remote volume/source control",
                        "Multi-room audio synchronization"
                    ],
                    firmware_relevant=True
                ).pack(fill="x", pady=(0, 12))

            elif cmd_test.get('error_rate', 0) > 0:
                EnhancedIssueCard(
                    parent,
                    title="Command Rate Limiting Detected",
                    severity="medium",
                    description=f"The amplifier rejected {cmd_test.get('error_rate', 0):.0f}% of rapid commands. Commands sent too quickly will fail.",
                    root_cause={
                        "category": "Firmware/Performance",
                        "technical_details": f"Burst test at 0ms delay resulted in {cmd_test.get('error_rate', 0):.1f}% error rate. The device command processor has rate limiting to prevent DoS conditions.",
                        "evidence": [
                            f"Control port: {cmd_test.get('port', 'Unknown')}",
                            f"Error rate: {cmd_test.get('error_rate', 0):.1f}%"
                        ]
                    },
                    corrective_actions=[
                        {
                            "priority": 1,
                            "action": "Add inter-command delay",
                            "description": "Configure control system to add 50-100ms delay between commands.",
                            "responsible_party": "installer",
                            "verification_steps": ["Add delays between commands", "Test with 50ms, increase if needed"],
                            "estimated_complexity": "low"
                        },
                        {
                            "priority": 2,
                            "action": "Implement command queueing",
                            "description": "Use a command queue with rate limiting on the control system side.",
                            "responsible_party": "installer",
                            "verification_steps": ["Implement FIFO queue", "Process with fixed interval"],
                            "estimated_complexity": "medium"
                        }
                    ],
                    affected_functionality=[
                        "Rapid command sequences",
                        "Macro execution",
                        "Bulk configuration changes"
                    ],
                    firmware_relevant=True
                ).pack(fill="x", pady=(0, 12))

        # Network Reachability Issue
        reach_test = tests.get('reachability', {})
        if not reach_test.get('passed', True):
            EnhancedIssueCard(
                parent,
                title="Device Not Reachable",
                severity="critical",
                description="The amplifier is not responding to network requests. It may be offline, disconnected, or on a different network.",
                root_cause={
                    "category": "Network/Hardware",
                    "technical_details": "ICMP ping requests are not being answered. This typically indicates the device is powered off, not connected to the network, or blocked by a firewall.",
                    "evidence": [
                        "ICMP ping failed - no response",
                        "All TCP connection attempts timed out"
                    ]
                },
                corrective_actions=[
                    {
                        "priority": 1,
                        "action": "Verify IP address is correct",
                        "description": "Confirm the target IP matches the device's actual address.",
                        "responsible_party": "installer",
                        "verification_steps": ["Check device display or web interface for IP"],
                        "estimated_complexity": "low"
                    },
                    {
                        "priority": 2,
                        "action": "Check physical connections",
                        "description": "Verify power and network cable connections.",
                        "responsible_party": "installer",
                        "verification_steps": ["Check power LED", "Verify Ethernet link lights", "Try different cable/port"],
                        "estimated_complexity": "low"
                    },
                    {
                        "priority": 3,
                        "action": "Check firewall rules",
                        "description": "Ensure no firewall is blocking ICMP or TCP traffic.",
                        "responsible_party": "installer",
                        "verification_steps": ["Review network firewall rules", "Check VLAN configuration"],
                        "estimated_complexity": "medium"
                    }
                ],
                affected_functionality=[
                    "All network communication",
                    "Web interface access",
                    "Control system integration"
                ],
                firmware_relevant=False
            ).pack(fill="x", pady=(0, 12))

        # HTTP/Web Interface Issue
        http_test = tests.get('http', {})
        if not http_test.get('passed', True) and reach_test.get('passed', False):
            EnhancedIssueCard(
                parent,
                title="Web Interface Not Accessible",
                severity="high",
                description="The amplifier responds to ping but the web interface is not working. Browser access is unavailable.",
                root_cause={
                    "category": "Firmware/Service",
                    "technical_details": "Device responds to ICMP but HTTP connections to port 80 fail. The web server service may have crashed or port 80 may be blocked.",
                    "evidence": [
                        "Ping successful",
                        "HTTP port 80 not responding",
                        "Landing.htm not accessible"
                    ]
                },
                corrective_actions=[
                    {
                        "priority": 1,
                        "action": "Reboot the amplifier",
                        "description": "Power cycle the device to restart all services.",
                        "responsible_party": "installer",
                        "verification_steps": ["Power off", "Wait 10 seconds", "Power on", "Wait for boot"],
                        "estimated_complexity": "low"
                    },
                    {
                        "priority": 2,
                        "action": "Try alternate port 8080",
                        "description": "Some devices may serve web interface on port 8080.",
                        "responsible_party": "installer",
                        "verification_steps": ["Try http://<IP>:8080 in browser"],
                        "estimated_complexity": "low"
                    }
                ],
                affected_functionality=[
                    "Device configuration via browser",
                    "Firmware updates",
                    "Status monitoring"
                ],
                firmware_relevant=True
            ).pack(fill="x", pady=(0, 12))

        # DNS Issue
        dns_test = tests.get('dns', {})
        if not dns_test.get('passed', True):
            EnhancedIssueCard(
                parent,
                title="DNS Configuration Issue",
                severity="low",
                description="DNS servers are not responding. This may affect hostname resolution on the network.",
                root_cause={
                    "category": "Network Configuration",
                    "technical_details": "System DNS servers failed to respond to queries. This is typically a network infrastructure issue rather than a device issue.",
                    "evidence": [
                        "DNS servers not responding",
                        "May affect hostname resolution"
                    ]
                },
                corrective_actions=[
                    {
                        "priority": 1,
                        "action": "Check network DNS configuration",
                        "description": "Verify DNS servers are correctly configured and accessible.",
                        "responsible_party": "installer",
                        "verification_steps": ["Check router DNS settings", "Try public DNS (8.8.8.8)"],
                        "estimated_complexity": "low"
                    }
                ],
                affected_functionality=[
                    "Hostname resolution",
                    "Network name lookups"
                ],
                firmware_relevant=False
            ).pack(fill="x", pady=(0, 12))

    def _add_issue_explanation(self, parent, title: str, description: str,
                                findings: list, recommendations: list) -> None:
        """Add a detailed issue explanation card."""
        issue_card = ctk.CTkFrame(parent, fg_color=("#ffe0e0", "#3d2020"), corner_radius=8)
        issue_card.pack(fill="x", padx=15, pady=8)

        # Title
        ctk.CTkLabel(
            issue_card,
            text=f"✗ {title}",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#e74c3c"
        ).pack(anchor="w", padx=12, pady=(12, 5))

        # Description
        ctk.CTkLabel(
            issue_card,
            text=description,
            font=ctk.CTkFont(size=12),
            wraplength=700,
            justify="left",
            anchor="w"
        ).pack(anchor="w", padx=12, pady=(0, 10))

        # Findings
        findings_frame = ctk.CTkFrame(issue_card, fg_color="transparent")
        findings_frame.pack(fill="x", padx=12, pady=(0, 5))

        ctk.CTkLabel(
            findings_frame,
            text="What we found:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w")

        for finding in findings:
            ctk.CTkLabel(
                findings_frame,
                text=f"  • {finding}",
                font=ctk.CTkFont(size=11),
                anchor="w"
            ).pack(anchor="w", padx=10)

        # Recommendations
        rec_frame = ctk.CTkFrame(issue_card, fg_color=("#d4edda", "#1a3d1a"), corner_radius=5)
        rec_frame.pack(fill="x", padx=12, pady=(10, 12))

        ctk.CTkLabel(
            rec_frame,
            text="Recommended Actions:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#155724"
        ).pack(anchor="w", padx=10, pady=(8, 5))

        for i, rec in enumerate(recommendations, 1):
            ctk.CTkLabel(
                rec_frame,
                text=f"  {i}. {rec}",
                font=ctk.CTkFont(size=11),
                text_color="#155724",
                anchor="w",
                wraplength=650,
                justify="left"
            ).pack(anchor="w", padx=10, pady=1)

        ctk.CTkLabel(rec_frame, text="").pack(pady=3)  # Spacer

    def _export_report(self) -> None:
        """Export diagnostic report."""
        from tkinter import filedialog

        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[
                ("JSON files", "*.json"),
                ("HTML files", "*.html"),
                ("All files", "*.*")
            ],
            initialfile=f"mk3_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )

        if not filename:
            return

        try:
            if filename.endswith('.html'):
                self._export_html(filename)
            else:
                self._export_json(filename)

            self.progress_label.configure(text=f"Report exported: {Path(filename).name}")
        except Exception as e:
            logger.error(f"Export error: {e}")
            self.progress_label.configure(text=f"Export error: {e}", text_color="red")

    def _export_json(self, filename: str) -> None:
        """Export as JSON."""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self._results, f, indent=2, default=str)

    def _export_html(self, filename: str) -> None:
        """Export as HTML report."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>MK3 Diagnostic Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #1a1a1a; color: #fff; }}
        h1 {{ color: #3498db; }}
        .passed {{ color: #27ae60; }}
        .failed {{ color: #e74c3c; }}
        .warning {{ color: #f39c12; }}
        .test {{ background: #2a2a2a; padding: 15px; margin: 10px 0; border-radius: 8px; }}
        .summary {{ background: #333; padding: 20px; border-radius: 10px; margin: 20px 0; }}
    </style>
</head>
<body>
    <h1>MK3 Amplifier Diagnostic Report</h1>
    <p>Generated: {self._results['timestamp']}</p>
    <p>Target IP: {self._results['ip_address']}</p>

    <div class="summary">
        <h2>Summary</h2>
        <p class="passed">Passed: {self._results['summary']['passed']}</p>
        <p class="warning">Warnings: {self._results['summary']['warnings']}</p>
        <p class="failed">Failed: {self._results['summary']['failed']}</p>
    </div>

    <h2>Test Results</h2>
"""

        for test_name, test_data in self._results['tests'].items():
            status_class = 'passed' if test_data.get('passed') else 'failed'
            html += f"""
    <div class="test">
        <h3 class="{status_class}">{test_data.get('name', test_name)}</h3>
        <pre>{json.dumps(test_data, indent=2, default=str)}</pre>
    </div>
"""

        html += """
</body>
</html>
"""

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)
