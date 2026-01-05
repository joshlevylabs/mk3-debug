"""Result card component for displaying test results - Enhanced Corporate Design."""

import customtkinter as ctk
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum


class ResultStatus(Enum):
    """Status of a test result."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"


class Severity(Enum):
    """Severity level for issues."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class TestResult:
    """Represents a single test result."""
    name: str
    status: ResultStatus
    message: str = ""
    details: str = ""
    duration_ms: Optional[float] = None


class ResultCard(ctk.CTkFrame):
    """
    A modern card component for displaying test results with status indicator.
    Features a polished, corporate design with smooth animations.
    """

    # Modern corporate color palette
    STATUS_COLORS = {
        ResultStatus.PENDING: {"primary": "#64748b", "bg": "#1e293b", "icon_bg": "#334155"},
        ResultStatus.RUNNING: {"primary": "#3b82f6", "bg": "#1e3a5f", "icon_bg": "#1d4ed8"},
        ResultStatus.PASSED: {"primary": "#10b981", "bg": "#064e3b", "icon_bg": "#047857"},
        ResultStatus.FAILED: {"primary": "#ef4444", "bg": "#450a0a", "icon_bg": "#b91c1c"},
        ResultStatus.WARNING: {"primary": "#f59e0b", "bg": "#451a03", "icon_bg": "#b45309"},
        ResultStatus.ERROR: {"primary": "#a855f7", "bg": "#3b0764", "icon_bg": "#7e22ce"},
        ResultStatus.SKIPPED: {"primary": "#6b7280", "bg": "#1f2937", "icon_bg": "#374151"},
    }

    STATUS_ICONS = {
        ResultStatus.PENDING: "○",
        ResultStatus.RUNNING: "◉",
        ResultStatus.PASSED: "✓",
        ResultStatus.FAILED: "✗",
        ResultStatus.WARNING: "!",
        ResultStatus.ERROR: "⊘",
        ResultStatus.SKIPPED: "−",
    }

    SEVERITY_COLORS = {
        Severity.CRITICAL: "#dc2626",
        Severity.HIGH: "#ea580c",
        Severity.MEDIUM: "#d97706",
        Severity.LOW: "#2563eb",
        Severity.INFO: "#64748b",
    }

    def __init__(
        self,
        master,
        test_name: str,
        status: ResultStatus = ResultStatus.PENDING,
        message: str = "",
        details: str = "",
        duration_ms: Optional[float] = None,
        expandable: bool = True,
        **kwargs
    ):
        # Set the card background color based on status
        colors = self.STATUS_COLORS.get(status, self.STATUS_COLORS[ResultStatus.PENDING])

        super().__init__(
            master,
            corner_radius=12,
            fg_color=colors["bg"],
            border_width=1,
            border_color=colors["primary"],
            **kwargs
        )

        self._test_name = test_name
        self._status = status
        self._message = message
        self._details = details
        self._duration_ms = duration_ms
        self._expandable = expandable
        self._expanded = False

        self._build_ui()
        self._update_display()

    def _build_ui(self) -> None:
        """Build the modern card UI."""
        # Main container with padding
        self._main_container = ctk.CTkFrame(self, fg_color="transparent")
        self._main_container.pack(fill="x", padx=16, pady=12)

        # Top row: Status icon, name, message, duration, expand button
        self._top_row = ctk.CTkFrame(self._main_container, fg_color="transparent")
        self._top_row.pack(fill="x")

        # Status icon container (circular badge)
        colors = self.STATUS_COLORS.get(self._status, self.STATUS_COLORS[ResultStatus.PENDING])
        self._icon_container = ctk.CTkFrame(
            self._top_row,
            width=36,
            height=36,
            corner_radius=18,
            fg_color=colors["icon_bg"]
        )
        self._icon_container.pack(side="left")
        self._icon_container.pack_propagate(False)

        self._status_icon = ctk.CTkLabel(
            self._icon_container,
            text="○",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="white"
        )
        self._status_icon.place(relx=0.5, rely=0.5, anchor="center")

        # Text container
        self._text_container = ctk.CTkFrame(self._top_row, fg_color="transparent")
        self._text_container.pack(side="left", fill="x", expand=True, padx=(12, 8))

        # Test name (bold, larger)
        self._name_label = ctk.CTkLabel(
            self._text_container,
            text=self._test_name,
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
            text_color="#f8fafc"
        )
        self._name_label.pack(anchor="w")

        # Message (smaller, secondary color)
        self._message_label = ctk.CTkLabel(
            self._text_container,
            text=self._message,
            font=ctk.CTkFont(size=13),
            anchor="w",
            text_color="#94a3b8"
        )
        self._message_label.pack(anchor="w", pady=(2, 0))

        # Right side container
        self._right_container = ctk.CTkFrame(self._top_row, fg_color="transparent")
        self._right_container.pack(side="right")

        # Duration badge
        self._duration_badge = ctk.CTkFrame(
            self._right_container,
            corner_radius=6,
            fg_color="#374151",
            height=24
        )
        self._duration_badge.pack(side="left", padx=(0, 8))

        self._duration_label = ctk.CTkLabel(
            self._duration_badge,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af"
        )
        self._duration_label.pack(padx=8, pady=2)

        # Expand button (modern chevron)
        if self._expandable:
            self._expand_btn = ctk.CTkButton(
                self._right_container,
                text="▾",
                width=32,
                height=32,
                corner_radius=8,
                font=ctk.CTkFont(size=12),
                fg_color="transparent",
                hover_color="#475569",
                text_color="#94a3b8",
                command=self._toggle_expand
            )
            self._expand_btn.pack(side="right")

        # Details frame (hidden initially) - more polished design
        self._details_frame = ctk.CTkFrame(
            self._main_container,
            fg_color="#0f172a",
            corner_radius=8,
            border_width=1,
            border_color="#334155"
        )

        self._details_text = ctk.CTkTextbox(
            self._details_frame,
            height=120,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            fg_color="transparent",
            text_color="#cbd5e1",
            border_width=0
        )
        self._details_text.pack(fill="both", expand=True, padx=12, pady=10)

        # Make main frame clickable for expansion
        if self._expandable:
            for widget in [self._top_row, self._text_container, self._name_label, self._message_label]:
                widget.bind("<Button-1>", lambda e: self._toggle_expand())
                widget.bind("<Enter>", lambda e: self.configure(cursor="hand2"))
                widget.bind("<Leave>", lambda e: self.configure(cursor=""))

    def _toggle_expand(self) -> None:
        """Toggle the expanded state with smooth animation."""
        if not self._details:
            return

        self._expanded = not self._expanded
        if self._expanded:
            self._details_frame.pack(fill="x", pady=(12, 0))
            self._expand_btn.configure(text="▴")
        else:
            self._details_frame.pack_forget()
            self._expand_btn.configure(text="▾")

    def _update_display(self) -> None:
        """Update the display based on current state."""
        # Get colors for current status
        colors = self.STATUS_COLORS.get(self._status, self.STATUS_COLORS[ResultStatus.PENDING])
        icon = self.STATUS_ICONS.get(self._status, "○")

        # Update card styling
        self.configure(fg_color=colors["bg"], border_color=colors["primary"])

        # Update icon
        self._icon_container.configure(fg_color=colors["icon_bg"])
        self._status_icon.configure(text=icon, text_color="white")

        # Update message
        self._message_label.configure(text=self._message)

        # Update duration
        if self._duration_ms is not None:
            if self._duration_ms < 1000:
                duration_text = f"{self._duration_ms:.0f}ms"
            else:
                duration_text = f"{self._duration_ms/1000:.1f}s"
            self._duration_label.configure(text=duration_text)
            self._duration_badge.pack(side="left", padx=(0, 8))
        else:
            self._duration_badge.pack_forget()

        # Update details
        if self._details:
            self._details_text.configure(state="normal")
            self._details_text.delete("1.0", "end")
            self._details_text.insert("1.0", self._details)
            self._details_text.configure(state="disabled")

            if self._expandable and hasattr(self, '_expand_btn'):
                self._expand_btn.pack(side="right")
        else:
            if self._expandable and hasattr(self, '_expand_btn'):
                self._expand_btn.pack_forget()

    def update_result(
        self,
        status: Optional[ResultStatus] = None,
        message: Optional[str] = None,
        details: Optional[str] = None,
        duration_ms: Optional[float] = None
    ) -> None:
        """Update the result card with new values."""
        if status is not None:
            self._status = status
        if message is not None:
            self._message = message
        if details is not None:
            self._details = details
        if duration_ms is not None:
            self._duration_ms = duration_ms

        self._update_display()

    def set_running(self, message: str = "Running...") -> None:
        """Set the card to running state."""
        self.update_result(status=ResultStatus.RUNNING, message=message)

    def set_passed(self, message: str = "Passed", details: str = "",
                   duration_ms: Optional[float] = None) -> None:
        """Set the card to passed state."""
        self.update_result(
            status=ResultStatus.PASSED,
            message=message,
            details=details,
            duration_ms=duration_ms
        )

    def set_failed(self, message: str = "Failed", details: str = "",
                   duration_ms: Optional[float] = None) -> None:
        """Set the card to failed state."""
        self.update_result(
            status=ResultStatus.FAILED,
            message=message,
            details=details,
            duration_ms=duration_ms
        )

    def set_warning(self, message: str = "Warning", details: str = "",
                    duration_ms: Optional[float] = None) -> None:
        """Set the card to warning state."""
        self.update_result(
            status=ResultStatus.WARNING,
            message=message,
            details=details,
            duration_ms=duration_ms
        )

    @property
    def status(self) -> ResultStatus:
        """Get the current status."""
        return self._status

    @property
    def test_name(self) -> str:
        """Get the test name."""
        return self._test_name


class EnhancedIssueCard(ctk.CTkFrame):
    """
    A modern issue card with root cause analysis display.
    Designed for corporate diagnostic reports.
    """

    SEVERITY_STYLES = {
        "critical": {"bg": "#450a0a", "border": "#dc2626", "badge": "#dc2626", "text": "CRITICAL"},
        "high": {"bg": "#431407", "border": "#ea580c", "badge": "#ea580c", "text": "HIGH"},
        "medium": {"bg": "#451a03", "border": "#d97706", "badge": "#d97706", "text": "MEDIUM"},
        "low": {"bg": "#172554", "border": "#2563eb", "badge": "#2563eb", "text": "LOW"},
        "info": {"bg": "#1e293b", "border": "#64748b", "badge": "#64748b", "text": "INFO"},
    }

    def __init__(
        self,
        master,
        title: str,
        severity: str = "medium",
        description: str = "",
        root_cause: Optional[Dict[str, Any]] = None,
        corrective_actions: Optional[List[Dict[str, Any]]] = None,
        affected_functionality: Optional[List[str]] = None,
        firmware_relevant: bool = False,
        **kwargs
    ):
        style = self.SEVERITY_STYLES.get(severity.lower(), self.SEVERITY_STYLES["medium"])

        super().__init__(
            master,
            corner_radius=12,
            fg_color=style["bg"],
            border_width=2,
            border_color=style["border"],
            **kwargs
        )

        self._title = title
        self._severity = severity
        self._description = description
        self._root_cause = root_cause or {}
        self._corrective_actions = corrective_actions or []
        self._affected_functionality = affected_functionality or []
        self._firmware_relevant = firmware_relevant
        self._style = style

        self._build_ui()

    def _build_ui(self) -> None:
        """Build the enhanced issue card UI."""
        # Main container
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="x", padx=20, pady=16)

        # Header row
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x")

        # Severity badge
        severity_badge = ctk.CTkFrame(
            header,
            corner_radius=6,
            fg_color=self._style["badge"],
            height=24
        )
        severity_badge.pack(side="left")

        ctk.CTkLabel(
            severity_badge,
            text=self._style["text"],
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="white"
        ).pack(padx=10, pady=3)

        # Firmware badge if relevant
        if self._firmware_relevant:
            fw_badge = ctk.CTkFrame(
                header,
                corner_radius=6,
                fg_color="#7e22ce",
                height=24
            )
            fw_badge.pack(side="left", padx=(8, 0))

            ctk.CTkLabel(
                fw_badge,
                text="FIRMWARE TEAM",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="white"
            ).pack(padx=10, pady=3)

        # Title
        ctk.CTkLabel(
            container,
            text=self._title,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#f8fafc",
            anchor="w"
        ).pack(anchor="w", pady=(12, 4))

        # Description
        ctk.CTkLabel(
            container,
            text=self._description,
            font=ctk.CTkFont(size=13),
            text_color="#cbd5e1",
            anchor="w",
            wraplength=700,
            justify="left"
        ).pack(anchor="w", pady=(0, 16))

        # Root Cause Analysis Section
        if self._root_cause:
            self._build_root_cause_section(container)

        # Corrective Actions Section
        if self._corrective_actions:
            self._build_actions_section(container)

        # Affected Functionality Section
        if self._affected_functionality:
            self._build_affected_section(container)

    def _build_root_cause_section(self, parent) -> None:
        """Build the root cause analysis section."""
        section = ctk.CTkFrame(parent, fg_color="#0f172a", corner_radius=8)
        section.pack(fill="x", pady=(0, 12))

        inner = ctk.CTkFrame(section, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        # Section header
        header_row = ctk.CTkFrame(inner, fg_color="transparent")
        header_row.pack(fill="x")

        ctk.CTkLabel(
            header_row,
            text="🔍",
            font=ctk.CTkFont(size=14)
        ).pack(side="left")

        ctk.CTkLabel(
            header_row,
            text="Root Cause Analysis",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#60a5fa"
        ).pack(side="left", padx=(8, 0))

        # Category
        if self._root_cause.get("category"):
            ctk.CTkLabel(
                inner,
                text=f"Category: {self._root_cause['category']}",
                font=ctk.CTkFont(size=12),
                text_color="#94a3b8",
                anchor="w"
            ).pack(anchor="w", pady=(10, 4))

        # Technical details
        if self._root_cause.get("technical_details"):
            tech_frame = ctk.CTkFrame(inner, fg_color="#1e293b", corner_radius=6)
            tech_frame.pack(fill="x", pady=(8, 0))

            ctk.CTkLabel(
                tech_frame,
                text=self._root_cause["technical_details"],
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color="#e2e8f0",
                anchor="w",
                wraplength=650,
                justify="left"
            ).pack(padx=12, pady=10, anchor="w")

        # Evidence
        if self._root_cause.get("evidence"):
            ctk.CTkLabel(
                inner,
                text="Evidence:",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#94a3b8",
                anchor="w"
            ).pack(anchor="w", pady=(12, 4))

            for evidence in self._root_cause["evidence"]:
                ctk.CTkLabel(
                    inner,
                    text=f"  • {evidence}",
                    font=ctk.CTkFont(size=11),
                    text_color="#94a3b8",
                    anchor="w",
                    wraplength=640,
                    justify="left"
                ).pack(anchor="w", padx=(8, 0))

    def _build_actions_section(self, parent) -> None:
        """Build the corrective actions section."""
        section = ctk.CTkFrame(parent, fg_color="#052e16", corner_radius=8, border_width=1, border_color="#166534")
        section.pack(fill="x", pady=(0, 12))

        inner = ctk.CTkFrame(section, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        # Section header
        header_row = ctk.CTkFrame(inner, fg_color="transparent")
        header_row.pack(fill="x")

        ctk.CTkLabel(
            header_row,
            text="✓",
            font=ctk.CTkFont(size=14),
            text_color="#22c55e"
        ).pack(side="left")

        ctk.CTkLabel(
            header_row,
            text="Corrective Actions",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#22c55e"
        ).pack(side="left", padx=(8, 0))

        # Actions list
        for action in self._corrective_actions:
            action_frame = ctk.CTkFrame(inner, fg_color="#0f172a", corner_radius=6)
            action_frame.pack(fill="x", pady=(10, 0))

            action_inner = ctk.CTkFrame(action_frame, fg_color="transparent")
            action_inner.pack(fill="x", padx=12, pady=10)

            # Priority and owner row
            meta_row = ctk.CTkFrame(action_inner, fg_color="transparent")
            meta_row.pack(fill="x")

            # Priority badge
            priority = action.get("priority", 1)
            priority_badge = ctk.CTkFrame(meta_row, corner_radius=10, fg_color="#22c55e", width=24, height=24)
            priority_badge.pack(side="left")
            priority_badge.pack_propagate(False)

            ctk.CTkLabel(
                priority_badge,
                text=str(priority),
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="white"
            ).place(relx=0.5, rely=0.5, anchor="center")

            # Action title
            ctk.CTkLabel(
                meta_row,
                text=action.get("action", ""),
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#f8fafc",
                anchor="w"
            ).pack(side="left", padx=(10, 0))

            # Owner badge
            owner = action.get("responsible_party", "")
            if owner:
                owner_badge = ctk.CTkFrame(meta_row, corner_radius=4, fg_color="#374151")
                owner_badge.pack(side="right", padx=(0, 8))

                ctk.CTkLabel(
                    owner_badge,
                    text=owner,
                    font=ctk.CTkFont(size=10),
                    text_color="#9ca3af"
                ).pack(padx=8, pady=2)

            # Complexity badge
            complexity = action.get("estimated_complexity", "low")
            complexity_colors = {"low": "#22c55e", "medium": "#f59e0b", "high": "#ef4444"}

            complexity_badge = ctk.CTkFrame(meta_row, corner_radius=4, fg_color=complexity_colors.get(complexity, "#6b7280"))
            complexity_badge.pack(side="right")

            ctk.CTkLabel(
                complexity_badge,
                text=complexity,
                font=ctk.CTkFont(size=10),
                text_color="white"
            ).pack(padx=8, pady=2)

            # Description
            if action.get("description"):
                ctk.CTkLabel(
                    action_inner,
                    text=action["description"],
                    font=ctk.CTkFont(size=12),
                    text_color="#cbd5e1",
                    anchor="w",
                    wraplength=620,
                    justify="left"
                ).pack(anchor="w", pady=(8, 0))

            # Verification steps
            if action.get("verification_steps"):
                ctk.CTkLabel(
                    action_inner,
                    text="Verification:",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color="#94a3b8",
                    anchor="w"
                ).pack(anchor="w", pady=(8, 4))

                for i, step in enumerate(action["verification_steps"], 1):
                    ctk.CTkLabel(
                        action_inner,
                        text=f"  {i}. {step}",
                        font=ctk.CTkFont(size=11),
                        text_color="#94a3b8",
                        anchor="w",
                        wraplength=600,
                        justify="left"
                    ).pack(anchor="w")

    def _build_affected_section(self, parent) -> None:
        """Build the affected functionality section."""
        section = ctk.CTkFrame(parent, fg_color="#1e1b4b", corner_radius=8, border_width=1, border_color="#4338ca")
        section.pack(fill="x", pady=(0, 0))

        inner = ctk.CTkFrame(section, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        # Section header
        ctk.CTkLabel(
            inner,
            text="⚡ Affected Functionality",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#a5b4fc",
            anchor="w"
        ).pack(anchor="w")

        # Functionality list
        for func in self._affected_functionality:
            ctk.CTkLabel(
                inner,
                text=f"  • {func}",
                font=ctk.CTkFont(size=11),
                text_color="#c7d2fe",
                anchor="w"
            ).pack(anchor="w", pady=(2, 0))
