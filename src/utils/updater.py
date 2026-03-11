"""Auto-update checker and in-place updater using GitHub Releases API."""

import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
import zipfile
from dataclasses import dataclass
from pathlib import Path
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


@dataclass
class UpdateProgress:
    """Progress info for the download/install process."""
    stage: str       # "downloading", "extracting", "replacing", "done", "error"
    message: str
    percent: float = 0.0  # 0-100


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


# ═══════════════════════════════════════════════════════════════════════
# In-place self-update: download, extract, replace, relaunch
# ═══════════════════════════════════════════════════════════════════════

def _get_running_executable() -> Optional[Path]:
    """Get the path to the currently running executable (PyInstaller bundle)."""
    if getattr(sys, 'frozen', False):
        # Running as a PyInstaller bundle
        exe_path = Path(sys.executable)
        return exe_path
    return None


def _get_app_bundle_path() -> Optional[Path]:
    """
    On macOS, find the .app bundle path if we're running inside one.
    e.g. /Applications/MK3_Diagnostic_Tool.app
    """
    exe = _get_running_executable()
    if not exe:
        return None

    # Walk up to find .app bundle: .../Foo.app/Contents/MacOS/Foo
    current = exe
    for _ in range(5):
        current = current.parent
        if current.name.endswith(".app"):
            return current
    return None


def download_and_replace(
    update_info: UpdateInfo,
    progress_callback: Optional[Callable[[UpdateProgress], None]] = None,
) -> bool:
    """
    Download the latest release, extract it, and replace the running application.

    Platform behavior:
      - macOS (.zip): Downloads zip, extracts .app bundle, replaces existing
        .app in the same directory, then relaunches.
      - Windows (.exe): Downloads new .exe, schedules replacement via a
        small batch script that waits for the current process to exit,
        then swaps the file and relaunches.
      - Linux: Downloads binary, replaces in-place, relaunches.

    Args:
        update_info: UpdateInfo with the download URL.
        progress_callback: Called with UpdateProgress at each stage.

    Returns:
        True if update was initiated (app will restart), False on error.
    """
    def _progress(stage: str, message: str, percent: float = 0.0):
        if progress_callback:
            progress_callback(UpdateProgress(stage=stage, message=message, percent=percent))

    download_url = update_info.download_url
    if not download_url or download_url == update_info.release_url:
        _progress("error", "No direct download URL available for this platform")
        return False

    system = platform.system()
    tmp_dir = Path(tempfile.mkdtemp(prefix="mk3_update_"))

    try:
        # ── Step 1: Download ──────────────────────────────────────
        _progress("downloading", f"Downloading {update_info.latest_version}...", 0)

        resp = requests.get(download_url, stream=True, timeout=120)
        resp.raise_for_status()

        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0

        # Determine filename from URL
        filename = download_url.split("/")[-1]
        download_path = tmp_dir / filename

        with open(download_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = (downloaded / total_size) * 100
                        size_mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        _progress(
                            "downloading",
                            f"Downloading: {size_mb:.1f} / {total_mb:.1f} MB",
                            pct,
                        )

        _progress("downloading", "Download complete", 100)
        logger.info("Downloaded update to %s (%d bytes)", download_path, downloaded)

        # ── Step 2: Extract and replace ───────────────────────────
        if system == "Darwin":
            return _update_macos(download_path, tmp_dir, _progress)
        elif system == "Windows":
            return _update_windows(download_path, tmp_dir, _progress)
        else:
            return _update_linux(download_path, tmp_dir, _progress)

    except requests.RequestException as e:
        _progress("error", f"Download failed: {e}")
        logger.error("Update download failed: %s", e)
        return False
    except Exception as e:
        _progress("error", f"Update failed: {e}")
        logger.error("Update failed: %s", e)
        return False


def _update_macos(
    download_path: Path,
    tmp_dir: Path,
    _progress: Callable,
) -> bool:
    """
    macOS update: extract .zip containing .app bundle, replace existing.

    The zip typically contains a folder like MK3_Diagnostic_Tool/ with
    the .app bundle inside, or the .app directly.
    """
    _progress("extracting", "Extracting update...", 0)

    extract_dir = tmp_dir / "extracted"
    extract_dir.mkdir()

    with zipfile.ZipFile(download_path, "r") as zf:
        zf.extractall(extract_dir)

    _progress("extracting", "Finding application bundle...", 50)

    # Find the .app bundle or the main executable in the extracted files
    app_bundle = None
    main_executable = None

    for root, dirs, files in os.walk(extract_dir):
        root_path = Path(root)
        # Look for .app bundle
        for d in dirs:
            if d.endswith(".app"):
                app_bundle = root_path / d
                break
        # Look for the main executable (PyInstaller --onedir output)
        for f in files:
            if f == "MK3_Diagnostic_Tool" or f == "MK3 Diagnostic Tool":
                main_executable = root_path / f
        if app_bundle:
            break

    # Determine what we're replacing
    current_app = _get_app_bundle_path()
    current_exe = _get_running_executable()

    if app_bundle and current_app:
        # Replacing a .app bundle with a .app bundle
        _progress("replacing", f"Replacing {current_app.name}...", 0)
        dest = current_app.parent / app_bundle.name
        backup = current_app.parent / f"{current_app.name}.backup"

        # Backup current, move new in
        if current_app.exists():
            if backup.exists():
                shutil.rmtree(backup)
            current_app.rename(backup)

        shutil.copytree(str(app_bundle), str(dest))
        _progress("replacing", "Application replaced", 100)

        # Find the executable inside the new .app to relaunch
        new_exe = dest / "Contents" / "MacOS"
        exe_candidates = list(new_exe.glob("*"))
        if exe_candidates:
            relaunch_path = exe_candidates[0]
            os.chmod(str(relaunch_path), os.stat(str(relaunch_path)).st_mode | stat.S_IEXEC)
            _progress("done", f"Updated to {dest.name}. Relaunching...")
            _relaunch_macos(str(relaunch_path))
        else:
            _progress("done", "Updated! Please relaunch the application manually.")

        # Clean up backup
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

        return True

    elif main_executable or current_exe:
        # PyInstaller --onedir: find the extracted folder containing the exe
        # and replace the entire directory
        if not main_executable:
            # Try to find any executable in the extracted files
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    fp = Path(root) / f
                    if os.access(str(fp), os.X_OK) and not f.endswith(('.py', '.txt', '.md')):
                        main_executable = fp
                        break

        if main_executable and current_exe:
            _progress("replacing", "Replacing application files...", 0)

            # The extracted directory containing the executable
            new_app_dir = main_executable.parent
            current_dir = current_exe.parent

            # Backup current
            backup_dir = current_dir.parent / f"{current_dir.name}.backup"
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

            # Copy new files over current (preserving directory)
            for item in new_app_dir.iterdir():
                dest_item = current_dir / item.name
                if dest_item.exists():
                    if dest_item.is_dir():
                        shutil.rmtree(dest_item)
                    else:
                        dest_item.unlink()
                if item.is_dir():
                    shutil.copytree(str(item), str(dest_item))
                else:
                    shutil.copy2(str(item), str(dest_item))

            # Make executable
            os.chmod(str(current_exe), os.stat(str(current_exe)).st_mode | stat.S_IEXEC)

            _progress("done", "Updated! Relaunching...")
            _relaunch_macos(str(current_exe))
            return True

    _progress("error", "Could not find application to replace")
    return False


def _relaunch_macos(exe_path: str) -> None:
    """Relaunch the app on macOS after a short delay."""
    script = f'''
    sleep 1
    open "{exe_path}"
    '''
    subprocess.Popen(["bash", "-c", script])
    # Give the script a moment to start
    time.sleep(0.5)
    sys.exit(0)


def _update_windows(
    download_path: Path,
    tmp_dir: Path,
    _progress: Callable,
) -> bool:
    """
    Windows update: use a batch script to replace the .exe after exit.
    """
    current_exe = _get_running_executable()
    if not current_exe:
        _progress("error", "Cannot determine current executable path")
        return False

    new_exe = download_path  # Already an .exe file
    _progress("replacing", "Preparing update...", 0)

    # Create a batch script that:
    # 1. Waits for the current process to exit
    # 2. Replaces the exe
    # 3. Relaunches
    # 4. Deletes itself
    batch_path = tmp_dir / "update.bat"
    batch_content = f'''@echo off
echo Updating MK3 Diagnostic Tool...
timeout /t 2 /nobreak >nul

:retry
tasklist /FI "PID eq {os.getpid()}" 2>NUL | find /I "{os.getpid()}" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto retry
)

copy /Y "{new_exe}" "{current_exe}"
if errorlevel 1 (
    echo Update failed. Please download manually.
    pause
    exit /b 1
)

echo Update complete. Launching...
start "" "{current_exe}"
del "%~f0"
'''

    with open(batch_path, "w") as f:
        f.write(batch_content)

    _progress("done", "Update ready. Restarting...")

    # Launch the batch script and exit
    subprocess.Popen(
        ["cmd", "/c", str(batch_path)],
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
    )
    time.sleep(0.5)
    sys.exit(0)


def _update_linux(
    download_path: Path,
    tmp_dir: Path,
    _progress: Callable,
) -> bool:
    """
    Linux update: replace the binary in-place and relaunch.
    """
    current_exe = _get_running_executable()
    if not current_exe:
        _progress("error", "Cannot determine current executable path")
        return False

    _progress("replacing", "Replacing executable...", 0)

    # Make the downloaded file executable
    os.chmod(str(download_path), os.stat(str(download_path)).st_mode | stat.S_IEXEC)

    # Backup current
    backup = current_exe.with_suffix(".backup")
    try:
        shutil.copy2(str(current_exe), str(backup))
        shutil.copy2(str(download_path), str(current_exe))
        os.chmod(str(current_exe), os.stat(str(current_exe)).st_mode | stat.S_IEXEC)
    except PermissionError:
        _progress("error", "Permission denied. Try running with sudo.")
        return False

    _progress("done", "Updated! Relaunching...")

    # Relaunch
    subprocess.Popen([str(current_exe)])
    time.sleep(0.5)
    sys.exit(0)


def download_and_replace_async(
    update_info: UpdateInfo,
    progress_callback: Optional[Callable[[UpdateProgress], None]] = None,
    done_callback: Optional[Callable[[bool], None]] = None,
) -> None:
    """
    Run the download-and-replace update in a background thread.

    Args:
        update_info: The update to install.
        progress_callback: Called with UpdateProgress at each stage.
        done_callback: Called with True/False when complete (only on failure,
                       since success triggers app exit/restart).
    """
    def _run():
        success = download_and_replace(update_info, progress_callback)
        if not success and done_callback:
            done_callback(False)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
