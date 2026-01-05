"""Connectivity testing tab frame."""

import customtkinter as ctk
import threading
from typing import Optional, Callable

from ...network import ConnectivityTester
from ...utils import get_logger, Config
from ..components import ResultCard
from ..components.result_card import ResultStatus

logger = get_logger(__name__)


class ConnectivityFrame(ctk.CTkFrame):
    """
    Frame for connectivity testing functionality.
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
        self._tester = ConnectivityTester()
        self._is_testing = False

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the connectivity UI."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Controls
        self._build_controls()

        # Results
        self._build_results()

    def _build_controls(self) -> None:
        """Build controls section."""
        controls = ctk.CTkFrame(self)
        controls.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        # Test buttons
        self.ping_btn = ctk.CTkButton(
            controls,
            text="Extended Ping",
            command=self._run_ping_test,
            font=ctk.CTkFont(size=13),
            width=130
        )
        self.ping_btn.pack(side="left", padx=10)

        self.port_btn = ctk.CTkButton(
            controls,
            text="Port Scan",
            command=self._run_port_scan,
            font=ctk.CTkFont(size=13),
            width=100
        )
        self.port_btn.pack(side="left", padx=5)

        self.http_btn = ctk.CTkButton(
            controls,
            text="HTTP Endpoints",
            command=self._run_http_test,
            font=ctk.CTkFont(size=13),
            width=130
        )
        self.http_btn.pack(side="left", padx=5)

        self.full_btn = ctk.CTkButton(
            controls,
            text="Run All Tests",
            command=self._run_all_tests,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="green",
            hover_color="darkgreen",
            width=130
        )
        self.full_btn.pack(side="left", padx=20)

        # Progress
        self.progress_label = ctk.CTkLabel(
            controls,
            text="",
            font=ctk.CTkFont(size=12)
        )
        self.progress_label.pack(side="right", padx=10)

    def _build_results(self) -> None:
        """Build results section."""
        self.results_scroll = ctk.CTkScrollableFrame(self)
        self.results_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.results_scroll.grid_columnconfigure(0, weight=1)

        # Section headers and result cards will be added dynamically
        self._ping_section = None
        self._ports_section = None
        self._http_section = None

    def _check_ip(self) -> Optional[str]:
        """Check if target IP is set."""
        ip = self._get_target_ip()
        if not ip:
            self.progress_label.configure(text="No target IP set!", text_color="red")
            return None
        return ip

    def _run_ping_test(self) -> None:
        """Run extended ping test."""
        ip = self._check_ip()
        if not ip:
            return

        self.ping_btn.configure(state="disabled")
        self._clear_section("ping")

        def run():
            try:
                result = self._tester.ping_extended(
                    ip, count=10,
                    progress_callback=lambda c, t: self.after(
                        0, lambda: self.progress_label.configure(text=f"Ping {c}/{t}")
                    )
                )
                self.after(0, lambda: self._display_ping_result(result))
            except Exception as e:
                logger.error(f"Ping test error: {e}")
                self.after(0, lambda: self.progress_label.configure(text=f"Error: {e}"))
            finally:
                self.after(0, lambda: self.ping_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _display_ping_result(self, result) -> None:
        """Display ping test results."""
        self._clear_section("ping")

        section = ctk.CTkFrame(self.results_scroll)
        section.pack(fill="x", pady=5)
        section._section_name = "ping"

        ctk.CTkLabel(
            section,
            text="Ping Results",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        if result.is_reachable:
            status = ResultStatus.PASSED
            msg = f"{result.packets_received}/{result.packets_sent} packets, " \
                  f"avg {result.avg_ms:.1f}ms, loss {result.packet_loss_percent:.1f}%"
            details = f"Min: {result.min_ms:.1f}ms\n" \
                     f"Avg: {result.avg_ms:.1f}ms\n" \
                     f"Max: {result.max_ms:.1f}ms\n" \
                     f"Packet Loss: {result.packet_loss_percent:.1f}%"
        else:
            status = ResultStatus.FAILED
            msg = "Host unreachable"
            details = f"Sent {result.packets_sent} packets, received {result.packets_received}"

        card = ResultCard(section, "ICMP Ping", status, msg, details)
        card.pack(fill="x", padx=5, pady=2)

        self.progress_label.configure(text="Ping complete")
        self._ping_section = section

    def _run_port_scan(self) -> None:
        """Run port scan."""
        ip = self._check_ip()
        if not ip:
            return

        self.port_btn.configure(state="disabled")
        self._clear_section("ports")

        def run():
            try:
                results = self._tester.scan_ports(
                    ip, self.config.common_ports,
                    progress_callback=lambda c, t, p: self.after(
                        0, lambda: self.progress_label.configure(text=f"Scanning port {p}")
                    )
                )
                self.after(0, lambda: self._display_port_results(results))
            except Exception as e:
                logger.error(f"Port scan error: {e}")
            finally:
                self.after(0, lambda: self.port_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _display_port_results(self, results) -> None:
        """Display port scan results."""
        self._clear_section("ports")

        section = ctk.CTkFrame(self.results_scroll)
        section.pack(fill="x", pady=5)
        section._section_name = "ports"

        open_ports = [r for r in results if r.is_open]

        ctk.CTkLabel(
            section,
            text=f"Port Scan Results ({len(open_ports)} open)",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        for result in results:
            if result.is_open:
                status = ResultStatus.PASSED
                msg = f"OPEN - {result.service_name or 'Unknown service'}"
                details = f"Response time: {result.response_time_ms:.1f}ms"
                if result.banner:
                    details += f"\nBanner: {result.banner}"
            else:
                status = ResultStatus.FAILED
                msg = "CLOSED"
                details = ""

            card = ResultCard(section, f"Port {result.port}", status, msg, details)
            card.pack(fill="x", padx=5, pady=2)

        self.progress_label.configure(text="Port scan complete")
        self._ports_section = section

    def _run_http_test(self) -> None:
        """Run HTTP endpoint tests."""
        ip = self._check_ip()
        if not ip:
            return

        self.http_btn.configure(state="disabled")
        self._clear_section("http")

        def run():
            try:
                results = self._tester.test_http_endpoints(
                    ip, self.config.http_endpoints,
                    progress_callback=lambda c, t, e: self.after(
                        0, lambda: self.progress_label.configure(text=f"Testing {e}")
                    )
                )
                self.after(0, lambda: self._display_http_results(results))
            except Exception as e:
                logger.error(f"HTTP test error: {e}")
            finally:
                self.after(0, lambda: self.http_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _display_http_results(self, results) -> None:
        """Display HTTP test results."""
        self._clear_section("http")

        section = ctk.CTkFrame(self.results_scroll)
        section.pack(fill="x", pady=5)
        section._section_name = "http"

        accessible = [r for r in results if r.is_accessible]

        ctk.CTkLabel(
            section,
            text=f"HTTP Endpoints ({len(accessible)} accessible)",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        for result in results:
            if result.is_accessible:
                status = ResultStatus.PASSED
                msg = f"HTTP {result.status_code} - {result.response_time_ms:.0f}ms"
                details = f"URL: {result.url}\n" \
                         f"Content-Type: {result.content_type}\n" \
                         f"Content-Length: {result.content_length} bytes"
                if result.title:
                    details += f"\nTitle: {result.title}"
            else:
                status = ResultStatus.FAILED
                msg = result.error or "Not accessible"
                details = f"URL: {result.url}"

            card = ResultCard(section, result.url.split('/')[-1] or "/", status, msg, details)
            card.pack(fill="x", padx=5, pady=2)

        self.progress_label.configure(text="HTTP test complete")
        self._http_section = section

    def _run_all_tests(self) -> None:
        """Run all connectivity tests."""
        ip = self._check_ip()
        if not ip:
            return

        self.full_btn.configure(state="disabled")
        self._clear_all_sections()

        def run():
            try:
                report = self._tester.run_full_test(
                    ip,
                    self.config.common_ports,
                    self.config.http_endpoints,
                    progress_callback=lambda phase, c, t: self.after(
                        0, lambda: self.progress_label.configure(text=f"{phase}: {c}/{t}")
                    )
                )
                self.after(0, lambda: self._display_full_report(report))
            except Exception as e:
                logger.error(f"Full test error: {e}")
            finally:
                self.after(0, lambda: self.full_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _display_full_report(self, report) -> None:
        """Display full connectivity report."""
        self._clear_all_sections()

        # Summary
        summary = ctk.CTkFrame(self.results_scroll)
        summary.pack(fill="x", pady=5)

        status_colors = {
            "healthy": "green",
            "partial": "orange",
            "reachable": "yellow",
            "unreachable": "red"
        }

        ctk.CTkLabel(
            summary,
            text=f"Overall Status: {report.overall_status.upper()}",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=status_colors.get(report.overall_status, "gray")
        ).pack(pady=10)

        # Display individual sections
        if report.ping_result:
            self._display_ping_result(report.ping_result)

        if report.open_ports:
            self._display_port_results(report.open_ports)

        if report.http_endpoints:
            self._display_http_results(report.http_endpoints)

        self.progress_label.configure(text="All tests complete")

    def _clear_section(self, name: str) -> None:
        """Clear a specific section."""
        for widget in self.results_scroll.winfo_children():
            if hasattr(widget, '_section_name') and widget._section_name == name:
                widget.destroy()

    def _clear_all_sections(self) -> None:
        """Clear all result sections."""
        for widget in self.results_scroll.winfo_children():
            widget.destroy()
