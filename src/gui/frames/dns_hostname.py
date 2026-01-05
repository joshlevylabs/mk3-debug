"""DNS and Hostname testing tab frame."""

import customtkinter as ctk
import threading
from typing import Optional, Callable

from ...network import DNSTester, HostnameTester
from ...utils import get_logger, Config
from ..components import ResultCard
from ..components.result_card import ResultStatus

logger = get_logger(__name__)


class DNSHostnameFrame(ctk.CTkFrame):
    """
    Frame for DNS and hostname testing functionality.
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
        self._dns_tester = DNSTester()
        self._hostname_tester = HostnameTester()

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
        """Build controls section."""
        controls = ctk.CTkFrame(self)
        controls.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        # Hostname tests
        ctk.CTkLabel(
            controls,
            text="Hostname Tests:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=10)

        self.socket_btn = ctk.CTkButton(
            controls,
            text="DNS Reverse",
            command=lambda: self._run_hostname_test("socket"),
            font=ctk.CTkFont(size=13),
            width=100
        )
        self.socket_btn.pack(side="left", padx=5)

        self.netbios_btn = ctk.CTkButton(
            controls,
            text="NetBIOS",
            command=lambda: self._run_hostname_test("netbios"),
            font=ctk.CTkFont(size=13),
            width=90
        )
        self.netbios_btn.pack(side="left", padx=5)

        self.mdns_btn = ctk.CTkButton(
            controls,
            text="mDNS",
            command=lambda: self._run_hostname_test("mdns"),
            font=ctk.CTkFont(size=13),
            width=80
        )
        self.mdns_btn.pack(side="left", padx=5)

        self.all_hostname_btn = ctk.CTkButton(
            controls,
            text="All Methods",
            command=self._run_all_hostname_tests,
            font=ctk.CTkFont(size=13),
            width=100
        )
        self.all_hostname_btn.pack(side="left", padx=5)

        # DNS server tests
        ctk.CTkLabel(
            controls,
            text="DNS Servers:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=(20, 10))

        self.dns_servers_btn = ctk.CTkButton(
            controls,
            text="Test Servers",
            command=self._run_dns_server_test,
            font=ctk.CTkFont(size=13),
            width=110
        )
        self.dns_servers_btn.pack(side="left", padx=5)

        # Full diagnosis
        self.diagnose_btn = ctk.CTkButton(
            controls,
            text="Full Diagnosis",
            command=self._run_full_diagnosis,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="green",
            hover_color="darkgreen",
            width=130
        )
        self.diagnose_btn.pack(side="left", padx=20)

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

    def _check_ip(self) -> Optional[str]:
        """Check if target IP is set."""
        ip = self._get_target_ip()
        if not ip:
            self.progress_label.configure(text="No target IP set!", text_color="red")
            return None
        return ip

    def _clear_results(self) -> None:
        """Clear all results."""
        for widget in self.results_scroll.winfo_children():
            widget.destroy()

    def _run_hostname_test(self, method: str) -> None:
        """Run a single hostname test."""
        ip = self._check_ip()
        if not ip:
            return

        self.progress_label.configure(text=f"Testing {method}...")

        def run():
            try:
                if method == "socket":
                    result = self._hostname_tester.resolve_via_socket(ip)
                elif method == "netbios":
                    result = self._hostname_tester.resolve_via_netbios(ip)
                elif method == "mdns":
                    result = self._hostname_tester.resolve_via_mdns(ip)
                else:
                    return

                self.after(0, lambda: self._display_hostname_result(result))
            except Exception as e:
                logger.error(f"Hostname test error: {e}")
                self.after(0, lambda: self.progress_label.configure(text=f"Error: {e}"))

        threading.Thread(target=run, daemon=True).start()

    def _display_hostname_result(self, result) -> None:
        """Display a single hostname result."""
        self._clear_results()

        section = ctk.CTkFrame(self.results_scroll)
        section.pack(fill="x", pady=5)

        ctk.CTkLabel(
            section,
            text=f"Hostname Resolution ({result.method})",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        if result.success:
            status = ResultStatus.PASSED
            msg = f"Hostname: {result.hostname}"
            details = f"Method: {result.method}\n" \
                     f"Response time: {result.response_time_ms:.1f}ms"
        else:
            status = ResultStatus.FAILED
            msg = result.error or "Resolution failed"
            details = f"Method: {result.method}"

        card = ResultCard(section, result.method.upper(), status, msg, details)
        card.pack(fill="x", padx=5, pady=2)

        self.progress_label.configure(text="Test complete")

    def _run_all_hostname_tests(self) -> None:
        """Run all hostname resolution methods."""
        ip = self._check_ip()
        if not ip:
            return

        self.all_hostname_btn.configure(state="disabled")
        self.progress_label.configure(text="Testing all methods...")

        def run():
            try:
                results = self._hostname_tester.resolve_all_methods(ip, "DSP")
                self.after(0, lambda: self._display_all_hostname_results(results))
            except Exception as e:
                logger.error(f"Hostname test error: {e}")
            finally:
                self.after(0, lambda: self.all_hostname_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _display_all_hostname_results(self, results) -> None:
        """Display all hostname resolution results."""
        self._clear_results()

        section = ctk.CTkFrame(self.results_scroll)
        section.pack(fill="x", pady=5)

        successful = sum(1 for r in results.values() if r.success)
        ctk.CTkLabel(
            section,
            text=f"Hostname Resolution ({successful}/{len(results)} methods succeeded)",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        for method, result in results.items():
            if result.success:
                status = ResultStatus.PASSED
                msg = f"Hostname: {result.hostname}"
                details = f"Response time: {result.response_time_ms:.1f}ms"
            else:
                status = ResultStatus.FAILED
                msg = result.error or "Failed"
                details = ""

            card = ResultCard(section, method.upper(), status, msg, details)
            card.pack(fill="x", padx=5, pady=2)

        self.progress_label.configure(text="All tests complete")

    def _run_dns_server_test(self) -> None:
        """Test DNS servers."""
        self.dns_servers_btn.configure(state="disabled")
        self.progress_label.configure(text="Testing DNS servers...")

        def run():
            try:
                # Get system DNS servers
                system_servers = self._dns_tester.get_system_dns_servers()
                all_servers = list(set(system_servers + self.config.common_dns_servers[:3]))

                results = self._dns_tester.test_multiple_dns_servers(all_servers)
                self.after(0, lambda: self._display_dns_server_results(results, system_servers))
            except Exception as e:
                logger.error(f"DNS server test error: {e}")
            finally:
                self.after(0, lambda: self.dns_servers_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _display_dns_server_results(self, results, system_servers) -> None:
        """Display DNS server test results."""
        self._clear_results()

        section = ctk.CTkFrame(self.results_scroll)
        section.pack(fill="x", pady=5)

        working = sum(1 for r in results if r.can_resolve)
        ctk.CTkLabel(
            section,
            text=f"DNS Server Tests ({working}/{len(results)} working)",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        for result in results:
            is_system = result.server_ip in system_servers

            if result.can_resolve:
                status = ResultStatus.PASSED
                msg = f"Working - {result.response_time_ms:.1f}ms"
            elif result.is_reachable:
                status = ResultStatus.WARNING
                msg = f"Reachable but not resolving: {result.error}"
            else:
                status = ResultStatus.FAILED
                msg = f"Unreachable: {result.error}"

            label = result.server_ip
            if is_system:
                label += " (System)"

            card = ResultCard(section, label, status, msg)
            card.pack(fill="x", padx=5, pady=2)

        self.progress_label.configure(text="DNS test complete")

    def _run_full_diagnosis(self) -> None:
        """Run full DNS and hostname diagnosis."""
        ip = self._check_ip()
        if not ip:
            return

        self.diagnose_btn.configure(state="disabled")
        self.progress_label.configure(text="Running full diagnosis...")

        def run():
            try:
                # Hostname diagnosis
                hostname_diag = self._hostname_tester.diagnose_hostname_issue(ip, "DSP")

                # DNS diagnosis
                dns_diag = self._dns_tester.full_dns_diagnostic(ip)

                self.after(0, lambda: self._display_full_diagnosis(hostname_diag, dns_diag))
            except Exception as e:
                logger.error(f"Diagnosis error: {e}")
            finally:
                self.after(0, lambda: self.diagnose_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _display_full_diagnosis(self, hostname_diag, dns_diag) -> None:
        """Display full diagnosis results."""
        self._clear_results()

        # Hostname section
        section1 = ctk.CTkFrame(self.results_scroll)
        section1.pack(fill="x", pady=5)

        ctk.CTkLabel(
            section1,
            text="Hostname Diagnosis",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        for method, data in hostname_diag.get('resolution_results', {}).items():
            if data.get('success'):
                status = ResultStatus.PASSED
                msg = f"Hostname: {data.get('hostname', 'Unknown')}"
            else:
                status = ResultStatus.FAILED
                msg = data.get('error', 'Failed')

            card = ResultCard(section1, method.upper(), status, msg)
            card.pack(fill="x", padx=5, pady=2)

        # Issues and recommendations
        if hostname_diag.get('issues'):
            issues_frame = ctk.CTkFrame(section1, fg_color=("gray90", "gray20"))
            issues_frame.pack(fill="x", padx=10, pady=5)

            ctk.CTkLabel(
                issues_frame,
                text="Issues Found:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="orange"
            ).pack(anchor="w", padx=10, pady=5)

            for issue in hostname_diag['issues']:
                ctk.CTkLabel(
                    issues_frame,
                    text=f"  • {issue}",
                    font=ctk.CTkFont(size=12),
                    wraplength=600,
                    justify="left"
                ).pack(anchor="w", padx=15, pady=2)

        if hostname_diag.get('recommendations'):
            rec_frame = ctk.CTkFrame(section1, fg_color=("gray85", "gray25"))
            rec_frame.pack(fill="x", padx=10, pady=5)

            ctk.CTkLabel(
                rec_frame,
                text="Recommendations:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="cyan"
            ).pack(anchor="w", padx=10, pady=5)

            for rec in hostname_diag['recommendations']:
                ctk.CTkLabel(
                    rec_frame,
                    text=f"  → {rec}",
                    font=ctk.CTkFont(size=12),
                    wraplength=600,
                    justify="left"
                ).pack(anchor="w", padx=15, pady=2)

        # DNS section
        section2 = ctk.CTkFrame(self.results_scroll)
        section2.pack(fill="x", pady=5)

        ctk.CTkLabel(
            section2,
            text="DNS Diagnosis",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=10, pady=5)

        # Reverse lookup
        rev = dns_diag.get('reverse_lookup')
        if rev:
            if rev.success:
                status = ResultStatus.PASSED
                msg = f"PTR: {', '.join(rev.answers)}"
            else:
                status = ResultStatus.FAILED
                msg = rev.error or "No PTR record"

            card = ResultCard(section2, "Reverse DNS (PTR)", status, msg)
            card.pack(fill="x", padx=5, pady=2)

        # Forward lookup
        fwd = dns_diag.get('forward_lookup')
        if fwd:
            if fwd.success:
                status = ResultStatus.PASSED
                msg = f"A records: {', '.join(fwd.answers)}"
            else:
                status = ResultStatus.FAILED
                msg = fwd.error or "Resolution failed"

            card = ResultCard(section2, "Forward DNS (A)", status, msg)
            card.pack(fill="x", padx=5, pady=2)

        # DNS issues
        if dns_diag.get('issues'):
            issues_frame = ctk.CTkFrame(section2, fg_color=("gray90", "gray20"))
            issues_frame.pack(fill="x", padx=10, pady=5)

            ctk.CTkLabel(
                issues_frame,
                text="DNS Issues:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="orange"
            ).pack(anchor="w", padx=10, pady=5)

            for issue in dns_diag['issues']:
                ctk.CTkLabel(
                    issues_frame,
                    text=f"  • {issue}",
                    font=ctk.CTkFont(size=12),
                    wraplength=600,
                    justify="left"
                ).pack(anchor="w", padx=15, pady=2)

        self.progress_label.configure(text="Diagnosis complete")
