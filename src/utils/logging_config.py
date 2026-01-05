"""Logging configuration for MK3 Diagnostic Tool."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, List
from dataclasses import dataclass, field
import threading


@dataclass
class LogEntry:
    """Represents a single log entry."""
    timestamp: datetime
    level: str
    logger_name: str
    message: str

    def format(self) -> str:
        """Format the log entry as a string."""
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        return f"[{ts}] [{self.level:8}] {self.logger_name}: {self.message}"


class LogBuffer:
    """Thread-safe buffer for storing log entries with callbacks."""

    def __init__(self, max_entries: int = 10000):
        self._entries: List[LogEntry] = []
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[LogEntry], None]] = []

    def add(self, entry: LogEntry) -> None:
        """Add a log entry to the buffer."""
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries:]

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(entry)
            except Exception:
                pass

    def get_entries(self, level_filter: Optional[str] = None,
                    search_text: Optional[str] = None) -> List[LogEntry]:
        """Get log entries with optional filtering."""
        with self._lock:
            entries = self._entries.copy()

        if level_filter:
            entries = [e for e in entries if e.level == level_filter]

        if search_text:
            search_lower = search_text.lower()
            entries = [e for e in entries if search_lower in e.message.lower()]

        return entries

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._entries.clear()

    def add_callback(self, callback: Callable[[LogEntry], None]) -> None:
        """Add a callback to be notified of new entries."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[LogEntry], None]) -> None:
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def export_to_file(self, filepath: Path) -> int:
        """Export all entries to a file. Returns number of entries written."""
        with self._lock:
            entries = self._entries.copy()

        with open(filepath, 'w', encoding='utf-8') as f:
            for entry in entries:
                f.write(entry.format() + '\n')

        return len(entries)


# Global log buffer instance
_log_buffer: Optional[LogBuffer] = None


def get_log_buffer() -> LogBuffer:
    """Get the global log buffer instance."""
    global _log_buffer
    if _log_buffer is None:
        _log_buffer = LogBuffer()
    return _log_buffer


class BufferHandler(logging.Handler):
    """Logging handler that writes to the log buffer."""

    def __init__(self, buffer: LogBuffer):
        super().__init__()
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the buffer."""
        entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created),
            level=record.levelname,
            logger_name=record.name,
            message=self.format(record)
        )
        self.buffer.add(entry)


def setup_logging(level: int = logging.DEBUG,
                  log_file: Optional[Path] = None) -> LogBuffer:
    """
    Set up logging for the application.

    Args:
        level: Minimum log level to capture
        log_file: Optional file path to also write logs to

    Returns:
        The LogBuffer instance for GUI access
    """
    buffer = get_log_buffer()

    # Create root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d [%(levelname)-8s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Buffer handler for GUI
    buffer_handler = BufferHandler(buffer)
    buffer_handler.setLevel(level)
    buffer_handler.setFormatter(logging.Formatter('%(message)s'))
    root_logger.addHandler(buffer_handler)

    # Optional file handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return buffer


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name."""
    return logging.getLogger(name)
