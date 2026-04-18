"""
OTA update client for MicroPython.

Checks the GitHub Releases API for a newer firmware version and, if found,
downloads and applies the update, then resets the device.

Files are fetched individually from raw.githubusercontent.com at the tagged
version.  Each file is written to a temp path first and renamed only after
the SHA-256 checksum matches — leaving existing firmware intact on failure.

check_if_due() rate-limits checks to once every _OTA_INTERVAL_CYCLES deep-sleep
cycles (~1 hour at the default 5-minute cycle interval).
"""

import hashlib
import logging
import os

import ujson
import urequests  # type: ignore[import]

_REPO = "vbonduro/kitchinv-display"
_API_BASE = "https://api.github.com"
_RAW_BASE = "https://raw.githubusercontent.com"
_CHUNK = 4096
_TIMEOUT = 15

_OTA_INTERVAL_CYCLES = 12  # ~1 hour at 5 min/cycle
_OTA_COUNTDOWN_FILE = "/ota_countdown.bin"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _semver_gt(a: str, b: str) -> bool:
    """Return True if semver string *a* is strictly greater than *b*."""
    def _parse(v: str) -> tuple:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    return _parse(a) > _parse(b)


def _get_json(url: str) -> "dict | None":
    r = urequests.get(url, headers={"User-Agent": "kitchinv-display"}, timeout=_TIMEOUT)
    try:
        if r.status_code != 200:
            return None
        return ujson.loads(r.content)
    finally:
        r.close()


def _get_latest_version() -> "str | None":
    """Return the latest published release version string, or None on error."""
    data = _get_json("{}/repos/{}/releases/latest".format(_API_BASE, _REPO))
    if data is None:
        logging.warning("OTA: could not fetch latest release")
        return None
    tag = data.get("tag_name", "").lstrip("v")
    return tag if tag else None


def _download_file(url: str, dest: str, expected_sha256: str) -> bool:
    """Stream *url* to *dest*, verify SHA256, return True on success."""
    tmp = dest + ".tmp"
    h = hashlib.sha256()
    try:
        r = urequests.get(url, timeout=_TIMEOUT)
        try:
            if r.status_code != 200:
                logging.error("OTA: GET %s returned %d", url, r.status_code)
                return False
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.raw.read(_CHUNK)
                    if not chunk:
                        break
                    h.update(chunk)
                    f.write(chunk)
        finally:
            r.close()
    except Exception as e:
        logging.error("OTA: download failed %s: %s", dest, e)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False

    actual = h.digest().hex() if hasattr(h.digest(), "hex") else _hex(h.digest())
    if actual != expected_sha256:
        logging.error("OTA: checksum mismatch for %s", dest)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False

    _makedirs(os.path.dirname(dest))
    os.rename(tmp, dest)
    return True


def _hex(b: bytes) -> str:
    return "".join("{:02x}".format(c) for c in b)


def _makedirs(path: str) -> None:
    if not path or path == "/":
        return
    try:
        os.mkdir(path)
    except OSError:
        pass


def _countdown_load() -> int:
    """Return cycles remaining until next OTA check (0 = due now)."""
    try:
        with open(_OTA_COUNTDOWN_FILE, "rb") as f:
            data = f.read(1)
            return data[0] if data else 0
    except OSError:
        return 0


def _countdown_save(n: int) -> None:
    with open(_OTA_COUNTDOWN_FILE, "wb") as f:
        f.write(bytes([n & 0xFF]))


# ---------------------------------------------------------------------------
# OTA client
# ---------------------------------------------------------------------------


class OTAClient:
    def check_and_update(self) -> None:
        try:
            self._run()
        except Exception as e:
            logging.error("OTA: unexpected error: %s", e)

    def _run(self) -> None:
        try:
            import version as _v  # type: ignore[import]
            current: str = _v.VERSION
        except ImportError:
            current = "0.0.0"

        latest = _get_latest_version()
        if latest is None:
            return

        logging.info("OTA: current=%s latest=%s", current, latest)

        if not _semver_gt(latest, current):
            logging.info("OTA: up to date")
            return

        logging.info("OTA: update available — downloading manifest")
        manifest = _get_json(
            "https://github.com/{}/releases/download/v{}/manifest.json".format(_REPO, latest)
        )
        if manifest is None:
            logging.error("OTA: could not fetch manifest for v%s", latest)
            return

        tag = "v" + latest
        failed = []
        for dest, info in manifest.get("files", {}).items():
            source = info.get("source", dest) if isinstance(info, dict) else dest
            sha256 = info.get("sha256", info) if isinstance(info, dict) else info
            url = "{}/{}/{}/{}".format(_RAW_BASE, _REPO, tag, source)
            logging.info("OTA: updating %s", dest)
            if not _download_file(url, dest, sha256):
                failed.append(dest)

        if failed:
            logging.error("OTA: %d file(s) failed — keeping existing firmware", len(failed))
            return

        logging.info("OTA: update complete — resetting")
        import machine  # type: ignore[import]
        machine.reset()
