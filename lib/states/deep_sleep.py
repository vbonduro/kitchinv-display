"""Deep sleep state — timer/cold wake: WiFi, optional cache refresh, full render, sleep."""

import logging

import picozero  # type: ignore[import]

from lib import buttons, cycle, wifi
from lib.config import Settings
from lib.display import Display
from lib.kitchinvdb import KitchInvDB
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

        db = KitchInvDB(self._settings.kitchinv_url)
        synced = db.is_synced()

        if synced is None:
            self._fetch_error("Failed to fetch DB hash")

        if not synced:
            logging.info("DB out of sync — pulling from server")
            if not db.pull():
                self._fetch_error("Failed to pull DB")

        wifi.disconnect()
        picozero.pico_led.off()

        area_ids = db.area_ids()
        assert area_ids is not None  # guaranteed: synced=True or pull() succeeded

        state = cycle.load()
        area_id, area_name = state.sync_areas(area_ids)
        del area_ids

        area = db.load_area(area_id, area_name)
        if area is None:
            logging.error(
                "Cache miss for area %r after sync — skipping render", area_name
            )
            buttons.configure_wake()
            self._sleeper.sleep(_CYCLE_INTERVAL_MS)  # no-return

        assert area is not None

        # Reset to area 0 and reboot if the item count changed since the last
        # render — this keeps the cycle state consistent when items are added or
        # removed from an area mid-cycle.
        if state.has_items_changed(len(area.items)):
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

    def _fetch_error(self, message: str) -> None:
        """Log *message*, show a retry notice, disconnect, and sleep for retry."""
        logging.error("%s — retrying in %ds", message, _ERROR_RETRY_MS // 1000)
        self._display.show(
            self._renderer.render_text_centered("Fetch failed", "Retrying in 1 min")
        )
        wifi.disconnect()
        buttons.configure_wake()
        self._sleeper.sleep(_ERROR_RETRY_MS)  # no-return
