"""KitchInv local database — cache management and server sync.

Wraps the HTTP client and flash cache behind a single interface.
The caller is responsible for WiFi and error handling (pull() returns
False on network failure; is_synced() returns None).

Typical deep-sleep flow:
    db = KitchInvDB(url)
    synced = db.is_synced()    # fetches + caches server hash
    if not synced:
        db.pull()              # uses cached hash — no second network call
    area_ids = db.area_ids()
    area = db.load_area(aid, name)
"""

import logging

from lib import cache
from lib.kitchinv import (
    Area,  # re-exported for callers
    KitchInv,
)


class KitchInvDB:
    def __init__(self, server_url: str) -> None:
        self._client = KitchInv(server_url)
        self._server_hash: "str | None" = None

    def is_synced(self) -> "bool | None":
        """Return whether the local cache matches the server.

        Returns None  — server unreachable.
        Returns False — hashes differ, or cache is empty (needs pull).
        Returns True  — hashes match and area data is on flash.
        """
        self._server_hash = self._client.get_db_hash()
        if self._server_hash is None:
            return None
        if self._server_hash != cache.load_hash():
            return False
        return True

    def pull(self) -> bool:
        """Fetch the full DB from the server and write it to flash.

        Uses the server hash cached by is_synced() if available, otherwise
        fetches it fresh.  Returns True on success, False on any failure.
        """
        if self._server_hash is None:
            self._server_hash = self._client.get_db_hash()
            if self._server_hash is None:
                return False

        logging.info("Pulling full DB from server")
        all_areas = self._client.get_all_areas()
        if all_areas is None:
            return False

        area_ids = [(aid, a.name) for aid, a in all_areas]
        for aid, a in all_areas:
            cache.save_area(aid, a)
        del all_areas
        cache.save_area_ids(area_ids)
        cache.save_hash(self._server_hash)
        logging.info("Cache refreshed: %d areas", len(area_ids))
        return True

    @staticmethod
    def is_cached() -> bool:
        """True if a completed pull exists on flash (hash file present)."""
        return cache.load_hash() is not None

    def area_ids(self) -> "list | None":
        """Return [(area_id, name)] from flash. None if cache is empty."""
        return cache.load_area_ids()

    def load_area(self, aid: int, name: str) -> "Area | None":
        """Return the Area for *aid* from flash. None on cache miss."""
        return cache.load_area(aid, name)
