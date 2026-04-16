"""
KitchInv API client for MicroPython.

Fetches inventory data from the kitchinv server over HTTP and assembles it
into typed data structures for the display to render.

The client is intentionally lazy: callers fetch area IDs first, then request
one area at a time.  This keeps only a single area's items in memory at once,
which is critical on the Pico W's constrained heap.

Usage
-----
    from lib.kitchinv import KitchInv

    client = KitchInv("http://192.168.2.254:9000")

    area_ids = client.get_area_ids()   # [(id, name), ...] or None
    if area_ids:
        area = client.get_area(area_ids[0][0])   # Area | None
"""

import logging

import ujson
import urequests

_TIMEOUT_S = 10
_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class Item:
    """A single inventory item.

    Mirrors a dataclass — MicroPython has no dataclasses module.
    count is None when the server's quantity string cannot be parsed as int.
    """

    def __init__(self, name: str, count: int | None) -> None:
        self.name = name
        self.count = count

    def __repr__(self) -> str:
        return "Item(name={!r}, count={!r})".format(self.name, self.count)


class Area:
    """A named kitchen area with its inventory items."""

    def __init__(self, name: str, items: list[Item]) -> None:
        self.name = name
        self.items = items

    def __repr__(self) -> str:
        return "Area(name={!r}, items={!r})".format(self.name, self.items)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


def _parse_count(quantity: str) -> int | None:
    """Parse a free-form quantity string into an integer count.

    Returns None if the string cannot be resolved to an integer.
    Examples: "2" -> 2, "half-full" -> None.
    """
    try:
        return int(quantity.strip())
    except ValueError:
        return None


class KitchInv:
    """HTTP client for the kitchinv inventory server."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def get_area_ids(self) -> list[tuple[int, str]] | None:
        """Return a list of (area_id, area_name) tuples, or None on error.

        This is a lightweight call — it fetches only area metadata, not items.
        Use the returned IDs with get_area() to load one area at a time.
        """
        url = self._base_url + "/api/areas"
        try:
            resp = urequests.get(url, timeout=_TIMEOUT_S)
            raw: list[dict] = ujson.loads(resp.content)
            return [(a["id"], a["name"]) for a in raw]
        except Exception as exc:
            _log.error("get_area_ids failed: %s", exc)
            return None

    def get_db_hash(self) -> "str | None":
        """Return the server-side DB hash, or None on error.

        Lightweight call — use this to check whether the local cache is still
        valid before deciding whether to fetch the full database.
        """
        url = self._base_url + "/api/db/hash"
        try:
            resp = urequests.get(url, timeout=_TIMEOUT_S)
            return ujson.loads(resp.content)["hash"]
        except Exception as exc:
            _log.error("get_db_hash failed: %s", exc)
            return None

    def get_all_areas(self) -> "list | None":
        """Fetch the full database and return [(area_id, Area), ...], or None on error.

        One HTTP call replaces N individual get_area() calls.  Use after
        get_db_hash() detects a change.
        """
        url = self._base_url + "/api/db"
        try:
            resp = urequests.get(url, timeout=_TIMEOUT_S)
            raw = ujson.loads(resp.content)
            resp.close()
            result = []
            for a in raw["areas"]:
                items = [
                    Item(name=i["Name"], count=_parse_count(i["Quantity"]))
                    for i in a["items"]
                ]
                result.append((a["id"], Area(name=a["name"], items=items)))
            return result
        except Exception as exc:
            _log.error("get_all_areas failed: %s", exc)
            return None

    def get_area(self, area_id: int, area_name: str) -> "Area | None":
        """Fetch items for *area_id* and return an Area instance, or None on error.

        *area_name* is the name returned alongside the ID by get_area_ids().
        Keeping it as a separate parameter avoids a redundant network call.
        """
        url = "{}/areas/{}/items".format(self._base_url, area_id)
        try:
            resp = urequests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=_TIMEOUT_S,
            )
            raw_items: list[dict] = ujson.loads(resp.content)
        except Exception as exc:
            _log.error("get_area(%s) failed: %s", area_id, exc)
            return None

        items = [Item(name=i["Name"], count=_parse_count(i["Quantity"])) for i in raw_items]
        return Area(name=area_name, items=items)
