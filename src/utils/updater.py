"""Auto-update checker using GitHub Releases API."""

import platform
import threading
import webbrowser
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import requests

from . import get_logger

logger = get_logger(__name__)

GITHUB_REPO = "joshlevylabs/mk3-debug"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


@dataclass
class UpdateInfo:
    """Information about an available update."""
    current_version: str
    latest_version: str
    release_url: str
    download_url: str
    release_notes: str
    is_newer: bool


def parse_version(version_str: str) -> Tuple[int, ...]:
    """Parse a version string like 'v1.2.3' or '1.2.3' into a tuple of ints."""
    clean = version_str.lstrip("vV").strip()
    parts = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) or (0,)


def check_for_update(current_version: str) -> Optional[UpdateInfo]:
    """
    Check GitHub Releases for a newer version.

    Returns UpdateInfo if a newer version is available, None otherwise.
    Returns None on any network error (fails silently).
    """
    try:
        resp = requests.get(
            GITHUB_API_URL,
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        latest_tag = data.get("tag_name", "")
        release_url = data.get("html_url", "")
        release_notes = data.get("body", "")

        current_tuple = parse_version(current_version)
        latest_tuple = parse_version(latest_tag)
        is_newer = latest_tuple > current_tuple

        # Find the right download asset for this platform
        download_url = _get_platform_download_url(data.get("assets", []))
        if not download_url:
            download_url = release_url

        return UpdateInfo(
            current_version=current_version,
            latest_version=latest_tag,
            release_url=release_url,
            download_url=download_url,
            release_notes=release_notes,
            is_newer=is_newer,
        )

    except Exception as exc:
        logger.debug("Update check failed (non-critical): %s", exc)
        return None


def _get_platform_download_url(assets: list) -> Optional[str]:
    """Find the download URL for the current platform from release assets."""
    system = platform.system()

    for asset in assets:
        name = asset.get("name", "").lower()
        url = asset.get("browser_download_url", "")

        if system == "Windows" and "windows" in name and name.endswith(".exe"):
            return url
        elif system == "Darwin" and "macos" in name and name.endswith(".zip"):
            return url
        elif system == "Linux" and "linux" in name:
            return url

    return None


def check_for_update_async(
    current_version: str,
    callback: Callable[[Optional[UpdateInfo]], None],
) -> None:
    """
    Check for updates in a background thread.

    Calls callback(update_info) on completion. If no update or error,
    callback receives None or UpdateInfo with is_newer=False.
    """
    def _check():
        result = check_for_update(current_version)
        callback(result)

    thread = threading.Thread(target=_check, daemon=True)
    thread.start()


def open_download(update_info: UpdateInfo) -> None:
    """Open the download URL in the default browser."""
    url = update_info.download_url or update_info.release_url
    logger.info("Opening download URL: %s", url)
    webbrowser.open(url)
