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
        area_ids = self._db.area_ids()
        if area_ids is None:
            logging.error("Active wake but cache is empty — sleeping for timer wake")
            buttons.configure_wake()
            self._sleeper.sleep(_CYCLE_INTERVAL_MS)  # no-return

        assert area_ids is not None

        picozero.pico_led.on()
        state = cycle.load()
        area_id, area_name = _navigate(self._button, state, area_ids)

        fb, cursor = self._load_and_render(area_id, area_name, state.page_index)
        if fb is None:
            buttons.configure_wake()
            self._sleeper.sleep(_CYCLE_INTERVAL_MS)  # no-return

        assert fb is not None

        if cursor is not None:
            state.update_page(cursor.page)

        flag, pressed_pin, prev_pin, next_pin = buttons.register_irq_handlers()

        self._display.show_fast(fb)
        del fb

        state.advance(cursor)
        state.save()

        asyncio.run(self._active_loop(flag, pressed_pin, prev_pin, next_pin))

        logging.info("Sleeping %ds", _CYCLE_INTERVAL_MS // 1000)
        buttons.configure_wake()
        self._sleeper.sleep(_CYCLE_INTERVAL_MS)  # no-return

    async def _active_loop(
        self,
        flag: object,
        pressed_pin: list,
        prev_pin: "Pin",
        next_pin: "Pin",
    ) -> None:
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

            logging.info("Button press in active mode: %s", direction)

            _state = cycle.load()
            _area_ids = self._db.area_ids()
            if _area_ids is None:
                logging.error("Cache gone mid-active-mode — exiting active loop")
                return

            _area_id, _area_name = _navigate(direction, _state, _area_ids)
            del _area_ids

            _fb, _cursor = self._load_and_render(_area_id, _area_name, _state.page_index)
            if _fb is None:
                return

            if _cursor is not None:
                _state.update_page(_cursor.page)

            self._display.show_fast(_fb)
            del _fb

            _state.advance(_cursor)
            _state.save()

    def _load_and_render(self, aid: int, aname: str, page: int) -> tuple:
        """Load area from cache and render it. Returns (fb, cursor) or (None, None)."""
        area = self._db.load_area(aid, aname)
        if area is None:
            logging.error("Cache miss for area %r in active mode", aname)
            return None, None
        return self._renderer.render_area(area, page)


def _navigate(direction: str, state: CycleState, area_ids: list) -> tuple:
    """Apply direction to state and return (area_id, area_name).

    sync_areas runs first in both branches so _num_areas is set correctly
    before retreat() performs its modulo wrap-around.
    """
    state.sync_areas(area_ids)
    if direction == buttons.Direction.PREV:
        state.retreat()
    return state.sync_areas(area_ids)
