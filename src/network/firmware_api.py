"""
Sonance Beta Portal — Firmware API Client.

Provides access to the firmware hosting platform at sonance-beta.info
for listing hardware models, firmware versions, checking for updates,
and downloading firmware binaries.

API Docs: https://sonance-beta.info (Admin > API Keys for access)
"""

import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import requests

from ..utils import get_logger

logger = get_logger(__name__)

BASE_URL = "https://sonance-beta.info/api/v1"
DEFAULT_TIMEOUT = 15


@dataclass
class HardwareModel:
    """A hardware model from the firmware platform."""
    id: int
    name: str
    model_number: str
    category: str = ""
    description: str = ""
    active: bool = True


@dataclass
class FirmwareInfo:
    """Firmware version info from the platform."""
    id: int
    name: str
    version: str
    channel: str
    status: str
    is_channel_current: bool = False
    file_name: str = ""
    file_size: int = 0
    checksum_sha256: str = ""
    description: str = ""
    release_notes: str = ""
    build_number: str = ""
    released_at: Optional[str] = None
    created_at: Optional[str] = None
    hardware_models: List[Dict] = field(default_factory=list)
    download_count: int = 0
    version_major: int = 0
    version_minor: int = 0
    version_patch: int = 0
    version_prerelease: Optional[str] = None

    @property
    def version_tuple(self):
        return (self.version_major, self.version_minor, self.version_patch)

    @property
    def channel_badge_color(self) -> str:
        colors = {
            "stable": "#22c55e",
            "beta": "#f59e0b",
            "alpha": "#ef4444",
            "hotfix": "#a855f7",
        }
        return colors.get(self.channel, "#64748b")


@dataclass
class UpdateCheck:
    """Result of an update check for a specific device."""
    update_available: bool
    current_version: str
    latest: Optional[FirmwareInfo] = None


class FirmwareAPIClient:
    """Client for the Sonance firmware hosting API."""

    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._session = requests.Session()
        if api_key:
            self._session.headers["Authorization"] = f"Bearer {api_key}"
        self._session.headers["Accept"] = "application/json"

    def set_api_key(self, api_key: str) -> None:
        self._api_key = api_key
        self._session.headers["Authorization"] = f"Bearer {api_key}"

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        """Make a GET request and return the parsed JSON."""
        url = f"{BASE_URL}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                raise APIError(data.get("error", "Unknown API error"))
            return data
        except requests.ConnectionError:
            raise APIError("Cannot connect to sonance-beta.info — check your internet connection")
        except requests.Timeout:
            raise APIError("Request timed out")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                raise APIError("Invalid API key — check your key in Settings")
            raise APIError(f"HTTP error: {e}")

    # ── Hardware Models ──────────────────────────────────────────────

    def list_hardware(self) -> List[HardwareModel]:
        """List all active hardware models."""
        data = self._get("/hardware")
        models = []
        for item in data.get("data", []):
            models.append(HardwareModel(
                id=item["id"],
                name=item.get("name", ""),
                model_number=item.get("model_number", ""),
                category=item.get("category", ""),
                description=item.get("description", ""),
                active=item.get("active", True),
            ))
        return models

    # ── Firmware Listing ─────────────────────────────────────────────

    def list_firmware(
        self,
        channel: Optional[str] = None,
        status: Optional[str] = None,
        hardware_model_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[FirmwareInfo]:
        """List firmware versions with optional filters."""
        params: Dict = {"limit": limit, "sort": "version_desc"}
        if channel:
            params["channel"] = channel
        if status:
            params["status"] = status
        if hardware_model_id:
            params["hardware_model"] = hardware_model_id

        data = self._get("/firmware", params=params)
        return [self._parse_firmware(item) for item in data.get("data", [])]

    def get_firmware(self, firmware_id: int) -> FirmwareInfo:
        """Get detailed info for a specific firmware."""
        data = self._get(f"/firmware/{firmware_id}")
        return self._parse_firmware(data["data"])

    def get_latest(
        self,
        channel: str = "stable",
        hardware_model_id: Optional[int] = None,
        current_version: Optional[str] = None,
    ) -> UpdateCheck:
        """Check for the latest firmware on a channel."""
        params: Dict = {"channel": channel}
        if hardware_model_id:
            params["hardware_model_id"] = hardware_model_id
        if current_version:
            params["current_version"] = current_version

        data = self._get("/firmware/latest", params=params)
        fw_data = data.get("data")

        if fw_data is None:
            return UpdateCheck(
                update_available=False,
                current_version=current_version or "",
            )

        firmware = self._parse_firmware(fw_data)
        update_available = fw_data.get("update_available", False)

        return UpdateCheck(
            update_available=update_available,
            current_version=current_version or "",
            latest=firmware,
        )

    def get_download_url(self, firmware_id: int) -> str:
        """Get a signed download URL for a firmware binary."""
        data = self._get(f"/firmware/{firmware_id}/download", params={"format": "json"})
        return data["data"]["download_url"]

    def list_channels(self) -> List[Dict]:
        """List all firmware channels with their current released firmware."""
        data = self._get("/channels")
        return data.get("data", [])

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_firmware(item: Dict) -> FirmwareInfo:
        return FirmwareInfo(
            id=item.get("id", 0),
            name=item.get("name", ""),
            version=item.get("version", ""),
            channel=item.get("channel", ""),
            status=item.get("status", ""),
            is_channel_current=item.get("is_channel_current", False),
            file_name=item.get("file_name", ""),
            file_size=item.get("file_size", 0),
            checksum_sha256=item.get("checksum_sha256", ""),
            description=item.get("description", ""),
            release_notes=item.get("release_notes", ""),
            build_number=item.get("build_number", ""),
            released_at=item.get("released_at"),
            created_at=item.get("created_at"),
            hardware_models=item.get("hardware_models", []),
            download_count=item.get("download_count", 0),
            version_major=item.get("version_major", 0),
            version_minor=item.get("version_minor", 0),
            version_patch=item.get("version_patch", 0),
            version_prerelease=item.get("version_prerelease"),
        )


class APIError(Exception):
    """Raised when a firmware API call fails."""
    pass


# ── Async helpers for GUI usage ──────────────────────────────────────

def fetch_async(func: Callable, callback: Callable, *args, **kwargs) -> None:
    """Run an API call in a background thread, then call callback with the result."""
    def _run():
        try:
            result = func(*args, **kwargs)
            callback(result, None)
        except Exception as e:
            callback(None, e)

    threading.Thread(target=_run, daemon=True).start()
