"""Network discovery tab frame."""

import customtkinter as ctk
import threading
from typing import Optional, Callable, List

from ...network import NetworkDiscovery
from ...utils import get_logger, Config

logger = get_logger(__name__)


class DiscoveryFrame(ctk.CTkFrame):
    """
    Frame for network discovery functionality.
    """

    def __init__(
        self,
        master,
        config: Config,
        on_ip_selected: Optional[Callable[[str], None]] = None,
        **kwargs
    ):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.config = config
        self._on_ip_selected = on_ip_selected
        self._discovery = NetworkDiscovery()
        self._is_scanning = False

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the discovery UI."""
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Controls section
        self._build_controls()

        # Results section
        self._build_results()

    def _build_controls(self) -> None:
        """Build the controls section."""
        controls = ctk.CTkFrame(self)
        controls.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        # Subnet entry
        ctk.CTkLabel(
            controls,
            text="Subnet:",
            font=ctk.CTkFont(size=14)
        ).pack(side="left", padx=(10, 5))

        self.subnet_entry = ctk.CTkEntry(
            controls,
            placeholder_text="e.g., 192.168.1.0/24 (leave empty for auto)",
            width=250,
            font=ctk.CTkFont(size=13)
        )
        self.subnet_entry.pack(side="left", padx=5)

        # Scan button
        self.scan_btn = ctk.CTkButton(
            controls,
            text="Scan Network",
            command=self._start_scan,
            font=ctk.CTkFont(size=14, weight="bold"),
            width=140
        )
        self.scan_btn.pack(side="left", padx=10)

        # Quick scan single IP
        ctk.CTkLabel(
            controls,
            text="Quick Scan:",
            font=ctk.CTkFont(size=14)
        ).pack(side="left", padx=(20, 5))

        self.quick_ip_entry = ctk.CTkEntry(
            controls,
            placeholder_text="Single IP",
            width=150,
            font=ctk.CTkFont(size=13)
        )
        self.quick_ip_entry.pack(side="left", padx=5)

        self.quick_scan_btn = ctk.CTkButton(
            controls,
            text="Quick Scan",
            command=self._quick_scan,
            font=ctk.CTkFont(size=13),
            width=100
        )
        self.quick_scan_btn.pack(side="left", padx=5)

        # Progress
        self.progress_label = ctk.CTkLabel(
            controls,
            text="",
            font=ctk.CTkFont(size=12)
        )
        self.progress_label.pack(side="right", padx=10)

    def _build_results(self) -> None:
        """Build the results section."""
        results_frame = ctk.CTkFrame(self)
        results_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        results_frame.grid_columnconfigure(0, weight=1)
        results_frame.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(results_frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=5)

        ctk.CTkLabel(
            header,
            text="Discovered Devices",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(side="left")

        self.device_count_label = ctk.CTkLabel(
            header,
            text="0 devices found",
            font=ctk.CTkFont(size=13),
            text_color="gray60"
        )
        self.device_count_label.pack(side="right")

        # Results list (scrollable)
        self.results_scroll = ctk.CTkScrollableFrame(results_frame)
        self.results_scroll.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.results_scroll.grid_columnconfigure(0, weight=1)

        # Header row
        self._create_header_row()

    def _create_header_row(self) -> None:
        """Create the header row for results."""
        header = ctk.CTkFrame(self.results_scroll, fg_color=("gray85", "gray25"))
        header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        header.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        headers = ["IP Address", "Hostname", "MAC Address", "Response Time", "Actions"]
        for i, text in enumerate(headers):
            ctk.CTkLabel(
                header,
                text=text,
                font=ctk.CTkFont(size=12, weight="bold")
            ).grid(row=0, column=i, padx=10, pady=8, sticky="w")

    def _start_scan(self) -> None:
        """Start a network scan."""
        if self._is_scanning:
            self._discovery.cancel()
            self.scan_btn.configure(text="Scan Network")
            self._is_scanning = False
            return

        subnet = self.subnet_entry.get().strip() or None
        self._is_scanning = True
        self.scan_btn.configure(text="Cancel Scan")

        # Clear previous results
        for widget in self.results_scroll.winfo_children()[1:]:
            widget.destroy()

        # Start scan in thread
        thread = threading.Thread(target=self._run_scan, args=(subnet,))
        thread.daemon = True
        thread.start()

    def _run_scan(self, subnet: Optional[str]) -> None:
        """Run the scan in a background thread."""
        try:
            devices = self._discovery.scan_subnet(
                subnet=subnet,
                progress_callback=self._update_progress
            )

            # Enrich devices with additional info
            for device in devices:
                self._discovery.enrich_device(device)

            # Update UI from main thread
            self.after(0, lambda: self._display_results(devices))

        except Exception as e:
            logger.error(f"Scan error: {e}")
            self.after(0, lambda: self.progress_label.configure(text=f"Error: {e}"))

        finally:
            self._is_scanning = False
            self.after(0, lambda: self.scan_btn.configure(text="Scan Network"))

    def _update_progress(self, current: int, total: int, ip: str) -> None:
        """Update progress display."""
        percent = (current / total) * 100
        self.after(0, lambda: self.progress_label.configure(
            text=f"Scanning: {current}/{total} ({percent:.0f}%)"
        ))

    def _display_results(self, devices: List) -> None:
        """Display scan results."""
        # Clear existing results
        for widget in self.results_scroll.winfo_children()[1:]:
            widget.destroy()

        self.device_count_label.configure(text=f"{len(devices)} devices found")
        self.progress_label.configure(text="Scan complete")

        for i, device in enumerate(devices):
            self._add_device_row(i + 1, device)

    def _add_device_row(self, row: int, device) -> None:
        """Add a device row to results."""
        # Determine row color based on MK3 candidate
        fg_color = ("gray90", "gray20") if device.is_mk3_candidate else ("transparent", "transparent")

        row_frame = ctk.CTkFrame(self.results_scroll, fg_color=fg_color)
        row_frame.grid(row=row, column=0, sticky="ew", pady=2)
        row_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        # IP Address
        ip_label = ctk.CTkLabel(
            row_frame,
            text=device.ip_address,
            font=ctk.CTkFont(size=13, weight="bold" if device.is_mk3_candidate else "normal")
        )
        ip_label.grid(row=0, column=0, padx=10, pady=8, sticky="w")

        # Hostname
        hostname = device.hostname or "-"
        ctk.CTkLabel(
            row_frame,
            text=hostname,
            font=ctk.CTkFont(size=13)
        ).grid(row=0, column=1, padx=10, pady=8, sticky="w")

        # MAC Address
        mac = device.mac_address or "-"
        ctk.CTkLabel(
            row_frame,
            text=mac,
            font=ctk.CTkFont(size=12, family="Consolas")
        ).grid(row=0, column=2, padx=10, pady=8, sticky="w")

        # Response Time
        resp_time = f"{device.response_time_ms:.1f}ms" if device.response_time_ms else "-"
        ctk.CTkLabel(
            row_frame,
            text=resp_time,
            font=ctk.CTkFont(size=13)
        ).grid(row=0, column=3, padx=10, pady=8, sticky="w")

        # Actions
        actions_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
        actions_frame.grid(row=0, column=4, padx=10, pady=5, sticky="w")

        select_btn = ctk.CTkButton(
            actions_frame,
            text="Select",
            width=70,
            height=28,
            command=lambda ip=device.ip_address: self._select_device(ip),
            font=ctk.CTkFont(size=12)
        )
        select_btn.pack(side="left", padx=2)

        if device.open_ports:
            ports_text = ", ".join(str(p) for p in device.open_ports[:3])
            if len(device.open_ports) > 3:
                ports_text += "..."
            ctk.CTkLabel(
                actions_frame,
                text=f"Ports: {ports_text}",
                font=ctk.CTkFont(size=11),
                text_color="gray60"
            ).pack(side="left", padx=10)

    def _select_device(self, ip: str) -> None:
        """Select a device as the target."""
        if self._on_ip_selected:
            self._on_ip_selected(ip)
        logger.info(f"Selected device: {ip}")

    def _quick_scan(self) -> None:
        """Perform a quick scan of a single IP."""
        ip = self.quick_ip_entry.get().strip()
        if not ip:
            return

        self.quick_scan_btn.configure(state="disabled", text="Scanning...")

        def run():
            try:
                device = self._discovery.quick_scan(ip, self.config.common_ports[:10])
                self.after(0, lambda: self._display_quick_result(device))
            except Exception as e:
                logger.error(f"Quick scan error: {e}")
            finally:
                self.after(0, lambda: self.quick_scan_btn.configure(
                    state="normal", text="Quick Scan"
                ))

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def _display_quick_result(self, device) -> None:
        """Display quick scan result."""
        # Clear and add single result
        for widget in self.results_scroll.winfo_children()[1:]:
            widget.destroy()

        if device.response_time_ms is not None:
            self.device_count_label.configure(text="1 device found")
            self._add_device_row(1, device)
        else:
            self.device_count_label.configure(text="Device not responding")
