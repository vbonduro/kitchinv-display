import logging
import time

import picozero

from lib import config, wifi
from lib.display import Display
from lib.kitchinv import KitchInv
from lib.renderer import Renderer
from lib.wifi import AP_IP, AP_SSID

# Six hour sleep.
SLEEP_DURATION_S = 6 * 60 * 60

logging.basicConfig(level=logging.INFO)

display = Display()
renderer = Renderer()

settings = config.load()
while settings is None:
    logging.warning("No wifi settings found. Switch to AP mode.")
    picozero.pico_led.blink(2)
    display.show(renderer.render_text_centered(
        "To configure this device:",
        "1. Connect to WiFi:  " + AP_SSID,
        "2. Open browser to:  http://" + AP_IP,
    ))
    settings = wifi.run_captive_portal()
    config.save(settings)

picozero.pico_led.blink(0.25)
display.show(renderer.render_text_centered("Connecting to...", settings.wifi["ssid"]))
wifi.connect(settings.wifi)

picozero.pico_led.on()
logging.info("Connected to WiFi network: %s. IP=%s", settings.wifi["ssid"], wifi.my_ip())

client = KitchInv(settings.kitchinv_url)
area_ids = client.get_area_ids()
logging.info("Fetched %d area IDs", len(area_ids) if area_ids else 0)

if area_ids:
    first_id, first_name = area_ids[0]
    del area_ids  # free the list before fetching items
    area = client.get_area(first_id, first_name)
    if area:
        logging.info("Rendering area: %s (%d items)", area.name, len(area.items))
        fb, cursor = renderer.render_area(area)
        del area  # cursor holds the items reference
        display.show(fb)

while True:
    # TODO: replace with machine.lightsleep once query/display cycle is
    # implemented — Pico W constrains lightsleep duration when WiFi is active.
    time.sleep(SLEEP_DURATION_S)
