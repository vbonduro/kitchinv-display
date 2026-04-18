"""Config state — first-boot setup: captive portal (if needed), WiFi, initial DB pull."""

import logging

import machine  # type: ignore[import]
import picozero  # type: ignore[import]

from lib import config, wifi
from lib.config import Settings
from lib.display import Display
from lib.kitchinvdb import KitchInvDB
from lib.renderer import Renderer
from lib.wifi import AP_IP, AP_SSID, WiFiSession


class ConfigState:
    def __init__(self, settings: "Settings | None") -> None:
        self._settings = settings
        self._display = Display()
        self._renderer = Renderer()

    def run(self) -> None:
        if self._settings is None:
            self._settings = self._run_captive_portal()

        self._pull_db()
        machine.reset()  # type: ignore[attr-defined]  # no-return; next boot enters DeepSleepState

    def _run_captive_portal(self) -> Settings:
        """Show AP instructions, run captive portal, save and return settings."""
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
        return settings

    def _pull_db(self) -> None:
        """Connect to WiFi, pull the full DB, disconnect.

        On failure, shows an error and resets — main will re-enter ConfigState
        (settings now exist, so captive portal is skipped) and retry the pull.
        """
        assert self._settings is not None
        picozero.pico_led.blink(0.25)
        self._display.show(
            self._renderer.render_text_centered("Connecting to...", self._settings.wifi["ssid"])
        )
        with WiFiSession(self._settings.wifi):
            picozero.pico_led.on()
            logging.info("Connected: %s  IP=%s", self._settings.wifi["ssid"], wifi.my_ip())
            success = KitchInvDB(self._settings.kitchinv_url).pull()
        picozero.pico_led.off()

        if not success:
            logging.error("Initial DB pull failed — resetting to retry")
            self._display.show(self._renderer.render_text_centered("Fetch failed", "Retrying..."))
