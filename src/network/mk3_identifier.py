"""MK3 Amplifier identification — probes devices to detect MK3 amps, firmware, and model.

Combines multiple detection strategies:
  1. Port 52000 probe (MK3 binary protocol)
  2. WebSocket device info query (ws://IP/ws)
  3. HTTP web interface scraping (Landing.htm / Status.htm)
  4. mDNS/Bonjour service discovery
  5. ARP MAC prefix matching (Microchip OUI)
"""

import json
import re
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from ..utils import get_logger

logger = get_logger(__name__)

MK3_CONTROL_PORT = 52000
MK3_PROTOCOL_HEADER = bytes([0xFF, 0x55])
HTTP_TIMEOUT = 5
PROBE_TIMEOUT = 2.0

# Sonance MK3 amps use Microchip ethernet controllers.
# Known OUI prefixes for Microchip Technology Inc.
KNOWN_MAC_PREFIXES = [
    "00:04:a3",   # Microchip Technology
    "00:1e:c0",   # Microchip Technology
    "d8:80:39",   # Microchip Technology
    "54:10:ec",   # Microchip Technology
    "04:91:62",   # Microchip Technology
    "70:b3:d5",   # IEEE Registration Authority (common for embedded)
]

# Pages to try for scraping device info
_WEB_PAGES = [
    "/Landing.htm",
    "/",
    "/Status.htm",
    "/index.htm",
    "/index.html",
    "/info.htm",
]


@dataclass
class MK3DeviceInfo:
    """Identified MK3 amplifier with extracted metadata."""
    ip: str
    is_mk3: bool = False

    # Identification confidence: "confirmed" (protocol probe), "likely" (web match), "possible"
    confidence: str = "unknown"

    # Device info extracted from web interface
    device_name: str = ""
    model: str = ""
    firmware_version: str = ""
    serial_number: str = ""
    mac_address: str = ""

    # Network info
    hostname: str = ""
    response_time_ms: float = 0.0
    open_ports: List[int] = field(default_factory=list)

    # Raw data for debugging
    web_title: str = ""
    web_page_snippet: str = ""
    protocol_response: bytes = b""

    # Detection methods that succeeded
    detected_by: List[str] = field(default_factory=list)


def identify_mk3(ip: str, timeout: float = PROBE_TIMEOUT) -> MK3DeviceInfo:
    """
    Probe a single IP to determine if it's an MK3 amplifier.
    Extracts firmware version, model, and device name when possible.

    This is the primary identification function. It tries multiple methods
    in order of reliability.
    """
    info = MK3DeviceInfo(ip=ip)

    # Method 1: TCP probe on port 52000 (most reliable for MK3 detection)
    _probe_mk3_protocol(info, timeout)

    # Method 2: WebSocket query for device info (most reliable for metadata)
    _query_websocket(info, timeout)

    # Method 3: HTTP web interface scraping (fallback)
    if not info.firmware_version:
        _scrape_web_interface(info, timeout)

    # Method 4: Hostname / DNS check
    _check_hostname(info)

    # Determine overall confidence
    if "protocol" in info.detected_by:
        info.is_mk3 = True
        info.confidence = "confirmed"
    elif "websocket" in info.detected_by:
        info.is_mk3 = True
        info.confidence = "confirmed"
    elif "web_title" in info.detected_by or "web_content" in info.detected_by:
        info.is_mk3 = True
        info.confidence = "likely"
    elif "hostname" in info.detected_by:
        info.is_mk3 = True
        info.confidence = "possible"

    # Fallback model guess from device name
    if not info.model and info.device_name:
        info.model = _guess_model_from_name(info.device_name)

    return info


def scan_for_mk3_devices(
    subnet_ips: List[str],
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    max_workers: int = 30,
    timeout: float = PROBE_TIMEOUT,
) -> List[MK3DeviceInfo]:
    """
    Scan a list of IPs to find MK3 amplifiers.

    This is a fast scanner that first probes port 52000, then enriches
    confirmed devices with web scraping.

    Args:
        subnet_ips: List of IP addresses to probe.
        progress_callback: Optional callback(current, total, ip).
        max_workers: Thread pool size.
        timeout: Per-probe timeout.

    Returns:
        List of MK3DeviceInfo for confirmed/likely MK3 devices.
    """
    results: List[MK3DeviceInfo] = []
    total = len(subnet_ips)
    completed = 0

    def _probe(ip: str) -> Optional[MK3DeviceInfo]:
        # Fast check: port 52000 open?
        if not _is_port_open(ip, MK3_CONTROL_PORT, timeout):
            return None
        # Full identification
        return identify_mk3(ip, timeout)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_probe, ip): ip for ip in subnet_ips}

        for future in as_completed(futures):
            completed += 1
            ip = futures[future]
            if progress_callback:
                progress_callback(completed, total, ip)

            try:
                info = future.result()
                if info and info.is_mk3:
                    results.append(info)
            except Exception as e:
                logger.debug("Error probing %s: %s", ip, e)

    results.sort(key=lambda d: d.ip)
    return results


# ── Detection methods ──────────────────────────────────────────────────

def _is_port_open(ip: str, port: int, timeout: float) -> bool:
    """Quick TCP port check."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _probe_mk3_protocol(info: MK3DeviceInfo, timeout: float) -> None:
    """
    Connect to port 52000 and send a power query command.
    If we get a valid response, this is definitely an MK3 amp.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        start = time.perf_counter()
        sock.connect((info.ip, MK3_CONTROL_PORT))
        elapsed = (time.perf_counter() - start) * 1000
        info.response_time_ms = elapsed

        # Send power query: FF 55 01 10 (global power status query)
        power_query = bytes([0xFF, 0x55, 0x01, 0x10])
        sock.sendall(power_query)

        response = sock.recv(64)
        sock.close()

        if response and len(response) >= 1:
            info.protocol_response = response
            info.detected_by.append("protocol")
            info.open_ports.append(MK3_CONTROL_PORT)
            logger.info("MK3 confirmed at %s (protocol response: %s)",
                        info.ip, response.hex().upper())
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        logger.debug("Protocol probe failed for %s: %s", info.ip, e)


def _query_websocket(info: MK3DeviceInfo, timeout: float) -> None:
    """
    Query the amp's WebSocket endpoint for device info.

    MK3 amps serve a WebSocket at ws://IP/ws that responds to a
    configure-get-all request with JSON containing deviceinfo
    (model, firmware version, MAC address, serial number, device name).
    """
    try:
        import websocket
    except ImportError:
        logger.debug("websocket-client not installed — WebSocket query unavailable")
        return

    ws_url = f"ws://{info.ip}/ws"
    try:
        ws = websocket.create_connection(
            ws_url,
            timeout=timeout + 3,
            origin=f"http://{info.ip}",
        )
        # The amp's JS includes a token field (can be empty for initial reads)
        ws.send(json.dumps({
            "type": "configure",
            "direction": "get",
            "section": "all",
            "token": "",
        }))
        result = ws.recv()
        ws.close()

        data = json.loads(result)
        device_info = data.get("configures", {}).get("deviceinfo", {})

        if device_info:
            fw = device_info.get("firmwareversion", "")
            model = device_info.get("devicemodel", "")
            name = device_info.get("devicename", "") or device_info.get("ampname", "")
            mac = device_info.get("macaddress", "")
            serial = device_info.get("serialnumber", "")

            if fw:
                # Strip leading "V" prefix if present (e.g. "V3.1.34.2750" -> "3.1.34.2750")
                info.firmware_version = fw.lstrip("Vv")
            if model:
                info.model = _normalize_model(model)
            if name:
                info.device_name = name
            if mac:
                info.mac_address = mac
            if serial:
                info.serial_number = serial

            if 80 not in info.open_ports:
                info.open_ports.append(80)
            info.detected_by.append("websocket")
            logger.info(
                "WebSocket device info for %s: model=%s, fw=%s, name=%s, mac=%s, serial=%s",
                info.ip, model, fw, name, mac, serial,
            )
        else:
            logger.debug("WebSocket response for %s had no deviceinfo", info.ip)

    except Exception as e:
        logger.debug("WebSocket query failed for %s: %s", info.ip, e)


def _scrape_web_interface(info: MK3DeviceInfo, timeout: float) -> None:
    """
    Fetch the amp's web pages and extract device info.

    Typical MK3 web pages contain:
    - Page title with model name (e.g. "DSP 8-130 MK3")
    - Firmware version strings
    - Device/amp name
    - Network status information
    """
    base_url = f"http://{info.ip}"

    for page in _WEB_PAGES:
        try:
            resp = requests.get(
                base_url + page, timeout=timeout,
                headers={"User-Agent": "MK3DiagTool/1.3"}
            )
            if resp.status_code != 200:
                continue

            html = resp.text
            if not html.strip():
                continue

            # Check port 80 is open
            if 80 not in info.open_ports:
                info.open_ports.append(80)

            # Extract page title
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            if title_match:
                title = title_match.group(1).strip()
                info.web_title = title

                # Check for Sonance/DSP keywords in title
                if _is_sonance_title(title):
                    info.detected_by.append("web_title")
                    # Try to extract model from title
                    model = _extract_model_from_text(title)
                    if model:
                        info.model = model

            # Extract firmware version from page content
            fw = _extract_firmware_version(html)
            if fw:
                info.firmware_version = fw

            # Extract device name
            name = _extract_device_name(html)
            if name:
                info.device_name = name

            # Extract model from page body (if not already found in title)
            if not info.model:
                model = _extract_model_from_text(html)
                if model:
                    info.model = model

            # Check body content for Sonance markers
            if not info.detected_by or "web_title" not in info.detected_by:
                body_lower = html.lower()
                if any(kw in body_lower for kw in ["sonance", "dsp8-130", "dsp2-150",
                                                    "dsp2-750", "mk3", "sonamp"]):
                    info.detected_by.append("web_content")

            # Save a snippet for debugging
            info.web_page_snippet = html[:500]

            # If we found firmware version, we have enough — stop
            if info.firmware_version:
                break

        except requests.RequestException:
            continue
        except Exception as e:
            logger.debug("Web scrape error for %s%s: %s", info.ip, page, e)


def _check_hostname(info: MK3DeviceInfo) -> None:
    """Check DNS reverse lookup for Sonance-related hostname."""
    try:
        hostname, _, _ = socket.gethostbyaddr(info.ip)
        info.hostname = hostname
        hostname_lower = hostname.lower()
        if any(kw in hostname_lower for kw in ["dsp", "sonance", "mk3", "sonamp", "amp"]):
            info.detected_by.append("hostname")
            if not info.device_name:
                info.device_name = hostname
    except (socket.herror, socket.gaierror, OSError):
        pass


def check_mac_prefix(mac: str) -> bool:
    """Check if a MAC address matches known Sonance/Microchip OUI prefixes."""
    mac_lower = mac.lower().replace("-", ":")
    prefix = mac_lower[:8]
    return prefix in KNOWN_MAC_PREFIXES


# ── Text extraction helpers ────────────────────────────────────────────

def _is_sonance_title(title: str) -> bool:
    """Check if a page title indicates a Sonance device."""
    t = title.lower()
    return any(kw in t for kw in [
        "sonance", "dsp", "mk3", "sonamp",
        "dsp8", "dsp2", "dsp 8", "dsp 2",
    ])


def _extract_model_from_text(text: str) -> str:
    """
    Extract MK3 model identifier from text.

    Matches patterns like:
    - DSP8-130, DSP 8-130, DSP8130
    - DSP2-150, DSP 2-150
    - DSP2-750, DSP 2-750
    """
    patterns = [
        r"(DSP\s*8[\s-]*130)",
        r"(DSP\s*2[\s-]*150)",
        r"(DSP\s*2[\s-]*750)",
        r"(DSP\s*\d+[\s-]*\d+)",
        r"(Sonamp\s+\w+[\s-]*\w*)",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            # Normalize to standard format
            return _normalize_model(raw)
    return ""


def _normalize_model(raw: str) -> str:
    """Normalize a model string to canonical form (e.g. 'DSP8-130')."""
    # Remove extra spaces: "DSP 8-130" -> "DSP8-130"
    normalized = re.sub(r"DSP\s+(\d)", r"DSP\1", raw, flags=re.IGNORECASE)
    # Ensure hyphen: "DSP8130" -> "DSP8-130"
    normalized = re.sub(r"(DSP\d)(\d{3})", r"\1-\2", normalized, flags=re.IGNORECASE)
    return normalized.upper() if normalized else raw


def _extract_firmware_version(html: str) -> str:
    """
    Extract firmware version from HTML page content.

    Looks for patterns like:
    - Firmware: 3.1.52
    - FW Version: 3.1.52
    - Version: v3.1.52
    - firmware_version=3.1.52
    - SW Ver: 3.1.52
    - version="3.1.52"
    """
    patterns = [
        # Labeled version strings
        r"(?:firmware|fw|software|sw)\s*(?:version|ver|v)?\s*[=:]\s*v?(\d+\.\d+\.\d+)",
        # Generic "Version: X.Y.Z"
        r"[Vv]ersion\s*[=:]\s*v?(\d+\.\d+\.\d+)",
        # HTML data attributes
        r'(?:data-)?(?:firmware|version|fw)["\s]*[=:]\s*["\']?v?(\d+\.\d+\.\d+)',
        # JavaScript variables
        r"(?:firmware|version|fwVer|swVersion)\s*=\s*['\"]v?(\d+\.\d+\.\d+)",
    ]
    for pat in patterns:
        match = re.search(pat, html, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _extract_device_name(html: str) -> str:
    """
    Extract device name/label from HTML.

    Looks for patterns like:
    - Device Name: Living Room Amp
    - <h1>Living Room DSP8-130</h1>
    - hostname=LivingRoom
    """
    # Skip HTML meta/link tags before searching — they produce false positives
    # like <meta name="viewport"> matching as device name "viewport"
    cleaned = re.sub(r"<(?:meta|link|script|style)[^>]*>", "", html, flags=re.IGNORECASE)

    patterns = [
        # Explicit device/amp/host name labels
        r"(?:device\s*name|amp\s*name|host\s*name)\s*[=:]\s*['\"]?([A-Za-z0-9][\w\s\-\.]{2,30})",
        r"<h1[^>]*>\s*(.{3,40}?)\s*</h1>",
    ]
    # Common HTML attribute values to exclude
    _EXCLUDED_NAMES = {
        "home", "index", "status", "landing", "page",
        "viewport", "description", "keywords", "author",
        "generator", "robots", "content-type", "charset",
        "text", "submit", "button", "hidden", "checkbox",
    }
    for pat in patterns:
        match = re.search(pat, cleaned, re.IGNORECASE)
        if match:
            name = match.group(1).strip().strip("'\"")
            if name.lower() not in _EXCLUDED_NAMES:
                return name
    return ""


def _guess_model_from_name(name: str) -> str:
    """Try to guess model from device name or hostname."""
    return _extract_model_from_text(name)


# ── mDNS discovery ─────────────────────────────────────────────────────

def discover_mdns(timeout: float = 5.0) -> List[MK3DeviceInfo]:
    """
    Discover MK3 devices via mDNS/Bonjour.

    Requires the zeroconf package. Returns empty list if not available.
    """
    try:
        from zeroconf import ServiceBrowser, Zeroconf, ServiceInfo
    except ImportError:
        logger.debug("zeroconf package not installed — mDNS discovery unavailable")
        return []

    devices: List[MK3DeviceInfo] = []
    found_ips: set = set()
    lock = threading.Lock()

    class MK3Listener:
        def add_service(self, zc, service_type, name):
            _process_service(zc, service_type, name)

        def remove_service(self, zc, service_type, name):
            pass

        def update_service(self, zc, service_type, name):
            _process_service(zc, service_type, name)

    def _process_service(zc, service_type, name):
        try:
            svc_info = zc.get_service_info(service_type, name)
            if svc_info is None:
                return

            # Get IP addresses
            for addr in svc_info.parsed_addresses():
                if addr in found_ips:
                    continue

                svc_name = name.lower()
                # Check if service name contains Sonance-related keywords
                if any(kw in svc_name for kw in ["sonance", "dsp", "mk3", "sonamp"]):
                    with lock:
                        found_ips.add(addr)
                    info = MK3DeviceInfo(
                        ip=addr,
                        is_mk3=True,
                        confidence="likely",
                        device_name=svc_info.server or name.split(".")[0],
                        detected_by=["mdns"],
                    )
                    # Extract model from service name
                    model = _extract_model_from_text(name)
                    if model:
                        info.model = model
                    with lock:
                        devices.append(info)
                    logger.info("mDNS discovered MK3: %s at %s", name, addr)
        except Exception as e:
            logger.debug("mDNS service processing error: %s", e)

    zc = Zeroconf()
    listener = MK3Listener()

    # Browse common service types where Sonance amps might advertise
    service_types = [
        "_http._tcp.local.",
        "_sonance._tcp.local.",
        "_raop._tcp.local.",
    ]

    browsers = []
    for stype in service_types:
        try:
            browsers.append(ServiceBrowser(zc, stype, listener))
        except Exception:
            pass

    # Wait for discovery
    time.sleep(timeout)
    zc.close()

    return devices
