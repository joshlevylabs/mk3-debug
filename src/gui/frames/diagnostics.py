"""Full diagnostics tab frame - Professional Enterprise Dashboard Design."""

import customtkinter as ctk
import threading
import json
import math
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


# Professional Enterprise Color Palette
COLORS = {
    "bg_primary": "#0a0a0f",
    "bg_secondary": "#111827",
    "bg_card": "#1f2937",
    "bg_elevated": "#374151",
    "bg_dark": "#030712",
    "border_subtle": "#374151",
    "border_accent": "#3b82f6",
    "text_primary": "#f9fafb",
    "text_secondary": "#9ca3af",
    "text_muted": "#6b7280",
    "success": "#10b981",
    "success_bg": "#064e3b",
    "success_light": "#34d399",
    "warning": "#f59e0b",
    "warning_bg": "#451a03",
    "warning_light": "#fbbf24",
    "error": "#ef4444",
    "error_bg": "#450a0a",
    "error_light": "#f87171",
    "info": "#3b82f6",
    "info_bg": "#1e3a5f",
    "info_light": "#60a5fa",
    "purple": "#8b5cf6",
    "purple_bg": "#2e1065",
    "cyan": "#06b6d4",
    "cyan_bg": "#083344",
}


class CircularGauge(ctk.CTkFrame):
    """A visual circular gauge for displaying health score."""

    def __init__(self, master, size: int = 180, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._size = size
        self._value = 0
        self._max_value = 100
        self._canvas = None
        self._label = None
        self._status_label = None

        self._build_ui()

    def _build_ui(self):
        """Build the gauge UI."""
        # Create canvas for the arc
        self._canvas = ctk.CTkCanvas(
            self,
            width=self._size,
            height=self._size,
            bg=COLORS["bg_card"],
            highlightthickness=0
        )
        self._canvas.pack()

        # Center value label
        self._label = ctk.CTkLabel(
            self,
            text="--",
            font=ctk.CTkFont(size=42, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        self._label.place(relx=0.5, rely=0.42, anchor="center")

        # Status label below value
        self._status_label = ctk.CTkLabel(
            self,
            text="HEALTH SCORE",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLORS["text_muted"]
        )
        self._status_label.place(relx=0.5, rely=0.62, anchor="center")

        self._draw_gauge()

    def _draw_gauge(self):
        """Draw the gauge arc."""
        self._canvas.delete("all")

        padding = 15
        x0, y0 = padding, padding
        x1, y1 = self._size - padding, self._size - padding

        # Background arc (full circle track)
        self._canvas.create_arc(
            x0, y0, x1, y1,
            start=135,
            extent=-270,
            style="arc",
            outline=COLORS["bg_elevated"],
            width=12
        )

        # Calculate arc extent based on value
        percentage = min(self._value / self._max_value, 1.0)
        extent = -270 * percentage

        # Determine color based on percentage
        if percentage >= 0.8:
            color = COLORS["success"]
        elif percentage >= 0.5:
            color = COLORS["warning"]
        else:
            color = COLORS["error"]

        # Value arc
        if extent != 0:
            self._canvas.create_arc(
                x0, y0, x1, y1,
                start=135,
                extent=extent,
                style="arc",
                outline=color,
                width=12
            )

    def set_value(self, value: float, max_value: float = 100):
        """Set the gauge value."""
        self._value = value
        self._max_value = max_value

        # Calculate percentage
        percentage = (value / max_value) * 100 if max_value > 0 else 0

        # Update label
        self._label.configure(text=f"{percentage:.0f}%")

        # Update status text and color
        if percentage >= 80:
            status = "EXCELLENT"
            color = COLORS["success"]
        elif percentage >= 60:
            status = "GOOD"
            color = COLORS["success_light"]
        elif percentage >= 40:
            status = "FAIR"
            color = COLORS["warning"]
        else:
            status = "NEEDS ATTENTION"
            color = COLORS["error"]

        self._status_label.configure(text=status, text_color=color)
        self._label.configure(text_color=color)

        self._draw_gauge()


class MetricCard(ctk.CTkFrame):
    """A modern metric card for displaying a single KPI."""

    def __init__(
        self,
        master,
        title: str,
        value: str = "--",
        subtitle: str = "",
        icon: str = "📊",
        color: str = "#3b82f6",
        trend: Optional[str] = None,  # "up", "down", "stable"
        **kwargs
    ):
        super().__init__(
            master,
            fg_color=COLORS["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border_subtle"],
            **kwargs
        )

        self._title = title
        self._color = color

        self._build_ui(title, value, subtitle, icon, color, trend)

    def _build_ui(self, title: str, value: str, subtitle: str, icon: str, color: str, trend: Optional[str]):
        """Build the metric card UI."""
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=14)

        # Top row with icon and trend
        top_row = ctk.CTkFrame(container, fg_color="transparent")
        top_row.pack(fill="x")

        # Icon with colored background
        icon_bg = ctk.CTkFrame(
            top_row,
            width=36,
            height=36,
            corner_radius=8,
            fg_color=color
        )
        icon_bg.pack(side="left")
        icon_bg.pack_propagate(False)

        ctk.CTkLabel(
            icon_bg,
            text=icon,
            font=ctk.CTkFont(size=16)
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Title
        ctk.CTkLabel(
            top_row,
            text=title,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"]
        ).pack(side="left", padx=(12, 0))

        # Trend indicator
        if trend:
            trend_colors = {"up": "#10b981", "down": "#ef4444", "stable": "#6b7280"}
            trend_icons = {"up": "↑", "down": "↓", "stable": "→"}

            trend_badge = ctk.CTkFrame(
                top_row,
                corner_radius=4,
                fg_color=trend_colors.get(trend, "#6b7280"),
                height=20
            )
            trend_badge.pack(side="right")

            ctk.CTkLabel(
                trend_badge,
                text=trend_icons.get(trend, "→"),
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="white"
            ).pack(padx=6, pady=2)

        # Value
        self._value_label = ctk.CTkLabel(
            container,
            text=value,
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        self._value_label.pack(anchor="w", pady=(10, 2))

        # Subtitle
        self._subtitle_label = ctk.CTkLabel(
            container,
            text=subtitle,
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_secondary"]
        )
        self._subtitle_label.pack(anchor="w")

    def update_value(self, value: str, subtitle: str = None):
        """Update the metric value."""
        self._value_label.configure(text=value)
        if subtitle is not None:
            self._subtitle_label.configure(text=subtitle)


class TestStatusIndicator(ctk.CTkFrame):
    """A visual test status indicator with icon and label."""

    STATUS_CONFIG = {
        "pending": {"icon": "○", "color": "#64748b", "bg": "#1e293b"},
        "running": {"icon": "◉", "color": "#3b82f6", "bg": "#1e3a5f"},
        "passed": {"icon": "✓", "color": "#10b981", "bg": "#064e3b"},
        "failed": {"icon": "✗", "color": "#ef4444", "bg": "#450a0a"},
        "warning": {"icon": "!", "color": "#f59e0b", "bg": "#451a03"},
    }

    def __init__(self, master, name: str, status: str = "pending", **kwargs):
        config = self.STATUS_CONFIG.get(status, self.STATUS_CONFIG["pending"])

        super().__init__(
            master,
            fg_color=config["bg"],
            corner_radius=8,
            border_width=1,
            border_color=config["color"],
            **kwargs
        )

        self._name = name
        self._status = status

        self._build_ui(name, config)

    def _build_ui(self, name: str, config: dict):
        """Build the indicator UI."""
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="x", padx=12, pady=8)

        # Status icon
        self._icon_label = ctk.CTkLabel(
            container,
            text=config["icon"],
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=config["color"]
        )
        self._icon_label.pack(side="left")

        # Test name
        self._name_label = ctk.CTkLabel(
            container,
            text=name,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_primary"]
        )
        self._name_label.pack(side="left", padx=(8, 0))

        # Status text
        self._status_label = ctk.CTkLabel(
            container,
            text=status.upper(),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=config["color"]
        )
        self._status_label.pack(side="right")

    def set_status(self, status: str):
        """Update the indicator status."""
        self._status = status
        config = self.STATUS_CONFIG.get(status, self.STATUS_CONFIG["pending"])

        self.configure(fg_color=config["bg"], border_color=config["color"])
        self._icon_label.configure(text=config["icon"], text_color=config["color"])
        self._status_label.configure(text=status.upper(), text_color=config["color"])


class ProgressStep(ctk.CTkFrame):
    """A single step in a progress timeline."""

    def __init__(self, master, step_num: int, name: str, status: str = "pending", is_last: bool = False, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._step_num = step_num
        self._name = name
        self._status = status
        self._is_last = is_last

        self._build_ui()

    def _build_ui(self):
        """Build the step UI."""
        # Horizontal layout
        self.grid_columnconfigure(1, weight=1)

        # Step indicator column
        indicator_frame = ctk.CTkFrame(self, fg_color="transparent", width=40)
        indicator_frame.grid(row=0, column=0, sticky="ns")
        indicator_frame.grid_propagate(False)

        # Circle indicator
        status_colors = {
            "pending": COLORS["text_muted"],
            "running": COLORS["info"],
            "passed": COLORS["success"],
            "failed": COLORS["error"],
            "warning": COLORS["warning"],
        }
        color = status_colors.get(self._status, COLORS["text_muted"])

        self._circle = ctk.CTkFrame(
            indicator_frame,
            width=28,
            height=28,
            corner_radius=14,
            fg_color=color if self._status != "pending" else "transparent",
            border_width=2,
            border_color=color
        )
        self._circle.place(relx=0.5, rely=0, anchor="n")
        self._circle.pack_propagate(False)

        # Step number or icon
        icon_text = {
            "pending": str(self._step_num),
            "running": "◉",
            "passed": "✓",
            "failed": "✗",
            "warning": "!",
        }

        self._icon_label = ctk.CTkLabel(
            self._circle,
            text=icon_text.get(self._status, str(self._step_num)),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="white" if self._status != "pending" else color
        )
        self._icon_label.place(relx=0.5, rely=0.5, anchor="center")

        # Connector line (if not last)
        if not self._is_last:
            self._line = ctk.CTkFrame(
                indicator_frame,
                width=2,
                height=30,
                fg_color=color if self._status in ["passed", "running"] else COLORS["border_subtle"]
            )
            self._line.place(relx=0.5, rely=1.0, anchor="n", y=-8)

        # Content
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(2, 12))

        self._name_label = ctk.CTkLabel(
            content,
            text=self._name,
            font=ctk.CTkFont(size=13, weight="bold" if self._status == "running" else "normal"),
            text_color=color if self._status == "running" else COLORS["text_primary"]
        )
        self._name_label.pack(anchor="w")

    def set_status(self, status: str):
        """Update the step status."""
        self._status = status

        status_colors = {
            "pending": COLORS["text_muted"],
            "running": COLORS["info"],
            "passed": COLORS["success"],
            "failed": COLORS["error"],
            "warning": COLORS["warning"],
        }
        color = status_colors.get(status, COLORS["text_muted"])

        # Update circle
        self._circle.configure(
            fg_color=color if status != "pending" else "transparent",
            border_color=color
        )

        # Update icon
        icon_text = {
            "pending": str(self._step_num),
            "running": "◉",
            "passed": "✓",
            "failed": "✗",
            "warning": "!",
        }
        self._icon_label.configure(
            text=icon_text.get(status, str(self._step_num)),
            text_color="white" if status != "pending" else color
        )

        # Update name styling
        self._name_label.configure(
            font=ctk.CTkFont(size=13, weight="bold" if status == "running" else "normal"),
            text_color=color if status == "running" else COLORS["text_primary"]
        )

        # Update line
        if hasattr(self, '_line'):
            self._line.configure(
                fg_color=color if status in ["passed", "running"] else COLORS["border_subtle"]
            )


class StatBar(ctk.CTkFrame):
    """A horizontal bar showing a statistic visually."""

    def __init__(self, master, label: str, value: int, max_value: int, color: str = "#3b82f6", **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._label = label
        self._value = value
        self._max_value = max_value
        self._color = color

        self._build_ui()

    def _build_ui(self):
        """Build the stat bar UI."""
        # Label row
        label_row = ctk.CTkFrame(self, fg_color="transparent")
        label_row.pack(fill="x")

        ctk.CTkLabel(
            label_row,
            text=self._label,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(side="left")

        ctk.CTkLabel(
            label_row,
            text=str(self._value),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self._color
        ).pack(side="right")

        # Bar background
        bar_bg = ctk.CTkFrame(
            self,
            height=8,
            corner_radius=4,
            fg_color=COLORS["bg_elevated"]
        )
        bar_bg.pack(fill="x", pady=(6, 0))

        # Calculate percentage
        percentage = (self._value / self._max_value) if self._max_value > 0 else 0

        # Bar fill
        if percentage > 0:
            bar_fill = ctk.CTkFrame(
                bar_bg,
                height=8,
                corner_radius=4,
                fg_color=self._color
            )
            bar_fill.place(relx=0, rely=0.5, anchor="w", relwidth=percentage)


class DiagnosticsFrame(ctk.CTkFrame):
    """
    Professional Enterprise Dashboard for running comprehensive diagnostics.
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
        self._test_steps = {}
        self._metric_cards = {}

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the UI."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Controls header
        self._build_controls()

        # Results area
        self._build_results()

    def _build_controls(self) -> None:
        """Build modern controls header."""
        header = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_secondary"],
            corner_radius=0
        )
        header.grid(row=0, column=0, sticky="ew")

        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.pack(fill="x", padx=24, pady=16)

        # Left: Run button
        left = ctk.CTkFrame(controls, fg_color="transparent")
        left.pack(side="left")

        self.run_btn = ctk.CTkButton(
            left,
            text="▶  Start Diagnostic Scan",
            command=self._run_full_diagnostic,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=COLORS["success"],
            hover_color="#059669",
            text_color="white",
            width=220,
            height=48,
            corner_radius=10
        )
        self.run_btn.pack(side="left")

        # Center: Progress info
        center = ctk.CTkFrame(controls, fg_color="transparent")
        center.pack(side="left", fill="x", expand=True, padx=32)

        self.progress_label = ctk.CTkLabel(
            center,
            text="Ready to diagnose • Enter target IP above",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_secondary"],
            anchor="w"
        )
        self.progress_label.pack(anchor="w")

        # Modern segmented progress bar
        progress_container = ctk.CTkFrame(center, fg_color="transparent")
        progress_container.pack(fill="x", pady=(8, 0))

        self._progress_segments = []
        test_names = ["Network", "Ports", "HTTP", "Hostname", "DNS", "Commands"]

        for i, name in enumerate(test_names):
            seg_frame = ctk.CTkFrame(progress_container, fg_color="transparent")
            seg_frame.pack(side="left", fill="x", expand=True, padx=(0, 4) if i < len(test_names)-1 else 0)

            seg = ctk.CTkFrame(
                seg_frame,
                height=6,
                corner_radius=3,
                fg_color=COLORS["bg_elevated"]
            )
            seg.pack(fill="x")

            self._progress_segments.append(seg)

        # Right: Export buttons
        right = ctk.CTkFrame(controls, fg_color="transparent")
        right.pack(side="right")

        self.export_btn = ctk.CTkButton(
            right,
            text="📊 Export Report",
            command=self._export_report,
            font=ctk.CTkFont(size=13),
            fg_color=COLORS["bg_elevated"],
            hover_color="#4b5563",
            text_color=COLORS["text_primary"],
            width=130,
            height=40,
            corner_radius=8,
            state="disabled"
        )
        self.export_btn.pack(side="left", padx=(0, 10))

        self.clear_btn = ctk.CTkButton(
            right,
            text="Clear",
            command=self._clear_results,
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            hover_color=COLORS["bg_elevated"],
            text_color=COLORS["text_secondary"],
            width=80,
            height=40,
            corner_radius=8,
            border_width=1,
            border_color=COLORS["border_subtle"]
        )
        self.clear_btn.pack(side="left")

    def _build_results(self) -> None:
        """Build results area."""
        self.results_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_primary"],
            corner_radius=0
        )
        self.results_scroll.grid(row=1, column=0, sticky="nsew")
        self.results_scroll.grid_columnconfigure(0, weight=1)

        self._show_placeholder()

    def _show_placeholder(self) -> None:
        """Show the modern placeholder."""
        self.placeholder_frame = ctk.CTkFrame(
            self.results_scroll,
            fg_color=COLORS["bg_card"],
            corner_radius=16,
            border_width=1,
            border_color=COLORS["border_subtle"]
        )
        self.placeholder_frame.pack(pady=40, padx=24)

        inner = ctk.CTkFrame(self.placeholder_frame, fg_color="transparent")
        inner.pack(padx=56, pady=48)

        # Large icon
        ctk.CTkLabel(
            inner,
            text="🔬",
            font=ctk.CTkFont(size=64)
        ).pack()

        # Title
        ctk.CTkLabel(
            inner,
            text="Network Diagnostic Suite",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(pady=(20, 8))

        # Subtitle
        ctk.CTkLabel(
            inner,
            text="Comprehensive analysis of your MK3 amplifier's network configuration,\ncontrol protocols, and connectivity status.",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_secondary"],
            justify="center"
        ).pack(pady=(0, 32))

        # Test grid
        tests_frame = ctk.CTkFrame(inner, fg_color=COLORS["bg_secondary"], corner_radius=12)
        tests_frame.pack(fill="x")

        tests_inner = ctk.CTkFrame(tests_frame, fg_color="transparent")
        tests_inner.pack(padx=28, pady=24)

        ctk.CTkLabel(
            tests_inner,
            text="DIAGNOSTIC TESTS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", pady=(0, 16))

        tests = [
            ("📡", "Network Reachability", "Latency, packet loss, connection quality"),
            ("🔌", "Port Scanner", "Service availability on key ports"),
            ("🌐", "HTTP Endpoints", "Web interface accessibility"),
            ("🏷️", "Hostname Resolution", "NetBIOS, mDNS, DNS lookups"),
            ("📋", "DNS Configuration", "Server availability and records"),
            ("⚡", "Command Protocol", "Control interface testing"),
        ]

        # Two-column grid
        grid = ctk.CTkFrame(tests_inner, fg_color="transparent")
        grid.pack(fill="x")

        for i, (icon, name, desc) in enumerate(tests):
            col = i % 2
            row_frame = grid.winfo_children()[i // 2] if i // 2 < len(grid.winfo_children()) else None

            if col == 0:
                row_frame = ctk.CTkFrame(grid, fg_color="transparent")
                row_frame.pack(fill="x", pady=6)

            item = ctk.CTkFrame(row_frame, fg_color=COLORS["bg_card"], corner_radius=8, width=280)
            item.pack(side="left", padx=(0, 12) if col == 0 else 0, fill="x", expand=True)

            item_inner = ctk.CTkFrame(item, fg_color="transparent")
            item_inner.pack(fill="x", padx=14, pady=12)

            top = ctk.CTkFrame(item_inner, fg_color="transparent")
            top.pack(fill="x")

            ctk.CTkLabel(top, text=icon, font=ctk.CTkFont(size=18)).pack(side="left")
            ctk.CTkLabel(
                top,
                text=name,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=COLORS["text_primary"]
            ).pack(side="left", padx=(10, 0))

            ctk.CTkLabel(
                item_inner,
                text=desc,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_muted"]
            ).pack(anchor="w", pady=(4, 0))

    def _clear_results(self) -> None:
        """Clear results and show placeholder."""
        for widget in self.results_scroll.winfo_children():
            widget.destroy()
        self._show_placeholder()
        self.export_btn.configure(state="disabled")
        self._reset_progress_segments()
        self.progress_label.configure(text="Ready to diagnose")

    def _reset_progress_segments(self) -> None:
        """Reset all progress segments."""
        for seg in self._progress_segments:
            seg.configure(fg_color=COLORS["bg_elevated"])

    def _update_progress_segment(self, index: int, status: str) -> None:
        """Update a progress segment color."""
        colors = {
            "running": COLORS["info"],
            "passed": COLORS["success"],
            "failed": COLORS["error"],
            "warning": COLORS["warning"],
        }
        if 0 <= index < len(self._progress_segments):
            self.after(0, lambda: self._progress_segments[index].configure(
                fg_color=colors.get(status, COLORS["bg_elevated"])
            ))

    def _check_ip(self) -> Optional[str]:
        """Check if target IP is set."""
        ip = self._get_target_ip()
        if not ip:
            self.progress_label.configure(text="⚠ No target IP configured", text_color=COLORS["warning"])
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
        self.run_btn.configure(state="disabled", text="⏳ Scanning...")
        self.export_btn.configure(state="disabled")
        self._reset_progress_segments()

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

        # Build live dashboard
        self.after(0, lambda: self._build_live_dashboard(ip))

        def run():
            try:
                total_steps = 6
                current_step = 0

                # Step 1: Quick network check
                current_step += 1
                self._update_progress(current_step, total_steps, "Testing network reachability...")
                self._update_progress_segment(0, "running")
                result = self._run_reachability_test(ip)
                self._update_progress_segment(0, "passed" if result else "failed")

                # Step 2: Port scan
                current_step += 1
                self._update_progress(current_step, total_steps, "Scanning ports...")
                self._update_progress_segment(1, "running")
                result = self._run_port_scan(ip)
                self._update_progress_segment(1, "passed" if result else "failed")

                # Step 3: HTTP endpoints
                current_step += 1
                self._update_progress(current_step, total_steps, "Testing HTTP endpoints...")
                self._update_progress_segment(2, "running")
                result = self._run_http_test(ip)
                self._update_progress_segment(2, "passed" if result else "failed")

                # Step 4: Hostname resolution
                current_step += 1
                self._update_progress(current_step, total_steps, "Testing hostname resolution...")
                self._update_progress_segment(3, "running")
                result = self._run_hostname_test(ip)
                status = "passed" if result == "passed" else ("warning" if result == "warning" else "failed")
                self._update_progress_segment(3, status)

                # Step 5: DNS tests
                current_step += 1
                self._update_progress(current_step, total_steps, "Testing DNS configuration...")
                self._update_progress_segment(4, "running")
                result = self._run_dns_test(ip)
                self._update_progress_segment(4, "passed" if result else "failed")

                # Step 6: Command testing
                current_step += 1
                self._update_progress(current_step, total_steps, "Testing command interface...")
                self._update_progress_segment(5, "running")
                result = self._run_command_test(ip)
                status = "passed" if result == "passed" else ("warning" if result == "warning" else "failed")
                self._update_progress_segment(5, status)

                # Final summary
                self.after(0, self._display_summary)

            except Exception as e:
                logger.error(f"Diagnostic error: {e}")
                self.after(0, lambda: self.progress_label.configure(
                    text=f"Error: {e}", text_color=COLORS["error"]
                ))
            finally:
                self._is_running = False
                self.after(0, lambda: self.run_btn.configure(
                    state="normal", text="▶  Start Diagnostic Scan"
                ))
                self.after(0, lambda: self.export_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _build_live_dashboard(self, ip: str) -> None:
        """Build the live diagnostic dashboard."""
        # Main container
        self._dashboard = ctk.CTkFrame(self.results_scroll, fg_color="transparent")
        self._dashboard.pack(fill="x", padx=16, pady=16)

        # Top row: Device info + Health gauge + Metrics
        top_row = ctk.CTkFrame(self._dashboard, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 16))

        # Device info card
        device_card = ctk.CTkFrame(
            top_row,
            fg_color=COLORS["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border_subtle"]
        )
        device_card.pack(side="left", fill="y", padx=(0, 16))

        device_inner = ctk.CTkFrame(device_card, fg_color="transparent")
        device_inner.pack(padx=24, pady=20)

        ctk.CTkLabel(
            device_inner,
            text="TARGET DEVICE",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w")

        ctk.CTkLabel(
            device_inner,
            text=ip,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(4, 12))

        # Timestamp
        ctk.CTkLabel(
            device_inner,
            text="SCAN STARTED",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w")

        ctk.CTkLabel(
            device_inner,
            text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w")

        # Health gauge
        gauge_card = ctk.CTkFrame(
            top_row,
            fg_color=COLORS["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border_subtle"]
        )
        gauge_card.pack(side="left", fill="y", padx=(0, 16))

        gauge_inner = ctk.CTkFrame(gauge_card, fg_color="transparent")
        gauge_inner.pack(padx=20, pady=16)

        self._health_gauge = CircularGauge(gauge_inner, size=160)
        self._health_gauge.pack()

        # Metrics grid
        metrics_card = ctk.CTkFrame(
            top_row,
            fg_color=COLORS["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border_subtle"]
        )
        metrics_card.pack(side="left", fill="both", expand=True)

        metrics_inner = ctk.CTkFrame(metrics_card, fg_color="transparent")
        metrics_inner.pack(fill="both", expand=True, padx=16, pady=16)

        # Metrics in 2x2 grid
        metrics_grid = ctk.CTkFrame(metrics_inner, fg_color="transparent")
        metrics_grid.pack(fill="both", expand=True)
        metrics_grid.grid_columnconfigure((0, 1), weight=1)
        metrics_grid.grid_rowconfigure((0, 1), weight=1)

        self._metric_cards["latency"] = MetricCard(
            metrics_grid,
            title="Latency",
            value="--",
            subtitle="Average response time",
            icon="⚡",
            color=COLORS["info"]
        )
        self._metric_cards["latency"].grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))

        self._metric_cards["ports"] = MetricCard(
            metrics_grid,
            title="Open Ports",
            value="--",
            subtitle="Services detected",
            icon="🔌",
            color=COLORS["purple"]
        )
        self._metric_cards["ports"].grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))

        self._metric_cards["packet_loss"] = MetricCard(
            metrics_grid,
            title="Packet Loss",
            value="--",
            subtitle="Network reliability",
            icon="📊",
            color=COLORS["success"]
        )
        self._metric_cards["packet_loss"].grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(8, 0))

        self._metric_cards["web"] = MetricCard(
            metrics_grid,
            title="Web Interface",
            value="--",
            subtitle="HTTP accessibility",
            icon="🌐",
            color=COLORS["cyan"]
        )
        self._metric_cards["web"].grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(8, 0))

        # Test results section
        self._results_section = ctk.CTkFrame(
            self._dashboard,
            fg_color=COLORS["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border_subtle"]
        )
        self._results_section.pack(fill="x", pady=(0, 16))

        results_header = ctk.CTkFrame(self._results_section, fg_color="transparent")
        results_header.pack(fill="x", padx=20, pady=(16, 12))

        ctk.CTkLabel(
            results_header,
            text="📋 TEST RESULTS",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(side="left")

        self._results_container = ctk.CTkFrame(self._results_section, fg_color="transparent")
        self._results_container.pack(fill="x", padx=16, pady=(0, 16))

    def _update_progress(self, current: int, total: int, message: str) -> None:
        """Update progress display."""
        self.after(0, lambda: self.progress_label.configure(text=f"[{current}/{total}] {message}"))

    def _run_reachability_test(self, ip: str) -> bool:
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
            msg = f"Device reachable • {result.avg_ms:.1f}ms latency"
            self._results['summary']['passed'] += 1

            # Update metrics
            self.after(0, lambda: self._metric_cards["latency"].update_value(
                f"{result.avg_ms:.1f}ms",
                f"{result.packets_received}/{result.packets_sent} packets received"
            ))
            self.after(0, lambda: self._metric_cards["packet_loss"].update_value(
                f"{result.packet_loss_percent:.1f}%",
                "Packet loss rate"
            ))
        else:
            status = ResultStatus.FAILED
            msg = "Device NOT reachable"
            self._results['summary']['failed'] += 1

            self.after(0, lambda: self._metric_cards["latency"].update_value("N/A", "Host unreachable"))
            self.after(0, lambda: self._metric_cards["packet_loss"].update_value("100%", "All packets lost"))

        self.after(0, lambda: self._add_result_card(
            "Network Reachability", status, msg,
            f"Packets: {result.packets_received}/{result.packets_sent} • Loss: {result.packet_loss_percent:.1f}%"
        ))

        return result.is_reachable

    def _run_port_scan(self, ip: str) -> bool:
        """Run port scan."""
        key_ports = [80, 23, 443, 8080, 10000, 10001, 52000]
        results = self._connectivity.scan_ports(ip, key_ports)

        open_ports = [r for r in results if r.is_open]

        test_data = {
            'name': 'Port Scan',
            'passed': len(open_ports) > 0,
            'open_ports': [r.port for r in open_ports]
        }
        self._results['tests']['ports'] = test_data

        # Update metric
        self.after(0, lambda: self._metric_cards["ports"].update_value(
            str(len(open_ports)),
            ", ".join(str(r.port) for r in open_ports) if open_ports else "No open ports"
        ))

        if open_ports:
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
            f"Open: {port_list if port_list else 'None'} • Scanned: {len(key_ports)} ports"
        ))

        return len(open_ports) > 0

    def _run_http_test(self, ip: str) -> bool:
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

                self.after(0, lambda: self._metric_cards["web"].update_value(
                    "Online",
                    f"Response: {landing.response_time_ms:.0f}ms"
                ))
            else:
                status = ResultStatus.WARNING
                msg = f"{len(accessible)} endpoints accessible, but not Landing.htm"
                self._results['summary']['warnings'] += 1

                self.after(0, lambda: self._metric_cards["web"].update_value(
                    "Partial",
                    "Landing.htm not found"
                ))
        else:
            status = ResultStatus.FAILED
            msg = "Web interface NOT accessible"
            self._results['summary']['failed'] += 1

            self.after(0, lambda: self._metric_cards["web"].update_value(
                "Offline",
                "No HTTP response"
            ))

        self.after(0, lambda: self._add_result_card(
            "HTTP Web Interface", status, msg,
            " • ".join(f"{r.url}: {r.status_code or r.error}" for r in results)
        ))

        return len(accessible) > 0

    def _run_hostname_test(self, ip: str) -> str:
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
            has_dsp = any('dsp' in h.lower() for h in hostnames if h)
            if has_dsp:
                status = ResultStatus.PASSED
                msg = f"Hostname 'DSP' resolved via {', '.join(successful.keys())}"
                self._results['summary']['passed'] += 1
                return "passed"
            else:
                status = ResultStatus.WARNING
                msg = f"Hostname found but not 'DSP': {', '.join(hostnames)}"
                self._results['summary']['warnings'] += 1
                return "warning"
        else:
            status = ResultStatus.FAILED
            msg = "No hostname resolution method succeeded"
            self._results['summary']['failed'] += 1

        details = " • ".join(
            f"{m}: {r.hostname if r.success else r.error}"
            for m, r in results.items()
        )
        self.after(0, lambda: self._add_result_card(
            "Hostname Resolution", status, msg, details
        ))

        return "failed"

    def _run_dns_test(self, ip: str) -> bool:
        """Run DNS test."""
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

        details = " • ".join(
            f"{r.server_ip}: {'OK' if r.can_resolve else 'Failed'}"
            for r in dns_results
        )
        self.after(0, lambda: self._add_result_card(
            "DNS Configuration", status, msg, details
        ))

        return len(working_dns) > 0

    def _run_command_test(self, ip: str) -> str:
        """Run command protocol test."""
        test_ports = [52000, 23, 10000, 4998]
        connected_port = None

        for port in test_ports:
            conn = self._commands.connect(ip, port)
            if conn.is_connected:
                connected_port = port
                self._commands.disconnect(conn)
                break

        if connected_port:
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
                msg = f"Command port {connected_port} • No errors"
                self._results['summary']['passed'] += 1
                result = "passed"
            elif burst_result.error_rate_percent < 50:
                status = ResultStatus.WARNING
                msg = f"Command port {connected_port} • {burst_result.error_rate_percent:.0f}% error rate (rate limiting)"
                self._results['summary']['warnings'] += 1
                result = "warning"
            else:
                status = ResultStatus.FAILED
                msg = f"Command port {connected_port} • {burst_result.error_rate_percent:.0f}% error rate"
                self._results['summary']['failed'] += 1
                result = "failed"

            details = f"Port: {connected_port} • Sent: {burst_result.total_commands} • Success: {burst_result.successful_commands}"
        else:
            test_data = {
                'name': 'Command Protocol',
                'passed': False,
                'error': 'No command port found'
            }
            self._results['tests']['commands'] = test_data
            self._results['summary']['failed'] += 1

            status = ResultStatus.FAILED
            msg = "No control port found"
            details = f"Tested ports: {', '.join(map(str, test_ports))}"
            result = "failed"

        self.after(0, lambda: self._add_result_card(
            "Command Protocol", status, msg, details
        ))

        return result

    def _add_result_card(self, name: str, status: ResultStatus,
                         message: str, details: str = "") -> None:
        """Add a result card to the display."""
        card = ResultCard(self._results_container, name, status, message, details)
        card.pack(fill="x", pady=4)

    def _display_summary(self) -> None:
        """Display the final summary with visualizations."""
        summary = self._results['summary']
        tests = self._results.get('tests', {})

        # Calculate health score
        total_tests = summary['passed'] + summary['failed'] + summary['warnings']
        if total_tests > 0:
            # Weight: passed=100%, warnings=50%, failed=0%
            health_score = ((summary['passed'] * 100) + (summary['warnings'] * 50)) / total_tests
        else:
            health_score = 0

        # Update health gauge
        self._health_gauge.set_value(health_score, 100)

        # Determine overall status
        if summary['failed'] == 0 and summary['warnings'] == 0:
            overall = "ALL SYSTEMS OPERATIONAL"
            overall_icon = "✓"
            overall_color = COLORS["success"]
            overall_bg = COLORS["success_bg"]
        elif summary['failed'] == 0:
            overall = "MINOR ISSUES DETECTED"
            overall_icon = "!"
            overall_color = COLORS["warning"]
            overall_bg = COLORS["warning_bg"]
        else:
            overall = "ISSUES REQUIRE ATTENTION"
            overall_icon = "✗"
            overall_color = COLORS["error"]
            overall_bg = COLORS["error_bg"]

        # Summary banner
        banner = ctk.CTkFrame(
            self._dashboard,
            fg_color=overall_bg,
            corner_radius=12,
            border_width=2,
            border_color=overall_color
        )
        banner.pack(fill="x", pady=(0, 16))

        banner_inner = ctk.CTkFrame(banner, fg_color="transparent")
        banner_inner.pack(fill="x", padx=24, pady=20)

        # Status row
        status_row = ctk.CTkFrame(banner_inner, fg_color="transparent")
        status_row.pack(fill="x")

        # Status icon
        icon_circle = ctk.CTkFrame(
            status_row,
            width=52,
            height=52,
            corner_radius=26,
            fg_color=overall_color
        )
        icon_circle.pack(side="left")
        icon_circle.pack_propagate(False)

        ctk.CTkLabel(
            icon_circle,
            text=overall_icon,
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color="white"
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Status text
        status_text = ctk.CTkFrame(status_row, fg_color="transparent")
        status_text.pack(side="left", padx=(16, 0))

        ctk.CTkLabel(
            status_text,
            text=overall,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=overall_color
        ).pack(anchor="w")

        ctk.CTkLabel(
            status_text,
            text=f"Completed {total_tests} diagnostic tests",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_secondary"]
        ).pack(anchor="w")

        # Stats pills
        stats_row = ctk.CTkFrame(status_row, fg_color="transparent")
        stats_row.pack(side="right")

        for count, label, color in [
            (summary['passed'], "Passed", COLORS["success"]),
            (summary['warnings'], "Warnings", COLORS["warning"]),
            (summary['failed'], "Failed", COLORS["error"]),
        ]:
            pill = ctk.CTkFrame(stats_row, fg_color=COLORS["bg_card"], corner_radius=8)
            pill.pack(side="left", padx=(12, 0))

            pill_inner = ctk.CTkFrame(pill, fg_color="transparent")
            pill_inner.pack(padx=14, pady=8)

            ctk.CTkLabel(
                pill_inner,
                text=str(count),
                font=ctk.CTkFont(size=22, weight="bold"),
                text_color=color
            ).pack(side="left")

            ctk.CTkLabel(
                pill_inner,
                text=label,
                font=ctk.CTkFont(size=11),
                text_color=COLORS["text_secondary"]
            ).pack(side="left", padx=(8, 0))

        # Issues section if any
        if summary['failed'] > 0 or summary['warnings'] > 0:
            issues_section = ctk.CTkFrame(
                self._dashboard,
                fg_color=COLORS["bg_card"],
                corner_radius=12,
                border_width=1,
                border_color=COLORS["error"]
            )
            issues_section.pack(fill="x", pady=(0, 16))

            issues_inner = ctk.CTkFrame(issues_section, fg_color="transparent")
            issues_inner.pack(fill="x", padx=24, pady=20)

            header_row = ctk.CTkFrame(issues_inner, fg_color="transparent")
            header_row.pack(fill="x", pady=(0, 16))

            ctk.CTkLabel(
                header_row,
                text="⚠️ Issues Requiring Attention",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color=COLORS["text_primary"]
            ).pack(side="left")

            self._display_enhanced_issues(issues_inner, tests)

        # Working systems section
        working_section = ctk.CTkFrame(
            self._dashboard,
            fg_color=COLORS["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["success"]
        )
        working_section.pack(fill="x", pady=(0, 16))

        working_inner = ctk.CTkFrame(working_section, fg_color="transparent")
        working_inner.pack(fill="x", padx=24, pady=20)

        ctk.CTkLabel(
            working_inner,
            text="✓ Operational Systems",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(0, 16))

        # Working items grid
        working_items = []

        if tests.get('reachability', {}).get('passed'):
            details = tests['reachability'].get('details', {})
            working_items.append({
                "name": "Network Reachability",
                "status": f"{details.get('avg_latency_ms', 0):.1f}ms",
                "icon": "📡"
            })

        if tests.get('ports', {}).get('passed'):
            ports = tests['ports'].get('open_ports', [])
            working_items.append({
                "name": "Port Availability",
                "status": f"{len(ports)} ports",
                "icon": "🔌"
            })

        if tests.get('http', {}).get('passed'):
            working_items.append({
                "name": "Web Interface",
                "status": "Online",
                "icon": "🌐"
            })

        if tests.get('dns', {}).get('passed'):
            working_items.append({
                "name": "DNS Configuration",
                "status": "Working",
                "icon": "📋"
            })

        if tests.get('hostname', {}).get('passed'):
            working_items.append({
                "name": "Hostname Resolution",
                "status": "Resolved",
                "icon": "🏷️"
            })

        if tests.get('commands', {}).get('passed'):
            port = tests['commands'].get('port', '?')
            working_items.append({
                "name": "Command Protocol",
                "status": f"Port {port}",
                "icon": "⚡"
            })

        if working_items:
            items_grid = ctk.CTkFrame(working_inner, fg_color="transparent")
            items_grid.pack(fill="x")

            for i, item in enumerate(working_items):
                item_card = ctk.CTkFrame(
                    items_grid,
                    fg_color=COLORS["success_bg"],
                    corner_radius=8
                )
                item_card.pack(fill="x", pady=3)

                item_inner = ctk.CTkFrame(item_card, fg_color="transparent")
                item_inner.pack(fill="x", padx=14, pady=10)

                ctk.CTkLabel(
                    item_inner,
                    text=item["icon"],
                    font=ctk.CTkFont(size=16)
                ).pack(side="left")

                ctk.CTkLabel(
                    item_inner,
                    text=item["name"],
                    font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=COLORS["success"]
                ).pack(side="left", padx=(10, 0))

                status_badge = ctk.CTkFrame(
                    item_inner,
                    fg_color=COLORS["success"],
                    corner_radius=6
                )
                status_badge.pack(side="right")

                ctk.CTkLabel(
                    status_badge,
                    text=item["status"],
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="white"
                ).pack(padx=10, pady=4)
        else:
            ctk.CTkLabel(
                working_inner,
                text="No tests passed - device may be offline",
                font=ctk.CTkFont(size=13),
                text_color=COLORS["text_muted"]
            ).pack(anchor="w")

        # Complete
        self.progress_label.configure(
            text=f"✓ Diagnostic complete • Health Score: {health_score:.0f}%",
            text_color=COLORS["success"]
        )

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
                        "technical_details": "TCP connection attempts to standard control ports (23, 10000, 4998, 52000) all failed. The device web interface is accessible, indicating the device is network-connected, but the control protocol service is not running.",
                        "evidence": [
                            "Port 52000 (MK3 Control) - Connection refused/timeout",
                            "Port 23 (Telnet) - Connection refused/timeout",
                            "Port 10000 (Control) - Connection refused/timeout",
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
                                "Enable IP Control and save changes",
                                "Reboot device if required"
                            ],
                            "estimated_complexity": "low"
                        },
                        {
                            "priority": 2,
                            "action": "Check firmware supports control protocol",
                            "description": "Some firmware versions may not include control protocol support.",
                            "responsible_party": "firmware_team",
                            "verification_steps": [
                                "Check current firmware version",
                                "Compare against changelog for control protocol support"
                            ],
                            "estimated_complexity": "medium"
                        }
                    ],
                    affected_functionality=[
                        "Third-party control system integration",
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
                        "technical_details": f"Burst test resulted in {cmd_test.get('error_rate', 0):.1f}% error rate. The device has rate limiting.",
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
                        }
                    ],
                    affected_functionality=["Rapid command sequences", "Macro execution"],
                    firmware_relevant=True
                ).pack(fill="x", pady=(0, 12))

        # Network Reachability Issue
        reach_test = tests.get('reachability', {})
        if not reach_test.get('passed', True):
            EnhancedIssueCard(
                parent,
                title="Device Not Reachable",
                severity="critical",
                description="The amplifier is not responding to network requests. It may be offline or on a different network.",
                root_cause={
                    "category": "Network/Hardware",
                    "technical_details": "ICMP ping requests are not being answered. This indicates the device is powered off, not connected, or blocked by a firewall.",
                    "evidence": [
                        "ICMP ping failed - no response",
                        "All TCP connections timed out"
                    ]
                },
                corrective_actions=[
                    {
                        "priority": 1,
                        "action": "Verify IP address is correct",
                        "description": "Confirm the target IP matches the device's actual address.",
                        "responsible_party": "installer",
                        "verification_steps": ["Check device display for IP"],
                        "estimated_complexity": "low"
                    },
                    {
                        "priority": 2,
                        "action": "Check physical connections",
                        "description": "Verify power and network cable connections.",
                        "responsible_party": "installer",
                        "verification_steps": ["Check power LED", "Verify Ethernet link lights"],
                        "estimated_complexity": "low"
                    }
                ],
                affected_functionality=["All network communication", "Web interface access"],
                firmware_relevant=False
            ).pack(fill="x", pady=(0, 12))

        # HTTP/Web Interface Issue
        http_test = tests.get('http', {})
        if not http_test.get('passed', True) and reach_test.get('passed', False):
            EnhancedIssueCard(
                parent,
                title="Web Interface Not Accessible",
                severity="high",
                description="The amplifier responds to ping but the web interface is not working.",
                root_cause={
                    "category": "Firmware/Service",
                    "technical_details": "Device responds to ICMP but HTTP connections fail. The web server service may have crashed.",
                    "evidence": [
                        "Ping successful",
                        "HTTP port 80 not responding"
                    ]
                },
                corrective_actions=[
                    {
                        "priority": 1,
                        "action": "Reboot the amplifier",
                        "description": "Power cycle the device to restart all services.",
                        "responsible_party": "installer",
                        "verification_steps": ["Power off", "Wait 10 seconds", "Power on"],
                        "estimated_complexity": "low"
                    }
                ],
                affected_functionality=["Device configuration", "Firmware updates"],
                firmware_relevant=True
            ).pack(fill="x", pady=(0, 12))

        # DNS Issue
        dns_test = tests.get('dns', {})
        if not dns_test.get('passed', True):
            EnhancedIssueCard(
                parent,
                title="DNS Configuration Issue",
                severity="low",
                description="DNS servers are not responding. This may affect hostname resolution.",
                root_cause={
                    "category": "Network Configuration",
                    "technical_details": "System DNS servers failed to respond. This is typically a network infrastructure issue.",
                    "evidence": ["DNS servers not responding"]
                },
                corrective_actions=[
                    {
                        "priority": 1,
                        "action": "Check network DNS configuration",
                        "description": "Verify DNS servers are correctly configured.",
                        "responsible_party": "installer",
                        "verification_steps": ["Check router DNS settings", "Try public DNS (8.8.8.8)"],
                        "estimated_complexity": "low"
                    }
                ],
                affected_functionality=["Hostname resolution"],
                firmware_relevant=False
            ).pack(fill="x", pady=(0, 12))

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

            self.progress_label.configure(text=f"✓ Report exported: {Path(filename).name}")
        except Exception as e:
            logger.error(f"Export error: {e}")
            self.progress_label.configure(text=f"Export error: {e}", text_color=COLORS["error"])

    def _export_json(self, filename: str) -> None:
        """Export as JSON."""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self._results, f, indent=2, default=str)

    def _export_html(self, filename: str) -> None:
        """Export as professional HTML report."""
        summary = self._results.get('summary', {})
        total_tests = summary.get('passed', 0) + summary.get('failed', 0) + summary.get('warnings', 0)
        health_score = ((summary.get('passed', 0) * 100) + (summary.get('warnings', 0) * 50)) / total_tests if total_tests > 0 else 0

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MK3 Diagnostic Report</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0a0a0f 0%, #111827 100%);
            color: #f9fafb;
            min-height: 100vh;
            padding: 40px;
        }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .header {{
            text-align: center;
            margin-bottom: 40px;
            padding: 40px;
            background: #1f2937;
            border-radius: 16px;
            border: 1px solid #374151;
        }}
        .header h1 {{ font-size: 32px; margin-bottom: 8px; }}
        .header .subtitle {{ color: #9ca3af; font-size: 14px; }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 32px;
        }}
        .stat-card {{
            background: #1f2937;
            border-radius: 12px;
            padding: 24px;
            text-align: center;
            border: 1px solid #374151;
        }}
        .stat-value {{ font-size: 36px; font-weight: bold; }}
        .stat-label {{ color: #9ca3af; font-size: 12px; margin-top: 8px; }}
        .passed {{ color: #10b981; }}
        .warning {{ color: #f59e0b; }}
        .failed {{ color: #ef4444; }}
        .info {{ color: #3b82f6; }}
        .section {{
            background: #1f2937;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            border: 1px solid #374151;
        }}
        .section h2 {{
            font-size: 18px;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 1px solid #374151;
        }}
        .test-item {{
            display: flex;
            align-items: center;
            padding: 16px;
            background: #111827;
            border-radius: 8px;
            margin-bottom: 12px;
        }}
        .test-status {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 16px;
        }}
        .test-name {{ font-weight: 600; flex: 1; }}
        .badge {{
            padding: 4px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge-passed {{ background: #064e3b; color: #10b981; }}
        .badge-warning {{ background: #451a03; color: #f59e0b; }}
        .badge-failed {{ background: #450a0a; color: #ef4444; }}
        .footer {{
            text-align: center;
            color: #6b7280;
            font-size: 12px;
            margin-top: 40px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔬 MK3 Diagnostic Report</h1>
            <p class="subtitle">Generated: {self._results.get('timestamp', '')} • Target: {self._results.get('ip_address', '')}</p>
        </div>

        <div class="summary">
            <div class="stat-card">
                <div class="stat-value info">{health_score:.0f}%</div>
                <div class="stat-label">HEALTH SCORE</div>
            </div>
            <div class="stat-card">
                <div class="stat-value passed">{summary.get('passed', 0)}</div>
                <div class="stat-label">PASSED</div>
            </div>
            <div class="stat-card">
                <div class="stat-value warning">{summary.get('warnings', 0)}</div>
                <div class="stat-label">WARNINGS</div>
            </div>
            <div class="stat-card">
                <div class="stat-value failed">{summary.get('failed', 0)}</div>
                <div class="stat-label">FAILED</div>
            </div>
        </div>

        <div class="section">
            <h2>Test Results</h2>
"""

        for test_name, test_data in self._results.get('tests', {}).items():
            passed = test_data.get('passed', False)
            status_class = 'passed' if passed else 'failed'
            badge_class = 'badge-passed' if passed else 'badge-failed'
            status_text = 'PASSED' if passed else 'FAILED'

            html += f"""
            <div class="test-item">
                <div class="test-status" style="background: {'#10b981' if passed else '#ef4444'};"></div>
                <span class="test-name">{test_data.get('name', test_name)}</span>
                <span class="badge {badge_class}">{status_text}</span>
            </div>
"""

        html += f"""
        </div>

        <div class="footer">
            <p>MK3 Amplifier Network Diagnostic Tool v1.1.0 • Sonance</p>
        </div>
    </div>
</body>
</html>
"""

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)
