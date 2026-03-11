"""Firmware download and OTA update for MK3 amplifiers.

Downloads firmware binaries from sonance-beta.info and pushes them to
MK3 amplifiers via their HTTP firmware update endpoint.

Typical MK3 firmware update flow:
  1. Download .bin from the firmware API (signed URL)
  2. POST the binary to the amp's web server (e.g. /update or /firmware)
  3. Amp reboots and applies the firmware
"""

import hashlib
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from ..utils import get_logger
from .firmware_api import FirmwareAPIClient, FirmwareInfo, APIError

logger = get_logger(__name__)

# Common firmware upload endpoints to try on MK3 amps
_UPDATE_ENDPOINTS = [
    "/update",
    "/firmware",
    "/upgrade",
    "/fwupdate",
    "/cgi-bin/firmware",
    "/firmware_update",
]

HTTP_TIMEOUT = 120  # Firmware uploads can take a while


@dataclass
class DownloadResult:
    """Result of a firmware download."""
    success: bool
    file_path: str = ""
    file_size: int = 0
    checksum_sha256: str = ""
    error: str = ""


@dataclass
class UpdateResult:
    """Result of a firmware update attempt."""
    success: bool
    message: str = ""
    error: str = ""
    device_ip: str = ""
    firmware_version: str = ""
    upload_endpoint: str = ""
    response_status: int = 0
    response_body: str = ""


class FirmwareUpdater:
    """Handles firmware download from API and upload to MK3 amplifiers."""

    def __init__(self, api_client: FirmwareAPIClient):
        self._api = api_client
        self._download_dir = Path(tempfile.gettempdir()) / "mk3_firmware"
        self._download_dir.mkdir(parents=True, exist_ok=True)

    def download_firmware(
        self,
        firmware: FirmwareInfo,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> DownloadResult:
        """
        Download a firmware binary from the API.

        Args:
            firmware: FirmwareInfo object with the firmware to download.
            progress_callback: Optional callback(bytes_downloaded, total_bytes).

        Returns:
            DownloadResult with the local file path.
        """
        try:
            # Get signed download URL
            download_url = self._api.get_download_url(firmware.id)
            if not download_url:
                return DownloadResult(success=False, error="No download URL returned by API")

            # Determine local filename
            filename = firmware.file_name or f"mk3_fw_{firmware.version}.bin"
            local_path = self._download_dir / filename

            # Download with progress
            logger.info("Downloading firmware %s from API...", firmware.version)
            resp = requests.get(download_url, stream=True, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()

            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            sha256 = hashlib.sha256()

            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        sha256.update(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size)

            checksum = sha256.hexdigest()

            # Verify checksum if available
            if firmware.checksum_sha256 and checksum != firmware.checksum_sha256:
                os.unlink(local_path)
                return DownloadResult(
                    success=False,
                    error=f"Checksum mismatch: expected {firmware.checksum_sha256}, got {checksum}",
                )

            logger.info(
                "Downloaded firmware %s: %s (%d bytes, sha256=%s)",
                firmware.version, local_path, downloaded, checksum[:16],
            )

            return DownloadResult(
                success=True,
                file_path=str(local_path),
                file_size=downloaded,
                checksum_sha256=checksum,
            )

        except requests.RequestException as e:
            return DownloadResult(success=False, error=f"Download failed: {e}")
        except Exception as e:
            return DownloadResult(success=False, error=f"Unexpected error: {e}")

    def upload_firmware(
        self,
        device_ip: str,
        firmware_path: str,
        firmware_version: str = "",
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> UpdateResult:
        """
        Upload a firmware binary to an MK3 amplifier.

        Tries multiple known firmware upload endpoints. The amp's web server
        typically accepts a multipart POST with the .bin file.

        Args:
            device_ip: IP address of the target amplifier.
            firmware_path: Path to the firmware .bin file.
            firmware_version: Version string for logging.
            progress_callback: Optional status message callback.

        Returns:
            UpdateResult with the outcome.
        """
        if not os.path.exists(firmware_path):
            return UpdateResult(
                success=False, error=f"Firmware file not found: {firmware_path}",
                device_ip=device_ip,
            )

        file_size = os.path.getsize(firmware_path)
        logger.info(
            "Uploading firmware %s (%d bytes) to %s",
            firmware_version, file_size, device_ip,
        )

        base_url = f"http://{device_ip}"

        # Try each known endpoint
        for endpoint in _UPDATE_ENDPOINTS:
            url = base_url + endpoint
            if progress_callback:
                progress_callback(f"Trying {endpoint}...")

            try:
                with open(firmware_path, "rb") as f:
                    files = {"file": (os.path.basename(firmware_path), f, "application/octet-stream")}
                    resp = requests.post(url, files=files, timeout=HTTP_TIMEOUT)

                if resp.status_code in (200, 201, 202, 204):
                    logger.info(
                        "Firmware upload successful via %s (status %d)",
                        endpoint, resp.status_code,
                    )
                    if progress_callback:
                        progress_callback(f"Upload successful! Device may reboot.")

                    return UpdateResult(
                        success=True,
                        message=f"Firmware uploaded via {endpoint}. Device may reboot to apply.",
                        device_ip=device_ip,
                        firmware_version=firmware_version,
                        upload_endpoint=endpoint,
                        response_status=resp.status_code,
                        response_body=resp.text[:500],
                    )

                logger.debug(
                    "Endpoint %s returned status %d: %s",
                    endpoint, resp.status_code, resp.text[:200],
                )

            except requests.ConnectionError:
                logger.debug("Endpoint %s: connection refused", endpoint)
            except requests.Timeout:
                logger.debug("Endpoint %s: timeout (device may be rebooting)", endpoint)
                # Timeout during upload might mean the device accepted and is rebooting
                return UpdateResult(
                    success=True,
                    message=f"Upload sent via {endpoint}. Device appears to be rebooting (connection lost).",
                    device_ip=device_ip,
                    firmware_version=firmware_version,
                    upload_endpoint=endpoint,
                )
            except Exception as e:
                logger.debug("Endpoint %s error: %s", endpoint, e)

        return UpdateResult(
            success=False,
            error="No firmware upload endpoint found on the device. "
                  "The device may not support OTA updates via HTTP.",
            device_ip=device_ip,
            firmware_version=firmware_version,
        )

    def download_and_update(
        self,
        device_ip: str,
        firmware: FirmwareInfo,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> UpdateResult:
        """
        Full pipeline: download firmware from API, then upload to device.

        Args:
            device_ip: Target amplifier IP.
            firmware: FirmwareInfo to install.
            progress_callback: Status message callback.

        Returns:
            UpdateResult with the outcome.
        """
        if progress_callback:
            progress_callback(f"Downloading firmware v{firmware.version}...")

        # Step 1: Download
        def dl_progress(downloaded, total):
            if total > 0:
                pct = (downloaded / total) * 100
                if progress_callback:
                    progress_callback(f"Downloading: {pct:.0f}% ({downloaded // 1024} KB)")

        dl_result = self.download_firmware(firmware, progress_callback=dl_progress)
        if not dl_result.success:
            return UpdateResult(
                success=False,
                error=f"Download failed: {dl_result.error}",
                device_ip=device_ip,
                firmware_version=firmware.version,
            )

        if progress_callback:
            progress_callback(f"Download complete. Uploading to {device_ip}...")

        # Step 2: Upload to device
        result = self.upload_firmware(
            device_ip=device_ip,
            firmware_path=dl_result.file_path,
            firmware_version=firmware.version,
            progress_callback=progress_callback,
        )

        return result


def update_firmware_async(
    updater: FirmwareUpdater,
    device_ip: str,
    firmware: FirmwareInfo,
    callback: Callable[[UpdateResult], None],
    progress_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """Run firmware download+update in a background thread."""
    def _run():
        result = updater.download_and_update(device_ip, firmware, progress_callback)
        callback(result)

    threading.Thread(target=_run, daemon=True).start()
