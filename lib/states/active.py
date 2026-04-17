"""Active state — button wake: navigate from cache, asyncio button loop, sleep."""

import logging
import time

import picozero  # type: ignore[import]
import uasyncio as asyncio  # type: ignore[import]
from machine import Pin  # type: ignore[import]

from lib import buttons, cache, cycle, wifi
from lib.config import Settings
from lib.display import Display
from lib.kitchinv import KitchInv
from lib.renderer import Renderer
from lib.sleep import DeepSleep, LightSleep

_CYCLE_INTERVAL_MS = 5 * 60 * 1000
_ACTIVE_TIMEOUT_MS = 30 * 1000
_ERROR_RETRY_MS = 60 * 1000


class ActiveState:
    def __init__(
        self, settings: Settings, button: str, sleeper: "DeepSleep | LightSleep"
    ) -> None:
        self._settings = settings
        self._button = button
        self._sleeper = sleeper
        self._display = Display()
        self._renderer = Renderer()

    def run(self) -> None:
        area_ids = self._ensure_cache()

        picozero.pico_led.on()
        state = cycle.load()

        # sync_areas must run before retreat() so _num_areas is correct for wrap-around.
        area_id, area_name = state.sync_areas(area_ids)
        if self._button == buttons.Direction.PREV:
            state.retreat()
            area_id, area_name = state.sync_areas(area_ids)

        fb, cursor = self._load_and_render(area_id, area_name, state.page_index)
        if fb is None:
            buttons.configure_wake()
            self._sleeper.sleep(_CYCLE_INTERVAL_MS)  # no-return

        assert fb is not None

        if cursor is not None:
            state.update_page(cursor.page)

        # Register IRQ handlers before show_fast so any button press during the
        # ~2s display operation is captured.
        _btn_flag = asyncio.ThreadSafeFlag()
        _pressed_pin: list = [None]

        def _btn_handler(pin: object) -> None:
            _pressed_pin[0] = pin
            _btn_flag.set()

        _prev_pin = Pin(buttons.PREV_PIN, Pin.IN, Pin.PULL_UP)
        _next_pin = Pin(buttons.NEXT_PIN, Pin.IN, Pin.PULL_UP)
        _prev_pin.irq(trigger=Pin.IRQ_FALLING, handler=_btn_handler)
        _next_pin.irq(trigger=Pin.IRQ_FALLING, handler=_btn_handler)

        time.sleep_ms(200)  # type: ignore[attr-defined]  # settle spurious IRQs
        _btn_flag.clear()  # type: ignore[attr-defined]
        _pressed_pin[0] = None

        self._display.show_fast(fb)
        del fb

        state.advance(cursor)
        state.save()

        async def _loop() -> None:
            while True:
                try:
                    await asyncio.wait_for(_btn_flag.wait(), _ACTIVE_TIMEOUT_MS / 1000)
                except asyncio.TimeoutError:
                    logging.info("Active mode timeout — returning to deep sleep")
                    return

                _btn_flag.clear()  # type: ignore[attr-defined]
                pin_at_irq = _pressed_pin[0]
                _pressed_pin[0] = None
                time.sleep_ms(20)  # type: ignore[attr-defined]  # debounce

                if pin_at_irq is _prev_pin or _prev_pin.value() == 0:
                    direction = buttons.Direction.PREV
                elif pin_at_irq is _next_pin or _next_pin.value() == 0:
                    direction = buttons.Direction.NEXT
                else:
                    continue  # spurious IRQ

                logging.info("Button press in active mode: %s", direction)

                # Reload state from flash — advance() already saved it above.
                _state = cycle.load()
                _area_ids = cache.load_area_ids()
                if _area_ids is None:
                    logging.error("Cache gone mid-active-mode — exiting active loop")
                    return

                # sync_areas must run before retreat() for correct wrap-around.
                _area_id, _area_name = _state.sync_areas(_area_ids)
                if direction == buttons.Direction.PREV:
                    _state.retreat()
                    _area_id, _area_name = _state.sync_areas(_area_ids)
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

        asyncio.run(_loop())

        logging.info("Sleeping %ds", _CYCLE_INTERVAL_MS // 1000)
        buttons.configure_wake()
        self._sleeper.sleep(_CYCLE_INTERVAL_MS)  # no-return

    def _load_and_render(self, aid: int, aname: str, page: int) -> tuple:
        """Load area from cache and render it. Returns (fb, cursor) or (None, None)."""
        a = cache.load_area(aid, aname)
        if a is None:
            logging.error("Cache miss for area %r in active mode", aname)
            return None, None
        return self._renderer.render_area(a, page)

    def _ensure_cache(self) -> list:
        """Return area IDs from cache, fetching over WiFi if the cache is empty."""
        area_ids = cache.load_area_ids()
        if area_ids is not None:
            return area_ids

        logging.warning("Button wake but no cache — connecting WiFi")
        wifi.connect(self._settings.wifi)
        picozero.pico_led.on()
        client = KitchInv(self._settings.kitchinv_url)
        all_areas = client.get_all_areas()
        wifi.disconnect()
        picozero.pico_led.off()

        if all_areas is None:
            logging.error("Failed to fetch DB on cache-miss button wake")
            buttons.configure_wake()
            self._sleeper.sleep(_ERROR_RETRY_MS)  # no-return

        assert all_areas is not None
        area_ids = [(aid, a.name) for aid, a in all_areas]
        for aid, a in all_areas:
            cache.save_area(aid, a)
        del all_areas
        cache.save_area_ids(area_ids)
        return area_ids
