import logging
import time

import picozero

from lib import config, wifi
from lib.renderer import Renderer
from lib.wifi import AP_IP, AP_SSID

# Six hour sleep.
SLEEP_DURATION_S = 6 * 60 * 60

logging.basicConfig(level=logging.INFO)

r = Renderer()

settings = config.load()
while settings is None:
    logging.warning("No wifi settings found. Switch to AP mode.")
    picozero.pico_led.blink(2)
    r.show_centered(
        "To configure this device:",
        "1. Connect to WiFi:  " + AP_SSID,
        "2. Open browser to:  http://" + AP_IP,
    )
    settings = wifi.run_captive_portal()
    config.save(settings)

picozero.pico_led.blink(0.25)
r.show_centered("Connecting to...", settings.wifi["ssid"])
wifi.connect(settings.wifi)

picozero.pico_led.on()
logging.info("Connected to WiFi network: %s. IP=%s", settings.wifi["ssid"], wifi.my_ip())

while True:
    # TODO: replace with machine.lightsleep once query/display cycle is
    # implemented — Pico W constrains lightsleep duration when WiFi is active.
    time.sleep(SLEEP_DURATION_S)
    # inventory = kitchinv.query_inventory(settings.kitchinv_url)
    # display.show_inventory(inventory)
