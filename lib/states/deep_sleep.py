"""Deep sleep state — timer/cold wake: WiFi, optional cache refresh, full render, sleep."""

import logging

import picozero  # type: ignore[import]

from lib import buttons, cycle, wifi
from lib.config import Settings
from lib.cycle import CycleState
from lib.display import Display
from lib.features import get as get_feature
from lib.kitchinv import Area
from lib.kitchinvdb import KitchInvDB
from lib.renderer import Renderer
from lib.sleep import DeepSleep, LightSleep
from lib.wifi import WiFiSession

_CYCLE_INTERVAL_MS = 5 * 60 * 1000
_ERROR_RETRY_MS = 60 * 1000


class DeepSleepState:
    def __init__(self, settings: Settings, sleeper: "DeepSleep | LightSleep") -> None:
        self._settings = settings
        self._sleeper = sleeper
        self._display = Display()
        self._renderer = Renderer()

    def run(self) -> None:
        self._show_connecting_splash()
        self._check_ota()
        with WiFiSession(self._settings.wifi):
            picozero.pico_led.on()
            logging.info("Connected: %s  IP=%s", self._settings.wifi["ssid"], wifi.my_ip())
            db = self._sync_db()
        picozero.pico_led.off()
        area, state = self._load_area(db)
        cursor = self._render_and_show(area, state)
        self._advance_cycle(state, cursor)
        self._sleep()

    def _check_ota(self) -> None:
        """Check for a firmware update on every wake, using its own WiFi session."""
        if get_feature("ota_check") != "true":
            return
        from lib.ota import OTAClient  # lazy: keeps urequests off the module-load path
        with WiFiSession(self._settings.wifi):
            OTAClient().check_and_update()

    def _show_connecting_splash(self) -> None:
        """Show the connecting screen on first cold boot (not after wake-from-sleep)."""
        if not self._sleeper.woke_from_sleep():
            self._display.show(
                self._renderer.render_text_centered("Connecting to...", self._settings.wifi["ssid"])
            )

    def _sync_db(self) -> KitchInvDB:
        """Check whether the local DB is current; pull from server if not."""
        db = KitchInvDB(self._settings.kitchinv_url)
        synced = db.is_synced()

        if synced is None:
            self._fetch_error("Failed to fetch DB hash")

        if not synced:
            logging.info("DB out of sync — pulling from server")
            if not db.pull():
                self._fetch_error("Failed to pull DB")

        return db

    def _load_area(self, db: KitchInvDB) -> "tuple[Area, CycleState]":
        """Determine which area to render and load it from cache.

        Resets cycle state and reboots if the area's item count changed since
        the last render — keeps pagination consistent when items are added or
        removed mid-cycle (no-return on reset).
        """
        state = cycle.load()
        area_id, area_name = state.sync_areas(db.area_ids())  # type: ignore[arg-type]

        area = db.load_area(area_id, area_name)
        if area is None:
            logging.error("Cache miss for area %r after sync — skipping render", area_name)
            buttons.configure_wake()
            self._sleeper.sleep(_CYCLE_INTERVAL_MS)  # no-return

        assert area is not None

        if state.has_items_changed(len(area.items)):
            state.save()
            buttons.configure_wake()
            self._sleeper.sleep(1)  # no-return

        return area, state

    def _render_and_show(self, area: Area, state: CycleState) -> object:
        """Render the current page and push it to the display. Returns the cursor."""
        from lib.battery import read_pct

        logging.info("Rendering %r page %d (full refresh)", area.name, state.page_index)
        fb, cursor = self._renderer.render_area(
            area, state.page_index, is_deep_sleep=True, battery_pct=read_pct()
        )
        self._display.show(fb)
        return cursor

    def _advance_cycle(self, state: CycleState, cursor: object) -> None:
        """Record the rendered page in cycle state and persist to flash."""
        state.advance(cursor)
        state.save()

    def _sleep(self) -> None:
        """Configure wake sources and enter deep sleep."""
        logging.info("Sleeping %ds", _CYCLE_INTERVAL_MS // 1000)
        buttons.configure_wake()
        self._sleeper.sleep(_CYCLE_INTERVAL_MS)  # no-return

    def _fetch_error(self, message: str) -> None:
        """Log *message*, show a retry notice, and sleep for retry.

        WiFi disconnect is handled by the WiFiSession context manager in run(),
        or by machine.deepsleep() cutting the radio on the no-return sleep path.
        """
        logging.error("%s — retrying in %ds", message, _ERROR_RETRY_MS // 1000)
        self._display.show(self._renderer.render_text_centered("Fetch failed", "Retrying in 1 min"))
        buttons.configure_wake()
        self._sleeper.sleep(_ERROR_RETRY_MS)  # no-return
