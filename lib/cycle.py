"""
Cycle state — tracks which area/page to display next.

Persisted across sleep cycles via an 8-byte binary file on flash.

Binary layout:
  [0]     area_index      — next area index to display
  [1]     page_index      — next page within the area
  [2..3]  areas_fp        — 16-bit fingerprint of the area list (order + membership)
  [4..5]  item_count      — 16-bit item count for the current area
  [6]     last_area_index — area index that was last shown (for PREV navigation)
  [7]     last_page_index — page index that was last shown

Old 6-byte files default last_area/last_page to 0.
Old 2-byte files additionally default areas_fp and item_count to 0, which
differs from any real fingerprint/count and triggers a one-time reset to
(0, 0) on the first wake after upgrading.
"""

import logging

_STATE_FILE = "/cycle_state.bin"


def _fingerprint(area_ids: list) -> int:
    """16-bit position-sensitive fingerprint of the area list."""
    fp = len(area_ids)
    for i, (area_id, _) in enumerate(area_ids):
        fp = (fp * 31 + (i + 1) * area_id) & 0xFFFF
    return fp


class CycleState:
    def __init__(
        self,
        area_index: int,
        page_index: int,
        areas_fp: int,
        item_count: int,
        last_area_index: int = 0,
        last_page_index: int = 0,
    ) -> None:
        self._area_index = area_index
        self._page_index = page_index
        self._areas_fp = areas_fp
        self._item_count = item_count
        self._last_area_index = last_area_index
        self._last_page_index = last_page_index
        self._num_areas = 1  # updated by sync_areas

    @property
    def page_index(self) -> int:
        return self._page_index

    def sync_areas(self, area_ids: list) -> tuple:
        """Reconcile against the live area list; reset to (0, 0) if changed.

        Returns (area_id, area_name) for the area to fetch this cycle.
        """
        self._num_areas = len(area_ids)
        self._area_index = self._area_index % self._num_areas
        fp = _fingerprint(area_ids)
        if fp != self._areas_fp:
            logging.info("Area list changed — resetting to area 0")
            self._area_index = 0
            self._page_index = 0
            self._areas_fp = fp
        return area_ids[self._area_index]

    def has_items_changed(self, item_count: int) -> bool:
        """Detect an item-count change for the current area and reset to (0, 0).

        item_count is stored per-area: advance() clears it to 0 whenever the
        area index changes, so a stored value of 0 means "first visit to this
        area — no baseline to compare against."  In that case we accept the
        current count without resetting to avoid false positives caused by
        comparing counts across different areas.

        Returns True when a device restart is needed — count changed from a
        known baseline and we are not already at (0, 0).  The caller should
        save state and reboot so the next boot starts cleanly from area 0.

        Returns False when the count is unchanged, unknown (first visit), or
        we are already at (0, 0) — rendering can proceed without a restart.
        """
        if self._item_count == 0 or item_count == self._item_count:
            self._item_count = item_count
            return False
        logging.info(
            "Item count changed (%d→%d) — resetting to area 0",
            self._item_count,
            item_count,
        )
        needs_restart = self._area_index != 0 or self._page_index != 0
        self._area_index = 0
        self._page_index = 0
        self._item_count = item_count
        return needs_restart

    def update_page(self, page: int) -> None:
        """Replace any sentinel page index with the actual rendered page.

        Call this after rendering but before advance() so that last_page_index
        is stored as the real page number, not a sentinel value.
        """
        self._page_index = page

    def retreat(self) -> None:
        """Navigate backward one page, or to the last page of the previous area.

        If the last shown page was > 0, step back one page within the same area.
        If the last shown page was 0 (or unknown), jump to the last page of the
        previous area (wrapping around).
        """
        if self._last_page_index > 0:
            self._area_index = self._last_area_index
            self._page_index = self._last_page_index - 1
            logging.info("Retreat: area %d page %d", self._area_index, self._page_index)
        else:
            prev_area = (self._last_area_index - 1) % self._num_areas
            self._area_index = prev_area
            self._page_index = 0xFF  # sentinel: renderer clamps to last page
            self._item_count = 0
            logging.info("Retreat: area %d (last page)", self._area_index)

    def advance(self, cursor: object) -> None:
        """Move to the next page, or wrap to the next area.

        Records the current position as last shown before moving, so
        retreat() can navigate relative to what was actually on screen.
        Clears _item_count when the area changes so has_items_changed() treats the
        first fetch of each new area as a fresh baseline rather than comparing
        against the previous area's count.
        """
        self._last_area_index = self._area_index
        self._last_page_index = self._page_index
        if cursor and cursor.has_next:  # type: ignore[union-attr,attr-defined]
            self._page_index += 1
        else:
            next_area = (self._area_index + 1) % self._num_areas
            if next_area != self._area_index:
                self._item_count = 0
            self._area_index = next_area
            self._page_index = 0
        logging.info("Next: area %d page %d", self._area_index, self._page_index)

    def save(self) -> None:
        """Persist state to flash."""
        with open(_STATE_FILE, "wb") as f:
            f.write(
                bytes(
                    [
                        self._area_index & 0xFF,
                        self._page_index & 0xFF,
                        (self._areas_fp >> 8) & 0xFF,
                        self._areas_fp & 0xFF,
                        (self._item_count >> 8) & 0xFF,
                        self._item_count & 0xFF,
                        self._last_area_index & 0xFF,
                        self._last_page_index & 0xFF,
                    ]
                )
            )


def load() -> CycleState:
    """Load cycle state from flash, returning defaults on first boot."""
    try:
        with open(_STATE_FILE, "rb") as f:
            data = f.read(8)
            if len(data) >= 8:
                areas_fp = (data[2] << 8) | data[3]
                item_count = (data[4] << 8) | data[5]
                return CycleState(data[0], data[1], areas_fp, item_count, data[6], data[7])
            if len(data) >= 6:
                areas_fp = (data[2] << 8) | data[3]
                item_count = (data[4] << 8) | data[5]
                return CycleState(data[0], data[1], areas_fp, item_count)
            if len(data) >= 2:
                return CycleState(data[0], data[1], 0, 0)
    except OSError:
        pass
    return CycleState(0, 0, 0, 0)
