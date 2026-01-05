"""Logs viewer tab frame."""

import customtkinter as ctk
from typing import Optional

from ...utils.logging_config import LogBuffer, LogEntry
from ..components import LogViewer

from ...utils import get_logger

logger = get_logger(__name__)


class LogsFrame(ctk.CTkFrame):
    """
    Frame for viewing application logs.
    """

    def __init__(
        self,
        master,
        log_buffer: LogBuffer,
        **kwargs
    ):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._log_buffer = log_buffer

        self._build_ui()

        # Subscribe to new log entries
        self._log_buffer.add_callback(self._on_new_log)

        # Load existing entries
        self._load_existing_logs()

    def _build_ui(self) -> None:
        """Build the UI."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Log viewer
        self.log_viewer = LogViewer(
            self,
            show_toolbar=True,
            max_lines=10000,
            auto_scroll=True
        )
        self.log_viewer.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    def _load_existing_logs(self) -> None:
        """Load existing log entries."""
        entries = self._log_buffer.get_entries()
        for entry in entries:
            self.log_viewer.add_log(
                entry.message,
                entry.level,
                entry.timestamp
            )

    def _on_new_log(self, entry: LogEntry) -> None:
        """Handle new log entry."""
        # Use after() to safely update from any thread
        self.after(0, lambda: self.log_viewer.add_log(
            entry.message,
            entry.level,
            entry.timestamp
        ))

    def destroy(self) -> None:
        """Clean up when frame is destroyed."""
        self._log_buffer.remove_callback(self._on_new_log)
        super().destroy()
