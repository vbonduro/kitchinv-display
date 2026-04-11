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

AP_SSID = "KitchInv-Setup"
AP_IP = "192.168.4.1"
_CONNECT_TIMEOUT_MS = 30_000


def _scan_networks():
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


def run_captive_portal():
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


def connect(wifi):
    """
    Connect to a WiFi network in STA mode.
    Raises RuntimeError if the connection does not succeed within 30 seconds.
    """
    sta = _net.WLAN(_net.STA_IF)
    sta.active(False)
    time.sleep_ms(500)  # let the radio settle after AP mode
    sta.active(True)
    sta.connect(wifi["ssid"], wifi["password"])
    logging.info("Connecting to WiFi: %s", wifi["ssid"])

    start = time.ticks_ms()
    last_status = None
    while not sta.isconnected():
        status = sta.status()
        if status != last_status:
            logging.info("WiFi status: %d", status)
            last_status = status
        if status < 0:  # terminal failure (wrong password, no AP, etc.)
            sta.active(False)
            raise RuntimeError("WiFi connection failed (status %d): %s" % (status, wifi["ssid"]))
        if time.ticks_diff(time.ticks_ms(), start) > _CONNECT_TIMEOUT_MS:
            sta.active(False)
            raise RuntimeError("WiFi connection timed out (status %d): %s" % (status, wifi["ssid"]))
        time.sleep_ms(100)


def my_ip():
    """Return the current STA IP address as a string."""
    return _net.WLAN(_net.STA_IF).ifconfig()[0]
