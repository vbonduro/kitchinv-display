"""
Local inventory cache — stores area data on flash so button-press wakes
can render without connecting to WiFi.

Files
-----
  /area_ids.json       — [(id, name), ...] area list
  /area_{id}.json      — items for a single area
  /area_{id}.tmp       — staging file during atomic write

All writes are atomic: data is written to a .tmp file first, then renamed
over the target.  A crash mid-write leaves a stale .tmp but never corrupts
the live file.
"""

import ujson  # type: ignore[import]
import uos  # type: ignore[import]

from lib.kitchinv import Area, Item

_AREA_IDS_FILE = "/area_ids.json"
_DB_HASH_FILE = "/db_hash.txt"


def _area_path(area_id: int) -> str:
    return "/area_{}.json".format(area_id)


def _write_atomic(path: str, data: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(data)
    uos.rename(tmp, path)


# ---------------------------------------------------------------------------
# Area ID list
# ---------------------------------------------------------------------------


def save_hash(hash_val: str) -> None:
    """Cache the server-side DB hash string."""
    _write_atomic(_DB_HASH_FILE, hash_val)


def load_hash() -> "str | None":
    """Return the cached DB hash, or None on miss."""
    try:
        with open(_DB_HASH_FILE) as f:
            return f.read().strip() or None
    except OSError:
        return None


def save_area_ids(area_ids: list) -> None:
    """Cache the area IDs list returned by KitchInv.get_area_ids()."""
    _write_atomic(_AREA_IDS_FILE, ujson.dumps(area_ids))


def load_area_ids() -> "list | None":
    """Return cached [(id, name), ...] or None on miss/corrupt."""
    try:
        with open(_AREA_IDS_FILE) as f:
            raw = ujson.loads(f.read())
        return [(int(a[0]), str(a[1])) for a in raw]
    except (OSError, ValueError, KeyError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Area item data
# ---------------------------------------------------------------------------


def save_area(area_id: int, area: Area) -> None:
    """Cache an Area's items to flash."""
    data = ujson.dumps(
        {
            "name": area.name,
            "items": [{"name": i.name, "count": i.count} for i in area.items],
        }
    )
    _write_atomic(_area_path(area_id), data)


def load_area(area_id: int, area_name: str) -> "Area | None":
    """Return a cached Area or None on miss/corrupt.

    *area_name* is used as a fallback if the cached name differs (e.g. after
    a server-side rename that hasn't been flushed to flash yet).
    """
    try:
        with open(_area_path(area_id)) as f:
            data = ujson.loads(f.read())
        items = [Item(name=i["name"], count=i.get("count")) for i in data["items"]]
        return Area(name=data["name"], items=items)
    except (OSError, ValueError, KeyError, TypeError):
        return None
