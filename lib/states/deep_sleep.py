"""Deep sleep state — timer/cold wake: WiFi, optional cache refresh, full render, sleep."""

import logging

import picozero  # type: ignore[import]

from lib import buttons, cache, cycle, wifi
from lib.config import Settings
from lib.display import Display
from lib.kitchinv import KitchInv
from lib.renderer import Renderer
from lib.sleep import DeepSleep, LightSleep

_CYCLE_INTERVAL_MS = 5 * 60 * 1000
_ERROR_RETRY_MS = 60 * 1000


class DeepSleepState:
    def __init__(self, settings: Settings, sleeper: "DeepSleep | LightSleep") -> None:
        self._settings = settings
        self._sleeper = sleeper
        self._display = Display()
        self._renderer = Renderer()

    def run(self) -> None:
        if not self._sleeper.woke_from_sleep():
            self._display.show(
                self._renderer.render_text_centered(
                    "Connecting to...", self._settings.wifi["ssid"]
                )
            )

        wifi.connect(self._settings.wifi)
        picozero.pico_led.on()
        logging.info(
            "Connected: %s  IP=%s",
            self._settings.wifi["ssid"],
            wifi.my_ip(),
        )

        client = KitchInv(self._settings.kitchinv_url)
        server_hash = client.get_db_hash()
        cached_hash = cache.load_hash()

        if server_hash is None:
            logging.error(
                "Failed to fetch DB hash — retrying in %ds", _ERROR_RETRY_MS // 1000
            )
            self._display.show(
                self._renderer.render_text_centered("Fetch failed", "Retrying in 1 min")
            )
            wifi.disconnect()
            buttons.configure_wake()
            self._sleeper.sleep(_ERROR_RETRY_MS)  # no-return

        assert server_hash is not None

        if server_hash != cached_hash:
            area_ids = self._fetch_and_cache(client, server_hash, cached_hash)
        else:
            area_ids = self._load_or_fetch_cache(client, server_hash)

        wifi.disconnect()
        picozero.pico_led.off()

        state = cycle.load()
        area_id, area_name = state.sync_areas(area_ids)
        del area_ids

        area = cache.load_area(area_id, area_name)
        if area is None:
            logging.error(
                "Cache miss for area %r after refresh — skipping render", area_name
            )
            buttons.configure_wake()
            self._sleeper.sleep(_CYCLE_INTERVAL_MS)  # no-return

        assert area is not None

        if state.check_items(len(area.items)):
            state.save()
            buttons.configure_wake()
            self._sleeper.sleep(1)  # no-return

        logging.info("Rendering %r page %d (full refresh)", area.name, state.page_index)
        fb, cursor = self._renderer.render_area(area, state.page_index)
        del area

        self._display.show(fb)
        del fb

        state.advance(cursor)
        state.save()
        logging.info("Sleeping %ds", _CYCLE_INTERVAL_MS // 1000)
        buttons.configure_wake()
        self._sleeper.sleep(_CYCLE_INTERVAL_MS)  # no-return

    def _fetch_and_cache(
        self, client: KitchInv, server_hash: str, cached_hash: "str | None"
    ) -> list:
        """Fetch the full DB from the server and update the cache."""
        logging.info(
            "DB changed (hash %s → %s) — fetching full DB", cached_hash, server_hash
        )
        all_areas = client.get_all_areas()
        if all_areas is None:
            logging.error(
                "Failed to fetch full DB — retrying in %ds", _ERROR_RETRY_MS // 1000
            )
            self._display.show(
                self._renderer.render_text_centered("Fetch failed", "Retrying in 1 min")
            )
            wifi.disconnect()
            buttons.configure_wake()
            self._sleeper.sleep(_ERROR_RETRY_MS)  # no-return

        assert all_areas is not None

        area_ids = [(aid, a.name) for aid, a in all_areas]
        for aid, a in all_areas:
            cache.save_area(aid, a)
        del all_areas
        cache.save_area_ids(area_ids)
        cache.save_hash(server_hash)
        logging.info("Cache refreshed: %d areas", len(area_ids))
        return area_ids

    def _load_or_fetch_cache(self, client: KitchInv, server_hash: str) -> list:
        """Return cached area IDs, fetching from server if the cache is empty."""
        logging.info("DB unchanged (hash %s) — using cached data", server_hash)
        area_ids = cache.load_area_ids()
        if area_ids is not None:
            return area_ids

        # Hash matched but no area data on flash — treat as a change and fetch.
        logging.warning("Hash matched but cache empty — fetching full DB")
        return self._fetch_and_cache(client, server_hash, server_hash)
