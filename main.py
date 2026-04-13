"""
KitchInv display — main entry point.

Each run is a single wake cycle:
  1. Connect WiFi
  2. Fetch area IDs
  3. Load cycle state; resolve which area/page to render
  4. Fetch the current area's items
  5. Render the page onto the e-paper display
  6. Disconnect WiFi
  7. Advance cycle state and persist to flash
  8. Sleep for CYCLE_INTERVAL_MS

Sleep behaviour is controlled by the sleep_mode feature flag (features.ini):
  deep  (prod) — machine.deepsleep(); execution restarts from the top on wake.
  light (dev)  — time.sleep_ms() + machine.deepsleep(1); USB stays alive during sleep.

Build targets write the appropriate features.ini to the device:
  make deploy      → features/prod.ini
  make deploy-dev  → features/dev.ini
  make run         → features/dev.ini
"""

import logging

import picozero

from lib import config, cycle, logger, wifi
from lib.display import Display
from lib.features import get as get_feature
from lib.kitchinv import KitchInv
from lib.renderer import Renderer
from lib.sleep import make_sleeper
from lib.wifi import AP_IP, AP_SSID

# How long to sleep between page displays.
CYCLE_INTERVAL_MS = 5 * 60 * 1000

# Shorter sleep when a fetch fails — retry sooner.
ERROR_RETRY_MS = 60 * 1000

logger.setup()

sleeper = make_sleeper(get_feature("sleep_mode"))
logging.info("sleep_mode=%s", get_feature("sleep_mode"))

display = Display()
renderer = Renderer()

# ---------------------------------------------------------------------------
# Boot sequence
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

# Only show the connecting screen on first power-on — on sleep wake the
# display already holds the previous page, which is a better user experience
# than a 2.5 s refresh to show a transient status message.
if not sleeper.woke_from_sleep():
    display.show(renderer.render_text_centered("Connecting to...", settings.wifi["ssid"]))

wifi.connect(settings.wifi)
picozero.pico_led.on()
logging.info("Connected: %s  IP=%s", settings.wifi["ssid"], wifi.my_ip())

# ---------------------------------------------------------------------------
# Fetch area list
# ---------------------------------------------------------------------------

client = KitchInv(settings.kitchinv_url)
area_ids = client.get_area_ids()

if not area_ids:
    logging.error("Failed to fetch area IDs — retrying in %ds", ERROR_RETRY_MS // 1000)
    display.show(renderer.render_text_centered("Fetch failed", "Retrying in 1 min"))
    wifi.disconnect()
    sleeper.sleep(ERROR_RETRY_MS)
assert area_ids is not None

state = cycle.load()
area_id, area_name = state.sync_areas(area_ids)
del area_ids

# ---------------------------------------------------------------------------
# Fetch current area
# ---------------------------------------------------------------------------

area = client.get_area(area_id, area_name)

if not area:
    logging.error("Failed to fetch area %r — retrying in %ds", area_name, ERROR_RETRY_MS // 1000)
    display.show(renderer.render_text_centered("Fetch failed", "Retrying in 1 min"))
    wifi.disconnect()
    sleeper.sleep(ERROR_RETRY_MS)
assert area is not None

if state.check_items(len(area.items)):
    # Item count changed and we were not at area 0 — save the reset state and
    # restart immediately so the next boot fetches area 0 from scratch.
    state.save()
    wifi.disconnect()
    sleeper.sleep(1)

# ---------------------------------------------------------------------------
# Render and display
# ---------------------------------------------------------------------------

logging.info("Rendering %r page %d", area.name, state.page_index)
fb, cursor = renderer.render_area(area, state.page_index)
del area

wifi.disconnect()  # radio off before the slow e-paper refresh
display.show(fb)
del fb

# ---------------------------------------------------------------------------
# Advance cycle position and sleep
# ---------------------------------------------------------------------------

state.advance(cursor)
state.save()
logging.info("Sleeping %ds", CYCLE_INTERVAL_MS // 1000)
sleeper.sleep(CYCLE_INTERVAL_MS)
