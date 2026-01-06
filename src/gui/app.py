"""Main application window for MK3 Diagnostic Tool - SaaS-style UI."""

import customtkinter as ctk
import threading
import sys
from typing import Optional, List, Dict
from datetime import datetime
from pathlib import Path
from PIL import Image


def get_resource_path(relative_path: str) -> Path:
    """Get absolute path to resource, works for dev and PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        # Running as compiled executable
        return Path(sys._MEIPASS) / relative_path
    # Running in development
    return Path(__file__).parent.parent.parent / relative_path

from ..utils import setup_logging, get_logger, Config, get_log_buffer
from ..network import NetworkDiscovery, ConnectivityTester, DNSTester, HostnameTester, CommandTester
from ..network.discovery import DiscoveredDevice
from .components import LogViewer

logger = get_logger(__name__)


class MK3DiagnosticApp(ctk.CTk):
    """
    Main application window with modern SaaS-style sidebar navigation.
    """

    # Color scheme - Sonance light blue theme
    COLORS = {
        'sidebar_bg': "#1a1a2e",
        'sidebar_hover': "#16213e",
        'sidebar_selected': "#0f3460",
        'accent': "#4a9fd4",           # Sonance light blue
        'accent_hover': "#6bb3e0",     # Lighter blue on hover
        'success': "#27ae60",
        'warning': "#f39c12",
        'error': "#e74c3c",
        'text_primary': "#ffffff",
        'text_secondary': "#a0a0a0",
        'card_bg': "#16213e",
        'main_bg': "#0f0f1a",
    }

    # Font family
    FONT_FAMILY = "Montserrat"

    def __init__(self):
        super().__init__()

        # Load configuration
        self.config = Config.load()

        # Set up logging
        self.log_buffer = setup_logging()

        # Configure window
        self.title("MK3 Network Diagnostic Tool")
        self.geometry("1400x900")
        self.minsize(1200, 700)

        # Set dark theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=self.COLORS['main_bg'])

        # Initialize testers
        self._discovery = NetworkDiscovery()
        self._connectivity = ConnectivityTester()
        self._dns = DNSTester()
        self._hostname = HostnameTester()
        self._commands = CommandTester()

        # State
        self._discovered_devices: List[DiscoveredDevice] = []
        self._selected_devices: Dict[str, bool] = {}  # IP -> selected
        self._current_view = "discovery"
        self._diagnostic_results: Dict[str, dict] = {}  # IP -> results
        self._device_checkboxes: Dict[str, ctk.BooleanVar] = {}
        self._device_cards: Dict[str, ctk.CTkFrame] = {}  # IP -> card widget
        self._is_scanning = False
        self._arp_cache: Dict[str, str] = {}  # IP -> MAC cache

        # Build UI
        self._build_ui()

        # Bind close event
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        logger.info("MK3 Diagnostic Tool started")

    def _build_ui(self) -> None:
        """Build the main UI with sidebar layout."""
        # Configure grid
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self._build_sidebar()

        # Main content area
        self._build_main_content()

    def _build_sidebar(self) -> None:
        """Build the left sidebar navigation."""
        self.sidebar = ctk.CTkFrame(
            self,
            width=220,
            corner_radius=0,
            fg_color=self.COLORS['sidebar_bg']
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Logo/Title
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", pady=(20, 30))

        # Top row with logo image and "SONANCE" text
        logo_row = ctk.CTkFrame(logo_frame, fg_color="transparent")
        logo_row.pack()

        # Load and display logo image
        logo_path = get_resource_path("public/sonanceA.png")
        if logo_path.exists():
            logo_image = Image.open(logo_path)
            # Resize to fit nicely (32x32 pixels)
            self._logo_ctk = ctk.CTkImage(light_image=logo_image, dark_image=logo_image, size=(32, 32))
            ctk.CTkLabel(
                logo_row,
                image=self._logo_ctk,
                text=""
            ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            logo_row,
            text="SONANCE",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=24, weight="bold"),
            text_color=self.COLORS['accent']
        ).pack(side="left")

        ctk.CTkLabel(
            logo_frame,
            text="MK3 Diagnostics",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            text_color=self.COLORS['text_secondary']
        ).pack()

        # Navigation buttons
        self.nav_buttons = {}

        nav_items = [
            ("discovery", "Discovery", "Find amplifiers on your network"),
            ("diagnostics", "Diagnostics", "View diagnostic results"),
            ("commands", "Quick Tests", "Run individual tests"),
            ("control", "Control", "Send MK3 commands"),
            ("logs", "Logs", "View activity logs"),
        ]

        for view_id, label, tooltip in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=f"  {label}",
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
                fg_color="transparent",
                hover_color=self.COLORS['sidebar_hover'],
                anchor="w",
                height=45,
                corner_radius=8,
                command=lambda v=view_id: self._switch_view(v)
            )
            btn.pack(fill="x", padx=10, pady=2)
            self.nav_buttons[view_id] = btn

        # Spacer
        ctk.CTkFrame(self.sidebar, fg_color="transparent", height=20).pack(fill="x")

        # Separator
        ctk.CTkFrame(self.sidebar, fg_color=self.COLORS['sidebar_hover'], height=1).pack(fill="x", padx=15)

        # Quick stats (will be updated)
        self.stats_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.stats_frame.pack(fill="x", pady=20, padx=15)

        ctk.CTkLabel(
            self.stats_frame,
            text="Quick Stats",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12, weight="bold"),
            text_color=self.COLORS['text_secondary']
        ).pack(anchor="w")

        self.stat_devices = ctk.CTkLabel(
            self.stats_frame,
            text="Devices found: 0",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            text_color=self.COLORS['text_primary']
        )
        self.stat_devices.pack(anchor="w", pady=(5, 0))

        self.stat_selected = ctk.CTkLabel(
            self.stats_frame,
            text="Selected: 0",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            text_color=self.COLORS['text_primary']
        )
        self.stat_selected.pack(anchor="w")

        # Bottom section - version
        bottom_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom_frame.pack(side="bottom", fill="x", pady=15)

        from .. import __version__
        ctk.CTkLabel(
            bottom_frame,
            text=f"v{__version__}",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=11),
            text_color=self.COLORS['text_secondary']
        ).pack()

        # Set initial selection
        self._update_nav_selection("discovery")

    def _build_main_content(self) -> None:
        """Build the main content area."""
        self.main_frame = ctk.CTkFrame(self, fg_color=self.COLORS['main_bg'], corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        # Content frames (we'll switch between these)
        self.views = {}

        # Discovery View
        self.views['discovery'] = self._build_discovery_view()

        # Diagnostics View
        self.views['diagnostics'] = self._build_diagnostics_view()

        # Commands View (Quick Tests)
        self.views['commands'] = self._build_commands_view()

        # Control View (MK3 Commands)
        self.views['control'] = self._build_control_view()

        # Logs View
        self.views['logs'] = self._build_logs_view()

        # Show discovery by default
        self._switch_view("discovery")

    def _build_discovery_view(self) -> ctk.CTkFrame:
        """Build the discovery view."""
        view = ctk.CTkFrame(self.main_frame, fg_color="transparent")

        # Header with hostname on right
        header = ctk.CTkFrame(view, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(30, 20))

        ctk.CTkLabel(
            header,
            text="Network Discovery",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=28, weight="bold"),
            text_color=self.COLORS['text_primary']
        ).pack(side="left")

        # Hostname entry on right side of header
        hostname_frame = ctk.CTkFrame(header, fg_color="transparent")
        hostname_frame.pack(side="right")

        ctk.CTkLabel(
            hostname_frame,
            text="Hostname:",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            text_color=self.COLORS['text_secondary']
        ).pack(side="left", padx=(0, 8))

        self.hostname_entry = ctk.CTkEntry(
            hostname_frame,
            placeholder_text="(auto-detected)",
            width=180,
            height=32,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            fg_color=self.COLORS['card_bg'],
            border_width=1,
            border_color=self.COLORS['sidebar_hover']
        )
        self.hostname_entry.pack(side="left")

        # Scan controls - Clean grid layout
        controls = ctk.CTkFrame(view, fg_color=self.COLORS['card_bg'], corner_radius=12)
        controls.pack(fill="x", padx=30, pady=(0, 20))

        # Configure grid columns
        controls.grid_columnconfigure(0, weight=0, minsize=100)  # Labels
        controls.grid_columnconfigure(1, weight=0)  # Start IP
        controls.grid_columnconfigure(2, weight=0)  # "to" label
        controls.grid_columnconfigure(3, weight=0)  # End IP
        controls.grid_columnconfigure(4, weight=1)  # Spacer
        controls.grid_columnconfigure(5, weight=0)  # Buttons

        # Row 0: IP Range
        ctk.CTkLabel(
            controls,
            text="IP Range:",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14, weight="bold"),
            text_color=self.COLORS['text_secondary'],
            anchor="e"
        ).grid(row=0, column=0, sticky="e", padx=(20, 10), pady=(20, 8))

        self.ip_start_entry = ctk.CTkEntry(
            controls,
            placeholder_text="Start IP",
            width=160,
            height=38,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14)
        )
        self.ip_start_entry.grid(row=0, column=1, padx=5, pady=(20, 8))

        ctk.CTkLabel(
            controls,
            text="to",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            text_color=self.COLORS['text_secondary']
        ).grid(row=0, column=2, padx=8, pady=(20, 8))

        self.ip_end_entry = ctk.CTkEntry(
            controls,
            placeholder_text="End IP",
            width=160,
            height=38,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14)
        )
        self.ip_end_entry.grid(row=0, column=3, padx=5, pady=(20, 8))

        # Buttons frame (right side)
        btn_frame = ctk.CTkFrame(controls, fg_color="transparent")
        btn_frame.grid(row=0, column=5, padx=(10, 20), pady=(20, 8), sticky="e")

        self.scan_btn = ctk.CTkButton(
            btn_frame,
            text="▶  Start Scan",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14, weight="bold"),
            fg_color=self.COLORS['accent'],
            hover_color=self.COLORS['accent_hover'],
            height=38,
            width=140,
            command=self._toggle_scan
        )
        self.scan_btn.pack(side="left", padx=(0, 10))

        self.auto_detect_btn = ctk.CTkButton(
            btn_frame,
            text="Auto-Detect",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            fg_color="transparent",
            hover_color=self.COLORS['sidebar_hover'],
            border_width=1,
            border_color=self.COLORS['text_secondary'],
            height=38,
            width=110,
            command=self._auto_detect_range
        )
        self.auto_detect_btn.pack(side="left")

        # Row 1: Add IP
        ctk.CTkLabel(
            controls,
            text="Add IP:",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14, weight="bold"),
            text_color=self.COLORS['text_secondary'],
            anchor="e"
        ).grid(row=1, column=0, sticky="e", padx=(20, 10), pady=8)

        add_ip_frame = ctk.CTkFrame(controls, fg_color="transparent")
        add_ip_frame.grid(row=1, column=1, columnspan=3, sticky="w", padx=5, pady=8)

        self.manual_ip_entry = ctk.CTkEntry(
            add_ip_frame,
            placeholder_text="e.g., 192.168.1.100",
            width=200,
            height=38,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14)
        )
        self.manual_ip_entry.pack(side="left", padx=(0, 10))

        self.add_ip_btn = ctk.CTkButton(
            add_ip_frame,
            text="+ Add",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13, weight="bold"),
            fg_color=self.COLORS['success'],
            hover_color="#219a52",
            width=80,
            height=38,
            command=self._add_manual_ip
        )
        self.add_ip_btn.pack(side="left")

        # Row 2: Progress bar and status
        progress_frame = ctk.CTkFrame(controls, fg_color="transparent")
        progress_frame.grid(row=2, column=0, columnspan=6, sticky="ew", padx=20, pady=(5, 20))

        self.scan_progress_bar = ctk.CTkProgressBar(
            progress_frame,
            width=400,
            height=8,
            progress_color=self.COLORS['accent'],
            fg_color=self.COLORS['sidebar_hover']
        )
        self.scan_progress_bar.pack(side="left", padx=(0, 15))
        self.scan_progress_bar.set(0)

        self.scan_progress = ctk.CTkLabel(
            progress_frame,
            text="Ready to scan",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            text_color=self.COLORS['text_secondary'],
            anchor="w"
        )
        self.scan_progress.pack(side="left", fill="x", expand=True)

        # Auto-detect on startup
        self.after(100, self._auto_detect_range)

        # Action bar (appears when devices selected)
        self.action_bar = ctk.CTkFrame(view, fg_color=self.COLORS['accent'], corner_radius=12)

        action_inner = ctk.CTkFrame(self.action_bar, fg_color="transparent")
        action_inner.pack(fill="x", padx=20, pady=12)

        self.action_label = ctk.CTkLabel(
            action_inner,
            text="0 devices selected",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14, weight="bold"),
            text_color="white"
        )
        self.action_label.pack(side="left")

        # Action buttons
        self.run_diag_btn = ctk.CTkButton(
            action_inner,
            text="Run Full Diagnostics",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13, weight="bold"),
            fg_color="white",
            text_color=self.COLORS['accent'],
            hover_color="#f0f0f0",
            height=35,
            command=self._run_diagnostics_on_selected
        )
        self.run_diag_btn.pack(side="right", padx=(10, 0))

        self.run_tests_menu = ctk.CTkOptionMenu(
            action_inner,
            values=["Run Individual Test...", "Ping Test", "Port Scan", "HTTP Test", "Hostname Test", "DNS Test", "Command Test"],
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
            fg_color="white",
            text_color=self.COLORS['sidebar_bg'],
            button_color="#e0e0e0",
            button_hover_color="#d0d0d0",
            dropdown_fg_color="white",
            dropdown_text_color=self.COLORS['sidebar_bg'],
            height=35,
            command=self._run_individual_test
        )
        self.run_tests_menu.pack(side="right", padx=10)

        self.select_all_btn = ctk.CTkButton(
            action_inner,
            text="Select All",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
            fg_color="transparent",
            text_color="white",
            hover_color="#ff8080",
            border_width=1,
            border_color="white",
            height=32,
            width=90,
            command=self._toggle_select_all
        )
        self.select_all_btn.pack(side="right", padx=10)

        # Device list header
        self.list_header_frame = ctk.CTkFrame(view, fg_color="transparent")
        self.list_header_frame.pack(fill="x", padx=30, pady=(0, 10))

        ctk.CTkLabel(
            self.list_header_frame,
            text="Discovered Devices",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=18, weight="bold")
        ).pack(side="left")

        self.device_count_label = ctk.CTkLabel(
            self.list_header_frame,
            text="0 devices",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            text_color=self.COLORS['text_secondary']
        )
        self.device_count_label.pack(side="right")

        # Device list (scrollable)
        self.device_list_frame = ctk.CTkScrollableFrame(
            view,
            fg_color="transparent",
            corner_radius=0
        )
        self.device_list_frame.pack(fill="both", expand=True, padx=30, pady=(0, 20))

        # Placeholder when empty
        self._show_empty_placeholder()

        return view

    def _show_empty_placeholder(self) -> None:
        """Show empty state placeholder."""
        self.empty_placeholder = ctk.CTkFrame(self.device_list_frame, fg_color="transparent")
        self.empty_placeholder.pack(fill="both", expand=True, pady=50)

        ctk.CTkLabel(
            self.empty_placeholder,
            text="No devices discovered yet",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=18),
            text_color=self.COLORS['text_secondary']
        ).pack()

        ctk.CTkLabel(
            self.empty_placeholder,
            text="Click 'Start Scan' to find MK3 amplifiers on your network,\nor manually add an IP address above.",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            text_color=self.COLORS['text_secondary']
        ).pack(pady=(10, 0))

    def _show_scanning_placeholder(self) -> None:
        """Show scanning animation placeholder."""
        self._scanning_placeholder = ctk.CTkFrame(self.device_list_frame, fg_color="transparent")
        self._scanning_placeholder.pack(fill="both", expand=True, pady=50)

        # Spinner label
        self._spinner_label = ctk.CTkLabel(
            self._scanning_placeholder,
            text="◐",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=48),
            text_color=self.COLORS['accent']
        )
        self._spinner_label.pack()

        ctk.CTkLabel(
            self._scanning_placeholder,
            text="Scanning network...",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=18),
            text_color=self.COLORS['text_secondary']
        ).pack(pady=(15, 0))

        self._scanning_text_label = ctk.CTkLabel(
            self._scanning_placeholder,
            text="Looking for devices on your network",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            text_color=self.COLORS['text_secondary']
        )
        self._scanning_text_label.pack(pady=(5, 0))

        # Start spinner animation
        self._spinner_chars = ["◐", "◓", "◑", "◒"]
        self._spinner_index = 0
        self._animate_spinner()

    def _animate_spinner(self) -> None:
        """Animate the spinner."""
        if not self._is_scanning:
            return
        if not hasattr(self, '_spinner_label') or not self._spinner_label.winfo_exists():
            return

        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_chars)
        self._spinner_label.configure(text=self._spinner_chars[self._spinner_index])
        self.after(100, self._animate_spinner)

    def _hide_scanning_placeholder(self) -> None:
        """Hide the scanning placeholder."""
        if hasattr(self, '_scanning_placeholder') and self._scanning_placeholder.winfo_exists():
            self._scanning_placeholder.destroy()

    def _build_diagnostics_view(self) -> ctk.CTkFrame:
        """Build the diagnostics results view."""
        view = ctk.CTkFrame(self.main_frame, fg_color="transparent")

        # Header
        header = ctk.CTkFrame(view, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(30, 20))

        ctk.CTkLabel(
            header,
            text="Diagnostic Results",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=28, weight="bold"),
            text_color=self.COLORS['text_primary']
        ).pack(side="left")

        # Clear results button
        self.clear_results_btn = ctk.CTkButton(
            header,
            text="Clear All Results",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            fg_color="transparent",
            hover_color=self.COLORS['card_bg'],
            border_width=1,
            border_color=self.COLORS['text_secondary'],
            height=35,
            command=self._clear_diagnostic_results
        )
        self.clear_results_btn.pack(side="right")

        # Export button
        self.export_btn = ctk.CTkButton(
            header,
            text="Export All",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            fg_color=self.COLORS['success'],
            hover_color="#219a52",
            height=35,
            command=self._export_results
        )
        self.export_btn.pack(side="right", padx=10)

        # Results container (scrollable)
        self.results_container = ctk.CTkScrollableFrame(
            view,
            fg_color="transparent"
        )
        self.results_container.pack(fill="both", expand=True, padx=30, pady=(0, 20))

        # Placeholder
        self.results_placeholder = ctk.CTkLabel(
            self.results_container,
            text="No diagnostic results yet.\nSelect devices in Discovery and run diagnostics.",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=16),
            text_color=self.COLORS['text_secondary'],
            justify="center"
        )
        self.results_placeholder.pack(pady=100)

        return view

    def _build_commands_view(self) -> ctk.CTkFrame:
        """Build the quick tests view for running individual diagnostic tests."""
        view = ctk.CTkFrame(self.main_frame, fg_color="transparent")

        # Header
        header = ctk.CTkFrame(view, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(30, 20))

        ctk.CTkLabel(
            header,
            text="Quick Tests",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=28, weight="bold")
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="Run individual diagnostic tests on a single IP address",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            text_color=self.COLORS['text_secondary']
        ).pack(side="right")

        # Target IP input card
        target_frame = ctk.CTkFrame(view, fg_color=self.COLORS['card_bg'], corner_radius=12)
        target_frame.pack(fill="x", padx=30, pady=(0, 20))

        target_inner = ctk.CTkFrame(target_frame, fg_color="transparent")
        target_inner.pack(fill="x", padx=20, pady=15)

        ctk.CTkLabel(
            target_inner,
            text="Target IP:",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14, weight="bold")
        ).pack(side="left")

        self.quick_test_ip_entry = ctk.CTkEntry(
            target_inner,
            width=200,
            height=38,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            placeholder_text="e.g., 10.179.3.91"
        )
        self.quick_test_ip_entry.pack(side="left", padx=(15, 20))

        # Status indicator
        self.quick_test_status = ctk.CTkLabel(
            target_inner,
            text="Enter an IP address to begin testing",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            text_color=self.COLORS['text_secondary']
        )
        self.quick_test_status.pack(side="left", padx=10)

        # Run All button
        self.run_all_tests_btn = ctk.CTkButton(
            target_inner,
            text="Run All Tests",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13, weight="bold"),
            fg_color=self.COLORS['accent'],
            hover_color=self.COLORS['accent_hover'],
            height=38,
            width=120,
            command=self._run_all_quick_tests
        )
        self.run_all_tests_btn.pack(side="right")

        # Test buttons grid
        tests_label = ctk.CTkLabel(
            view,
            text="Available Tests",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=18, weight="bold")
        )
        tests_label.pack(anchor="w", padx=30, pady=(10, 15))

        tests_grid = ctk.CTkFrame(view, fg_color="transparent")
        tests_grid.pack(fill="x", padx=30, pady=(0, 20))

        # Configure grid columns
        for i in range(3):
            tests_grid.grid_columnconfigure(i, weight=1, uniform="test_col")

        # Test definitions: (name, description, icon, color, command)
        test_buttons = [
            ("Ping Test", "Check network reachability\nand measure latency", "ping", self.COLORS['accent'], self._quick_ping_test),
            ("Port Scan", "Scan common ports\n(80, 23, 8080, etc.)", "ports", "#9b59b6", self._quick_port_test),
            ("HTTP Test", "Test web interface\naccessibility", "http", "#3498db", self._quick_http_test),
            ("Hostname Test", "Resolve hostname via\nmultiple methods", "hostname", "#1abc9c", self._quick_hostname_test),
            ("DNS Test", "Verify DNS server\nconfiguration", "dns", "#e67e22", self._quick_dns_test),
            ("Command Port", "Test control ports\n(23, 10000, 4998)", "cmd", "#e74c3c", self._quick_command_test),
        ]

        self._quick_test_buttons = {}

        for idx, (name, desc, test_id, color, cmd) in enumerate(test_buttons):
            row = idx // 3
            col = idx % 3

            btn_frame = ctk.CTkFrame(tests_grid, fg_color=self.COLORS['card_bg'], corner_radius=10)
            btn_frame.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

            btn_inner = ctk.CTkFrame(btn_frame, fg_color="transparent")
            btn_inner.pack(fill="both", expand=True, padx=15, pady=15)

            # Test name with colored indicator
            name_row = ctk.CTkFrame(btn_inner, fg_color="transparent")
            name_row.pack(fill="x")

            indicator = ctk.CTkFrame(name_row, fg_color=color, width=8, height=8, corner_radius=4)
            indicator.pack(side="left", padx=(0, 10))

            ctk.CTkLabel(
                name_row,
                text=name,
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=15, weight="bold"),
                text_color=self.COLORS['text_primary']
            ).pack(side="left")

            # Description
            ctk.CTkLabel(
                btn_inner,
                text=desc,
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
                text_color=self.COLORS['text_secondary'],
                justify="left"
            ).pack(anchor="w", pady=(8, 12))

            # Run button
            run_btn = ctk.CTkButton(
                btn_inner,
                text="Run Test",
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=12, weight="bold"),
                fg_color=color,
                hover_color=color,
                height=32,
                command=cmd
            )
            run_btn.pack(fill="x")
            self._quick_test_buttons[test_id] = run_btn

        # Command sending section
        cmd_label = ctk.CTkLabel(
            view,
            text="Send Commands",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=18, weight="bold")
        )
        cmd_label.pack(anchor="w", padx=30, pady=(10, 10))

        cmd_frame = ctk.CTkFrame(view, fg_color=self.COLORS['card_bg'], corner_radius=12)
        cmd_frame.pack(fill="x", padx=30, pady=(0, 20))

        cmd_inner = ctk.CTkFrame(cmd_frame, fg_color="transparent")
        cmd_inner.pack(fill="x", padx=20, pady=15)

        # Port selection
        ctk.CTkLabel(
            cmd_inner,
            text="Port:",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13)
        ).pack(side="left")

        self.cmd_port_entry = ctk.CTkEntry(
            cmd_inner,
            width=80,
            height=36,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13)
        )
        self.cmd_port_entry.pack(side="left", padx=(10, 5))
        self.cmd_port_entry.insert(0, "23")

        # Port presets
        self.port_presets = ctk.CTkOptionMenu(
            cmd_inner,
            values=["23 (Telnet)", "80 (HTTP)", "10000", "4998", "52000 (MK3)"],
            command=self._on_port_preset_select,
            width=120,
            height=36,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12)
        )
        self.port_presets.set("Presets")
        self.port_presets.pack(side="left", padx=(5, 20))

        # Command entry
        ctk.CTkLabel(
            cmd_inner,
            text="Command:",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13)
        ).pack(side="left")

        self.command_entry = ctk.CTkEntry(
            cmd_inner,
            width=300,
            height=36,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            placeholder_text="Enter command to send"
        )
        self.command_entry.pack(side="left", padx=(10, 15))
        self.command_entry.bind("<Return>", lambda e: self._send_command())

        # Send button
        self.send_cmd_btn = ctk.CTkButton(
            cmd_inner,
            text="Send",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13, weight="bold"),
            fg_color=self.COLORS['accent'],
            hover_color=self.COLORS['accent_hover'],
            height=36,
            width=80,
            command=self._send_command
        )
        self.send_cmd_btn.pack(side="left", padx=(0, 10))

        # Burst test button
        self.burst_btn = ctk.CTkButton(
            cmd_inner,
            text="Burst (10x)",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
            fg_color=self.COLORS['warning'],
            hover_color="#e67e22",
            height=36,
            width=90,
            command=self._run_burst_test
        )
        self.burst_btn.pack(side="left")

        # Results section
        results_header = ctk.CTkFrame(view, fg_color="transparent")
        results_header.pack(fill="x", padx=30, pady=(10, 10))

        ctk.CTkLabel(
            results_header,
            text="Results Log",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=18, weight="bold")
        ).pack(side="left")

        self.clear_quick_results_btn = ctk.CTkButton(
            results_header,
            text="Clear",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
            fg_color="transparent",
            hover_color=self.COLORS['card_bg'],
            border_width=1,
            border_color=self.COLORS['text_secondary'],
            height=30,
            width=70,
            command=self._clear_quick_test_results
        )
        self.clear_quick_results_btn.pack(side="right")

        # Results log
        self.quick_test_log = ctk.CTkTextbox(
            view,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=self.COLORS['card_bg'],
            corner_radius=12
        )
        self.quick_test_log.pack(fill="both", expand=True, padx=30, pady=(0, 20))

        # Add initial message
        self.quick_test_log.insert("end", "Quick Tests & Commands\n")
        self.quick_test_log.insert("end", "=" * 50 + "\n")
        self.quick_test_log.insert("end", "Enter a target IP address above and click a test button,\n")
        self.quick_test_log.insert("end", "or send TCP commands directly using the command input.\n\n")

        return view

    def _build_control_view(self) -> ctk.CTkFrame:
        """Build the MK3 control panel view."""
        from ..network import (
            MK3Command, MK3GroupCommand, MK3ProtocolTester,
            get_hex_string, OutputGroup, ChannelIndex
        )

        view = ctk.CTkFrame(self.main_frame, fg_color="transparent")

        # Create scrollable frame for content
        scroll_frame = ctk.CTkScrollableFrame(view, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True)

        # Header
        header = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(30, 20))

        ctk.CTkLabel(
            header,
            text="MK3 Control Panel",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=28, weight="bold")
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="Send commands to MK3 DSP amplifiers via port 52000",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            text_color=self.COLORS['text_secondary']
        ).pack(side="right")

        # Target IP and Model row
        target_frame = ctk.CTkFrame(scroll_frame, fg_color=self.COLORS['card_bg'], corner_radius=12)
        target_frame.pack(fill="x", padx=30, pady=(0, 15))

        target_inner = ctk.CTkFrame(target_frame, fg_color="transparent")
        target_inner.pack(fill="x", padx=20, pady=15)

        ctk.CTkLabel(
            target_inner,
            text="Target IP:",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14, weight="bold")
        ).pack(side="left")

        self.control_ip_entry = ctk.CTkEntry(
            target_inner,
            width=180,
            height=36,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            placeholder_text="e.g., 10.179.3.91"
        )
        self.control_ip_entry.pack(side="left", padx=(10, 25))

        ctk.CTkLabel(
            target_inner,
            text="Model:",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14, weight="bold")
        ).pack(side="left")

        self.model_selector = ctk.CTkOptionMenu(
            target_inner,
            values=["DSP8-130 (8 groups)", "DSP2-150 (2 groups)", "DSP2-750 (2 groups)"],
            width=180,
            height=36,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            command=self._on_model_change
        )
        self.model_selector.set("DSP8-130 (8 groups)")
        self.model_selector.pack(side="left", padx=(10, 25))

        # Status indicator
        self.control_status = ctk.CTkLabel(
            target_inner,
            text="Not connected",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            text_color=self.COLORS['text_secondary']
        )
        self.control_status.pack(side="right")

        # Power Controls
        power_frame = ctk.CTkFrame(scroll_frame, fg_color=self.COLORS['card_bg'], corner_radius=12)
        power_frame.pack(fill="x", padx=30, pady=(0, 15))

        power_header = ctk.CTkFrame(power_frame, fg_color="transparent")
        power_header.pack(fill="x", padx=20, pady=(15, 10))

        ctk.CTkLabel(
            power_header,
            text="Power Controls",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=16, weight="bold")
        ).pack(side="left")

        power_btns = ctk.CTkFrame(power_frame, fg_color="transparent")
        power_btns.pack(fill="x", padx=20, pady=(0, 15))

        power_commands = [
            ("Power ON", MK3Command.POWER_ON, self.COLORS['success']),
            ("Power OFF", MK3Command.POWER_OFF, self.COLORS['error']),
            ("Toggle", MK3Command.POWER_TOGGLE, self.COLORS['warning']),
            ("Query Status", MK3Command.POWER_QUERY, self.COLORS['accent']),
        ]

        for name, cmd, color in power_commands:
            btn = ctk.CTkButton(
                power_btns,
                text=name,
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=13, weight="bold"),
                fg_color=color,
                hover_color=color,
                height=36,
                width=110,
                command=lambda c=cmd: self._send_mk3_global_command(c)
            )
            btn.pack(side="left", padx=(0, 10))

        # Global Controls
        global_frame = ctk.CTkFrame(scroll_frame, fg_color=self.COLORS['card_bg'], corner_radius=12)
        global_frame.pack(fill="x", padx=30, pady=(0, 15))

        global_header = ctk.CTkFrame(global_frame, fg_color="transparent")
        global_header.pack(fill="x", padx=20, pady=(15, 10))

        ctk.CTkLabel(
            global_header,
            text="Global Controls (All Groups)",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=16, weight="bold")
        ).pack(side="left")

        # Volume row
        vol_row = ctk.CTkFrame(global_frame, fg_color="transparent")
        vol_row.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(
            vol_row,
            text="Volume:",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            width=70
        ).pack(side="left")

        vol_btns = [
            ("Vol -", MK3Command.VOLUME_DOWN),
            ("Vol +", MK3Command.VOLUME_UP),
            ("-3dB", lambda: bytes([0xFF, 0x55, 0x01, 0x0F])),
            ("+3dB", lambda: bytes([0xFF, 0x55, 0x01, 0x0E])),
        ]

        for name, cmd in vol_btns:
            btn = ctk.CTkButton(
                vol_row,
                text=name,
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
                fg_color=self.COLORS['accent'],
                hover_color=self.COLORS['accent_hover'],
                height=32,
                width=65,
                command=lambda c=cmd: self._send_mk3_global_command(c) if hasattr(c, 'value') else self._send_mk3_raw_command(c())
            )
            btn.pack(side="left", padx=(0, 5))

        # Direct volume slider
        ctk.CTkLabel(vol_row, text="Direct:", font=ctk.CTkFont(family=self.FONT_FAMILY, size=12)).pack(side="left", padx=(15, 5))

        self.global_vol_slider = ctk.CTkSlider(
            vol_row,
            from_=-70,
            to=0,
            number_of_steps=70,
            width=150,
            command=self._on_global_volume_change
        )
        self.global_vol_slider.set(-30)
        self.global_vol_slider.pack(side="left", padx=(0, 5))

        self.global_vol_label = ctk.CTkLabel(vol_row, text="-30 dB", font=ctk.CTkFont(family=self.FONT_FAMILY, size=12), width=50)
        self.global_vol_label.pack(side="left")

        ctk.CTkButton(
            vol_row,
            text="Set",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12, weight="bold"),
            fg_color=self.COLORS['success'],
            height=32,
            width=50,
            command=self._set_global_volume
        ).pack(side="left", padx=(5, 0))

        # Mute row
        mute_row = ctk.CTkFrame(global_frame, fg_color="transparent")
        mute_row.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(mute_row, text="Mute:", font=ctk.CTkFont(family=self.FONT_FAMILY, size=13), width=70).pack(side="left")

        mute_btns = [
            ("Mute ON", MK3Command.MUTE_ON, self.COLORS['error']),
            ("Mute OFF", MK3Command.MUTE_OFF, self.COLORS['success']),
            ("Toggle", MK3Command.MUTE_TOGGLE, self.COLORS['warning']),
        ]

        for name, cmd, color in mute_btns:
            btn = ctk.CTkButton(
                mute_row,
                text=name,
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
                fg_color=color,
                hover_color=color,
                height=32,
                width=80,
                command=lambda c=cmd: self._send_mk3_global_command(c)
            )
            btn.pack(side="left", padx=(0, 5))

        # Source row
        source_row = ctk.CTkFrame(global_frame, fg_color="transparent")
        source_row.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(source_row, text="Source:", font=ctk.CTkFont(family=self.FONT_FAMILY, size=13), width=70).pack(side="left")

        source_btns = [
            ("Input 1", MK3Command.INPUT_1),
            ("Input 2", MK3Command.INPUT_2),
            ("Input 3", MK3Command.INPUT_3),
            ("Input 4", MK3Command.INPUT_4),
        ]

        for name, cmd in source_btns:
            btn = ctk.CTkButton(
                source_row,
                text=name,
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
                fg_color="#9b59b6",
                hover_color="#8e44ad",
                height=32,
                width=70,
                command=lambda c=cmd: self._send_mk3_global_command(c)
            )
            btn.pack(side="left", padx=(0, 5))

        # Per-Group Controls
        group_frame = ctk.CTkFrame(scroll_frame, fg_color=self.COLORS['card_bg'], corner_radius=12)
        group_frame.pack(fill="x", padx=30, pady=(0, 15))

        group_header = ctk.CTkFrame(group_frame, fg_color="transparent")
        group_header.pack(fill="x", padx=20, pady=(15, 10))

        ctk.CTkLabel(
            group_header,
            text="Per-Group Controls",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=16, weight="bold")
        ).pack(side="left")

        ctk.CTkLabel(group_header, text="Group:", font=ctk.CTkFont(family=self.FONT_FAMILY, size=13)).pack(side="left", padx=(20, 5))

        self.group_selector = ctk.CTkOptionMenu(
            group_header,
            values=["A", "B", "C", "D", "E", "F", "G", "H"],
            width=80,
            height=32,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13)
        )
        self.group_selector.set("A")
        self.group_selector.pack(side="left")

        group_btns = ctk.CTkFrame(group_frame, fg_color="transparent")
        group_btns.pack(fill="x", padx=20, pady=(0, 15))

        group_commands = [
            ("Power ON", MK3GroupCommand.POWER_ON, self.COLORS['success']),
            ("Power OFF", MK3GroupCommand.POWER_OFF, self.COLORS['error']),
            ("Vol +", MK3GroupCommand.VOLUME_UP, self.COLORS['accent']),
            ("Vol -", MK3GroupCommand.VOLUME_DOWN, self.COLORS['accent']),
            ("Mute ON", MK3GroupCommand.MUTE_ON, self.COLORS['warning']),
            ("Mute OFF", MK3GroupCommand.MUTE_OFF, "#1abc9c"),
        ]

        for name, cmd, color in group_commands:
            btn = ctk.CTkButton(
                group_btns,
                text=name,
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
                fg_color=color,
                hover_color=color,
                height=32,
                width=75,
                command=lambda c=cmd: self._send_mk3_group_command(c)
            )
            btn.pack(side="left", padx=(0, 5))

        # Query source buttons for group
        query_row = ctk.CTkFrame(group_frame, fg_color="transparent")
        query_row.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(query_row, text="Set Source:", font=ctk.CTkFont(family=self.FONT_FAMILY, size=12)).pack(side="left", padx=(0, 10))

        for i, cmd in enumerate([MK3GroupCommand.SOURCE_1, MK3GroupCommand.SOURCE_2, MK3GroupCommand.SOURCE_3, MK3GroupCommand.SOURCE_4]):
            btn = ctk.CTkButton(
                query_row,
                text=f"Src {i+1}",
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=11),
                fg_color="#9b59b6",
                hover_color="#8e44ad",
                height=28,
                width=55,
                command=lambda c=cmd: self._send_mk3_group_command(c)
            )
            btn.pack(side="left", padx=(0, 5))

        # MK3 Protocol Status Check
        status_frame = ctk.CTkFrame(scroll_frame, fg_color=self.COLORS['card_bg'], corner_radius=12)
        status_frame.pack(fill="x", padx=30, pady=(0, 15))

        status_header = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_header.pack(fill="x", padx=20, pady=(15, 10))

        ctk.CTkLabel(
            status_header,
            text="Protection & Status Queries",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=16, weight="bold")
        ).pack(side="left")

        status_btns = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_btns.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkButton(
            status_btns,
            text="Query All Channel Status",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13, weight="bold"),
            fg_color=self.COLORS['accent'],
            hover_color=self.COLORS['accent_hover'],
            height=36,
            width=180,
            command=self._query_all_channel_status
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            status_btns,
            text="Full MK3 Diagnostic",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13, weight="bold"),
            fg_color="#e67e22",
            hover_color="#d35400",
            height=36,
            width=150,
            command=self._run_mk3_diagnostic
        ).pack(side="left", padx=(0, 10))

        # Response Log
        log_header = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=30, pady=(10, 10))

        ctk.CTkLabel(
            log_header,
            text="Command Log",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=16, weight="bold")
        ).pack(side="left")

        ctk.CTkButton(
            log_header,
            text="Clear",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
            fg_color="transparent",
            hover_color=self.COLORS['card_bg'],
            border_width=1,
            border_color=self.COLORS['text_secondary'],
            height=28,
            width=60,
            command=self._clear_control_log
        ).pack(side="right")

        self.control_log = ctk.CTkTextbox(
            scroll_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=self.COLORS['card_bg'],
            corner_radius=12,
            height=200
        )
        self.control_log.pack(fill="x", padx=30, pady=(0, 20))

        self.control_log.insert("end", "MK3 Control Panel Ready\n")
        self.control_log.insert("end", "=" * 50 + "\n")
        self.control_log.insert("end", "Enter a target IP and use the controls above.\n")
        self.control_log.insert("end", "All commands use TCP port 52000 (MK3 binary protocol).\n\n")

        # Store MK3 protocol tester
        self._mk3_protocol = MK3ProtocolTester(timeout=3.0)

        return view

    def _on_model_change(self, value: str) -> None:
        """Handle model selection change."""
        if "8" in value:
            self.group_selector.configure(values=["A", "B", "C", "D", "E", "F", "G", "H"])
        else:
            self.group_selector.configure(values=["A", "B"])
            if self.group_selector.get() not in ["A", "B"]:
                self.group_selector.set("A")

    def _on_global_volume_change(self, value: float) -> None:
        """Update volume label when slider changes."""
        self.global_vol_label.configure(text=f"{int(value)} dB")

    def _get_control_ip(self) -> Optional[str]:
        """Get the target IP for control commands."""
        ip = self.control_ip_entry.get().strip()
        if not ip:
            self.control_status.configure(text="Please enter a target IP", text_color=self.COLORS['error'])
            return None
        return ip

    def _log_control(self, message: str) -> None:
        """Log a message to the control log."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.control_log.insert("end", f"[{timestamp}] {message}\n")
        self.control_log.see("end")

    def _send_mk3_global_command(self, cmd) -> None:
        """Send a global MK3 command."""
        from ..network import get_hex_string

        ip = self._get_control_ip()
        if not ip:
            return

        cmd_bytes = cmd.value if hasattr(cmd, 'value') else cmd
        hex_str = get_hex_string(cmd_bytes)

        self.control_status.configure(text=f"Sending {hex_str}...", text_color=self.COLORS['accent'])
        self._log_control(f"TX> {hex_str}")

        def run():
            result = self._mk3_protocol.send_command_simple(ip, cmd_bytes)
            if result.success:
                response = result.raw_data.hex().upper() if result.raw_data else "OK"
                self.after(0, lambda: self._log_control(f"RX< {response} ({result.response_time_ms:.1f}ms)"))
                self.after(0, lambda: self.control_status.configure(text="Command sent OK", text_color=self.COLORS['success']))
            else:
                self.after(0, lambda: self._log_control(f"ERR: {result.error}"))
                self.after(0, lambda: self.control_status.configure(text=f"Error: {result.error}", text_color=self.COLORS['error']))

        threading.Thread(target=run, daemon=True).start()

    def _send_mk3_raw_command(self, cmd_bytes: bytes) -> None:
        """Send raw MK3 command bytes."""
        from ..network import get_hex_string

        ip = self._get_control_ip()
        if not ip:
            return

        hex_str = get_hex_string(cmd_bytes)
        self.control_status.configure(text=f"Sending {hex_str}...", text_color=self.COLORS['accent'])
        self._log_control(f"TX> {hex_str}")

        def run():
            result = self._mk3_protocol.send_command_simple(ip, cmd_bytes)
            if result.success:
                response = result.raw_data.hex().upper() if result.raw_data else "OK"
                self.after(0, lambda: self._log_control(f"RX< {response} ({result.response_time_ms:.1f}ms)"))
                self.after(0, lambda: self.control_status.configure(text="Command sent OK", text_color=self.COLORS['success']))
            else:
                self.after(0, lambda: self._log_control(f"ERR: {result.error}"))
                self.after(0, lambda: self.control_status.configure(text=f"Error: {result.error}", text_color=self.COLORS['error']))

        threading.Thread(target=run, daemon=True).start()

    def _send_mk3_group_command(self, cmd) -> None:
        """Send a per-group MK3 command."""
        from ..network import get_hex_string

        ip = self._get_control_ip()
        if not ip:
            return

        group_letter = self.group_selector.get()
        group_idx = ord(group_letter) - ord('A')

        cmd_bytes = cmd.value + bytes([group_idx])
        hex_str = get_hex_string(cmd_bytes)

        self.control_status.configure(text=f"Sending {hex_str} (Group {group_letter})...", text_color=self.COLORS['accent'])
        self._log_control(f"TX> {hex_str} [Group {group_letter}]")

        def run():
            result = self._mk3_protocol.send_command_simple(ip, cmd_bytes)
            if result.success:
                response = result.raw_data.hex().upper() if result.raw_data else "OK"
                self.after(0, lambda: self._log_control(f"RX< {response} ({result.response_time_ms:.1f}ms)"))
                self.after(0, lambda: self.control_status.configure(text="Command sent OK", text_color=self.COLORS['success']))
            else:
                self.after(0, lambda: self._log_control(f"ERR: {result.error}"))
                self.after(0, lambda: self.control_status.configure(text=f"Error: {result.error}", text_color=self.COLORS['error']))

        threading.Thread(target=run, daemon=True).start()

    def _set_global_volume(self) -> None:
        """Set global volume to slider value."""
        ip = self._get_control_ip()
        if not ip:
            return

        db = int(self.global_vol_slider.get())
        self._log_control(f"Setting global volume to {db} dB...")

        def run():
            result = self._mk3_protocol.set_global_volume_direct(ip, db)
            if result.success:
                self.after(0, lambda: self._log_control(f"Volume set to {db} dB"))
                self.after(0, lambda: self.control_status.configure(text=f"Volume: {db} dB", text_color=self.COLORS['success']))
            else:
                self.after(0, lambda: self._log_control(f"ERR: {result.error}"))
                self.after(0, lambda: self.control_status.configure(text=f"Error: {result.error}", text_color=self.COLORS['error']))

        threading.Thread(target=run, daemon=True).start()

    def _query_all_channel_status(self) -> None:
        """Query protection status for all channels."""
        ip = self._get_control_ip()
        if not ip:
            return

        model = self.model_selector.get()
        num_channels = 8 if "8" in model else 2

        self.control_status.configure(text="Querying channel status...", text_color=self.COLORS['accent'])
        self._log_control(f"Querying {num_channels} channels for protection status...")

        def run():
            channels = self._mk3_protocol.query_all_channel_status(ip, num_channels)

            if channels:
                self.after(0, lambda: self._log_control("\n--- CHANNEL STATUS ---"))
                has_fault = False
                for ch in channels:
                    status = f"Ch {ch.channel_name}: "
                    if ch.has_short:
                        status += "SHORT! "
                        has_fault = True
                    else:
                        status += "OK "
                    if ch.has_overtemp:
                        status += "OVERTEMP! "
                        has_fault = True
                    else:
                        status += f"Temp={ch.overtemp_status} "
                    if ch.dsp_preset:
                        status += f"DSP={ch.dsp_preset}"
                    self.after(0, lambda s=status: self._log_control(s))

                if has_fault:
                    self.after(0, lambda: self.control_status.configure(text="FAULTS DETECTED!", text_color=self.COLORS['error']))
                else:
                    self.after(0, lambda: self.control_status.configure(text="All channels OK", text_color=self.COLORS['success']))
                self.after(0, lambda: self._log_control("--- END STATUS ---\n"))
            else:
                self.after(0, lambda: self._log_control("ERR: Could not query channels"))
                self.after(0, lambda: self.control_status.configure(text="Query failed", text_color=self.COLORS['error']))

        threading.Thread(target=run, daemon=True).start()

    def _run_mk3_diagnostic(self) -> None:
        """Run full MK3 protocol diagnostic."""
        ip = self._get_control_ip()
        if not ip:
            return

        model = self.model_selector.get()
        num_groups = 8 if "8" in model else 2

        self.control_status.configure(text="Running full diagnostic...", text_color=self.COLORS['accent'])
        self._log_control(f"Running full MK3 diagnostic on {ip}...")

        def run():
            status = self._mk3_protocol.run_full_diagnostic(ip, num_groups)

            self.after(0, lambda: self._log_control(f"\n{'='*50}"))
            self.after(0, lambda: self._log_control(f"MK3 DIAGNOSTIC RESULTS - {ip}"))
            self.after(0, lambda: self._log_control(f"{'='*50}"))

            if not status.is_reachable:
                self.after(0, lambda: self._log_control(f"ERROR: Port 52000 not reachable"))
                self.after(0, lambda: self.control_status.configure(text="Port 52000 not reachable", text_color=self.COLORS['error']))
                return

            self.after(0, lambda: self._log_control(f"Connection: OK"))

            if status.power_status:
                pwr = "ON" if status.power_status.is_on else "OFF"
                self.after(0, lambda: self._log_control(f"Power: {pwr}"))

            if status.thermal_status:
                self.after(0, lambda: self._log_control(f"Thermal: {status.thermal_status.state_name}"))

            if status.global_protect:
                gp = status.global_protect
                self.after(0, lambda: self._log_control(f"Global Protect: {'FAULT' if gp.has_any_fault else 'OK'}"))
                if gp.thermal_warning:
                    self.after(0, lambda: self._log_control("  - THERMAL WARNING"))
                if gp.protection_active:
                    self.after(0, lambda: self._log_control("  - PROTECTION ACTIVE"))

            self.after(0, lambda: self._log_control(f"\nGroups queried: {len(status.groups)}"))
            for g in status.groups:
                info = f"Group {g.group_name}: Vol={g.volume}, Mute={'ON' if g.mute else 'OFF'}, Src={g.source}"
                if g.protect_status and g.protect_status.get('has_any_fault'):
                    info += " [FAULT]"
                self.after(0, lambda i=info: self._log_control(f"  {i}"))

            if status.fault_summary:
                self.after(0, lambda: self._log_control(f"\nFAULTS DETECTED:"))
                for fault in status.fault_summary:
                    self.after(0, lambda f=fault: self._log_control(f"  - {f}"))
                self.after(0, lambda: self.control_status.configure(text="FAULTS DETECTED", text_color=self.COLORS['error']))
            else:
                self.after(0, lambda: self._log_control(f"\nNo faults detected"))
                self.after(0, lambda: self.control_status.configure(text="Diagnostic OK", text_color=self.COLORS['success']))

            self.after(0, lambda: self._log_control(f"{'='*50}\n"))

        threading.Thread(target=run, daemon=True).start()

    def _clear_control_log(self) -> None:
        """Clear the control log."""
        self.control_log.delete("1.0", "end")
        self.control_log.insert("end", "Control log cleared.\n\n")

    def _build_logs_view(self) -> ctk.CTkFrame:
        """Build the logs view."""
        view = ctk.CTkFrame(self.main_frame, fg_color="transparent")

        # Header
        header = ctk.CTkFrame(view, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(30, 20))

        ctk.CTkLabel(
            header,
            text="Activity Logs",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=28, weight="bold")
        ).pack(side="left")

        # Log viewer
        self.log_viewer = LogViewer(
            view,
            show_toolbar=True,
            max_lines=10000,
            auto_scroll=True
        )
        self.log_viewer.pack(fill="both", expand=True, padx=30, pady=(0, 20))

        # Subscribe to logs
        self.log_buffer.add_callback(self._on_new_log)

        return view

    def _switch_view(self, view_id: str) -> None:
        """Switch to a different view."""
        # Hide all views
        for v in self.views.values():
            v.pack_forget()

        # Show selected view
        if view_id in self.views:
            self.views[view_id].pack(fill="both", expand=True)
            self._current_view = view_id
            self._update_nav_selection(view_id)

    def _update_nav_selection(self, selected_id: str) -> None:
        """Update navigation button styling."""
        for view_id, btn in self.nav_buttons.items():
            if view_id == selected_id:
                btn.configure(fg_color=self.COLORS['sidebar_selected'])
            else:
                btn.configure(fg_color="transparent")

    def _toggle_scan(self) -> None:
        """Toggle between starting and stopping a scan."""
        if self._is_scanning:
            self._stop_scan()
        else:
            # Check if there are existing devices
            if self._discovered_devices:
                self._show_rescan_dialog()
            else:
                self._start_scan()

    def _show_rescan_dialog(self) -> None:
        """Show dialog asking if user wants to clear existing devices."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Rescan Network")
        dialog.geometry("400x180")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # Center the dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 180) // 2
        dialog.geometry(f"+{x}+{y}")

        dialog.configure(fg_color=self.COLORS['card_bg'])

        # Content
        ctk.CTkLabel(
            dialog,
            text="Clear Existing Devices?",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=18, weight="bold"),
            text_color=self.COLORS['text_primary']
        ).pack(pady=(25, 10))

        ctk.CTkLabel(
            dialog,
            text=f"You have {len(self._discovered_devices)} devices discovered.\nDo you want to clear the list and rescan?",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            text_color=self.COLORS['text_secondary']
        ).pack(pady=(0, 20))

        # Buttons
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=30)

        ctk.CTkButton(
            btn_frame,
            text="Clear & Rescan",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14, weight="bold"),
            fg_color=self.COLORS['accent'],
            hover_color=self.COLORS['accent_hover'],
            width=140,
            command=lambda: self._handle_rescan_choice(dialog, True)
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            fg_color="transparent",
            hover_color=self.COLORS['sidebar_hover'],
            border_width=1,
            border_color=self.COLORS['text_secondary'],
            width=100,
            command=lambda: dialog.destroy()
        ).pack(side="left")

    def _handle_rescan_choice(self, dialog, clear: bool) -> None:
        """Handle the rescan dialog choice."""
        dialog.destroy()
        if clear:
            self._start_scan()

    def _stop_scan(self) -> None:
        """Stop the current scan."""
        self._discovery._cancel_flag.set()
        self._is_scanning = False
        self._hide_scanning_placeholder()
        self.scan_btn.configure(text="▶  Start Scan", fg_color=self.COLORS['accent'])
        self.scan_progress.configure(text=f"Scan stopped. {len(self._discovered_devices)} devices found.")

    def _start_scan(self) -> None:
        """Start network scan using IP range."""
        import ipaddress
        import socket

        start_ip = self.ip_start_entry.get().strip()
        end_ip = self.ip_end_entry.get().strip()

        # If empty, auto-detect first
        if not start_ip or not end_ip:
            local_ip = self._discovery.get_local_ip()
            network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
            hosts = list(network.hosts())
            start_ip = str(hosts[0]) if hosts else local_ip
            end_ip = str(hosts[-1]) if hosts else local_ip
            self.ip_start_entry.delete(0, "end")
            self.ip_start_entry.insert(0, start_ip)
            self.ip_end_entry.delete(0, "end")
            self.ip_end_entry.insert(0, end_ip)

        # Generate IP range
        try:
            start = ipaddress.ip_address(start_ip)
            end = ipaddress.ip_address(end_ip)
            ip_list = [str(ipaddress.ip_address(ip)) for ip in range(int(start), int(end) + 1)]
        except ValueError as e:
            self.scan_progress.configure(text=f"Invalid IP range: {e}")
            return

        range_display = f"{start_ip} - {end_ip}"
        total = len(ip_list)

        # Reset UI for new scan
        self._discovered_devices = []
        self._selected_devices = {}
        self._device_cards = {}
        self._device_checkboxes.clear()
        self._is_scanning = True
        self.scan_progress_bar.set(0)
        self.scan_progress.configure(text=f"Scanning {range_display}...")
        self.scan_btn.configure(text="⏹  Stop Scan", fg_color=self.COLORS['error'])

        # Clear the device list and show scanning animation
        self._clear_device_list(show_scanning=True)

        # Pre-fetch ARP table for MAC lookup
        def prefetch_arp():
            arp_table = self._discovery.get_arp_table()
            self._arp_cache = {entry['ip']: entry['mac'] for entry in arp_table}
        threading.Thread(target=prefetch_arp, daemon=True).start()

        def run():
            try:
                completed = 0
                found_count = 0

                from concurrent.futures import ThreadPoolExecutor, as_completed

                def scan_host(ip: str):
                    """Scan a single host and get all details immediately."""
                    if self._discovery._cancel_flag.is_set():
                        return None

                    success, response_time = self._discovery.ping(ip)
                    if not success:
                        return None

                    # Create device with ping result
                    device = DiscoveredDevice(
                        ip_address=ip,
                        response_time_ms=response_time
                    )

                    # Get MAC from ARP cache
                    if ip in self._arp_cache:
                        device.mac_address = self._arp_cache[ip]

                    # Try to resolve hostname - first socket, then NetBIOS
                    try:
                        hostname, _, _ = socket.gethostbyaddr(ip)
                        device.hostname = hostname
                    except:
                        # Try NetBIOS (what AngryIP Scanner uses)
                        try:
                            result = self._hostname.resolve_via_netbios(ip)
                            if result.success and result.hostname:
                                device.hostname = result.hostname
                        except:
                            pass

                    return device

                def update_progress(c, f, t):
                    progress = c / t
                    self.scan_progress_bar.set(progress)
                    self.scan_progress.configure(text=f"Scanning... {c}/{t} ({f} found)")

                with ThreadPoolExecutor(max_workers=50) as executor:
                    futures = {executor.submit(scan_host, ip): ip for ip in ip_list}

                    for future in as_completed(futures):
                        if self._discovery._cancel_flag.is_set():
                            break
                        completed += 1

                        try:
                            device = future.result()
                            if device:
                                # Add device to our list
                                self._discovered_devices.append(device)
                                self._selected_devices[device.ip_address] = False
                                found_count += 1

                                # Add ONLY this device's card (don't re-render entire list)
                                self.after(0, lambda d=device: self._add_single_device_card(d))

                        except Exception as e:
                            logger.debug(f"Scan error: {e}")

                        # Update progress
                        self.after(0, lambda c=completed, f=found_count, t=total: update_progress(c, f, t))

                # Scan complete
                if not self._discovery._cancel_flag.is_set():
                    self.after(0, lambda: self.scan_progress.configure(
                        text=f"Complete: {len(self._discovered_devices)} devices in {range_display}"
                    ))
                    self.after(0, lambda: self.scan_progress_bar.set(1.0))

            except Exception as e:
                logger.error(f"Scan error: {e}")
                self.after(0, lambda: self.scan_progress.configure(text=f"Error: {e}"))
            finally:
                self._is_scanning = False
                self.after(0, lambda: self.scan_btn.configure(text="▶  Start Scan", fg_color=self.COLORS['accent']))

        self._discovery.reset_cancel()
        threading.Thread(target=run, daemon=True).start()

    def _clear_device_list(self, show_scanning: bool = False) -> None:
        """Clear the device list UI."""
        for widget in self.device_list_frame.winfo_children():
            widget.destroy()
        self._device_cards.clear()
        self._device_checkboxes.clear()
        self.device_count_label.configure(text="0 devices")
        self.stat_devices.configure(text="Devices found: 0")
        self.action_bar.pack_forget()

        # Show scanning placeholder if requested
        if show_scanning:
            self._show_scanning_placeholder()

    def _add_single_device_card(self, device: DiscoveredDevice) -> None:
        """Add a single device card without re-rendering the entire list."""
        # Remove empty placeholder if present
        if hasattr(self, 'empty_placeholder') and self.empty_placeholder.winfo_exists():
            self.empty_placeholder.destroy()

        # Hide scanning placeholder when first device arrives
        self._hide_scanning_placeholder()

        # Create the card
        card = self._create_device_card(device)
        self._device_cards[device.ip_address] = card

        # Update stats
        count = len(self._discovered_devices)
        self.device_count_label.configure(text=f"{count} devices")
        self.stat_devices.configure(text=f"Devices found: {count}")

        self._update_selection_ui()

    def _add_manual_ip(self) -> None:
        """Add a manual IP address."""
        ip = self.manual_ip_entry.get().strip()
        if not ip:
            return

        # Check if already exists
        existing_ips = [d.ip_address for d in self._discovered_devices]
        if ip in existing_ips:
            self.scan_progress.configure(text=f"{ip} already in list")
            return

        # Quick scan the IP
        self.add_ip_btn.configure(state="disabled")
        self.scan_progress.configure(text=f"Checking {ip}...")

        def run():
            device = self._discovery.quick_scan(ip)
            self._discovered_devices.append(device)
            self._selected_devices[ip] = False
            self.after(0, self._update_device_list)
            if device.response_time_ms is not None:
                self.after(0, lambda: self.scan_progress.configure(text=f"Added {ip}"))
            else:
                self.after(0, lambda: self.scan_progress.configure(text=f"Added {ip} (not responding)"))
            self.after(0, lambda: self.add_ip_btn.configure(state="normal"))
            self.after(0, lambda: self.manual_ip_entry.delete(0, "end"))

        threading.Thread(target=run, daemon=True).start()

    def _auto_detect_range(self) -> None:
        """Auto-detect IP range and hostname based on local network."""
        self.hostname_entry.delete(0, "end")
        self.hostname_entry.insert(0, "(detecting...)")
        self.ip_start_entry.delete(0, "end")
        self.ip_end_entry.delete(0, "end")

        def run():
            import socket
            import ipaddress

            # Get local IP
            local_ip = self._discovery.get_local_ip()

            # Get local hostname
            try:
                local_hostname = socket.gethostname()
            except:
                local_hostname = "Unknown"

            # Calculate IP range (assume /24 subnet)
            try:
                ip_obj = ipaddress.ip_address(local_ip)
                network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
                hosts = list(network.hosts())
                start_ip = str(hosts[0]) if hosts else local_ip
                end_ip = str(hosts[-1]) if hosts else local_ip
            except:
                # Fallback: just use .1 to .254 of the current IP's subnet
                parts = local_ip.rsplit('.', 1)
                if len(parts) == 2:
                    start_ip = f"{parts[0]}.1"
                    end_ip = f"{parts[0]}.254"
                else:
                    start_ip = local_ip
                    end_ip = local_ip

            # Update UI on main thread
            self.after(0, lambda: self._update_range_fields(start_ip, end_ip, local_hostname))

        threading.Thread(target=run, daemon=True).start()

    def _update_range_fields(self, start_ip: str, end_ip: str, hostname: str) -> None:
        """Update the IP range fields and hostname entry."""
        self.ip_start_entry.delete(0, "end")
        self.ip_start_entry.insert(0, start_ip)
        self.ip_end_entry.delete(0, "end")
        self.ip_end_entry.insert(0, end_ip)
        self.hostname_entry.delete(0, "end")
        self.hostname_entry.insert(0, hostname)

    def _update_device_list(self) -> None:
        """Full refresh of device list display (used after diagnostics, etc.)."""
        # Clear existing
        for widget in self.device_list_frame.winfo_children():
            widget.destroy()

        self._device_checkboxes.clear()
        self._device_cards.clear()

        if not self._discovered_devices:
            self._show_empty_placeholder()
            self.device_count_label.configure(text="0 devices")
            self.stat_devices.configure(text="Devices found: 0")
            self.action_bar.pack_forget()
            return

        # Create device cards
        for device in self._discovered_devices:
            card = self._create_device_card(device)
            self._device_cards[device.ip_address] = card

        # Update stats
        self.device_count_label.configure(text=f"{len(self._discovered_devices)} devices")
        self.stat_devices.configure(text=f"Devices found: {len(self._discovered_devices)}")

        self._update_selection_ui()

    def _create_device_card(self, device: DiscoveredDevice) -> ctk.CTkFrame:
        """Create a device card in the list. Returns the card widget."""
        card = ctk.CTkFrame(
            self.device_list_frame,
            fg_color=self.COLORS['card_bg'],
            corner_radius=10
        )
        card.pack(fill="x", pady=5)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        # Checkbox
        var = ctk.BooleanVar(value=self._selected_devices.get(device.ip_address, False))
        self._device_checkboxes[device.ip_address] = var

        checkbox = ctk.CTkCheckBox(
            inner,
            text="",
            variable=var,
            width=24,
            command=lambda: self._toggle_device_selection(device.ip_address, var.get())
        )
        checkbox.pack(side="left")

        # Status indicator
        status_color = self.COLORS['success'] if device.response_time_ms else self.COLORS['error']
        status = ctk.CTkFrame(inner, fg_color=status_color, width=12, height=12, corner_radius=6)
        status.pack(side="left", padx=(10, 15))

        # Device info
        info_frame = ctk.CTkFrame(inner, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True)

        # IP and hostname
        ip_label = ctk.CTkLabel(
            info_frame,
            text=device.ip_address,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=16, weight="bold")
        )
        ip_label.pack(anchor="w")

        hostname_text = device.hostname or "Hostname not found"
        hostname_color = self.COLORS['text_primary'] if device.hostname else self.COLORS['warning']
        ctk.CTkLabel(
            info_frame,
            text=hostname_text,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            text_color=hostname_color
        ).pack(anchor="w")

        # Details
        details_frame = ctk.CTkFrame(inner, fg_color="transparent")
        details_frame.pack(side="left", padx=30)

        # MAC
        mac_text = device.mac_address or "Unknown MAC"
        ctk.CTkLabel(
            details_frame,
            text=f"MAC: {mac_text}",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
            text_color=self.COLORS['text_secondary']
        ).pack(anchor="w")

        # Response time
        if device.response_time_ms:
            ctk.CTkLabel(
                details_frame,
                text=f"Latency: {device.response_time_ms:.1f}ms",
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
                text_color=self.COLORS['text_secondary']
            ).pack(anchor="w")

        # Ports
        if device.open_ports:
            ports_text = f"Ports: {', '.join(map(str, device.open_ports[:5]))}"
            if len(device.open_ports) > 5:
                ports_text += "..."
            ctk.CTkLabel(
                details_frame,
                text=ports_text,
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
                text_color=self.COLORS['text_secondary']
            ).pack(anchor="w")

        # Quick actions
        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.pack(side="right")

        # View results button (if we have results for this device)
        if device.ip_address in self._diagnostic_results:
            result = self._diagnostic_results[device.ip_address]
            failed = result.get('summary', {}).get('failed', 0)
            status_text = "HEALTHY" if failed == 0 else f"{failed} ISSUES"
            status_color = self.COLORS['success'] if failed == 0 else self.COLORS['error']

            ctk.CTkButton(
                actions,
                text=status_text,
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=12, weight="bold"),
                fg_color=status_color,
                hover_color=status_color,
                width=90,
                height=30,
                command=lambda ip=device.ip_address: self._show_device_results(ip)
            ).pack(side="left", padx=5)

        ctk.CTkButton(
            actions,
            text="Run Diagnostic",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
            fg_color=self.COLORS['accent'],
            hover_color=self.COLORS['accent_hover'],
            width=110,
            height=30,
            command=lambda ip=device.ip_address: self._run_quick_diagnostic(ip)
        ).pack(side="left", padx=5)

        return card

    def _toggle_device_selection(self, ip: str, selected: bool) -> None:
        """Toggle device selection."""
        self._selected_devices[ip] = selected
        self._update_selection_ui()

    def _toggle_select_all(self) -> None:
        """Toggle select all devices."""
        # If any are selected, deselect all. Otherwise, select all.
        any_selected = any(self._selected_devices.values())
        new_state = not any_selected

        for ip in self._selected_devices:
            self._selected_devices[ip] = new_state
            if ip in self._device_checkboxes:
                self._device_checkboxes[ip].set(new_state)

        self._update_selection_ui()

    def _update_selection_ui(self) -> None:
        """Update UI based on selection."""
        selected_count = sum(1 for v in self._selected_devices.values() if v)

        self.stat_selected.configure(text=f"Selected: {selected_count}")
        self.action_label.configure(text=f"{selected_count} device{'s' if selected_count != 1 else ''} selected")

        if selected_count > 0:
            # Show action bar
            self.action_bar.pack(fill="x", padx=30, pady=(0, 15), after=self.views['discovery'].winfo_children()[1])
            self.select_all_btn.configure(text="Deselect All" if selected_count == len(self._selected_devices) else "Select All")
        else:
            self.action_bar.pack_forget()

    def _get_selected_ips(self) -> List[str]:
        """Get list of selected IP addresses."""
        return [ip for ip, selected in self._selected_devices.items() if selected]

    def _run_diagnostics_on_selected(self) -> None:
        """Run full diagnostics on selected devices."""
        selected_ips = self._get_selected_ips()
        if not selected_ips:
            return

        self.run_diag_btn.configure(state="disabled", text="Running...")

        # Switch to diagnostics view and show loading animation
        self._switch_view("diagnostics")
        self._show_diagnostics_loading(selected_ips)

        def run():
            for i, ip in enumerate(selected_ips):
                self.after(0, lambda ip=ip, i=i, t=len(selected_ips):
                    self._update_diagnostics_loading(ip, i + 1, t))
                self._run_full_diagnostic(ip)

            self.after(0, lambda: self.run_diag_btn.configure(state="normal", text="Run Full Diagnostics"))
            self.after(0, lambda: self.scan_progress.configure(text="Diagnostics complete"))
            self.after(0, self._display_diagnostic_results)
            self.after(0, self._update_device_list)

        threading.Thread(target=run, daemon=True).start()

    def _run_quick_diagnostic(self, ip: str) -> None:
        """Run quick diagnostic on a single device."""
        self.scan_progress.configure(text=f"Diagnosing {ip}...")

        # Switch to diagnostics view and show loading animation
        self._switch_view("diagnostics")
        self._show_diagnostics_loading([ip])

        def run():
            self._run_full_diagnostic(ip)
            self.after(0, lambda: self.scan_progress.configure(text="Diagnostic complete"))
            self.after(0, self._display_diagnostic_results)
            self.after(0, self._update_device_list)

        threading.Thread(target=run, daemon=True).start()

    def _show_diagnostics_loading(self, ips: List[str]) -> None:
        """Show loading animation in diagnostics view."""
        # Clear existing results
        for widget in self.results_container.winfo_children():
            widget.destroy()

        # Create loading frame
        self._diag_loading_frame = ctk.CTkFrame(self.results_container, fg_color="transparent")
        self._diag_loading_frame.pack(fill="both", expand=True, pady=50)

        # Spinner
        self._diag_spinner_label = ctk.CTkLabel(
            self._diag_loading_frame,
            text="◐",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=48),
            text_color=self.COLORS['accent']
        )
        self._diag_spinner_label.pack()

        ctk.CTkLabel(
            self._diag_loading_frame,
            text="Running Diagnostics...",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=20, weight="bold"),
            text_color=self.COLORS['text_primary']
        ).pack(pady=(20, 10))

        self._diag_status_label = ctk.CTkLabel(
            self._diag_loading_frame,
            text=f"Testing {len(ips)} device{'s' if len(ips) > 1 else ''}",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            text_color=self.COLORS['text_secondary']
        )
        self._diag_status_label.pack()

        # IP list being tested
        ip_text = ", ".join(ips[:3])
        if len(ips) > 3:
            ip_text += f" + {len(ips) - 3} more"
        ctk.CTkLabel(
            self._diag_loading_frame,
            text=ip_text,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
            text_color=self.COLORS['text_secondary']
        ).pack(pady=(5, 0))

        # Start spinner animation
        self._diag_running = True
        self._animate_diag_spinner()

    def _animate_diag_spinner(self) -> None:
        """Animate the diagnostics spinner."""
        if not self._diag_running:
            return
        if not hasattr(self, '_diag_spinner_label') or not self._diag_spinner_label.winfo_exists():
            return

        chars = ["◐", "◓", "◑", "◒"]
        if not hasattr(self, '_diag_spinner_idx'):
            self._diag_spinner_idx = 0
        self._diag_spinner_idx = (self._diag_spinner_idx + 1) % len(chars)
        self._diag_spinner_label.configure(text=chars[self._diag_spinner_idx])
        self.after(100, self._animate_diag_spinner)

    def _update_diagnostics_loading(self, ip: str, current: int, total: int) -> None:
        """Update the diagnostics loading status."""
        if hasattr(self, '_diag_status_label') and self._diag_status_label.winfo_exists():
            self._diag_status_label.configure(text=f"Testing device {current}/{total}: {ip}")

    def _run_full_diagnostic(self, ip: str) -> None:
        """Run full diagnostic suite on a device."""
        logger.info(f"Running diagnostics on {ip}")

        results = {
            'timestamp': datetime.now().isoformat(),
            'ip_address': ip,
            'tests': {},
            'summary': {'passed': 0, 'failed': 0, 'warnings': 0}
        }

        # 1. Reachability
        ping = self._connectivity.ping_extended(ip, count=5)
        results['tests']['reachability'] = {
            'name': 'Network Reachability',
            'passed': ping.is_reachable,
            'details': {
                'avg_latency_ms': ping.avg_ms,
                'packet_loss': ping.packet_loss_percent
            }
        }
        results['summary']['passed' if ping.is_reachable else 'failed'] += 1

        # 2. Ports
        ports = self._connectivity.scan_ports(ip, [80, 23, 8080, 10000, 4998])
        open_ports = [p.port for p in ports if p.is_open]
        results['tests']['ports'] = {
            'name': 'Port Scan',
            'passed': len(open_ports) > 0,
            'open_ports': open_ports
        }
        results['summary']['passed' if open_ports else 'failed'] += 1

        # 3. HTTP
        http = self._connectivity.test_http_endpoints(ip, ["/", "/Landing.htm"])
        accessible = [h for h in http if h.is_accessible]
        results['tests']['http'] = {
            'name': 'HTTP Web Interface',
            'passed': len(accessible) > 0,
            'accessible_endpoints': [h.url for h in accessible]
        }
        results['summary']['passed' if accessible else 'failed'] += 1

        # 4. Hostname
        hostname = self._hostname.resolve_all_methods(ip, "DSP")
        successful = [m for m, r in hostname.items() if r.success]
        hostnames_found = [hostname[m].hostname for m in successful if hostname[m].hostname]
        results['tests']['hostname'] = {
            'name': 'Hostname Resolution',
            'passed': len(successful) > 0,
            'methods_successful': successful,
            'hostnames_found': hostnames_found
        }
        results['summary']['passed' if successful else 'failed'] += 1

        # 5. DNS
        dns_servers = self._dns.get_system_dns_servers()
        dns_tests = self._dns.test_multiple_dns_servers(dns_servers[:2])
        working = [d.server_ip for d in dns_tests if d.can_resolve]
        results['tests']['dns'] = {
            'name': 'DNS Servers',
            'passed': len(working) > 0,
            'working_servers': working
        }
        results['summary']['passed' if working else 'failed'] += 1

        # 6. Commands
        cmd_ports = [23, 10000, 4998]
        connected_port = None
        for port in cmd_ports:
            conn = self._commands.connect(ip, port)
            if conn.is_connected:
                connected_port = port
                self._commands.disconnect(conn)
                break

        if connected_port:
            results['tests']['commands'] = {
                'name': 'Command Protocol',
                'passed': True,
                'port': connected_port
            }
            results['summary']['passed'] += 1
        else:
            results['tests']['commands'] = {
                'name': 'Command Protocol',
                'passed': False,
                'error': 'No command port found'
            }
            results['summary']['failed'] += 1

        self._diagnostic_results[ip] = results
        self.after(0, self._display_diagnostic_results)

    def _run_individual_test(self, test_name: str) -> None:
        """Run a specific test on selected devices."""
        if test_name == "Run Individual Test...":
            return

        selected_ips = self._get_selected_ips()
        if not selected_ips:
            return

        self.scan_progress.configure(text=f"Running {test_name}...")

        # Map test name to function
        test_map = {
            "Ping Test": self._run_ping_test,
            "Port Scan": self._run_port_test,
            "HTTP Test": self._run_http_test,
            "Hostname Test": self._run_hostname_test,
            "DNS Test": self._run_dns_test,
            "Command Test": self._run_command_test
        }

        if test_name in test_map:
            def run():
                for ip in selected_ips:
                    test_map[test_name](ip)
                self.after(0, lambda: self.scan_progress.configure(text=f"{test_name} complete - see Logs"))

            threading.Thread(target=run, daemon=True).start()

        # Reset dropdown
        self.run_tests_menu.set("Run Individual Test...")

    def _run_ping_test(self, ip: str) -> None:
        result = self._connectivity.ping_extended(ip, count=5)
        logger.info(f"[{ip}] Ping: {'OK' if result.is_reachable else 'FAILED'} - avg {result.avg_ms:.1f}ms, {result.packet_loss_percent:.0f}% loss")

    def _run_port_test(self, ip: str) -> None:
        ports = self._connectivity.scan_ports(ip, self.config.common_ports[:10])
        open_ports = [p.port for p in ports if p.is_open]
        logger.info(f"[{ip}] Open ports: {open_ports if open_ports else 'None'}")

    def _run_http_test(self, ip: str) -> None:
        results = self._connectivity.test_http_endpoints(ip, ["/", "/Landing.htm"])
        accessible = [r.url for r in results if r.is_accessible]
        logger.info(f"[{ip}] HTTP accessible: {accessible if accessible else 'None'}")

    def _run_hostname_test(self, ip: str) -> None:
        results = self._hostname.resolve_all_methods(ip)
        for method, result in results.items():
            status = f"{result.hostname}" if result.success else f"FAILED ({result.error})"
            logger.info(f"[{ip}] Hostname ({method}): {status}")

    def _run_dns_test(self, ip: str) -> None:
        servers = self._dns.get_system_dns_servers()
        results = self._dns.test_multiple_dns_servers(servers[:2])
        working = [r.server_ip for r in results if r.can_resolve]
        logger.info(f"[{ip}] DNS servers working: {working if working else 'None'}")

    def _run_command_test(self, ip: str) -> None:
        for port in [23, 10000, 4998]:
            conn = self._commands.connect(ip, port)
            if conn.is_connected:
                logger.info(f"[{ip}] Command port {port}: OPEN")
                self._commands.disconnect(conn)
                return
        logger.info(f"[{ip}] Command port: None found")

    def _display_diagnostic_results(self) -> None:
        """Display diagnostic results in the diagnostics view."""
        # Stop the diagnostics spinner
        self._diag_running = False

        # Clear existing (including loading animation)
        for widget in self.results_container.winfo_children():
            widget.destroy()

        if not self._diagnostic_results:
            self.results_placeholder = ctk.CTkLabel(
                self.results_container,
                text="No diagnostic results yet.\nSelect devices in Discovery and run diagnostics.",
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=16),
                text_color=self.COLORS['text_secondary'],
                justify="center"
            )
            self.results_placeholder.pack(pady=100)
            return

        # Display results for each device
        for ip, results in self._diagnostic_results.items():
            self._create_result_card(ip, results)

    def _create_result_card(self, ip: str, results: dict) -> None:
        """Create a result card for a device."""
        summary = results.get('summary', {})
        passed = summary.get('passed', 0)
        failed = summary.get('failed', 0)
        tests = results.get('tests', {})

        # Card color based on status
        if failed == 0:
            border_color = self.COLORS['success']
            status_text = "HEALTHY"
            status_bg = "#1a4d2e"
        elif failed <= 2:
            border_color = self.COLORS['warning']
            status_text = "ISSUES FOUND"
            status_bg = "#4d3d1a"
        else:
            border_color = self.COLORS['error']
            status_text = "PROBLEMS"
            status_bg = "#4d1a1a"

        card = ctk.CTkFrame(
            self.results_container,
            fg_color=self.COLORS['card_bg'],
            corner_radius=12,
            border_width=2,
            border_color=border_color
        )
        card.pack(fill="x", pady=10)

        # Header with status banner
        header_bg = ctk.CTkFrame(card, fg_color=status_bg, corner_radius=0)
        header_bg.pack(fill="x")

        header = ctk.CTkFrame(header_bg, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=15)

        ctk.CTkLabel(
            header,
            text=ip,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=22, weight="bold")
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text=status_text,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=16, weight="bold"),
            text_color=border_color
        ).pack(side="right")

        # Stats row
        stats = ctk.CTkFrame(card, fg_color="transparent")
        stats.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            stats,
            text=f"Passed: {passed}",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            text_color=self.COLORS['success']
        ).pack(side="left", padx=(0, 30))

        ctk.CTkLabel(
            stats,
            text=f"Failed: {failed}",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=14),
            text_color=self.COLORS['error']
        ).pack(side="left")

        ctk.CTkLabel(
            stats,
            text=f"Tested: {results.get('timestamp', '')[:19]}",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
            text_color=self.COLORS['text_secondary']
        ).pack(side="right")

        # Test results grid
        tests_frame = ctk.CTkFrame(card, fg_color="transparent")
        tests_frame.pack(fill="x", padx=20, pady=(0, 10))

        for test_id, test_data in tests.items():
            test_passed = test_data.get('passed', False)
            icon = "✓" if test_passed else "✗"
            color = self.COLORS['success'] if test_passed else self.COLORS['error']

            test_label = ctk.CTkLabel(
                tests_frame,
                text=f"{icon} {test_data.get('name', test_id)}",
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=13),
                text_color=color
            )
            test_label.pack(side="left", padx=(0, 25))

        # Issues section (if any failed)
        if failed > 0:
            issues_frame = ctk.CTkFrame(card, fg_color="#2d1f1f", corner_radius=8)
            issues_frame.pack(fill="x", padx=15, pady=(5, 15))

            ctk.CTkLabel(
                issues_frame,
                text="Issues Found:",
                font=ctk.CTkFont(family=self.FONT_FAMILY, size=14, weight="bold"),
                text_color=self.COLORS['error']
            ).pack(anchor="w", padx=15, pady=(12, 8))

            # Hostname issue
            if not tests.get('hostname', {}).get('passed', True):
                self._add_issue_item(issues_frame,
                    "Hostname Not Broadcasting",
                    "Device won't appear by name in network scanners like AngryIP. This may be a firmware limitation.",
                    "Check if hostname is configurable in amp settings, or contact Sonance support."
                )

            # Command issue
            if not tests.get('commands', {}).get('passed', True):
                self._add_issue_item(issues_frame,
                    "No Control Port Found",
                    "Ports 23, 10000, and 4998 are all closed. Control systems cannot send commands.",
                    "Check amp settings to ensure IP Control is ENABLED. Try rebooting the amplifier."
                )

            # HTTP issue
            if not tests.get('http', {}).get('passed', True):
                self._add_issue_item(issues_frame,
                    "Web Interface Not Accessible",
                    "Browser cannot reach the amp's web page. Port 80 may be down.",
                    "Try rebooting the amp. If issue persists, this may indicate a firmware problem."
                )

            # Reachability issue
            if not tests.get('reachability', {}).get('passed', True):
                self._add_issue_item(issues_frame,
                    "Device Not Reachable",
                    "Device is not responding to network requests.",
                    "Verify IP address, check power and network cables, ensure same VLAN."
                )

    def _add_issue_item(self, parent, title: str, description: str, recommendation: str) -> None:
        """Add an issue item to the issues frame."""
        item = ctk.CTkFrame(parent, fg_color="transparent")
        item.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(
            item,
            text=f"• {title}",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=13, weight="bold"),
            text_color=self.COLORS['warning']
        ).pack(anchor="w")

        ctk.CTkLabel(
            item,
            text=description,
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
            text_color=self.COLORS['text_secondary'],
            wraplength=700,
            justify="left"
        ).pack(anchor="w", padx=(15, 0))

        ctk.CTkLabel(
            item,
            text=f"→ {recommendation}",
            font=ctk.CTkFont(family=self.FONT_FAMILY, size=12),
            text_color=self.COLORS['success'],
            wraplength=700,
            justify="left"
        ).pack(anchor="w", padx=(15, 0), pady=(3, 0))

    def _show_device_results(self, ip: str) -> None:
        """Show results for a specific device."""
        self._switch_view("diagnostics")

    def _clear_diagnostic_results(self) -> None:
        """Clear all diagnostic results."""
        self._diagnostic_results = {}
        self._display_diagnostic_results()
        self._update_device_list()

    def _export_results(self) -> None:
        """Export all diagnostic results."""
        from tkinter import filedialog
        import json

        if not self._diagnostic_results:
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"mk3_diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        if filename:
            with open(filename, 'w') as f:
                json.dump(self._diagnostic_results, f, indent=2, default=str)
            logger.info(f"Results exported to {filename}")

    def _send_command(self) -> None:
        """Send a command to the device."""
        ip = self.quick_test_ip_entry.get().strip()
        port_str = self.cmd_port_entry.get().strip()
        cmd = self.command_entry.get().strip()

        if not ip:
            self.quick_test_status.configure(text="Please enter a target IP address", text_color=self.COLORS['error'])
            return
        if not cmd:
            self.quick_test_status.configure(text="Please enter a command to send", text_color=self.COLORS['error'])
            return

        try:
            port = int(port_str)
        except ValueError:
            port = 23

        self.quick_test_status.configure(text=f"Sending command to {ip}:{port}...", text_color=self.COLORS['accent'])

        def run():
            result = self._commands.send_command_simple(ip, port, cmd)
            self.after(0, lambda: self._display_command_result(ip, port, cmd, result))

        threading.Thread(target=run, daemon=True).start()

    def _display_command_result(self, ip: str, port: int, cmd: str, result) -> None:
        """Display command result in the log."""
        self.quick_test_log.insert("end", f"[{ip}:{port}] TX> {cmd}\n")
        if result.success:
            self.quick_test_log.insert("end", f"[{ip}:{port}] RX< {result.response}\n")
            self.quick_test_status.configure(text=f"Command sent successfully", text_color=self.COLORS['success'])
        else:
            self.quick_test_log.insert("end", f"[{ip}:{port}] ERR: {result.error}\n")
            self.quick_test_status.configure(text=f"Command failed: {result.error}", text_color=self.COLORS['error'])
        self.quick_test_log.insert("end", "\n")
        self.quick_test_log.see("end")

    def _run_burst_test(self) -> None:
        """Run burst test."""
        ip = self.quick_test_ip_entry.get().strip()
        port_str = self.cmd_port_entry.get().strip()
        cmd = self.command_entry.get().strip() or "status"

        if not ip:
            self.quick_test_status.configure(text="Please enter a target IP address", text_color=self.COLORS['error'])
            return

        try:
            port = int(port_str)
        except ValueError:
            port = 23

        self.burst_btn.configure(state="disabled")
        self.quick_test_status.configure(text=f"Running burst test on {ip}:{port}...", text_color=self.COLORS['accent'])

        def run():
            result = self._commands.burst_test(ip, port, cmd, count=10, delay_ms=0)
            self.after(0, lambda: self._show_burst_result(ip, port, result))
            self.after(0, lambda: self.burst_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    def _show_burst_result(self, ip: str, port: int, result) -> None:
        """Display burst test results."""
        self.quick_test_log.insert("end", "=" * 50 + "\n")
        self.quick_test_log.insert("end", f"BURST TEST RESULTS - {ip}:{port}\n")
        self.quick_test_log.insert("end", f"Commands sent: {result.total_commands}\n")
        self.quick_test_log.insert("end", f"Successful: {result.successful_commands}\n")
        self.quick_test_log.insert("end", f"Failed: {result.failed_commands}\n")
        self.quick_test_log.insert("end", f"Error Rate: {result.error_rate_percent:.1f}%\n")
        if result.avg_response_ms:
            self.quick_test_log.insert("end", f"Avg Response: {result.avg_response_ms:.1f}ms\n")
        self.quick_test_log.insert("end", "=" * 50 + "\n\n")
        self.quick_test_log.see("end")

        if result.error_rate_percent == 0:
            self.quick_test_status.configure(text="Burst test passed - all commands successful", text_color=self.COLORS['success'])
        else:
            self.quick_test_status.configure(text=f"Burst test: {result.error_rate_percent:.1f}% error rate", text_color=self.COLORS['warning'])

    def _on_port_preset_select(self, value: str) -> None:
        """Handle port preset selection."""
        port = value.split(" ")[0]
        self.cmd_port_entry.delete(0, "end")
        self.cmd_port_entry.insert(0, port)

    def _get_quick_test_ip(self) -> Optional[str]:
        """Get the target IP for quick tests."""
        ip = self.quick_test_ip_entry.get().strip()
        if not ip:
            self.quick_test_status.configure(text="Please enter a target IP address", text_color=self.COLORS['error'])
            return None
        return ip

    def _log_test_result(self, test_name: str, ip: str, passed: bool, details: str) -> None:
        """Log a test result to the quick test log."""
        status = "PASS" if passed else "FAIL"
        color_tag = "green" if passed else "red"
        timestamp = datetime.now().strftime("%H:%M:%S")

        self.quick_test_log.insert("end", f"[{timestamp}] {test_name} - {ip}\n")
        self.quick_test_log.insert("end", f"  Status: {status}\n")
        self.quick_test_log.insert("end", f"  {details}\n\n")
        self.quick_test_log.see("end")

    def _quick_ping_test(self) -> None:
        """Run ping test on target IP."""
        ip = self._get_quick_test_ip()
        if not ip:
            return

        self.quick_test_status.configure(text=f"Running ping test on {ip}...", text_color=self.COLORS['accent'])
        self._quick_test_buttons['ping'].configure(state="disabled")

        def run():
            result = self._connectivity.ping_extended(ip, count=5)
            passed = result.is_reachable
            if passed:
                details = f"Avg latency: {result.avg_ms:.1f}ms, Packet loss: {result.packet_loss_percent:.0f}%"
            else:
                details = "Device not reachable - no response to ping"

            self.after(0, lambda: self._log_test_result("PING TEST", ip, passed, details))
            self.after(0, lambda: self._quick_test_buttons['ping'].configure(state="normal"))
            self.after(0, lambda: self.quick_test_status.configure(
                text=f"Ping: {'OK' if passed else 'FAILED'} - {ip}",
                text_color=self.COLORS['success'] if passed else self.COLORS['error']
            ))

        threading.Thread(target=run, daemon=True).start()

    def _quick_port_test(self) -> None:
        """Run port scan on target IP."""
        ip = self._get_quick_test_ip()
        if not ip:
            return

        self.quick_test_status.configure(text=f"Scanning ports on {ip}...", text_color=self.COLORS['accent'])
        self._quick_test_buttons['ports'].configure(state="disabled")

        def run():
            ports_to_scan = [80, 23, 8080, 443, 10000, 4998, 52000, 22]
            results = self._connectivity.scan_ports(ip, ports_to_scan)
            open_ports = [p.port for p in results if p.is_open]
            passed = len(open_ports) > 0

            if passed:
                details = f"Open ports: {', '.join(map(str, open_ports))}"
            else:
                details = "No open ports found"

            self.after(0, lambda: self._log_test_result("PORT SCAN", ip, passed, details))
            self.after(0, lambda: self._quick_test_buttons['ports'].configure(state="normal"))
            self.after(0, lambda: self.quick_test_status.configure(
                text=f"Ports: {len(open_ports)} open on {ip}",
                text_color=self.COLORS['success'] if passed else self.COLORS['warning']
            ))

        threading.Thread(target=run, daemon=True).start()

    def _quick_http_test(self) -> None:
        """Run HTTP accessibility test on target IP."""
        ip = self._get_quick_test_ip()
        if not ip:
            return

        self.quick_test_status.configure(text=f"Testing HTTP on {ip}...", text_color=self.COLORS['accent'])
        self._quick_test_buttons['http'].configure(state="disabled")

        def run():
            endpoints = ["/", "/Landing.htm", "/index.html"]
            results = self._connectivity.test_http_endpoints(ip, endpoints)
            accessible = [r.url for r in results if r.is_accessible]
            passed = len(accessible) > 0

            if passed:
                details = f"Accessible: {', '.join(accessible)}"
            else:
                details = "Web interface not accessible - HTTP connection failed"

            self.after(0, lambda: self._log_test_result("HTTP TEST", ip, passed, details))
            self.after(0, lambda: self._quick_test_buttons['http'].configure(state="normal"))
            self.after(0, lambda: self.quick_test_status.configure(
                text=f"HTTP: {'OK' if passed else 'FAILED'} - {ip}",
                text_color=self.COLORS['success'] if passed else self.COLORS['error']
            ))

        threading.Thread(target=run, daemon=True).start()

    def _quick_hostname_test(self) -> None:
        """Run hostname resolution test on target IP."""
        ip = self._get_quick_test_ip()
        if not ip:
            return

        self.quick_test_status.configure(text=f"Resolving hostname for {ip}...", text_color=self.COLORS['accent'])
        self._quick_test_buttons['hostname'].configure(state="disabled")

        def run():
            results = self._hostname.resolve_all_methods(ip)
            successful = [m for m, r in results.items() if r.success]
            hostnames = [results[m].hostname for m in successful if results[m].hostname]
            passed = len(successful) > 0

            if passed and hostnames:
                details = f"Hostname: {hostnames[0]} (via {', '.join(successful)})"
            elif passed:
                details = f"Methods succeeded: {', '.join(successful)} (no hostname returned)"
            else:
                details = "Hostname resolution failed via all methods (reverse DNS, NetBIOS, mDNS)"

            self.after(0, lambda: self._log_test_result("HOSTNAME TEST", ip, passed, details))
            self.after(0, lambda: self._quick_test_buttons['hostname'].configure(state="normal"))
            self.after(0, lambda: self.quick_test_status.configure(
                text=f"Hostname: {hostnames[0] if hostnames else 'Not found'}" if passed else "Hostname: FAILED",
                text_color=self.COLORS['success'] if passed else self.COLORS['warning']
            ))

        threading.Thread(target=run, daemon=True).start()

    def _quick_dns_test(self) -> None:
        """Run DNS server test."""
        ip = self._get_quick_test_ip()
        if not ip:
            return

        self.quick_test_status.configure(text="Testing DNS servers...", text_color=self.COLORS['accent'])
        self._quick_test_buttons['dns'].configure(state="disabled")

        def run():
            servers = self._dns.get_system_dns_servers()
            results = self._dns.test_multiple_dns_servers(servers[:3])
            working = [r.server_ip for r in results if r.can_resolve]
            passed = len(working) > 0

            if passed:
                details = f"Working DNS servers: {', '.join(working)}"
            else:
                details = "No working DNS servers found"

            self.after(0, lambda: self._log_test_result("DNS TEST", ip, passed, details))
            self.after(0, lambda: self._quick_test_buttons['dns'].configure(state="normal"))
            self.after(0, lambda: self.quick_test_status.configure(
                text=f"DNS: {len(working)} servers working",
                text_color=self.COLORS['success'] if passed else self.COLORS['error']
            ))

        threading.Thread(target=run, daemon=True).start()

    def _quick_command_test(self) -> None:
        """Run command port test on target IP."""
        ip = self._get_quick_test_ip()
        if not ip:
            return

        self.quick_test_status.configure(text=f"Testing command ports on {ip}...", text_color=self.COLORS['accent'])
        self._quick_test_buttons['cmd'].configure(state="disabled")

        def run():
            cmd_ports = [23, 10000, 4998, 52000]
            connected_port = None

            for port in cmd_ports:
                conn = self._commands.connect(ip, port)
                if conn.is_connected:
                    connected_port = port
                    self._commands.disconnect(conn)
                    break

            passed = connected_port is not None

            if passed:
                details = f"Command port {connected_port} is open and accepting connections"
            else:
                details = f"No command ports found (tested: {', '.join(map(str, cmd_ports))})"

            self.after(0, lambda: self._log_test_result("COMMAND PORT TEST", ip, passed, details))
            self.after(0, lambda: self._quick_test_buttons['cmd'].configure(state="normal"))
            self.after(0, lambda: self.quick_test_status.configure(
                text=f"Command Port: {connected_port}" if passed else "Command Port: NONE FOUND",
                text_color=self.COLORS['success'] if passed else self.COLORS['error']
            ))

        threading.Thread(target=run, daemon=True).start()

    def _run_all_quick_tests(self) -> None:
        """Run all quick tests sequentially."""
        ip = self._get_quick_test_ip()
        if not ip:
            return

        self.quick_test_status.configure(text=f"Running all tests on {ip}...", text_color=self.COLORS['accent'])
        self.run_all_tests_btn.configure(state="disabled")

        # Disable all test buttons
        for btn in self._quick_test_buttons.values():
            btn.configure(state="disabled")

        def run():
            self.after(0, lambda: self.quick_test_log.insert("end", f"\n{'='*50}\nRUNNING ALL TESTS ON {ip}\n{'='*50}\n\n"))

            # Ping test
            self.after(0, lambda: self.quick_test_status.configure(text="[1/6] Running ping test..."))
            result = self._connectivity.ping_extended(ip, count=5)
            passed = result.is_reachable
            details = f"Avg: {result.avg_ms:.1f}ms, Loss: {result.packet_loss_percent:.0f}%" if passed else "Not reachable"
            self.after(0, lambda: self._log_test_result("PING", ip, passed, details))

            # Port scan
            self.after(0, lambda: self.quick_test_status.configure(text="[2/6] Scanning ports..."))
            ports = self._connectivity.scan_ports(ip, [80, 23, 8080, 10000, 4998, 52000])
            open_ports = [p.port for p in ports if p.is_open]
            self.after(0, lambda: self._log_test_result("PORTS", ip, len(open_ports) > 0,
                f"Open: {', '.join(map(str, open_ports))}" if open_ports else "None found"))

            # HTTP test
            self.after(0, lambda: self.quick_test_status.configure(text="[3/6] Testing HTTP..."))
            http = self._connectivity.test_http_endpoints(ip, ["/", "/Landing.htm"])
            accessible = [h.url for h in http if h.is_accessible]
            self.after(0, lambda: self._log_test_result("HTTP", ip, len(accessible) > 0,
                f"Accessible: {', '.join(accessible)}" if accessible else "Not accessible"))

            # Hostname test
            self.after(0, lambda: self.quick_test_status.configure(text="[4/6] Resolving hostname..."))
            hostname = self._hostname.resolve_all_methods(ip)
            successful = [m for m, r in hostname.items() if r.success]
            hostnames = [hostname[m].hostname for m in successful if hostname[m].hostname]
            self.after(0, lambda: self._log_test_result("HOSTNAME", ip, len(successful) > 0,
                f"{hostnames[0] if hostnames else 'No hostname'} via {', '.join(successful)}" if successful else "Not resolvable"))

            # DNS test
            self.after(0, lambda: self.quick_test_status.configure(text="[5/6] Testing DNS..."))
            servers = self._dns.get_system_dns_servers()
            dns_results = self._dns.test_multiple_dns_servers(servers[:2])
            working = [d.server_ip for d in dns_results if d.can_resolve]
            self.after(0, lambda: self._log_test_result("DNS", ip, len(working) > 0,
                f"Working servers: {', '.join(working)}" if working else "No working servers"))

            # Command port test
            self.after(0, lambda: self.quick_test_status.configure(text="[6/6] Testing command ports..."))
            connected_port = None
            for port in [23, 10000, 4998, 52000]:
                conn = self._commands.connect(ip, port)
                if conn.is_connected:
                    connected_port = port
                    self._commands.disconnect(conn)
                    break
            self.after(0, lambda: self._log_test_result("COMMAND", ip, connected_port is not None,
                f"Port {connected_port} open" if connected_port else "No command port found"))

            # Re-enable buttons
            self.after(0, lambda: self.run_all_tests_btn.configure(state="normal"))
            for btn in self._quick_test_buttons.values():
                self.after(0, lambda b=btn: b.configure(state="normal"))

            self.after(0, lambda: self.quick_test_log.insert("end", f"{'='*50}\nALL TESTS COMPLETE\n{'='*50}\n\n"))
            self.after(0, lambda: self.quick_test_status.configure(text=f"All tests complete for {ip}", text_color=self.COLORS['success']))

        threading.Thread(target=run, daemon=True).start()

    def _clear_quick_test_results(self) -> None:
        """Clear the quick test results log."""
        self.quick_test_log.delete("1.0", "end")
        self.quick_test_log.insert("end", "Quick Tests & Commands\n")
        self.quick_test_log.insert("end", "=" * 50 + "\n")
        self.quick_test_log.insert("end", "Results cleared.\n\n")
        self.quick_test_status.configure(text="Results cleared", text_color=self.COLORS['text_secondary'])

    def _on_new_log(self, entry) -> None:
        """Handle new log entry."""
        self.after(0, lambda: self.log_viewer.add_log(
            entry.message, entry.level, entry.timestamp
        ))

    def _on_close(self) -> None:
        """Handle window close."""
        self.config.save()
        logger.info("Application closing")
        self.destroy()


def run_app():
    """Run the MK3 Diagnostic application."""
    app = MK3DiagnosticApp()
    app.mainloop()
