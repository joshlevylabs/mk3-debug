"""Log viewer component for displaying real-time logs."""

import customtkinter as ctk
from typing import Optional, List, Callable
from datetime import datetime
import threading


class LogViewer(ctk.CTkFrame):
    """
    A scrollable log viewer with filtering and search capabilities.
    """

    LEVEL_COLORS = {
        "DEBUG": "gray60",
        "INFO": "#3498db",
        "WARNING": "#f39c12",
        "ERROR": "#e74c3c",
        "CRITICAL": "#9b59b6",
    }

    def __init__(
        self,
        master,
        show_toolbar: bool = True,
        max_lines: int = 5000,
        auto_scroll: bool = True,
        **kwargs
    ):
        super().__init__(master, **kwargs)

        self._max_lines = max_lines
        self._auto_scroll = auto_scroll
        self._level_filter: Optional[str] = None
        self._search_text: str = ""
        self._line_count = 0
        self._lock = threading.Lock()

        self._build_ui(show_toolbar)

    def _build_ui(self, show_toolbar: bool) -> None:
        """Build the log viewer UI."""
        if show_toolbar:
            self._build_toolbar()

        # Log text area
        self._text_frame = ctk.CTkFrame(self)
        self._text_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self._textbox = ctk.CTkTextbox(
            self._text_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="none",
            state="disabled"
        )
        self._textbox.pack(fill="both", expand=True)

        # Configure text tags for log levels
        for level, color in self.LEVEL_COLORS.items():
            self._textbox._textbox.tag_configure(level, foreground=color)

        self._textbox._textbox.tag_configure("timestamp", foreground="gray50")
        self._textbox._textbox.tag_configure("highlight", background="yellow", foreground="black")

    def _build_toolbar(self) -> None:
        """Build the toolbar with controls."""
        self._toolbar = ctk.CTkFrame(self, height=40)
        self._toolbar.pack(fill="x", padx=5, pady=(5, 0))

        # Level filter
        ctk.CTkLabel(
            self._toolbar,
            text="Level:",
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(5, 2))

        self._level_menu = ctk.CTkOptionMenu(
            self._toolbar,
            values=["All", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            command=self._on_level_filter_change,
            width=100,
            font=ctk.CTkFont(size=12)
        )
        self._level_menu.set("All")
        self._level_menu.pack(side="left", padx=5)

        # Search
        ctk.CTkLabel(
            self._toolbar,
            text="Search:",
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(15, 2))

        self._search_entry = ctk.CTkEntry(
            self._toolbar,
            placeholder_text="Filter logs...",
            width=200,
            font=ctk.CTkFont(size=12)
        )
        self._search_entry.pack(side="left", padx=5)
        self._search_entry.bind("<Return>", lambda e: self._apply_search())
        self._search_entry.bind("<KeyRelease>", lambda e: self._apply_search())

        # Clear button
        self._clear_btn = ctk.CTkButton(
            self._toolbar,
            text="Clear",
            width=60,
            command=self.clear,
            font=ctk.CTkFont(size=12)
        )
        self._clear_btn.pack(side="right", padx=5)

        # Export button
        self._export_btn = ctk.CTkButton(
            self._toolbar,
            text="Export",
            width=70,
            command=self._export_logs,
            font=ctk.CTkFont(size=12)
        )
        self._export_btn.pack(side="right", padx=5)

        # Auto-scroll toggle
        self._autoscroll_var = ctk.BooleanVar(value=self._auto_scroll)
        self._autoscroll_check = ctk.CTkCheckBox(
            self._toolbar,
            text="Auto-scroll",
            variable=self._autoscroll_var,
            command=self._on_autoscroll_toggle,
            font=ctk.CTkFont(size=12)
        )
        self._autoscroll_check.pack(side="right", padx=10)

    def _on_level_filter_change(self, value: str) -> None:
        """Handle level filter change."""
        self._level_filter = None if value == "All" else value
        # Note: For real-time filtering, we'd need to re-filter existing entries
        # This implementation filters new entries only

    def _apply_search(self) -> None:
        """Apply search highlighting."""
        search_text = self._search_entry.get().strip()
        self._search_text = search_text

        # Remove existing highlights
        self._textbox._textbox.tag_remove("highlight", "1.0", "end")

        if not search_text:
            return

        # Add highlights for matching text
        start = "1.0"
        while True:
            pos = self._textbox._textbox.search(
                search_text, start, stopindex="end", nocase=True
            )
            if not pos:
                break
            end = f"{pos}+{len(search_text)}c"
            self._textbox._textbox.tag_add("highlight", pos, end)
            start = end

    def _on_autoscroll_toggle(self) -> None:
        """Handle auto-scroll toggle."""
        self._auto_scroll = self._autoscroll_var.get()

    def _export_logs(self) -> None:
        """Export logs to file."""
        from tkinter import filedialog
        from datetime import datetime

        filename = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"mk3_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )

        if filename:
            content = self._textbox._textbox.get("1.0", "end")
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)

    def add_log(
        self,
        message: str,
        level: str = "INFO",
        timestamp: Optional[datetime] = None
    ) -> None:
        """Add a log entry to the viewer."""
        if timestamp is None:
            timestamp = datetime.now()

        # Apply level filter
        if self._level_filter and level != self._level_filter:
            return

        # Format the log line
        ts_str = timestamp.strftime("%H:%M:%S.%f")[:-3]
        log_line = f"[{ts_str}] [{level:8}] {message}\n"

        with self._lock:
            self._textbox.configure(state="normal")

            # Trim old lines if needed
            self._line_count += 1
            if self._line_count > self._max_lines:
                self._textbox._textbox.delete("1.0", "2.0")
                self._line_count -= 1

            # Insert the log line
            self._textbox._textbox.insert("end", f"[{ts_str}] ", "timestamp")
            self._textbox._textbox.insert("end", f"[{level:8}] ", level)
            self._textbox._textbox.insert("end", f"{message}\n")

            # Auto-scroll if enabled
            if self._auto_scroll:
                self._textbox._textbox.see("end")

            self._textbox.configure(state="disabled")

        # Apply search highlighting if active
        if self._search_text:
            self._apply_search()

    def clear(self) -> None:
        """Clear all log entries."""
        with self._lock:
            self._textbox.configure(state="normal")
            self._textbox._textbox.delete("1.0", "end")
            self._textbox.configure(state="disabled")
            self._line_count = 0

    def get_content(self) -> str:
        """Get all log content as a string."""
        return self._textbox._textbox.get("1.0", "end")

    def set_max_lines(self, max_lines: int) -> None:
        """Set the maximum number of lines to keep."""
        self._max_lines = max_lines
