"""Config state — no WiFi credentials saved; run captive portal then reset."""

import machine  # type: ignore[import]
import picozero  # type: ignore[import]

from lib import config, wifi
from lib.display import Display
from lib.renderer import Renderer
from lib.wifi import AP_IP, AP_SSID


class ConfigState:
    def __init__(self) -> None:
        self._display = Display()
        self._renderer = Renderer()

    def run(self) -> None:
        picozero.pico_led.blink(2)
        self._display.show(
            self._renderer.render_text_centered(
                "To configure this device:",
                "1. Connect to WiFi:  " + AP_SSID,
                "2. Open browser to:  http://" + AP_IP,
            )
        )
        settings = wifi.run_captive_portal()
        config.save(settings)
        machine.reset()  # type: ignore[attr-defined]  # no-return; next boot enters DeepSleepState
