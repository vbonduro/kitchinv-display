"""
KitchInv display — main entry point.

Each run is a single wake cycle:
  1. Read (area_index, page_index, areas_fp, item_count) from flash
  2. Connect WiFi
  3. Fetch area IDs; reset to (0, 0) if the area list changed
  4. Fetch current area's items; reset to (0, 0) if item count changed
  5. Render the page onto the e-paper display
  6. Disconnect WiFi
  7. Write the next cycle state to flash
  8. Sleep for CYCLE_INTERVAL_MS

Sleep behaviour is controlled by the sleep_mode feature flag (features.ini):
  deep  (prod) — machine.deepsleep(); execution restarts from the top on wake.
  light (dev)  — time.sleep_ms() + machine.reset(); USB stays alive during sleep.

Build targets write the appropriate features.ini to the device:
  make deploy      → features/prod.ini
  make deploy-dev  → features/dev.ini
  make run         → features/dev.ini (written to host dir before mount)
"""

import logging

import picozero

from lib import config, logger, wifi
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
# Cycle state helpers (persisted through sleep via flash file)
# ---------------------------------------------------------------------------
#
# Binary layout (6 bytes):
#   [0]     area_index   — current area index
#   [1]     page_index   — current page within the area
#   [2..3]  areas_fp     — 16-bit fingerprint of the area list (order + membership)
#   [4..5]  item_count   — 16-bit item count of the last-rendered area
#
# Old 2-byte state files are handled gracefully: areas_fp and item_count
# default to 0, which differs from any real fingerprint and triggers a
# one-time reset to (0, 0) on the first wake after upgrading.

_CYCLE_STATE_FILE = "/cycle_state.bin"


def _fingerprint_areas(area_ids: list) -> int:
    """16-bit position-sensitive fingerprint of the area list.

    Sensitive to changes in order, membership, and count.
    """
    fp = len(area_ids)
    for i, (area_id, _) in enumerate(area_ids):
        fp = (fp * 31 + (i + 1) * area_id) & 0xFFFF
    return fp


def _read_cycle_state() -> tuple:
    """Return (area_index, page_index, areas_fp, item_count) from flash."""
    try:
        with open(_CYCLE_STATE_FILE, "rb") as f:
            data = f.read(6)
            if len(data) >= 6:
                areas_fp = (data[2] << 8) | data[3]
                item_count = (data[4] << 8) | data[5]
                return data[0], data[1], areas_fp, item_count
            if len(data) >= 2:
                return data[0], data[1], 0, 0
    except OSError:
        pass
    return 0, 0, 0, 0


def _write_cycle_state(area_index: int, page_index: int,
                       areas_fp: int, item_count: int) -> None:
    """Persist cycle state to flash before sleep."""
    with open(_CYCLE_STATE_FILE, "wb") as f:
        f.write(bytes([
            area_index & 0xFF,
            page_index & 0xFF,
            (areas_fp >> 8) & 0xFF,
            areas_fp & 0xFF,
            (item_count >> 8) & 0xFF,
            item_count & 0xFF,
        ]))


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

# Only show the connecting screen on first power-on — on deep-sleep wake the
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

area_index, page_index, stored_areas_fp, stored_item_count = _read_cycle_state()
num_areas = len(area_ids)
area_index = area_index % num_areas

current_areas_fp = _fingerprint_areas(area_ids)
if current_areas_fp != stored_areas_fp:
    logging.info("Area list changed — resetting to area 0")
    area_index, page_index = 0, 0

# Keep area[0] in case an item-count reset is needed after we delete area_ids.
first_area_id, first_area_name = area_ids[0]
area_id, area_name = area_ids[area_index]
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

current_item_count = len(area.items)
if current_item_count != stored_item_count:
    logging.info("Item count changed (%d→%d) — resetting to area 0",
                 stored_item_count, current_item_count)
    area_index, page_index = 0, 0
    if area_id != first_area_id:
        del area
        area = client.get_area(first_area_id, first_area_name)
        if not area:
            logging.error("Failed to fetch area %r — retrying in %ds",
                          first_area_name, ERROR_RETRY_MS // 1000)
            display.show(renderer.render_text_centered("Fetch failed", "Retrying in 1 min"))
            wifi.disconnect()
            sleeper.sleep(ERROR_RETRY_MS)
        assert area is not None
        current_item_count = len(area.items)

# ---------------------------------------------------------------------------
# Render and display
# ---------------------------------------------------------------------------

logging.info("Rendering %r page %d", area.name, page_index)
fb, cursor = renderer.render_area(area, page_index)
del area

wifi.disconnect()  # radio off before the slow e-paper refresh
display.show(fb)
del fb

# ---------------------------------------------------------------------------
# Advance cycle position and sleep
# ---------------------------------------------------------------------------

if cursor and cursor.has_next:
    next_area_index = area_index
    next_page_index = cursor.page + 1
else:
    next_area_index = (area_index + 1) % num_areas
    next_page_index = 0

_write_cycle_state(next_area_index, next_page_index, current_areas_fp, current_item_count)
logging.info(
    "Next: area %d page %d — sleeping %ds",
    next_area_index,
    next_page_index,
    CYCLE_INTERVAL_MS // 1000,
)

sleeper.sleep(CYCLE_INTERVAL_MS)
