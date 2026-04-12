"""
WiFi management for KitchInv display.

Wraps MicroPython's built-in `network` module (aliased as `_net` to avoid
shadowing it) and provides:
  - run_captive_portal(): AP mode + captive portal (delegated to portal module)
  - connect(wifi): STA mode connection
  - my_ip(): current STA IP
"""

import logging
import time

import network as _net

from . import portal
from .config import Settings

AP_SSID = "KitchInv-Setup"
AP_IP = "192.168.4.1"
_CONNECT_TIMEOUT_MS = 30_000


def _scan_networks() -> list[str]:
    """Scan for nearby SSIDs, sorted by signal strength, duplicates removed."""
    sta = _net.WLAN(_net.STA_IF)
    sta.active(True)
    raw = sta.scan()  # [(ssid, bssid, channel, rssi, security, hidden), ...]
    sta.active(False)
    seen = set()
    networks = []
    for entry in sorted(raw, key=lambda x: x[3], reverse=True):
        raw_ssid = entry[0]
        decoded = raw_ssid.decode("utf-8", "ignore") if isinstance(raw_ssid, bytes) else raw_ssid
        ssid = decoded.strip()
        if ssid and ssid not in seen:
            seen.add(ssid)
            networks.append(ssid)
    return networks


def run_captive_portal() -> Settings:
    """
    Scan networks, start AP mode, run the captive portal, tear down AP, return Settings.
    """
    networks = _scan_networks()
    logging.info("Found %d networks", len(networks))

    ap = _net.WLAN(_net.AP_IF)
    ap.config(ssid=AP_SSID, security=0)
    ap.active(True)
    logging.info("AP active — SSID: %s", AP_SSID)
    try:
        return portal.run(networks)
    finally:
        ap.active(False)


_CONNECT_RETRIES = 3
_RETRY_DELAY_MS = 2_000


def connect(wifi: dict[str, str]) -> None:
    """Connect to a WiFi network in STA mode.

    Retries up to _CONNECT_RETRIES times to handle transient failures
    (e.g. STAT_CONNECT_FAIL/-1 during DHCP or brief signal drops).
    Raises RuntimeError if all attempts fail.
    """
    for attempt in range(_CONNECT_RETRIES):
        try:
            _connect_once(wifi)
            return
        except RuntimeError as exc:
            if attempt < _CONNECT_RETRIES - 1:
                logging.warning("WiFi attempt %d failed (%s), retrying…", attempt + 1, exc)
                time.sleep_ms(_RETRY_DELAY_MS)  # type: ignore[attr-defined]
            else:
                raise


def _connect_once(wifi: dict[str, str]) -> None:
    """Single connection attempt — raises RuntimeError on failure or timeout."""
    sta = _net.WLAN(_net.STA_IF)
    sta.active(False)
    time.sleep_ms(500)  # type: ignore[attr-defined]  # MicroPython extension
    sta.active(True)
    sta.connect(wifi["ssid"], wifi["password"])
    logging.info("Connecting to WiFi: %s", wifi["ssid"])

    start = time.ticks_ms()  # type: ignore[attr-defined]  # MicroPython extension
    last_status = None
    while not sta.isconnected():
        status = sta.status()
        if status != last_status:
            logging.info("WiFi status: %d", status)
            last_status = status
        if status < 0:  # terminal failure (wrong password, no AP, etc.)
            sta.active(False)
            raise RuntimeError("WiFi connection failed (status %d): %s" % (status, wifi["ssid"]))
        if time.ticks_diff(time.ticks_ms(), start) > _CONNECT_TIMEOUT_MS:  # type: ignore[attr-defined]
            sta.active(False)
            raise RuntimeError("WiFi connection timed out (status %d): %s" % (status, wifi["ssid"]))
        time.sleep_ms(100)  # type: ignore[attr-defined]  # MicroPython extension


def disconnect() -> None:
    """Disconnect from WiFi and deactivate the STA interface.

    Call before machine.deepsleep() to cut the radio and maximise battery life.
    """
    sta = _net.WLAN(_net.STA_IF)
    sta.disconnect()
    sta.active(False)


def my_ip() -> str:
    """Return the current STA IP address as a string."""
    return _net.WLAN(_net.STA_IF).ifconfig()[0]
