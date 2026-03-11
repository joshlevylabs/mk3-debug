"""Firmware Verification dashboard frame — integrates with sonance-beta.info firmware API."""

import customtkinter as ctk
import threading
import json
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime
from pathlib import Path

from ...utils import get_logger, Config
from ...network.firmware_api import (
    FirmwareAPIClient,
    FirmwareInfo,
    HardwareModel,
    APIError,
    fetch_async,
)
from ...network.firmware_updater import FirmwareUpdater, update_firmware_async
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
    'channel_stable': "#22c55e",
    'channel_beta': "#f59e0b",
    'channel_alpha': "#ef4444",
}

FONT_FAMILY = "Montserrat"

# Test group definitions mapped to JIRA tickets
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

        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - 560) // 2
        y = master.winfo_rooty() + (master.winfo_height() - 520) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _build_ui(self, test_name: str, ticket: str, color: str) -> None:
        header_frame = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=0)
        header_frame.pack(fill="x")

        header_inner = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_inner.pack(fill="x", padx=20, pady=16)

        ctk.CTkLabel(
            header_inner, text=test_name,
            font=ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold"),
            text_color=COLORS['text_primary'], anchor="w",
        ).pack(anchor="w")

        ticket_badge = ctk.CTkFrame(header_inner, fg_color=color, corner_radius=6)
        ticket_badge.pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(
            ticket_badge, text=ticket,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            text_color="white",
        ).pack(padx=10, pady=3)

        steps_scroll = ctk.CTkScrollableFrame(
            self, fg_color=COLORS['main_bg'],
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
            ctk.CTkCheckBox(
                step_frame, text=f"  Step {i}: {step}", variable=var,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                text_color=COLORS['text_primary'], fg_color=color, hover_color=color,
                command=self._on_check_changed, width=480,
            ).pack(anchor="w", padx=12, pady=8)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(4, 16))

        self._pass_btn = ctk.CTkButton(
            btn_frame, text="Mark as Passed",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=COLORS['success'], hover_color="#1e8449",
            state="disabled", width=160, command=lambda: self._finish(True),
        )
        self._pass_btn.pack(side="left", padx=(0, 8))

        self._fail_btn = ctk.CTkButton(
            btn_frame, text="Mark as Failed",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=COLORS['error'], hover_color="#c0392b",
            width=160, command=lambda: self._finish(False),
        )
        self._fail_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Cancel",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            fg_color=COLORS['card_bg'], hover_color=COLORS['sidebar_hover'],
            width=100, command=self.destroy,
        ).pack(side="right")

    def _on_check_changed(self) -> None:
        all_checked = all(var.get() for var in self._check_vars)
        self._pass_btn.configure(state="normal" if all_checked else "disabled")

    def _finish(self, passed: bool) -> None:
        self._on_complete(passed)
        self.destroy()


class TestCard(ctk.CTkFrame):
    """A clickable test card for the verification grid."""

    def __init__(self, master, test_group: Dict[str, Any], on_run: Callable,
                 on_stop: Optional[Callable] = None, **kwargs):
        super().__init__(
            master, corner_radius=12, fg_color=COLORS['card_bg'],
            border_width=1, border_color="#2a2a4a", **kwargs,
        )
        self._test_group = test_group
        self._on_run = on_run
        self._on_stop = on_stop
        self._status = ResultStatus.PENDING
        self._is_long_running = test_group['type'] == 'automated_long'
        self._build_ui()

    def _build_ui(self) -> None:
        tg = self._test_group
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="x", padx=16, pady=14)

        top_row = ctk.CTkFrame(container, fg_color="transparent")
        top_row.pack(fill="x")

        self._status_dot = ctk.CTkFrame(
            top_row, width=12, height=12, corner_radius=6, fg_color="#64748b",
        )
        self._status_dot.pack(side="left", pady=(4, 0))
        self._status_dot.pack_propagate(False)

        self._name_label = ctk.CTkLabel(
            top_row, text=tg['name'],
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            text_color=COLORS['text_primary'], anchor="w",
        )
        self._name_label.pack(side="left", padx=(10, 0))

        ticket_badge = ctk.CTkFrame(top_row, fg_color=tg['color'], corner_radius=6)
        ticket_badge.pack(side="right")
        ctk.CTkLabel(
            ticket_badge, text=tg['ticket'],
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color="white",
        ).pack(padx=8, pady=2)

        ctk.CTkLabel(
            container, text=tg['description'],
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLORS['text_secondary'], anchor="w",
            wraplength=380, justify="left",
        ).pack(anchor="w", pady=(6, 0))

        type_map = {
            'automated': ("Automated", COLORS['accent']),
            'manual': ("Manual", "#e67e22"),
            'automated_long': ("Automated (long)", COLORS['error']),
        }
        type_text, type_color = type_map.get(tg['type'], ("Unknown", "#666"))
        type_badge = ctk.CTkFrame(container, fg_color=type_color, corner_radius=4)
        type_badge.pack(anchor="w", pady=(8, 0))
        ctk.CTkLabel(
            type_badge, text=type_text,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10), text_color="white",
        ).pack(padx=8, pady=2)

        self._status_label = ctk.CTkLabel(
            container, text="Pending",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#64748b", anchor="w",
        )
        self._status_label.pack(anchor="w", pady=(8, 0))

        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))

        self._run_btn = ctk.CTkButton(
            btn_row, text="Run",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            fg_color=tg['color'], hover_color=self._darken(tg['color']),
            width=90, height=32, command=self._on_run,
        )
        self._run_btn.pack(side="left")

        if self._is_long_running and self._on_stop:
            self._stop_btn = ctk.CTkButton(
                btn_row, text="Stop",
                font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
                fg_color=COLORS['error'], hover_color="#c0392b",
                width=80, height=32, command=self._on_stop,
            )

        self._duration_label = ctk.CTkLabel(
            btn_row, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLORS['text_secondary'],
        )
        self._duration_label.pack(side="right")

        self._results_frame = ctk.CTkFrame(
            container, fg_color="#0f172a", corner_radius=8,
            border_width=1, border_color="#2a2a4a",
        )
        self._results_text = ctk.CTkTextbox(
            self._results_frame, height=120,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word", fg_color="transparent", text_color="#cbd5e1", border_width=0,
        )
        self._results_text.pack(fill="both", expand=True, padx=10, pady=8)

    @staticmethod
    def _darken(hex_color: str, factor: float = 0.8) -> str:
        hex_color = hex_color.lstrip('#')
        r = max(0, int(int(hex_color[0:2], 16) * factor))
        g = max(0, int(int(hex_color[2:4], 16) * factor))
        b = max(0, int(int(hex_color[4:6], 16) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    def set_running(self, message: str = "Running...") -> None:
        self._status = ResultStatus.RUNNING
        self._status_label.configure(text=message, text_color="#3b82f6")
        self._status_dot.configure(fg_color="#3b82f6")
        self._run_btn.configure(state="disabled")
        self.configure(border_color="#3b82f6")
        if self._is_long_running and hasattr(self, '_stop_btn'):
            self._stop_btn.pack(side="left", padx=(8, 0))

    def set_passed(self, message: str = "Passed", details: str = "",
                   duration_ms: Optional[float] = None) -> None:
        self._status = ResultStatus.PASSED
        self._status_label.configure(text=message, text_color=COLORS['success'])
        self._status_dot.configure(fg_color=COLORS['success'])
        self._run_btn.configure(state="normal")
        self.configure(border_color=COLORS['success'])
        if self._is_long_running and hasattr(self, '_stop_btn'):
            self._stop_btn.pack_forget()
        if duration_ms is not None:
            txt = f"{duration_ms:.0f}ms" if duration_ms < 1000 else f"{duration_ms / 1000:.1f}s"
            self._duration_label.configure(text=txt)
        if details:
            self._show_results(details)

    def set_failed(self, message: str = "Failed", details: str = "",
                   duration_ms: Optional[float] = None) -> None:
        self._status = ResultStatus.FAILED
        self._status_label.configure(text=message, text_color=COLORS['error'])
        self._status_dot.configure(fg_color=COLORS['error'])
        self._run_btn.configure(state="normal")
        self.configure(border_color=COLORS['error'])
        if self._is_long_running and hasattr(self, '_stop_btn'):
            self._stop_btn.pack_forget()
        if duration_ms is not None:
            txt = f"{duration_ms:.0f}ms" if duration_ms < 1000 else f"{duration_ms / 1000:.1f}s"
            self._duration_label.configure(text=txt)
        if details:
            self._show_results(details)

    def set_warning(self, message: str = "Warning", details: str = "") -> None:
        self._status = ResultStatus.WARNING
        self._status_label.configure(text=message, text_color=COLORS['warning'])
        self._status_dot.configure(fg_color=COLORS['warning'])
        self._run_btn.configure(state="normal")
        self.configure(border_color=COLORS['warning'])
        if details:
            self._show_results(details)

    def update_progress(self, message: str) -> None:
        self._status_label.configure(text=message)

    def reset(self) -> None:
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
        self._results_text.configure(state="normal")
        self._results_text.delete("1.0", "end")
        self._results_text.insert("1.0", details)
        self._results_text.configure(state="disabled")
        self._results_frame.pack(fill="x", pady=(10, 0))

    @property
    def status(self) -> ResultStatus:
        return self._status


# ── Firmware device row widget ─────────────────────────────────────────

class DeviceFirmwareRow(ctk.CTkFrame):
    """A row showing one discovered device with its firmware status."""

    def __init__(self, master, device_ip: str, model_name: str,
                 installed_version: str, **kwargs):
        super().__init__(master, fg_color=COLORS['card_bg'], corner_radius=10,
                         border_width=1, border_color="#2a2a4a", **kwargs)
        self.device_ip = device_ip
        self.model_name = model_name
        self.installed_version = installed_version

        self._latest_stable: Optional[FirmwareInfo] = None
        self._latest_beta: Optional[FirmwareInfo] = None
        self._latest_alpha: Optional[FirmwareInfo] = None

        self._build_ui()

    def _build_ui(self) -> None:
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="x", padx=16, pady=10)

        # Left: device info
        left = ctk.CTkFrame(container, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)

        # Row 1: IP + model
        row1 = ctk.CTkFrame(left, fg_color="transparent")
        row1.pack(fill="x")

        ctk.CTkLabel(
            row1, text=self.device_ip,
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            text_color=COLORS['text_primary'],
        ).pack(side="left")

        model_badge = ctk.CTkFrame(row1, fg_color=COLORS['accent'], corner_radius=6)
        model_badge.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(
            model_badge, text=self.model_name,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color="white",
        ).pack(padx=8, pady=2)

        # Row 2: installed version
        row2 = ctk.CTkFrame(left, fg_color="transparent")
        row2.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(
            row2, text="Installed:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLORS['text_secondary'],
        ).pack(side="left")

        self._installed_label = ctk.CTkLabel(
            row2, text=f"v{self.installed_version}",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color=COLORS['text_primary'],
        )
        self._installed_label.pack(side="left", padx=(6, 0))

        self._update_badge = ctk.CTkFrame(row2, fg_color="transparent", corner_radius=6)
        self._update_badge.pack(side="left", padx=(10, 0))

        self._update_label = ctk.CTkLabel(
            self._update_badge, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color="white",
        )
        self._update_label.pack(padx=8, pady=2)

        # Right: version columns (stable / beta / alpha)
        right = ctk.CTkFrame(container, fg_color="transparent")
        right.pack(side="right")

        self._channel_labels: Dict[str, ctk.CTkLabel] = {}
        for channel, color in [("stable", COLORS['channel_stable']),
                               ("beta", COLORS['channel_beta']),
                               ("alpha", COLORS['channel_alpha'])]:
            col = ctk.CTkFrame(right, fg_color="transparent")
            col.pack(side="left", padx=(12, 0))

            ctk.CTkLabel(
                col, text=channel.upper(),
                font=ctk.CTkFont(family=FONT_FAMILY, size=9, weight="bold"),
                text_color=color,
            ).pack()

            lbl = ctk.CTkLabel(
                col, text="--",
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color=COLORS['text_secondary'],
            )
            lbl.pack()
            self._channel_labels[channel] = lbl

    def set_channel_version(self, channel: str, firmware: Optional[FirmwareInfo]) -> None:
        """Update the displayed version for a channel."""
        if channel == "stable":
            self._latest_stable = firmware
        elif channel == "beta":
            self._latest_beta = firmware
        elif channel == "alpha":
            self._latest_alpha = firmware

        lbl = self._channel_labels.get(channel)
        if lbl and firmware:
            lbl.configure(text=f"v{firmware.version}", text_color=COLORS['text_primary'])

        # Update the update badge based on stable channel
        if channel == "stable" and firmware:
            try:
                installed_t = tuple(int(x) for x in self.installed_version.split(".") if x.isdigit())
                latest_t = firmware.version_tuple
                if latest_t > installed_t:
                    self._update_badge.configure(fg_color=COLORS['warning'])
                    self._update_label.configure(text=f"Update available: v{firmware.version}")
                else:
                    self._update_badge.configure(fg_color=COLORS['success'])
                    self._update_label.configure(text="Up to date")
            except (ValueError, TypeError):
                pass

    @property
    def latest_stable(self) -> Optional[FirmwareInfo]:
        return self._latest_stable


# ── Firmware version browser widget ────────────────────────────────────

class FirmwareVersionCard(ctk.CTkFrame):
    """Shows details for a single firmware version with optional install button."""

    def __init__(self, master, firmware: FirmwareInfo,
                 on_install: Optional[Callable] = None, **kwargs):
        super().__init__(master, fg_color="#1e293b", corner_radius=8,
                         border_width=1, border_color="#334155", height=60, **kwargs)
        self._firmware = firmware
        self._on_install = on_install
        self._build_ui()

    def _build_ui(self) -> None:
        fw = self._firmware
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="x", padx=12, pady=8)

        # Row 1: version + channel badge + status + install button
        row1 = ctk.CTkFrame(container, fg_color="transparent")
        row1.pack(fill="x")

        ctk.CTkLabel(
            row1, text=f"v{fw.version}",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color=COLORS['text_primary'],
        ).pack(side="left")

        ch_color = fw.channel_badge_color
        ch_badge = ctk.CTkFrame(row1, fg_color=ch_color, corner_radius=4)
        ch_badge.pack(side="left", padx=(8, 0))
        ctk.CTkLabel(
            ch_badge, text=fw.channel.upper(),
            font=ctk.CTkFont(family=FONT_FAMILY, size=9, weight="bold"),
            text_color="white",
        ).pack(padx=6, pady=1)

        if fw.is_channel_current:
            cur_badge = ctk.CTkFrame(row1, fg_color="#6366f1", corner_radius=4)
            cur_badge.pack(side="left", padx=(6, 0))
            ctk.CTkLabel(
                cur_badge, text="CURRENT",
                font=ctk.CTkFont(family=FONT_FAMILY, size=9, weight="bold"),
                text_color="white",
            ).pack(padx=6, pady=1)

        # Install button on the right
        if self._on_install:
            self._install_btn = ctk.CTkButton(
                row1, text="Install",
                font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                fg_color="#6366f1", hover_color="#4f46e5",
                width=70, height=24,
                command=lambda: self._on_install(fw),
            )
            self._install_btn.pack(side="right", padx=(8, 0))

        # Status on the right
        status_color = COLORS['success'] if fw.status == "released" else COLORS['text_secondary']
        ctk.CTkLabel(
            row1, text=fw.status,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10),
            text_color=status_color,
        ).pack(side="right")

        # Row 2: name, file info
        if fw.name:
            ctk.CTkLabel(
                container, text=fw.name,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11),
                text_color=COLORS['text_secondary'], anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        details = []
        if fw.file_name:
            details.append(fw.file_name)
        if fw.file_size:
            size_mb = fw.file_size / (1024 * 1024)
            details.append(f"{size_mb:.1f} MB")
        if fw.released_at:
            details.append(f"Released: {fw.released_at[:10]}")

        if details:
            ctk.CTkLabel(
                container, text="  |  ".join(details),
                font=ctk.CTkFont(family="Consolas", size=10),
                text_color="#64748b", anchor="w",
            ).pack(anchor="w", pady=(2, 0))


# ══════════════════════════════════════════════════════════════════════════
# Main Verification Frame
# ══════════════════════════════════════════════════════════════════════════

class VerificationFrame(ctk.CTkFrame):
    """
    Firmware Verification dashboard integrating the sonance-beta.info API.

    Sections:
      1. Header
      2. API key config bar
      3. Device + Firmware Status (discovered devices with installed vs latest)
      4. Available Firmware Versions browser
      5. Test verification matrix (existing test cards)
    """

    def __init__(self, master, config: Config,
                 get_target_ip: Callable[[], Optional[str]], **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.config = config
        self._get_target_ip = get_target_ip
        self._stop_event = threading.Event()
        self._test_cards: Dict[str, TestCard] = {}
        self._test_results: Dict[str, Dict[str, Any]] = {}
        self._device_rows: Dict[str, DeviceFirmwareRow] = {}

        # Firmware API client
        self._api = FirmwareAPIClient(api_key=config.firmware_api_key)
        self._updater = FirmwareUpdater(self._api)
        self._hardware_models: List[HardwareModel] = []
        self._firmware_list: List[FirmwareInfo] = []

        self._build_ui()

        # Auto-load if API key is already configured
        if self._api.has_api_key:
            self.after(500, self._refresh_firmware_data)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)  # scrollable content gets the stretch

        self._build_header()           # row 0
        self._build_api_key_bar()      # row 1
        self._build_device_panel()     # row 2
        self._build_firmware_browser() # row 3
        self._build_test_content()     # row 4

    # ── 1. Header ──────────────────────────────────────────────────────

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=12)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        ctk.CTkLabel(
            inner, text="Firmware Verification",
            font=ctk.CTkFont(family=FONT_FAMILY, size=24, weight="bold"),
            text_color=COLORS['text_primary'], anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            inner,
            text="Device firmware status, available updates, and verification test matrix",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
            text_color=COLORS['text_secondary'], anchor="w",
        ).pack(anchor="w", pady=(4, 0))

    # ── 2. API Key config bar ──────────────────────────────────────────

    def _build_api_key_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=12)
        bar.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            inner, text="Firmware API Key:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLORS['text_primary'],
        ).pack(side="left")

        self._api_key_entry = ctk.CTkEntry(
            inner, width=320, show="*",
            font=ctk.CTkFont(family="Consolas", size=12),
            placeholder_text="Paste your sonance-beta.info API key",
        )
        self._api_key_entry.pack(side="left", padx=(8, 0))

        # Pre-fill if saved
        if self.config.firmware_api_key:
            self._api_key_entry.insert(0, self.config.firmware_api_key)

        self._api_key_toggle = ctk.CTkButton(
            inner, text="Show", width=50, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            fg_color="#334155", hover_color="#475569",
            command=self._toggle_api_key_visibility,
        )
        self._api_key_toggle.pack(side="left", padx=(4, 0))

        self._connect_btn = ctk.CTkButton(
            inner, text="Connect & Refresh",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=COLORS['accent'], hover_color="#3a8fc4",
            width=150, height=30,
            command=self._on_connect,
        )
        self._connect_btn.pack(side="left", padx=(12, 0))

        self._api_status_label = ctk.CTkLabel(
            inner, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLORS['text_secondary'],
        )
        self._api_status_label.pack(side="right")

    def _toggle_api_key_visibility(self) -> None:
        current = self._api_key_entry.cget("show")
        if current == "*":
            self._api_key_entry.configure(show="")
            self._api_key_toggle.configure(text="Hide")
        else:
            self._api_key_entry.configure(show="*")
            self._api_key_toggle.configure(text="Show")

    def _on_connect(self) -> None:
        key = self._api_key_entry.get().strip()
        if not key:
            self._api_status_label.configure(
                text="Enter an API key first", text_color=COLORS['warning']
            )
            return

        # Save to config
        self.config.firmware_api_key = key
        self.config.save()

        self._api.set_api_key(key)
        self._api_status_label.configure(
            text="Connecting...", text_color=COLORS['accent']
        )
        self._connect_btn.configure(state="disabled")
        self._refresh_firmware_data()

    # ── 3. Device + Firmware Status panel ──────────────────────────────

    def _build_device_panel(self) -> None:
        panel = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=12)
        panel.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        inner = ctk.CTkFrame(panel, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=12)

        # Section header
        header_row = ctk.CTkFrame(inner, fg_color="transparent")
        header_row.pack(fill="x")

        ctk.CTkLabel(
            header_row, text="Network Devices",
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            text_color=COLORS['text_primary'], anchor="w",
        ).pack(side="left")

        # Target IP + Add button
        ctk.CTkLabel(
            header_row, text="Target IP:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLORS['text_secondary'],
        ).pack(side="left", padx=(20, 0))

        self._ip_entry = ctk.CTkEntry(
            header_row, width=160,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            placeholder_text="e.g. 192.168.1.100",
        )
        self._ip_entry.pack(side="left", padx=(8, 0))

        self._add_device_btn = ctk.CTkButton(
            header_row, text="Add Device",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            fg_color=COLORS['accent'], hover_color="#3a8fc4",
            width=110, height=28,
            command=self._add_device_from_ip,
        )
        self._add_device_btn.pack(side="left", padx=(8, 0))

        # Channel legend on right
        legend = ctk.CTkFrame(header_row, fg_color="transparent")
        legend.pack(side="right")
        for ch, color in [("STABLE", COLORS['channel_stable']),
                          ("BETA", COLORS['channel_beta']),
                          ("ALPHA", COLORS['channel_alpha'])]:
            dot = ctk.CTkFrame(legend, width=8, height=8, corner_radius=4, fg_color=color)
            dot.pack(side="left", padx=(8, 2))
            dot.pack_propagate(False)
            ctk.CTkLabel(
                legend, text=ch,
                font=ctk.CTkFont(family=FONT_FAMILY, size=9),
                text_color=color,
            ).pack(side="left")

        # Device rows container
        self._devices_container = ctk.CTkFrame(inner, fg_color="transparent")
        self._devices_container.pack(fill="x", pady=(8, 0))

        self._no_devices_label = ctk.CTkLabel(
            self._devices_container,
            text="No devices added yet. Enter a target IP above or select one from the Discovery tab.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#64748b",
        )
        self._no_devices_label.pack(pady=8)

    def _add_device_from_ip(self) -> None:
        ip = self._ip_entry.get().strip()
        if not ip:
            ip = self._get_target_ip()
        if not ip:
            return
        # Strip http:// prefix if user pasted a URL
        ip = ip.replace("http://", "").replace("https://", "").rstrip("/")
        if ip in self._device_rows:
            return  # already added

        self._add_device_row(ip, "Identifying...", "...")
        self._identify_device(ip)

    def _add_device_row(self, ip: str, model: str, version: str) -> None:
        """Add a device row to the panel."""
        if self._no_devices_label.winfo_exists():
            self._no_devices_label.pack_forget()

        row = DeviceFirmwareRow(self._devices_container, ip, model, version)
        row.pack(fill="x", pady=3)
        self._device_rows[ip] = row

    def _identify_device(self, ip: str) -> None:
        """Run full MK3 identification: protocol probe + web scraping."""
        def _run():
            from ...network.mk3_identifier import identify_mk3
            info = identify_mk3(ip)
            self.after(0, lambda: self._on_device_identified(ip, info))

        threading.Thread(target=_run, daemon=True).start()

    def _on_device_identified(self, ip: str, info) -> None:
        """Update the device row after MK3 identification completes."""
        row = self._device_rows.get(ip)
        if not row:
            return

        model = info.model or info.device_name or ("MK3 Amplifier" if info.is_mk3 else "Unknown Device")
        version = info.firmware_version or "unknown"
        confidence = info.confidence

        # Rebuild the row with the identified info
        row.destroy()
        new_row = DeviceFirmwareRow(self._devices_container, ip, model, version)
        new_row.pack(fill="x", pady=3)
        self._device_rows[ip] = new_row

        # Show identification result
        if info.is_mk3:
            detected = ", ".join(info.detected_by) if info.detected_by else "unknown"
            logger.info(
                "MK3 identified at %s: model=%s, fw=%s, confidence=%s, detected_by=%s",
                ip, model, version, confidence, detected,
            )
        else:
            logger.info("Device at %s not identified as MK3 (confidence=%s)", ip, confidence)

        # Query firmware API for available versions
        if self._api.has_api_key:
            self._check_firmware_for_device(ip)

    def _check_firmware_for_device(self, ip: str) -> None:
        """Query the firmware API for latest versions and update the device row."""
        row = self._device_rows.get(ip)
        if not row:
            return

        for channel in ["stable", "beta", "alpha"]:
            def _fetch(ch=channel):
                try:
                    result = self._api.get_latest(channel=ch, current_version=row.installed_version)
                    if result.latest:
                        self.after(0, lambda fw=result.latest, c=ch: row.set_channel_version(c, fw))
                except APIError as e:
                    logger.debug("API error checking %s channel: %s", ch, e)
                except Exception as e:
                    logger.debug("Error checking firmware channel %s: %s", ch, e)

            threading.Thread(target=_fetch, daemon=True).start()

    # ── 4. Firmware versions browser ───────────────────────────────────

    def _build_firmware_browser(self) -> None:
        panel = ctk.CTkFrame(self, fg_color=COLORS['card_bg'], corner_radius=12)
        panel.grid(row=3, column=0, sticky="ew", padx=10, pady=5)

        inner = ctk.CTkFrame(panel, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=12)

        # Header row with title + filter controls
        header_row = ctk.CTkFrame(inner, fg_color="transparent")
        header_row.pack(fill="x")

        ctk.CTkLabel(
            header_row, text="Available Firmware",
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            text_color=COLORS['text_primary'], anchor="w",
        ).pack(side="left")

        # Channel filter
        ctk.CTkLabel(
            header_row, text="Channel:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLORS['text_secondary'],
        ).pack(side="left", padx=(20, 0))

        self._channel_filter = ctk.CTkComboBox(
            header_row,
            values=["all", "stable", "beta", "alpha", "hotfix"],
            width=100, font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            command=self._on_channel_filter_changed,
        )
        self._channel_filter.set("all")
        self._channel_filter.pack(side="left", padx=(6, 0))

        # Hardware model filter
        ctk.CTkLabel(
            header_row, text="Model:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLORS['text_secondary'],
        ).pack(side="left", padx=(16, 0))

        self._hw_model_filter = ctk.CTkComboBox(
            header_row,
            values=["all"],
            width=140, font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            command=self._on_hw_model_filter_changed,
        )
        self._hw_model_filter.set("all")
        self._hw_model_filter.pack(side="left", padx=(6, 0))

        self._fw_count_label = ctk.CTkLabel(
            header_row, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLORS['text_secondary'],
        )
        self._fw_count_label.pack(side="right")

        # Firmware versions list (scrollable, max height)
        self._fw_scroll = ctk.CTkScrollableFrame(
            inner, fg_color="#0f172a", height=200,
        )
        self._fw_scroll.pack(fill="x", expand=True, pady=(8, 0))

        self._fw_placeholder = ctk.CTkLabel(
            self._fw_scroll,
            text="Connect to the firmware API to see available versions.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color="#64748b",
        )
        self._fw_placeholder.pack(pady=8)

    def _on_channel_filter_changed(self, _value: str) -> None:
        self._render_firmware_list()

    def _on_hw_model_filter_changed(self, _value: str) -> None:
        self._render_firmware_list()

    def _render_firmware_list(self) -> None:
        """Re-render the firmware version cards based on current filters."""
        # Clear existing
        for widget in self._fw_scroll.winfo_children():
            widget.destroy()

        channel = self._channel_filter.get()
        hw_model = self._hw_model_filter.get()

        filtered = self._firmware_list
        if channel != "all":
            filtered = [fw for fw in filtered if fw.channel == channel]
        if hw_model != "all":
            filtered = [
                fw for fw in filtered
                if any(m.get("model_number") == hw_model or m.get("name") == hw_model
                       for m in fw.hardware_models)
            ]

        if not filtered:
            ctk.CTkLabel(
                self._fw_scroll,
                text="No firmware versions match the current filters.",
                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                text_color="#64748b",
            ).pack(pady=8)
            self._fw_count_label.configure(text="0 versions")
            return

        self._fw_count_label.configure(text=f"{len(filtered)} version(s)")

        for fw in filtered[:20]:  # Show max 20 to keep UI responsive
            card = FirmwareVersionCard(
                self._fw_scroll, fw,
                on_install=self._on_install_firmware if self._device_rows else None,
            )
            card.pack(fill="x", padx=4, pady=4)

        # Force scroll frame to update its canvas after adding children
        self._fw_scroll.update_idletasks()

    # ── 5. Test verification matrix ────────────────────────────────────

    def _build_test_content(self) -> None:
        content_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content_scroll.grid(row=4, column=0, sticky="nsew", padx=10, pady=(5, 10))
        content_scroll.grid_columnconfigure(0, weight=1)
        content_scroll.grid_columnconfigure(1, weight=1)

        # Section title
        title_frame = ctk.CTkFrame(content_scroll, fg_color="transparent")
        title_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 8))

        ctk.CTkLabel(
            title_frame, text="Verification Test Matrix",
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            text_color=COLORS['text_primary'], anchor="w",
        ).pack(side="left")

        ctk.CTkLabel(
            title_frame,
            text="Tests map to JIRA tickets. Run per hardware + firmware combination.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLORS['text_secondary'], anchor="w",
        ).pack(side="left", padx=(12, 0))

        # Build test cards in a 2-column grid
        for idx, tg in enumerate(TEST_GROUPS):
            row = (idx // 2) + 1  # +1 to leave room for title
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

        # Bottom section
        bottom_row = ((len(TEST_GROUPS) + 1) // 2) + 1
        bottom_frame = ctk.CTkFrame(
            content_scroll, fg_color=COLORS['card_bg'], corner_radius=12,
        )
        bottom_frame.grid(
            row=bottom_row, column=0, columnspan=2,
            sticky="ew", padx=6, pady=(12, 6),
        )

        btn_inner = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        btn_inner.pack(fill="x", padx=20, pady=14)

        self._run_all_btn = ctk.CTkButton(
            btn_inner, text="Run All Automated Tests",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color=COLORS['accent'], hover_color="#3a8fc4",
            width=220, height=38, command=self._run_all_automated,
        )
        self._run_all_btn.pack(side="left")

        self._export_btn = ctk.CTkButton(
            btn_inner, text="Export Report",
            font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
            fg_color=COLORS['success'], hover_color="#1e8449",
            width=160, height=38, command=self._export_report,
        )
        self._export_btn.pack(side="left", padx=(12, 0))

        self._summary_label = ctk.CTkLabel(
            btn_inner, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLORS['text_secondary'],
        )
        self._summary_label.pack(side="right")

        # Progress label (used by test runners)
        self._progress_label = ctk.CTkLabel(
            btn_inner, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            text_color=COLORS['text_secondary'],
        )
        self._progress_label.pack(side="right", padx=(0, 20))

    # ── Firmware API data fetching ─────────────────────────────────────

    def _refresh_firmware_data(self) -> None:
        """Fetch hardware models and firmware list from the API."""
        self._api_status_label.configure(text="Loading...", text_color=COLORS['accent'])

        def _fetch():
            errors = []
            hw_models = []
            fw_list = []

            try:
                hw_models = self._api.list_hardware()
            except APIError as e:
                errors.append(f"Hardware: {e}")
            except Exception as e:
                errors.append(f"Hardware: {e}")

            try:
                fw_list = self._api.list_firmware(limit=50)
            except APIError as e:
                errors.append(f"Firmware: {e}")
            except Exception as e:
                errors.append(f"Firmware: {e}")

            self.after(0, lambda: self._on_firmware_data_loaded(hw_models, fw_list, errors))

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_firmware_data_loaded(
        self,
        hw_models: List[HardwareModel],
        fw_list: List[FirmwareInfo],
        errors: List[str],
    ) -> None:
        """Handle firmware data loaded from API."""
        self._connect_btn.configure(state="normal")
        self._hardware_models = hw_models
        self._firmware_list = fw_list

        if errors:
            self._api_status_label.configure(
                text=f"Errors: {'; '.join(errors)}", text_color=COLORS['error']
            )
        else:
            self._api_status_label.configure(
                text=f"Connected - {len(hw_models)} models, {len(fw_list)} firmware versions",
                text_color=COLORS['success'],
            )

        # Update hardware model filter dropdown
        model_names = ["all"] + [m.name or m.model_number for m in hw_models]
        self._hw_model_filter.configure(values=model_names)

        # Render firmware list
        self._render_firmware_list()

        # Update firmware info for any already-added devices
        for ip in list(self._device_rows.keys()):
            self._check_firmware_for_device(ip)

    # ── Firmware install ─────────────────────────────────────────────

    def _on_install_firmware(self, firmware: FirmwareInfo) -> None:
        """Handle user clicking 'Install' on a firmware version card."""
        ip = self._get_ip()
        if not ip:
            return

        # Confirm with user
        self._progress_label.configure(
            text=f"Installing v{firmware.version} to {ip}...",
            text_color=COLORS['accent'],
        )

        def _progress(msg: str):
            self.after(0, lambda m=msg: self._progress_label.configure(text=m))

        def _on_complete(result):
            if result.success:
                self.after(0, lambda: self._progress_label.configure(
                    text=f"Firmware v{firmware.version} installed! {result.message}",
                    text_color=COLORS['success'],
                ))
                # Re-identify device after update
                self.after(5000, lambda: self._identify_device(ip))
            else:
                self.after(0, lambda: self._progress_label.configure(
                    text=f"Install failed: {result.error}",
                    text_color=COLORS['error'],
                ))

        update_firmware_async(
            self._updater, ip, firmware,
            callback=_on_complete,
            progress_callback=_progress,
        )

    # ── Helpers ────────────────────────────────────────────────────────

    def _get_ip(self) -> Optional[str]:
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
        self._stop_event.set()
        self._progress_label.configure(text="Stopping...", text_color=COLORS['warning'])

    # ── Automated test runners ─────────────────────────────────────────

    def _run_ip_stability_test(self) -> None:
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
                    'ip_stability', f"verification module not found: {e}"
                ))
            except Exception as e:
                logger.error(f"IP stability test error: {e}")
                self.after(0, lambda: self._on_test_error('ip_stability', str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _run_status_page_test(self) -> None:
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
                    'status_page', f"verification module not found: {e}"
                ))
            except Exception as e:
                logger.error(f"Status page test error: {e}")
                self.after(0, lambda: self._on_test_error('status_page', str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _run_sleep_reboot_test(self) -> None:
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
                    ip, duration_sec=3600,
                    progress_callback=progress_cb, stop_event=self._stop_event,
                )
                result = test.run()
                self.after(0, lambda: self._on_test_complete('sleep_reboot', result))
            except ImportError as e:
                logger.error(f"Import error: {e}")
                self.after(0, lambda: self._on_test_error(
                    'sleep_reboot', f"verification module not found: {e}"
                ))
            except Exception as e:
                logger.error(f"Sleep/reboot test error: {e}")
                self.after(0, lambda: self._on_test_error('sleep_reboot', str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _run_http_stability_test(self) -> None:
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
                    ip, duration_sec=1800,
                    progress_callback=progress_cb, stop_event=self._stop_event,
                )
                result = test.run()
                self.after(0, lambda: self._on_test_complete('http_stability', result))
            except ImportError as e:
                logger.error(f"Import error: {e}")
                self.after(0, lambda: self._on_test_error(
                    'http_stability', f"verification module not found: {e}"
                ))
            except Exception as e:
                logger.error(f"HTTP stability test error: {e}")
                self.after(0, lambda: self._on_test_error('http_stability', str(e)))

        threading.Thread(target=run, daemon=True).start()

    # ── Manual test dialog ─────────────────────────────────────────────

    def _open_manual_dialog(self, tg: Dict[str, Any]) -> None:
        key = tg['key']
        card = self._test_cards[key]
        card.set_running("Awaiting manual verification...")

        def on_complete(passed: bool):
            if passed:
                card.set_passed("Manually verified - PASSED")
                self._test_results[key] = {
                    'status': 'passed', 'message': 'Manually verified',
                    'timestamp': datetime.now().isoformat(),
                }
            else:
                card.set_failed("Manually verified - FAILED")
                self._test_results[key] = {
                    'status': 'failed', 'message': 'Manually marked as failed',
                    'timestamp': datetime.now().isoformat(),
                }
            self._update_summary()

        ManualTestDialog(
            self, test_name=tg['name'], ticket=tg['ticket'],
            steps=tg.get('steps', []), color=tg['color'], on_complete=on_complete,
        )

    # ── Test completion handlers ───────────────────────────────────────

    def _on_test_complete(self, key: str, result: Any) -> None:
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
            'message': message, 'details': details,
            'duration_ms': duration_ms, 'timestamp': datetime.now().isoformat(),
        }
        self._progress_label.configure(
            text=f"Completed: {key}", text_color=COLORS['text_secondary']
        )
        self._update_summary()

    def _on_test_error(self, key: str, error_msg: str) -> None:
        card = self._test_cards[key]
        card.set_failed(f"Error: {error_msg}")
        self._test_results[key] = {
            'status': 'error', 'message': error_msg,
            'timestamp': datetime.now().isoformat(),
        }
        self._progress_label.configure(
            text=f"Error in {key}", text_color=COLORS['error']
        )
        self._update_summary()

    def _update_summary(self) -> None:
        total = len(TEST_GROUPS)
        completed = len(self._test_results)
        passed = sum(1 for r in self._test_results.values() if r.get('status') == 'passed')
        failed = sum(1 for r in self._test_results.values() if r.get('status') in ('failed', 'error'))
        self._summary_label.configure(
            text=f"{completed}/{total} complete  |  {passed} passed  |  {failed} failed"
        )

    # ── Run All Automated ──────────────────────────────────────────────

    def _run_all_automated(self) -> None:
        ip = self._get_ip()
        if not ip:
            return

        self._run_all_btn.configure(state="disabled")
        self._progress_label.configure(
            text="Running all automated tests...", text_color=COLORS['accent']
        )

        automated_keys = [tg['key'] for tg in TEST_GROUPS if tg['type'] == 'automated']

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
                    test = test_class(ip)
                    result = test.run()
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
        class_map = {
            'ip_stability': 'IPCommandStabilityTest',
            'status_page': 'StatusPageVerifier',
        }
        class_name = class_map.get(key)
        if not class_name:
            return None
        try:
            from ...network import verification as ver_mod
            return getattr(ver_mod, class_name, None)
        except ImportError:
            return None

    # ── Export Report ──────────────────────────────────────────────────

    def _export_report(self) -> None:
        if not self._test_results:
            self._progress_label.configure(
                text="No results to export", text_color=COLORS['warning']
            )
            return

        # Gather device info
        devices_info = {}
        for ip, row in self._device_rows.items():
            devices_info[ip] = {
                'model': row.model_name,
                'installed_version': row.installed_version,
                'latest_stable': row.latest_stable.version if row.latest_stable else None,
            }

        report = {
            'title': 'MK3 Firmware Verification Report',
            'generated': datetime.now().isoformat(),
            'target_ip': self._ip_entry.get().strip() or self._get_target_ip() or "N/A",
            'devices': devices_info,
            'firmware_api_connected': self._api.has_api_key,
            'hardware_models': [{'id': m.id, 'name': m.name, 'model_number': m.model_number}
                                for m in self._hardware_models],
            'tests': {},
        }

        for tg in TEST_GROUPS:
            key = tg['key']
            result = self._test_results.get(key, {'status': 'not_run'})
            report['tests'][key] = {
                'name': tg['name'], 'ticket': tg['ticket'], 'type': tg['type'],
                **result,
            }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"verification_report_{timestamp}.json"

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
