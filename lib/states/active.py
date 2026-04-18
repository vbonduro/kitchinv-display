"""Active state — button wake: navigate from cache, asyncio button loop, sleep."""

import logging

import picozero  # type: ignore[import]
import uasyncio as asyncio  # type: ignore[import]
from machine import Pin  # type: ignore[import]

from lib import buttons, cycle
from lib.config import Settings
from lib.cycle import CycleState
from lib.display import Display
from lib.kitchinvdb import KitchInvDB
from lib.renderer import Renderer
from lib.sleep import DeepSleep, LightSleep

_CYCLE_INTERVAL_MS = 5 * 60 * 1000
_ACTIVE_TIMEOUT_MS = 30 * 1000


class ActiveState:
    def __init__(self, settings: Settings, button: str, sleeper: "DeepSleep | LightSleep") -> None:
        self._settings = settings
        self._button = button
        self._sleeper = sleeper
        self._display = Display()
        self._renderer = Renderer()
        self._db = KitchInvDB(settings.kitchinv_url)

    def run(self) -> None:
        area_ids = self._db.area_ids()
        assert area_ids is not None  # guaranteed by main: is_cached() gated dispatch

        picozero.pico_led.on()
        flag, pressed_pin, prev_pin, next_pin = buttons.register_irq_handlers()
        self._turn_page(self._button, area_ids)
        asyncio.run(self._active_loop(flag, pressed_pin, prev_pin, next_pin))
        self._sleep()

    async def _active_loop(
        self,
        flag: object,
        pressed_pin: list,
        prev_pin: "Pin",
        next_pin: "Pin",
    ) -> None:
        """Wait for button presses, handling each with _turn_page."""
        while True:
            try:
                await asyncio.wait_for(flag.wait(), _ACTIVE_TIMEOUT_MS / 1000)  # type: ignore[attr-defined]
            except asyncio.TimeoutError:
                logging.info("Active mode timeout — returning to deep sleep")
                return

            flag.clear()  # type: ignore[attr-defined]
            pin_at_irq = pressed_pin[0]
            pressed_pin[0] = None

            direction = buttons.direction_from_press(pin_at_irq, prev_pin, next_pin)
            if direction is None:
                continue  # spurious IRQ

            area_ids = self._db.area_ids()
            if area_ids is None:
                logging.error("Cache gone mid-active-mode — exiting active loop")
                return

            logging.info("Button press: %s", direction)
            if not self._turn_page(direction, area_ids):
                return

    def _turn_page(self, direction: str, area_ids: list) -> bool:
        """Navigate, render, and show one page. Returns False on cache miss."""
        state = cycle.load()
        area_id, area_name = _navigate(direction, state, area_ids)

        fb, cursor = self._load_and_render(area_id, area_name, state.page_index)
        if fb is None:
            return False

        if cursor is not None:
            state.update_page(cursor.page)

        self._display.show_fast(fb)
        del fb

        state.advance(cursor)
        state.save()
        return True

    def _load_and_render(self, aid: int, aname: str, page: int) -> tuple:
        """Load area from cache and render it. Returns (fb, cursor) or (None, None)."""
        area = self._db.load_area(aid, aname)
        if area is None:
            logging.error("Cache miss for area %r in active mode", aname)
            return None, None
        return self._renderer.render_area(area, page)

    def _sleep(self) -> None:
        """Configure wake sources and enter deep sleep."""
        logging.info("Sleeping %ds", _CYCLE_INTERVAL_MS // 1000)
        buttons.configure_wake()
        self._sleeper.sleep(_CYCLE_INTERVAL_MS)  # no-return


def _navigate(direction: str, state: CycleState, area_ids: list) -> tuple:
    """Apply direction to state and return (area_id, area_name).

    sync_areas runs first so _num_areas is set before retreat() wraps around.
    """
    state.sync_areas(area_ids)
    if direction == buttons.Direction.PREV:
        state.retreat()
    return state.sync_areas(area_ids)
