"""
KitchInv API client for MicroPython.

Fetches inventory data from the kitchinv server over HTTP and assembles it
into typed data structures for the display to render.

Usage
-----
    from lib.kitchinv import KitchInv

    client = KitchInv("http://192.168.2.254:9000")
    inventory = client.get_inventory()
    if inventory is None:
        # show error state
        ...
"""

import logging
from typing import Any

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
    """A named kitchen area with its inventory items.

    Mirrors a dataclass — MicroPython has no dataclasses module.
    """

    def __init__(self, name: str, items: list[Item]) -> None:
        self.name = name
        self.items = items

    def __repr__(self) -> str:
        return "Area(name={!r}, items={!r})".format(self.name, self.items)


class Inventory:
    """The full kitchen inventory, composed of areas.

    Mirrors a dataclass — MicroPython has no dataclasses module.
    """

    def __init__(self, areas: list[Area]) -> None:
        self.areas = areas

    def __repr__(self) -> str:
        return "Inventory(areas={!r})".format(self.areas)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


def _parse_count(quantity: str) -> int | None:
    """Parse a free-form quantity string into an integer count.

    Returns None if the string cannot be resolved to an integer.
    Examples: "2" -> 2, "1 bag" -> 1, "half-full" -> None.
    """
    quantity = quantity.strip()
    if not quantity:
        return None
    # Fast path: the whole string is an integer.
    try:
        return int(quantity)
    except ValueError:
        pass
    # Slow path: extract leading digits.
    digits = ""
    for ch in quantity:
        if ch.isdigit():
            digits += ch
        else:
            break
    if digits:
        return int(digits)
    return None


class KitchInv:
    """HTTP client for the kitchinv inventory server."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def get_inventory(self) -> Inventory | None:
        """Fetch all areas and their items, returning a complete Inventory.

        Returns None if the areas list cannot be retrieved.  Individual areas
        that fail to load are skipped — partial data is better than nothing.
        """
        raw_areas = self._get_areas()
        if raw_areas is None:
            return None

        areas: list[Area] = []
        for raw in raw_areas:
            area_id: int = raw["id"]
            area_name: str = raw["name"]
            raw_items = self._get_area_inventory(area_id)
            if raw_items is None:
                _log.warning("skipping area %r (id=%s): failed to fetch items", area_name, area_id)
                continue
            items = [Item(name=i["Name"], count=_parse_count(i["Quantity"])) for i in raw_items]
            areas.append(Area(name=area_name, items=items))

        return Inventory(areas=areas)

    def _get_areas(self) -> list[dict[str, Any]] | None:
        """GET /api/areas → list of {id, name} dicts, or None on error."""
        url = self._base_url + "/api/areas"
        try:
            resp = urequests.get(url, timeout=_TIMEOUT_S)
            data: list[dict[str, Any]] = ujson.loads(resp.content)
            return data
        except Exception as exc:
            _log.error("get_areas failed: %s", exc)
            return None

    def _get_area_inventory(self, area_id: int) -> list[dict[str, Any]] | None:
        """GET /areas/{id}/items → list of Item dicts, or None on error."""
        url = "{}/areas/{}/items".format(self._base_url, area_id)
        try:
            resp = urequests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=_TIMEOUT_S,
            )
            data: list[dict[str, Any]] = ujson.loads(resp.content)
            return data
        except Exception as exc:
            _log.error("get_area_inventory(%s) failed: %s", area_id, exc)
            return None
