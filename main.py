"""
KitchInv display — main entry point.

Two operational states:

DEEP SLEEP STATE (timer wake / cold boot):
  1. Connect WiFi
  2. GET /api/db/hash — if unchanged, skip fetch; otherwise GET /api/db and
     refresh all area caches
  3. Render from cache with show() (full refresh — clears ghosting)
  4. Advance cycle state
  5. Configure GPIO wake sources and deepsleep(CYCLE_INTERVAL_MS)

ACTIVE STATE (button wake):
  1. Navigate (PREV/NEXT) using cached data only — no WiFi
  2. Render with show_fast() (~0.5 s)
  3. Enter asyncio button-wait loop:
       wait for button press OR ACTIVE_TIMEOUT_MS
       on press  → navigate + show_fast → repeat
       on timeout → fall through to sleep
  4. Configure GPIO wake sources and deepsleep(CYCLE_INTERVAL_MS)

Sleep behaviour is controlled by the sleep_mode feature flag (features.ini):
  deep  (prod) — machine.deepsleep(); execution restarts from the top on wake.
  light (dev)  — time.sleep_ms() + machine.deepsleep(1); USB stays alive.

Build targets write the appropriate features.ini to the device:
  make deploy      → features/prod.ini
  make deploy-dev  → features/dev.ini
  make run         → features/dev.ini
"""

import logging
import time

import picozero
import uasyncio as asyncio  # type: ignore[import]
from machine import Pin  # type: ignore[import]

from lib import buttons, cache, config, cycle, logger, wifi
from lib.display import Display
from lib.features import get as get_feature
from lib.kitchinv import KitchInv
from lib.renderer import Renderer
from lib.sleep import make_sleeper
from lib.wifi import AP_IP, AP_SSID

# How long to sleep between timer-driven display updates.
CYCLE_INTERVAL_MS = 5 * 60 * 1000

# How long to stay in active mode waiting for another button press.
ACTIVE_TIMEOUT_MS = 30 * 1000

# Shorter sleep when a fetch fails — retry sooner.
ERROR_RETRY_MS = 60 * 1000

logger.setup()

# Read button state immediately — must happen before the user releases the button.
button = buttons.read_wake_button()
if button:
    logging.info("Button wake: %s", button)

sleeper = make_sleeper(get_feature("sleep_mode"))
logging.info("sleep_mode=%s", get_feature("sleep_mode"))

display = Display()
renderer = Renderer()

# ---------------------------------------------------------------------------
# Boot sequence — WiFi config
# ---------------------------------------------------------------------------

settings = config.load()
while settings is None:
    logging.warning("No wifi settings found. Switch to AP mode.")
    picozero.pico_led.blink(2)
    display.show(
        renderer.render_text_centered(
            "To configure this device:",
            "1. Connect to WiFi:  " + AP_SSID,
            "2. Open browser to:  http://" + AP_IP,
        )
    )
    settings = wifi.run_captive_portal()
    config.save(settings)

picozero.pico_led.blink(0.25)

# ---------------------------------------------------------------------------
# DEEP SLEEP STATE — timer wake: WiFi, optional cache refresh, full render
# ---------------------------------------------------------------------------

if not button:
    if not sleeper.woke_from_sleep():
        display.show(renderer.render_text_centered("Connecting to...", settings.wifi["ssid"]))

    wifi.connect(settings.wifi)
    picozero.pico_led.on()
    logging.info("Connected: %s  IP=%s", settings.wifi["ssid"], wifi.my_ip())

    client = KitchInv(settings.kitchinv_url)

    # Check whether the server DB has changed since last fetch.
    server_hash = client.get_db_hash()
    cached_hash = cache.load_hash()

    if server_hash is None:
        logging.error("Failed to fetch DB hash — retrying in %ds", ERROR_RETRY_MS // 1000)
        display.show(renderer.render_text_centered("Fetch failed", "Retrying in 1 min"))
        wifi.disconnect()
        buttons.configure_wake()
        sleeper.sleep(ERROR_RETRY_MS)

    assert server_hash is not None

    if server_hash != cached_hash:
        logging.info("DB changed (hash %s → %s) — fetching full DB", cached_hash, server_hash)
        all_areas = client.get_all_areas()
        if all_areas is None:
            logging.error("Failed to fetch full DB — retrying in %ds", ERROR_RETRY_MS // 1000)
            display.show(renderer.render_text_centered("Fetch failed", "Retrying in 1 min"))
            wifi.disconnect()
            buttons.configure_wake()
            sleeper.sleep(ERROR_RETRY_MS)

        assert all_areas is not None

        area_ids = [(aid, a.name) for aid, a in all_areas]
        for aid, a in all_areas:
            cache.save_area(aid, a)
        del all_areas
        cache.save_area_ids(area_ids)
        cache.save_hash(server_hash)
        logging.info("Cache refreshed: %d areas", len(area_ids))
    else:
        logging.info("DB unchanged (hash %s) — using cached data", server_hash)
        _area_ids_cached = cache.load_area_ids()
        if _area_ids_cached is None:
            # Cache is empty (hash matched but no area data — treat as a change and fetch).
            logging.warning("Hash matched but cache empty — fetching full DB")
            all_areas = client.get_all_areas()
            if all_areas is None:
                logging.error("Failed to fetch full DB — retrying in %ds", ERROR_RETRY_MS // 1000)
                display.show(renderer.render_text_centered("Fetch failed", "Retrying in 1 min"))
                wifi.disconnect()
                buttons.configure_wake()
                sleeper.sleep(ERROR_RETRY_MS)
            assert all_areas is not None
            area_ids = [(aid, a.name) for aid, a in all_areas]
            for aid, a in all_areas:
                cache.save_area(aid, a)
            del all_areas
            cache.save_area_ids(area_ids)
            cache.save_hash(server_hash)
        else:
            area_ids = _area_ids_cached

    wifi.disconnect()
    picozero.pico_led.off()

    state = cycle.load()
    area_id, area_name = state.sync_areas(area_ids)
    del area_ids

    area = cache.load_area(area_id, area_name)
    if area is None:
        logging.error("Cache miss for area %r after refresh — skipping render", area_name)
        buttons.configure_wake()
        sleeper.sleep(CYCLE_INTERVAL_MS)

    assert area is not None

    if state.check_items(len(area.items)):
        state.save()
        buttons.configure_wake()
        sleeper.sleep(1)

    logging.info("Rendering %r page %d (full refresh)", area.name, state.page_index)
    fb, cursor = renderer.render_area(area, state.page_index)
    del area

    display.show(fb)
    del fb

    state.advance(cursor)
    state.save()
    logging.info("Sleeping %ds", CYCLE_INTERVAL_MS // 1000)
    buttons.configure_wake()
    sleeper.sleep(CYCLE_INTERVAL_MS)

# ---------------------------------------------------------------------------
# ACTIVE STATE — button wake: navigate from cache, asyncio button loop
# ---------------------------------------------------------------------------

_active_area_ids = cache.load_area_ids()
if _active_area_ids is None:
    # No cache yet — fall back to timer-style WiFi fetch.
    logging.warning("Button wake but no cache — connecting WiFi")
    wifi.connect(settings.wifi)
    picozero.pico_led.on()
    client = KitchInv(settings.kitchinv_url)
    all_areas = client.get_all_areas()
    wifi.disconnect()
    picozero.pico_led.off()
    if all_areas is None:
        logging.error("Failed to fetch DB on cache-miss button wake")
        buttons.configure_wake()
        sleeper.sleep(ERROR_RETRY_MS)
    assert all_areas is not None
    _active_area_ids = [(aid, a.name) for aid, a in all_areas]
    for aid, a in all_areas:
        cache.save_area(aid, a)
    del all_areas
    cache.save_area_ids(_active_area_ids)

area_ids = _active_area_ids
picozero.pico_led.on()
state = cycle.load()

# sync_areas must run before retreat() so _num_areas is correct for wrap-around.
area_id, area_name = state.sync_areas(area_ids)
if button == buttons.PREV:
    state.retreat()
    area_id, area_name = state.sync_areas(area_ids)


def _load_and_render(aid: int, aname: str, page: int) -> tuple:
    """Load area from cache and render it.  Returns (fb, cursor) or (None, None)."""
    a = cache.load_area(aid, aname)
    if a is None:
        logging.error("Cache miss for area %r in active mode", aname)
        return None, None
    return renderer.render_area(a, page)


fb, cursor = _load_and_render(area_id, area_name, state.page_index)
if fb is None:
    # Cache is corrupt — sleep and let timer wake rebuild it.
    buttons.configure_wake()
    sleeper.sleep(CYCLE_INTERVAL_MS)

assert fb is not None

if cursor is not None:
    state.update_page(cursor.page)

# Register IRQ handlers before show_fast so any button press during the
# ~2s display operation is captured.  Settle + clear drains registration
# noise; presses that arrive after the clear (during show_fast, advance,
# save) are queued in _btn_flag and handled in the asyncio loop below.
_btn_flag = asyncio.ThreadSafeFlag()
# IRQ handler writes the pressed pin here so direction is captured at interrupt
# time, not at (post-render) debounce time when the button may already be released.
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

display.show_fast(fb)
del fb

state.advance(cursor)
state.save()

# ------- asyncio button-wait loop -------


async def _active_loop() -> None:
    while True:
        try:
            await asyncio.wait_for(_btn_flag.wait(), ACTIVE_TIMEOUT_MS / 1000)
        except asyncio.TimeoutError:
            logging.info("Active mode timeout — returning to deep sleep")
            return

        _btn_flag.clear()  # type: ignore[attr-defined]
        pin_at_irq = _pressed_pin[0]
        _pressed_pin[0] = None
        time.sleep_ms(20)  # type: ignore[attr-defined]  # debounce

        # Use pin captured at IRQ time as primary source; fall back to live read
        # for presses that arrive while the previous render is still running.
        if pin_at_irq is _prev_pin or _prev_pin.value() == 0:
            direction = buttons.PREV
        elif pin_at_irq is _next_pin or _next_pin.value() == 0:
            direction = buttons.NEXT
        else:
            continue  # spurious IRQ

        logging.info("Button press in active mode: %s", direction)

        # Re-load state (advance() already saved it above; reload to get fresh area list).
        _state = cycle.load()
        _area_ids = cache.load_area_ids()
        if _area_ids is None:
            logging.error("Cache gone mid-active-mode — exiting active loop")
            return

        # sync_areas must run before retreat() so _num_areas is correct for wrap-around.
        _area_id, _area_name = _state.sync_areas(_area_ids)
        if direction == buttons.PREV:
            _state.retreat()
            _area_id, _area_name = _state.sync_areas(_area_ids)
        del _area_ids

        _fb, _cursor = _load_and_render(_area_id, _area_name, _state.page_index)
        if _fb is None:
            return

        if _cursor is not None:
            _state.update_page(_cursor.page)

        display.show_fast(_fb)
        del _fb

        _state.advance(_cursor)
        _state.save()


asyncio.run(_active_loop())

logging.info("Sleeping %ds", CYCLE_INTERVAL_MS // 1000)
buttons.configure_wake()
sleeper.sleep(CYCLE_INTERVAL_MS)
