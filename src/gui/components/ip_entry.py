"""IP Address entry widget with validation and history."""

import customtkinter as ctk
import re
from typing import Optional, Callable, List


class IPEntry(ctk.CTkFrame):
    """
    A widget for entering IP addresses with validation and history dropdown.
    """

    IP_PATTERN = re.compile(
        r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )

    def __init__(
        self,
        master,
        label: str = "IP Address:",
        placeholder: str = "192.168.1.100",
        recent_ips: Optional[List[str]] = None,
        on_submit: Optional[Callable[[str], None]] = None,
        **kwargs
    ):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._on_submit = on_submit
        self._recent_ips = recent_ips or []
        self._validation_label: Optional[ctk.CTkLabel] = None

        # Create widgets
        self._label = ctk.CTkLabel(
            self,
            text=label,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self._label.pack(side="left", padx=(0, 10))

        # Entry frame with dropdown
        self._entry_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._entry_frame.pack(side="left", fill="x", expand=True)

        self._entry = ctk.CTkEntry(
            self._entry_frame,
            placeholder_text=placeholder,
            width=200,
            font=ctk.CTkFont(size=14)
        )
        self._entry.pack(side="left", padx=(0, 5))
        self._entry.bind("<Return>", self._on_enter_pressed)
        self._entry.bind("<KeyRelease>", self._on_key_release)

        # Recent IPs dropdown (if any)
        if self._recent_ips:
            self._dropdown = ctk.CTkOptionMenu(
                self._entry_frame,
                values=self._recent_ips,
                command=self._on_dropdown_select,
                width=40,
                font=ctk.CTkFont(size=12)
            )
            self._dropdown.set("▼")
            self._dropdown.pack(side="left", padx=(0, 5))

        # Go button
        self._go_button = ctk.CTkButton(
            self._entry_frame,
            text="Go",
            width=60,
            command=self._submit,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self._go_button.pack(side="left", padx=(0, 10))

        # Validation indicator
        self._status_label = ctk.CTkLabel(
            self._entry_frame,
            text="",
            font=ctk.CTkFont(size=12),
            width=20
        )
        self._status_label.pack(side="left")

    def _on_enter_pressed(self, event) -> None:
        """Handle Enter key press."""
        self._submit()

    def _on_key_release(self, event) -> None:
        """Handle key release for validation feedback."""
        self._validate_and_update_status()

    def _validate_and_update_status(self) -> bool:
        """Validate current input and update status indicator."""
        ip = self._entry.get().strip()

        if not ip:
            self._status_label.configure(text="", text_color="gray")
            return False

        if self.IP_PATTERN.match(ip):
            self._status_label.configure(text="✓", text_color="green")
            return True
        else:
            self._status_label.configure(text="✗", text_color="red")
            return False

    def _on_dropdown_select(self, value: str) -> None:
        """Handle dropdown selection."""
        self._entry.delete(0, "end")
        self._entry.insert(0, value)
        self._validate_and_update_status()

    def _submit(self) -> None:
        """Submit the current IP address."""
        if self._validate_and_update_status():
            ip = self._entry.get().strip()
            if self._on_submit:
                self._on_submit(ip)

    def get(self) -> str:
        """Get the current IP address value."""
        return self._entry.get().strip()

    def set(self, ip: str) -> None:
        """Set the IP address value."""
        self._entry.delete(0, "end")
        self._entry.insert(0, ip)
        self._validate_and_update_status()

    def is_valid(self) -> bool:
        """Check if the current value is a valid IP address."""
        return self._validate_and_update_status()

    def update_recent_ips(self, ips: List[str]) -> None:
        """Update the dropdown with new recent IPs."""
        self._recent_ips = ips
        if hasattr(self, '_dropdown'):
            self._dropdown.configure(values=ips)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the widget."""
        state = "normal" if enabled else "disabled"
        self._entry.configure(state=state)
        self._go_button.configure(state=state)
        if hasattr(self, '_dropdown'):
            self._dropdown.configure(state=state)
