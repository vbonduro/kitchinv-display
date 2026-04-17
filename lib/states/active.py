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
    def __init__(
        self, settings: Settings, button: str, sleeper: "DeepSleep | LightSleep"
    ) -> None:
        self._settings = settings
        self._button = button
        self._sleeper = sleeper
        self._display = Display()
        self._renderer = Renderer()
        self._db = KitchInvDB(settings.kitchinv_url)

    def run(self) -> None:
        area_ids = self._require_cache()
        picozero.pico_led.on()
        irq_handles = self._prepare_button_loop(area_ids)
        asyncio.run(self._active_loop(*irq_handles))
        self._sleep()

    def _require_cache(self) -> list:
        """Return area IDs from cache, or sleep (no-return) if cache is empty."""
        area_ids = self._db.area_ids()
        if area_ids is None:
            logging.error("Active wake but cache is empty — sleeping for timer wake")
            self._sleep()
        assert area_ids is not None
        return area_ids

    def _prepare_button_loop(self, area_ids: list) -> tuple:
        """Navigate to the initial area, render, and start the button loop.

        Registers IRQ handlers before show_fast so any press during the ~0.5s
        display operation is captured. Returns the IRQ handles for the loop.
        """
        state = cycle.load()
        area_id, area_name = _navigate(self._button, state, area_ids)

        fb, cursor = self._load_and_render(area_id, area_name, state.page_index)
        if fb is None:
            self._sleep()

        assert fb is not None
        if cursor is not None:
            state.update_page(cursor.page)

        irq_handles = buttons.register_irq_handlers()
        self._display.show_fast(fb)
        del fb

        state.advance(cursor)
        state.save()
        return irq_handles

    async def _active_loop(
        self,
        flag: object,
        pressed_pin: list,
        prev_pin: "Pin",
        next_pin: "Pin",
    ) -> None:
        """Wait for button presses, delegating each to _handle_press."""
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

            logging.info("Button press: %s", direction)
            if not self._handle_press(direction):
                return

    def _handle_press(self, direction: str) -> bool:
        """Navigate and render for one button press. Returns False to exit the loop."""
        state = cycle.load()
        area_ids = self._db.area_ids()
        if area_ids is None:
            logging.error("Cache gone mid-active-mode — exiting active loop")
            return False

        area_id, area_name = _navigate(direction, state, area_ids)
        del area_ids

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
