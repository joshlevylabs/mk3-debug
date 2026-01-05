"""Command testing tab frame."""

import customtkinter as ctk
import threading
from typing import Optional, Callable

from ...network import CommandTester
from ...utils import get_logger, Config
from ..components import ResultCard
from ..components.result_card import ResultStatus

logger = get_logger(__name__)


class CommandsFrame(ctk.CTkFrame):
    """
    Frame for TCP command testing functionality.

    This frame helps diagnose the issue where multiple IP commands
    cause command errors due to rate limiting or queueing issues.
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
        self._tester = CommandTester()
        self._connection = None

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the UI."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Connection controls
        self._build_connection_controls()

        # Command controls
        self._build_command_controls()

        # Results
        self._build_results()

    def _build_connection_controls(self) -> None:
        """Build connection controls."""
        conn_frame = ctk.CTkFrame(self)
        conn_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        ctk.CTkLabel(
            conn_frame,
            text="Connection:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            conn_frame,
            text="Port:",
            font=ctk.CTkFont(size=13)
        ).pack(side="left", padx=(10, 5))

        self.port_entry = ctk.CTkEntry(
            conn_frame,
            placeholder_text="23",
            width=80,
            font=ctk.CTkFont(size=13)
        )
        self.port_entry.pack(side="left", padx=5)
        self.port_entry.insert(0, "23")  # Default telnet port

        # Preset ports dropdown
        self.port_presets = ctk.CTkOptionMenu(
            conn_frame,
            values=["23 (Telnet)", "80 (HTTP)", "10000", "10001", "4998", "4999", "5000"],
            command=self._on_port_preset,
            width=120
        )
        self.port_presets.set("Presets")
        self.port_presets.pack(side="left", padx=5)

        # Terminator selection
        ctk.CTkLabel(
            conn_frame,
            text="Terminator:",
            font=ctk.CTkFont(size=13)
        ).pack(side="left", padx=(20, 5))

        self.terminator_var = ctk.StringVar(value="crlf")
        self.terminator_menu = ctk.CTkOptionMenu(
            conn_frame,
            values=["crlf", "cr", "lf", "none"],
            variable=self.terminator_var,
            width=80
        )
        self.terminator_menu.pack(side="left", padx=5)

        # Connect button
        self.connect_btn = ctk.CTkButton(
            conn_frame,
            text="Connect",
            command=self._toggle_connection,
            font=ctk.CTkFont(size=13),
            width=100
        )
        self.connect_btn.pack(side="left", padx=20)

        # Connection status
        self.conn_status = ctk.CTkLabel(
            conn_frame,
            text="Disconnected",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.conn_status.pack(side="right", padx=10)

    def _build_command_controls(self) -> None:
        """Build command entry and test controls."""
        cmd_frame = ctk.CTkFrame(self)
        cmd_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        # Command entry
        left_frame = ctk.CTkFrame(cmd_frame, fg_color="transparent")
        left_frame.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            left_frame,
            text="Command:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=10)

        self.command_entry = ctk.CTkEntry(
            left_frame,
            placeholder_text="Enter command to send",
            width=300,
            font=ctk.CTkFont(size=13)
        )
        self.command_entry.pack(side="left", padx=5)
        self.command_entry.bind("<Return>", lambda e: self._send_command())

        self.send_btn = ctk.CTkButton(
            left_frame,
            text="Send",
            command=self._send_command,
            font=ctk.CTkFont(size=13),
            width=80
        )
        self.send_btn.pack(side="left", padx=5)

        # Burst test controls
        right_frame = ctk.CTkFrame(cmd_frame, fg_color="transparent")
        right_frame.pack(side="right")

        ctk.CTkLabel(
            right_frame,
            text="Burst Test:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            right_frame,
            text="Count:",
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=5)

        self.burst_count = ctk.CTkEntry(
            right_frame,
            width=50,
            font=ctk.CTkFont(size=12)
        )
        self.burst_count.pack(side="left", padx=2)
        self.burst_count.insert(0, "10")

        ctk.CTkLabel(
            right_frame,
            text="Delay (ms):",
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=5)

        self.burst_delay = ctk.CTkEntry(
            right_frame,
            width=60,
            font=ctk.CTkFont(size=12)
        )
        self.burst_delay.pack(side="left", padx=2)
        self.burst_delay.insert(0, "0")

        self.burst_btn = ctk.CTkButton(
            right_frame,
            text="Run Burst",
            command=self._run_burst_test,
            font=ctk.CTkFont(size=13),
            width=100
        )
        self.burst_btn.pack(side="left", padx=10)

        self.find_delay_btn = ctk.CTkButton(
            right_frame,
            text="Find Optimal Delay",
            command=self._find_optimal_delay,
            font=ctk.CTkFont(size=13),
            fg_color="green",
            hover_color="darkgreen",
            width=140
        )
        self.find_delay_btn.pack(side="left", padx=5)

    def _build_results(self) -> None:
        """Build results section."""
        self.results_scroll = ctk.CTkScrollableFrame(self)
        self.results_scroll.grid(row=2, column=0, sticky="nsew", padx=10, pady=(5, 10))
        self.results_scroll.grid_columnconfigure(0, weight=1)

        # Command log
        self._add_section_header("Command Log")

    def _add_section_header(self, title: str) -> None:
        """Add a section header."""
        header = ctk.CTkLabel(
            self.results_scroll,
            text=title,
            font=ctk.CTkFont(size=16, weight="bold")
        )
        header.pack(anchor="w", padx=10, pady=(10, 5))

    def _check_ip(self) -> Optional[str]:
        """Check if target IP is set."""
        ip = self._get_target_ip()
        if not ip:
            self.conn_status.configure(text="No target IP!", text_color="red")
            return None
        return ip

    def _get_port(self) -> int:
        """Get the port number."""
        try:
            return int(self.port_entry.get().strip())
        except ValueError:
            return 23

    def _on_port_preset(self, value: str) -> None:
        """Handle port preset selection."""
        port = value.split(" ")[0]
        self.port_entry.delete(0, "end")
        self.port_entry.insert(0, port)

    def _toggle_connection(self) -> None:
        """Toggle connection state."""
        if self._connection and self._connection.is_connected:
            self._tester.disconnect(self._connection)
            self._connection = None
            self.connect_btn.configure(text="Connect")
            self.conn_status.configure(text="Disconnected", text_color="gray")
        else:
            self._connect()

    def _connect(self) -> None:
        """Establish connection."""
        ip = self._check_ip()
        if not ip:
            return

        port = self._get_port()
        self.conn_status.configure(text="Connecting...", text_color="yellow")

        def run():
            # Update terminator
            self._tester.terminator = self._tester.TERMINATORS.get(
                self.terminator_var.get(), b'\r\n'
            )

            conn = self._tester.connect(ip, port)
            self._connection = conn

            if conn.is_connected:
                self.after(0, lambda: self._on_connected())
            else:
                self.after(0, lambda: self._on_connect_failed(conn.last_error))

        threading.Thread(target=run, daemon=True).start()

    def _on_connected(self) -> None:
        """Handle successful connection."""
        self.connect_btn.configure(text="Disconnect")
        self.conn_status.configure(text="Connected", text_color="green")
        self._add_log_entry("Connected", "INFO")

    def _on_connect_failed(self, error: str) -> None:
        """Handle connection failure."""
        self.conn_status.configure(text=f"Failed: {error}", text_color="red")
        self._add_log_entry(f"Connection failed: {error}", "ERROR")

    def _send_command(self) -> None:
        """Send a command."""
        command = self.command_entry.get().strip()
        if not command:
            return

        ip = self._check_ip()
        if not ip:
            return

        port = self._get_port()

        def run():
            result = self._tester.send_command_simple(ip, port, command)
            self.after(0, lambda: self._display_command_result(result))

        threading.Thread(target=run, daemon=True).start()

    def _display_command_result(self, result) -> None:
        """Display command result."""
        if result.success:
            self._add_log_entry(f"TX: {result.command}", "TX")
            if result.response:
                self._add_log_entry(f"RX: {result.response}", "RX")
            self._add_log_entry(f"Time: {result.total_time_ms:.1f}ms", "INFO")
        else:
            self._add_log_entry(f"TX: {result.command}", "TX")
            self._add_log_entry(f"Error: {result.error}", "ERROR")

    def _add_log_entry(self, text: str, level: str) -> None:
        """Add entry to command log."""
        colors = {
            "TX": "#3498db",
            "RX": "#27ae60",
            "INFO": "gray60",
            "ERROR": "#e74c3c",
            "WARNING": "#f39c12"
        }

        entry = ctk.CTkLabel(
            self.results_scroll,
            text=text,
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=colors.get(level, "gray"),
            anchor="w"
        )
        entry.pack(anchor="w", padx=15, pady=1)

    def _run_burst_test(self) -> None:
        """Run burst command test."""
        ip = self._check_ip()
        if not ip:
            return

        command = self.command_entry.get().strip()
        if not command:
            self._add_log_entry("Enter a command first", "ERROR")
            return

        try:
            count = int(self.burst_count.get())
            delay = float(self.burst_delay.get())
        except ValueError:
            self._add_log_entry("Invalid count or delay value", "ERROR")
            return

        port = self._get_port()
        self.burst_btn.configure(state="disabled")

        def run():
            result = self._tester.burst_test(
                ip, port, command,
                count=count,
                delay_ms=delay,
                progress_callback=lambda c, t: self.after(
                    0, lambda: self._add_log_entry(f"Burst progress: {c}/{t}", "INFO")
                )
            )
            self.after(0, lambda: self._display_burst_result(result))
            self.after(0, lambda: self.burst_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _display_burst_result(self, result) -> None:
        """Display burst test results."""
        self._add_log_entry("=" * 50, "INFO")
        self._add_log_entry("BURST TEST RESULTS", "INFO")
        self._add_log_entry(f"Commands: {result.total_commands}", "INFO")
        self._add_log_entry(f"Successful: {result.successful_commands}", "INFO")
        self._add_log_entry(f"Failed: {result.failed_commands}", "INFO")
        self._add_log_entry(f"Error Rate: {result.error_rate_percent:.1f}%",
                          "ERROR" if result.error_rate_percent > 0 else "INFO")
        self._add_log_entry(f"Delay: {result.delay_between_ms}ms", "INFO")

        if result.avg_response_ms:
            self._add_log_entry(f"Avg Response: {result.avg_response_ms:.1f}ms", "INFO")
            self._add_log_entry(f"Min/Max: {result.min_response_ms:.1f}ms / {result.max_response_ms:.1f}ms", "INFO")

        if result.errors:
            self._add_log_entry("Errors:", "ERROR")
            for error in result.errors[:5]:
                self._add_log_entry(f"  {error}", "ERROR")

        self._add_log_entry("=" * 50, "INFO")

        # Add result card
        if result.error_rate_percent == 0:
            status = ResultStatus.PASSED
            msg = f"All {result.total_commands} commands successful"
        elif result.error_rate_percent < 10:
            status = ResultStatus.WARNING
            msg = f"{result.error_rate_percent:.1f}% error rate"
        else:
            status = ResultStatus.FAILED
            msg = f"{result.error_rate_percent:.1f}% error rate - COMMAND QUEUEING ISSUE"

        details = f"Delay: {result.delay_between_ms}ms\n" \
                 f"Successful: {result.successful_commands}/{result.total_commands}\n"
        if result.avg_response_ms:
            details += f"Avg Response: {result.avg_response_ms:.1f}ms"

        card = ResultCard(self.results_scroll, "Burst Test", status, msg, details)
        card.pack(fill="x", padx=5, pady=5)

    def _find_optimal_delay(self) -> None:
        """Find the optimal delay between commands."""
        ip = self._check_ip()
        if not ip:
            return

        command = self.command_entry.get().strip()
        if not command:
            self._add_log_entry("Enter a command first", "ERROR")
            return

        port = self._get_port()
        self.find_delay_btn.configure(state="disabled")

        def run():
            result = self._tester.find_optimal_delay(
                ip, port, command,
                delays_to_test=self.config.command_test_delays_ms,
                commands_per_test=10,
                progress_callback=lambda phase, c, t: self.after(
                    0, lambda: self._add_log_entry(phase, "INFO")
                )
            )
            self.after(0, lambda: self._display_optimal_delay_result(result))
            self.after(0, lambda: self.find_delay_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _display_optimal_delay_result(self, result) -> None:
        """Display optimal delay analysis."""
        self._add_log_entry("=" * 50, "INFO")
        self._add_log_entry("OPTIMAL DELAY ANALYSIS", "INFO")

        for test in result['tests']:
            status_icon = "✓" if test['error_rate_percent'] == 0 else "✗"
            self._add_log_entry(
                f"  {status_icon} {test['delay_ms']}ms delay: "
                f"{test['successful']}/{test['successful'] + test['failed']} "
                f"({test['error_rate_percent']:.1f}% errors)",
                "INFO" if test['error_rate_percent'] == 0 else "WARNING"
            )

        if result['recommended_delay_ms'] is not None:
            self._add_log_entry(
                f"RECOMMENDED DELAY: {result['recommended_delay_ms']}ms",
                "INFO"
            )

            # Update the delay entry
            self.burst_delay.delete(0, "end")
            self.burst_delay.insert(0, str(result['recommended_delay_ms']))
        else:
            self._add_log_entry(
                "No reliable delay found - device may have persistent issues",
                "ERROR"
            )

        self._add_log_entry("=" * 50, "INFO")

        # Summary card
        if result['all_passed']:
            status = ResultStatus.PASSED
            msg = "No delay needed - all tests passed at 0ms"
        elif result['recommended_delay_ms'] is not None:
            status = ResultStatus.WARNING
            msg = f"Recommended delay: {result['recommended_delay_ms']}ms"
        else:
            status = ResultStatus.FAILED
            msg = "Unable to find stable delay"

        card = ResultCard(
            self.results_scroll,
            "Optimal Delay Analysis",
            status,
            msg,
            "Try using the recommended delay between commands to avoid errors"
        )
        card.pack(fill="x", padx=5, pady=5)
