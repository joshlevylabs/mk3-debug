"""Firmware Verification dashboard frame - Maps test groups to JIRA tickets."""

import customtkinter as ctk
import threading
import json
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime
from pathlib import Path

from ...utils import get_logger, Config
from ..components import ResultCard
from ..components.result_card import ResultStatus

logger = get_logger(__name__)


# Color scheme consistent with main app
COLORS = {
    'sidebar_bg': "#1a1a2e",
    'sidebar_hover': "#16213e",
    'sidebar_selected': "#0f3460",
    'accent': "#4a9fd4",
    'success': "#27ae60",
    'warning': "#f39c12",
    'error': "#e74c3c",
    'text_primary': "#ffffff",
    'text_secondary': "#a0a0a0",
    'card_bg': "#16213e",
    'main_bg': "#0f0f1a",
}

FONT_FAMILY = "Montserrat"

# Test group definitions
TEST_GROUPS = [
    {
        'key': 'ip_stability',
        'name': 'IP Command Stability',
        'ticket': 'DSP3-136/134',
        'description': 'Verify IP command responses are stable across repeated queries',
        'type': 'automated',
        'color': '#4a9fd4',
    },
    {
        'key': 'dns_config',
        'name': 'DNS Configuration',
        'ticket': 'DSP3-145',
        'description': 'Verify DNS resolution and configuration persistence',
        'type': 'manual',
        'color': '#e67e22',
        'steps': [
            'Connect device to network with DNS server configured',
            'Set custom DNS server via web UI',
            'Verify DNS resolution using nslookup from device',
            'Reboot device and confirm DNS settings persist',
            'Test DNS fallback behavior when primary server is unreachable',
            'Verify mDNS/Bonjour advertisement is correct',
        ],
    },
    {
        'key': 'status_page',
        'name': 'Status Page Updates',
        'ticket': 'DSP3-135',
        'description': 'Verify status page reflects real-time device state changes',
        'type': 'automated',
        'color': '#3498db',
    },
    {
        'key': 'pink_noise',
        'name': 'Pink Noise',
        'ticket': 'DSP3-148',
        'description': 'Verify pink noise generator output across all channels',
        'type': 'manual',
        'color': '#9b59b6',
        'steps': [
            'Navigate to the Pink Noise generator page on web UI',
            'Enable pink noise on Channel 1 at -20 dBFS',
            'Confirm audible output on Channel 1 speaker',
            'Verify signal level on output meter matches expected',
            'Repeat for each subsequent output channel',
            'Disable pink noise and confirm all channels return to silence',
        ],
    },
    {
        'key': 'crossover_filters',
        'name': 'Crossover Filters',
        'ticket': 'DSP3-146',
        'description': 'Verify crossover filter settings apply correctly to audio path',
        'type': 'manual',
        'color': '#1abc9c',
        'steps': [
            'Load default crossover preset from factory settings',
            'Set high-pass filter to 80 Hz Butterworth 24dB/oct',
            'Set low-pass filter to 1200 Hz Linkwitz-Riley 48dB/oct',
            'Play swept sine wave and verify rolloff frequencies',
            'Change filter type to Bessel and confirm slope change',
            'Save configuration and reboot - verify filters persist',
        ],
    },
    {
        'key': 'config_import',
        'name': 'Config Import',
        'ticket': 'DSP3-147',
        'description': 'Verify configuration file import/export round-trip integrity',
        'type': 'manual',
        'color': '#f39c12',
        'steps': [
            'Export current device configuration to file',
            'Reset device to factory defaults',
            'Import the exported configuration file',
            'Verify all settings match original (EQ, routing, levels)',
            'Verify network settings restored correctly',
            'Test import of configuration from different firmware version',
        ],
    },
    {
        'key': 'sleep_reboot',
        'name': 'Sleep/Reboot Monitor',
        'ticket': 'New',
        'description': 'Monitor device through sleep/wake and reboot cycles for stability',
        'type': 'automated_long',
        'color': '#e74c3c',
    },
    {
        'key': 'http_stability',
        'name': 'HTTP Stability',
        'ticket': 'DSP3-150',
        'description': 'Long-running HTTP endpoint stability and response time monitoring',
        'type': 'automated_long',
        'color': '#27ae60',
    },
]


class ManualTestDialog(ctk.CTkToplevel):
    """Popup dialog for manual test checklists."""

    def __init__(
        self,
        master,
        test_name: str,
        ticket: str,
        steps: List[str],
        color: str,
        on_complete: Callable[[bool], None],
        **kwargs
    ):
        super().__init__(master, **kwargs)

        self.title(f"{test_name} - {ticket}")
        self.geometry("560x520")
        self.resizable(False, False)
        self.configure(fg_color=COLORS['main_bg'])
        self.transient(master)
        self.grab_set()

        self._steps = steps
        self._on_complete = on_complete
        self._check_vars: List[ctk.BooleanVar] = []

        self._build_ui(test_name, ticket, color)

        # Center on parent
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - 560) // 2
        y = master.winfo_rooty() + (master.winfo_height() - 520) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _build_ui(self, test_name: str, ticket: str, color: str) -> None:
        """Build the dialog UI."""
        # Header
        header_frame = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=0)
        header_frame.pack(fill="x", padx=0, pady=0)

        header_inner = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_inner.pack(fill="x", padx=20, pady=16)

        ctk.CTkLabel(
            header_inner,
            text=test_name,
            font=ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold"),
            text_color=COLORS['text_primary'],
            anchor="w",
        ).pack(anchor="w")

        # Ticket badge
        ticket_badge = ctk.CTkFrame(header_inner, fg_color=color, corner_radius=6)
        ticket_badge.pack(anchor="w", pady=(6, 0))

        ctk.CTkLabel(
            ticket_badge,
            text=ticket,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color="white",
        ).pack(padx=10, pady=3)

        # Steps checklist (scrollable)
        steps_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS['main_bg'],
            label_text="Test Steps",
            label_font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            label_fg_color=COLORS['card_bg'],
        )
        steps_scroll.pack(fill="both", expand=True, padx=16, pady=(12, 8))

        for i, step in enumerate(self._steps, 1):
            var = ctk.BooleanVar(value=False)
            self._check_vars.append(var)

            step_frame = ctk.CTkFrame(steps_scroll, fg_color=COLORS['card_bg'], corner_radius=8)
            step_frame.pack(fill="x", pady=3)

            cb = ctk.CTkCheckBox(
                step_frame,
                text=f"  Step {i}: {step}",
                variable=var,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                text_color=COLORS['text_primary'],
                fg_color=color,
                hover_color=color,
                command=self._on_check_changed,
                width=480,
            )
            cb.pack(anchor="w", padx=12, pady=8)

        # Bottom buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(4, 16))

        self._pass_btn = ctk.CTkButton(
            btn_frame,
            text="Mark as Passed",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=COLORS['success'],
            hover_color="#1e8449",
            state="disabled",
            width=160,
            command=lambda: self._finish(True),
        )
        self._pass_btn.pack(side="left", padx=(0, 8))

        self._fail_btn = ctk.CTkButton(
            btn_frame,
            text="Mark as Failed",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=COLORS['error'],
            hover_color="#c0392b",
            width=160,
            command=lambda: self._finish(False),
        )
        self._fail_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=COLORS['card_bg'],
            hover_color=COLORS['sidebar_hover'],
            width=100,
            command=self.destroy,
        ).pack(side="right")

    def _on_check_changed(self) -> None:
        """Enable pass button when all steps are checked."""
        all_checked = all(var.get() for var in self._check_vars)
        self._pass_btn.configure(state="normal" if all_checked else "disabled")

    def _finish(self, passed: bool) -> None:
        """Complete the manual test."""
        self._on_complete(passed)
        self.destroy()


class TestCard(ctk.CTkFrame):
    """A clickable test card for the verification grid."""

    def __init__(
        self,
        master,
        test_group: Dict[str, Any],
        on_run: Callable,
        on_stop: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(
            master,
            corner_radius=12,
            fg_color=COLORS['card_bg'],
            border_width=1,
            border_color="#2a2a4a",
            **kwargs,
        )

        self._test_group = test_group
        self._on_run = on_run
        self._on_stop = on_stop
        self._status = ResultStatus.PENDING
        self._is_long_running = test_group['type'] == 'automated_long'

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the test card UI."""
        tg = self._test_group
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="x", padx=16, pady=14)

        # Top row: status indicator + name + ticket badge
        top_row = ctk.CTkFrame(container, fg_color="transparent")
        top_row.pack(fill="x")

        # Status dot
        self._status_dot = ctk.CTkFrame(
            top_row, width=12, height=12, corner_radius=6,
            fg_color="#64748b",
        )
        self._status_dot.pack(side="left", pady=(4, 0))
        self._status_dot.pack_propagate(False)

        # Test name
        self._name_label = ctk.CTkLabel(
            top_row,
            text=tg['name'],
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLORS['text_primary'],
            anchor="w",
        )
        self._name_label.pack(side="left", padx=(10, 0))

        # Ticket badge
        ticket_badge = ctk.CTkFrame(top_row, fg_color=tg['color'], corner_radius=6)
        ticket_badge.pack(side="right")

        ctk.CTkLabel(
            ticket_badge,
            text=tg['ticket'],
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color="white",
        ).pack(padx=8, pady=2)

        # Description
        ctk.CTkLabel(
            container,
            text=tg['description'],
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLORS['text_secondary'],
            anchor="w",
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        # Type badge
        type_map = {
            'automated': ("Automated", COLORS['accent']),
            'manual': ("Manual", "#e67e22"),
            'automated_long': ("Automated (long)", COLORS['error']),
        }
        type_text, type_color = type_map.get(tg['type'], ("Unknown", "#666"))

        type_badge = ctk.CTkFrame(container, fg_color=type_color, corner_radius=4)
        type_badge.pack(anchor="w", pady=(8, 0))

        ctk.CTkLabel(
            type_badge,
            text=type_text,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            text_color="white",
        ).pack(padx=8, pady=2)

        # Status message
        self._status_label = ctk.CTkLabel(
            container,
            text="Pending",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#64748b",
            anchor="w",
        )
        self._status_label.pack(anchor="w", pady=(8, 0))

        # Button row
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))

        self._run_btn = ctk.CTkButton(
            btn_row,
            text="Run",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=tg['color'],
            hover_color=self._darken(tg['color']),
            width=90,
            height=32,
            command=self._on_run,
        )
        self._run_btn.pack(side="left")

        # Stop button for long-running tests (hidden initially)
        if self._is_long_running and self._on_stop:
            self._stop_btn = ctk.CTkButton(
                btn_row,
                text="Stop",
                font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
                fg_color=COLORS['error'],
                hover_color="#c0392b",
                width=80,
                height=32,
                command=self._on_stop,
            )
            # Not packed until running

        # Duration label
        self._duration_label = ctk.CTkLabel(
            btn_row,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLORS['text_secondary'],
        )
        self._duration_label.pack(side="right")

        # Expandable results area (hidden initially)
        self._results_frame = ctk.CTkFrame(
            container,
            fg_color="#0f172a",
            corner_radius=8,
            border_width=1,
            border_color="#2a2a4a",
        )
        # Not packed until results available

        self._results_text = ctk.CTkTextbox(
            self._results_frame,
            height=120,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word",
            fg_color="transparent",
            text_color="#cbd5e1",
            border_width=0,
        )
        self._results_text.pack(fill="both", expand=True, padx=10, pady=8)

    @staticmethod
    def _darken(hex_color: str, factor: float = 0.8) -> str:
        """Darken a hex color by a factor."""
        hex_color = hex_color.lstrip('#')
        r = max(0, int(int(hex_color[0:2], 16) * factor))
        g = max(0, int(int(hex_color[2:4], 16) * factor))
        b = max(0, int(int(hex_color[4:6], 16) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    def set_running(self, message: str = "Running...") -> None:
        """Set card to running state."""
        self._status = ResultStatus.RUNNING
        self._status_label.configure(text=message, text_color="#3b82f6")
        self._status_dot.configure(fg_color="#3b82f6")
        self._run_btn.configure(state="disabled")
        self.configure(border_color="#3b82f6")

        if self._is_long_running and hasattr(self, '_stop_btn'):
            self._stop_btn.pack(side="left", padx=(8, 0))

    def set_passed(self, message: str = "Passed", details: str = "",
                   duration_ms: Optional[float] = None) -> None:
        """Set card to passed state."""
        self._status = ResultStatus.PASSED
        self._status_label.configure(text=message, text_color=COLORS['success'])
        self._status_dot.configure(fg_color=COLORS['success'])
        self._run_btn.configure(state="normal")
        self.configure(border_color=COLORS['success'])

        if self._is_long_running and hasattr(self, '_stop_btn'):
            self._stop_btn.pack_forget()

        if duration_ms is not None:
            if duration_ms < 1000:
                self._duration_label.configure(text=f"{duration_ms:.0f}ms")
            else:
                self._duration_label.configure(text=f"{duration_ms / 1000:.1f}s")

        if details:
            self._show_results(details)

    def set_failed(self, message: str = "Failed", details: str = "",
                   duration_ms: Optional[float] = None) -> None:
        """Set card to failed state."""
        self._status = ResultStatus.FAILED
        self._status_label.configure(text=message, text_color=COLORS['error'])
        self._status_dot.configure(fg_color=COLORS['error'])
        self._run_btn.configure(state="normal")
        self.configure(border_color=COLORS['error'])

        if self._is_long_running and hasattr(self, '_stop_btn'):
            self._stop_btn.pack_forget()

        if duration_ms is not None:
            if duration_ms < 1000:
                self._duration_label.configure(text=f"{duration_ms:.0f}ms")
            else:
                self._duration_label.configure(text=f"{duration_ms / 1000:.1f}s")

        if details:
            self._show_results(details)

    def set_warning(self, message: str = "Warning", details: str = "") -> None:
        """Set card to warning state."""
        self._status = ResultStatus.WARNING
        self._status_label.configure(text=message, text_color=COLORS['warning'])
        self._status_dot.configure(fg_color=COLORS['warning'])
        self._run_btn.configure(state="normal")
        self.configure(border_color=COLORS['warning'])

        if details:
            self._show_results(details)

    def update_progress(self, message: str) -> None:
        """Update progress message for long-running tests."""
        self._status_label.configure(text=message)

    def reset(self) -> None:
        """Reset card to pending state."""
        self._status = ResultStatus.PENDING
        self._status_label.configure(text="Pending", text_color="#64748b")
        self._status_dot.configure(fg_color="#64748b")
        self._run_btn.configure(state="normal")
        self.configure(border_color="#2a2a4a")
        self._duration_label.configure(text="")
        self._results_frame.pack_forget()

        if self._is_long_running and hasattr(self, '_stop_btn'):
            self._stop_btn.pack_forget()

    def _show_results(self, details: str) -> None:
        """Show results in the expandable area."""
        self._results_text.configure(state="normal")
        self._results_text.delete("1.0", "end")
        self._results_text.insert("1.0", details)
        self._results_text.configure(state="disabled")
        self._results_frame.pack(fill="x", pady=(10, 0))

    @property
    def status(self) -> ResultStatus:
        """Get current status."""
        return self._status


class VerificationFrame(ctk.CTkFrame):
    """
    Frame for the Firmware Verification dashboard.
    Maps each test group from the verification plan to a clickable test card.
    """

    def __init__(
        self,
        master,
        config: Config,
        get_target_ip: Callable[[], Optional[str]],
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.config = config
        self._get_target_ip = get_target_ip
        self._stop_event = threading.Event()
        self._test_cards: Dict[str, TestCard] = {}
        self._test_results: Dict[str, Dict[str, Any]] = {}

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the verification dashboard UI."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        self._build_header()

        # Target controls
        self._build_target_controls()

        # Scrollable content area
        self._build_content()

    def _build_header(self) -> None:
        """Build the header section."""
        header = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=12)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        ctk.CTkLabel(
            inner,
            text="Firmware Verification",
            font=ctk.CTkFont(family=FONT_FAMILY, size=24, weight="bold"),
            text_color=COLORS['text_primary'],
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            inner,
            text="MK3 Firmware Verification Sweep \u2014 Tests map to JIRA tickets",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color=COLORS['text_secondary'],
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

    def _build_target_controls(self) -> None:
        """Build target IP and firmware/model selector controls."""
        controls = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=12)
        controls.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        inner = ctk.CTkFrame(controls, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=12)

        # IP entry
        ctk.CTkLabel(
            inner,
            text="Target IP:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLORS['text_primary'],
        ).pack(side="left")

        self._ip_entry = ctk.CTkEntry(
            inner,
            width=160,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            placeholder_text="e.g. 192.168.1.100",
        )
        self._ip_entry.pack(side="left", padx=(8, 20))

        # Firmware version selector
        ctk.CTkLabel(
            inner,
            text="Firmware:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLORS['text_primary'],
        ).pack(side="left")

        self._fw_selector = ctk.CTkComboBox(
            inner,
            values=["3.1.34", "3.1.37", "3.1.52"],
            width=120,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            state="readonly",
        )
        self._fw_selector.set("3.1.52")
        self._fw_selector.pack(side="left", padx=(8, 20))

        # Model selector
        ctk.CTkLabel(
            inner,
            text="Model:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLORS['text_primary'],
        ).pack(side="left")

        self._model_selector = ctk.CTkComboBox(
            inner,
            values=["DSP8-130", "DSP2-150", "DSP2-750"],
            width=130,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            state="readonly",
        )
        self._model_selector.set("DSP8-130")
        self._model_selector.pack(side="left", padx=(8, 0))

        # Progress label
        self._progress_label = ctk.CTkLabel(
            inner,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLORS['text_secondary'],
        )
        self._progress_label.pack(side="right")

    def _build_content(self) -> None:
        """Build the scrollable content area with test cards grid and bottom buttons."""
        content_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
        )
        content_scroll.grid(row=2, column=0, sticky="nsew", padx=10, pady=(5, 10))
        content_scroll.grid_columnconfigure(0, weight=1)
        content_scroll.grid_columnconfigure(1, weight=1)

        # Build test cards in a 2-column grid
        for idx, tg in enumerate(TEST_GROUPS):
            row = idx // 2
            col = idx % 2

            on_stop = None
            if tg['type'] == 'automated_long':
                on_stop = self._stop_long_running

            card = TestCard(
                content_scroll,
                test_group=tg,
                on_run=self._make_run_handler(tg),
                on_stop=on_stop,
            )
            card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
            self._test_cards[tg['key']] = card

        # Bottom section - spans both columns
        bottom_row = (len(TEST_GROUPS) + 1) // 2
        bottom_frame = ctk.CTkFrame(
            content_scroll,
            fg_color=COLORS['card_bg'],
            corner_radius=12,
        )
        bottom_frame.grid(
            row=bottom_row, column=0, columnspan=2,
            sticky="ew", padx=6, pady=(12, 6),
        )

        btn_inner = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        btn_inner.pack(fill="x", padx=20, pady=14)

        self._run_all_btn = ctk.CTkButton(
            btn_inner,
            text="Run All Automated Tests",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color=COLORS['accent'],
            hover_color="#3a8fc4",
            width=220,
            height=38,
            command=self._run_all_automated,
        )
        self._run_all_btn.pack(side="left")

        self._export_btn = ctk.CTkButton(
            btn_inner,
            text="Export Report",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color=COLORS['success'],
            hover_color="#1e8449",
            width=160,
            height=38,
            command=self._export_report,
        )
        self._export_btn.pack(side="left", padx=(12, 0))

        # Summary label
        self._summary_label = ctk.CTkLabel(
            btn_inner,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLORS['text_secondary'],
        )
        self._summary_label.pack(side="right")

    # ── Helpers ──────────────────────────────────────────────────────────

    def _get_ip(self) -> Optional[str]:
        """Get the target IP, preferring the local entry, then the app-level callback."""
        ip = self._ip_entry.get().strip()
        if ip:
            return ip
        ip = self._get_target_ip()
        if not ip:
            self._progress_label.configure(
                text="No target IP set!", text_color=COLORS['error']
            )
        return ip

    def _make_run_handler(self, tg: Dict[str, Any]) -> Callable:
        """Create a run handler closure for a test group."""
        key = tg['key']
        test_type = tg['type']

        if test_type == 'automated':
            handler_map = {
                'ip_stability': self._run_ip_stability_test,
                'status_page': self._run_status_page_test,
            }
            return handler_map.get(key, lambda: None)

        elif test_type == 'manual':
            return lambda: self._open_manual_dialog(tg)

        elif test_type == 'automated_long':
            handler_map = {
                'sleep_reboot': self._run_sleep_reboot_test,
                'http_stability': self._run_http_stability_test,
            }
            return handler_map.get(key, lambda: None)

        return lambda: None

    def _stop_long_running(self) -> None:
        """Signal long-running tests to stop."""
        self._stop_event.set()
        self._progress_label.configure(
            text="Stopping...", text_color=COLORS['warning']
        )

    # ── Automated test runners ──────────────────────────────────────────

    def _run_ip_stability_test(self) -> None:
        """Run IP Command Stability test (DSP3-136/134)."""
        ip = self._get_ip()
        if not ip:
            return

        card = self._test_cards['ip_stability']
        card.set_running("Testing IP command stability...")
        self._progress_label.configure(
            text="Running: IP Command Stability", text_color=COLORS['accent']
        )

        def run():
            try:
                from ...network.verification import IPCommandStabilityTest
                test = IPCommandStabilityTest(ip)
                result = test.run()
                self.after(0, lambda: self._on_test_complete('ip_stability', result))
            except ImportError as e:
                logger.error(f"Import error: {e}")
                self.after(0, lambda: self._on_test_error(
                    'ip_stability',
                    f"verification module not found: {e}"
                ))
            except Exception as e:
                logger.error(f"IP stability test error: {e}")
                self.after(0, lambda: self._on_test_error('ip_stability', str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _run_status_page_test(self) -> None:
        """Run Status Page Updates test (DSP3-135)."""
        ip = self._get_ip()
        if not ip:
            return

        card = self._test_cards['status_page']
        card.set_running("Checking status page updates...")
        self._progress_label.configure(
            text="Running: Status Page Updates", text_color=COLORS['accent']
        )

        def run():
            try:
                from ...network.verification import StatusPageVerifier
                test = StatusPageVerifier(ip)
                result = test.run()
                self.after(0, lambda: self._on_test_complete('status_page', result))
            except ImportError as e:
                logger.error(f"Import error: {e}")
                self.after(0, lambda: self._on_test_error(
                    'status_page',
                    f"verification module not found: {e}"
                ))
            except Exception as e:
                logger.error(f"Status page test error: {e}")
                self.after(0, lambda: self._on_test_error('status_page', str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _run_sleep_reboot_test(self) -> None:
        """Run Sleep/Reboot Monitor test (long-running)."""
        ip = self._get_ip()
        if not ip:
            return

        self._stop_event.clear()
        card = self._test_cards['sleep_reboot']
        card.set_running("Monitoring sleep/reboot cycles...")
        self._progress_label.configure(
            text="Running: Sleep/Reboot Monitor (long-running)", text_color=COLORS['error']
        )

        def progress_cb(msg, current, total):
            self.after(0, lambda m=msg: self._progress_label.configure(
                text=f"Sleep/Reboot Monitor: {m}"
            ))

        def run():
            try:
                from ...network.verification import RebootDetector
                test = RebootDetector(
                    ip,
                    duration_sec=3600,
                    progress_callback=progress_cb,
                    stop_event=self._stop_event,
                )
                result = test.run()
                self.after(0, lambda: self._on_test_complete('sleep_reboot', result))
            except ImportError as e:
                logger.error(f"Import error: {e}")
                self.after(0, lambda: self._on_test_error(
                    'sleep_reboot',
                    f"verification module not found: {e}"
                ))
            except Exception as e:
                logger.error(f"Sleep/reboot test error: {e}")
                self.after(0, lambda: self._on_test_error('sleep_reboot', str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _run_http_stability_test(self) -> None:
        """Run HTTP Stability test (DSP3-150, long-running)."""
        ip = self._get_ip()
        if not ip:
            return

        self._stop_event.clear()
        card = self._test_cards['http_stability']
        card.set_running("Monitoring HTTP endpoint stability...")
        self._progress_label.configure(
            text="Running: HTTP Stability (long-running)", text_color=COLORS['success']
        )

        def progress_cb(msg, current, total):
            self.after(0, lambda m=msg: self._progress_label.configure(
                text=f"HTTP Stability: {m}"
            ))

        def run():
            try:
                from ...network.verification import HTTPStabilityMonitor
                test = HTTPStabilityMonitor(
                    ip,
                    duration_sec=1800,
                    progress_callback=progress_cb,
                    stop_event=self._stop_event,
                )
                result = test.run()
                self.after(0, lambda: self._on_test_complete('http_stability', result))
            except ImportError as e:
                logger.error(f"Import error: {e}")
                self.after(0, lambda: self._on_test_error(
                    'http_stability',
                    f"verification module not found: {e}"
                ))
            except Exception as e:
                logger.error(f"HTTP stability test error: {e}")
                self.after(0, lambda: self._on_test_error('http_stability', str(e)))

        threading.Thread(target=run, daemon=True).start()

    # ── Manual test dialog ──────────────────────────────────────────────

    def _open_manual_dialog(self, tg: Dict[str, Any]) -> None:
        """Open a manual test checklist dialog."""
        key = tg['key']
        card = self._test_cards[key]
        card.set_running("Awaiting manual verification...")

        def on_complete(passed: bool):
            if passed:
                card.set_passed("Manually verified - PASSED")
                self._test_results[key] = {
                    'status': 'passed',
                    'message': 'Manually verified',
                    'timestamp': datetime.now().isoformat(),
                }
            else:
                card.set_failed("Manually verified - FAILED")
                self._test_results[key] = {
                    'status': 'failed',
                    'message': 'Manually marked as failed',
                    'timestamp': datetime.now().isoformat(),
                }
            self._update_summary()

        ManualTestDialog(
            self,
            test_name=tg['name'],
            ticket=tg['ticket'],
            steps=tg.get('steps', []),
            color=tg['color'],
            on_complete=on_complete,
        )

    # ── Test completion handlers ────────────────────────────────────────

    def _on_test_complete(self, key: str, result: Any) -> None:
        """Handle automated test completion."""
        card = self._test_cards[key]

        passed = getattr(result, 'passed', False)
        message = getattr(result, 'message', str(result))
        details = getattr(result, 'details', '')
        duration_ms = getattr(result, 'duration_ms', None)

        if passed:
            card.set_passed(message, details, duration_ms)
        else:
            card.set_failed(message, details, duration_ms)

        self._test_results[key] = {
            'status': 'passed' if passed else 'failed',
            'message': message,
            'details': details,
            'duration_ms': duration_ms,
            'timestamp': datetime.now().isoformat(),
        }

        self._progress_label.configure(
            text=f"Completed: {key}", text_color=COLORS['text_secondary']
        )
        self._update_summary()

    def _on_test_error(self, key: str, error_msg: str) -> None:
        """Handle test error."""
        card = self._test_cards[key]
        card.set_failed(f"Error: {error_msg}")

        self._test_results[key] = {
            'status': 'error',
            'message': error_msg,
            'timestamp': datetime.now().isoformat(),
        }

        self._progress_label.configure(
            text=f"Error in {key}", text_color=COLORS['error']
        )
        self._update_summary()

    def _update_summary(self) -> None:
        """Update the summary label with current test status counts."""
        total = len(TEST_GROUPS)
        completed = len(self._test_results)
        passed = sum(1 for r in self._test_results.values() if r.get('status') == 'passed')
        failed = sum(1 for r in self._test_results.values() if r.get('status') in ('failed', 'error'))

        self._summary_label.configure(
            text=f"{completed}/{total} complete  |  {passed} passed  |  {failed} failed"
        )

    # ── Run All Automated ───────────────────────────────────────────────

    def _run_all_automated(self) -> None:
        """Run all automated (non-long-running) tests sequentially."""
        ip = self._get_ip()
        if not ip:
            return

        self._run_all_btn.configure(state="disabled")
        self._progress_label.configure(
            text="Running all automated tests...", text_color=COLORS['accent']
        )

        automated_keys = [
            tg['key'] for tg in TEST_GROUPS if tg['type'] == 'automated'
        ]

        def run():
            for key in automated_keys:
                card = self._test_cards[key]
                self.after(0, lambda c=card: c.set_running("Running..."))

                try:
                    test_class = self._get_test_class(key)
                    if test_class is None:
                        self.after(0, lambda k=key: self._on_test_error(
                            k, "verification module not found"
                        ))
                        continue

                    test = test_class()
                    result = test.run(ip)
                    self.after(0, lambda k=key, r=result: self._on_test_complete(k, r))

                except Exception as e:
                    logger.error(f"Error running {key}: {e}")
                    self.after(0, lambda k=key, err=str(e): self._on_test_error(k, err))

            self.after(0, lambda: self._run_all_btn.configure(state="normal"))
            self.after(0, lambda: self._progress_label.configure(
                text="All automated tests complete", text_color=COLORS['success']
            ))

        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def _get_test_class(key: str):
        """Dynamically import and return the test class for a given key."""
        class_map = {
            'ip_stability': 'IPCommandStabilityTest',
            'status_page': 'StatusPageUpdatesTest',
        }
        class_name = class_map.get(key)
        if not class_name:
            return None

        try:
            from ...network import verification as ver_mod
            return getattr(ver_mod, class_name, None)
        except ImportError:
            return None

    # ── Export Report ───────────────────────────────────────────────────

    def _export_report(self) -> None:
        """Export verification results to a JSON report file."""
        if not self._test_results:
            self._progress_label.configure(
                text="No results to export", text_color=COLORS['warning']
            )
            return

        report = {
            'title': 'MK3 Firmware Verification Report',
            'generated': datetime.now().isoformat(),
            'firmware_version': self._fw_selector.get(),
            'model': self._model_selector.get(),
            'target_ip': self._ip_entry.get().strip() or self._get_target_ip() or "N/A",
            'tests': {},
        }

        for tg in TEST_GROUPS:
            key = tg['key']
            result = self._test_results.get(key, {'status': 'not_run'})
            report['tests'][key] = {
                'name': tg['name'],
                'ticket': tg['ticket'],
                'type': tg['type'],
                **result,
            }

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fw_ver = self._fw_selector.get().replace('.', '_')
        filename = f"verification_report_{fw_ver}_{timestamp}.json"

        try:
            output_path = Path.cwd() / filename
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            self._progress_label.configure(
                text=f"Report saved: {filename}", text_color=COLORS['success']
            )
            logger.info(f"Verification report exported to {output_path}")

        except Exception as e:
            logger.error(f"Failed to export report: {e}")
            self._progress_label.configure(
                text=f"Export failed: {e}", text_color=COLORS['error']
            )
