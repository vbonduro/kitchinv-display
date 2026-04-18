"""
KitchInv display — main entry point.

Determines the boot state and delegates to the appropriate state class:

  ConfigState     — no WiFi credentials or DB not yet pulled: captive portal
                    (if needed), WiFi connect, initial DB pull, reset
  DeepSleepState  — timer/cold wake: WiFi, optional cache refresh, full render, sleep
  ActiveState     — button wake: navigate from cache, asyncio button loop, sleep
"""

import logging

import picozero

from lib import buttons, config, logger
from lib.features import get as get_feature
from lib.kitchinvdb import KitchInvDB
from lib.sleep import make_sleeper

logger.setup()

# Read button state immediately — must happen before the user releases the button.
button = buttons.read_wake_button()
if button:
    logging.info("Button wake: %s", button)

sleeper = make_sleeper(get_feature("sleep_mode"))
logging.info("sleep_mode=%s", get_feature("sleep_mode"))

settings = config.load()

if settings is None or not KitchInvDB.is_cached():
    from lib.states.config import ConfigState

    ConfigState(settings).run()
else:
    picozero.pico_led.blink(0.25)

    if button:
        from lib.states.active import ActiveState

        ActiveState(settings, button, sleeper).run()
    else:
        from lib.states.deep_sleep import DeepSleepState

        DeepSleepState(settings, sleeper).run()
