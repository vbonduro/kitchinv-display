"""
Sleep implementations selected by the sleep_mode feature flag.

Both implementations are effectively no-return — DeepSleep via
machine.deepsleep() (hardware reset on wake) and LightSleep via
machine.reset() after the timed sleep (soft restart, USB stays alive
during the sleep interval so mpremote can connect at any time).
"""

import time


def _woke_from_sleep() -> bool:
    """True when this boot is not a first power-on.

    PWRON_RESET is the only cause that unambiguously means first boot.
    All other causes (deepsleep wake, watchdog, soft reset) indicate the
    device was already running and restarted as part of a sleep cycle.
    """
    import machine  # type: ignore[import]

    return machine.reset_cause() != machine.PWRON_RESET


class DeepSleep:
    """Maximum battery life.  USB drops for the duration of the sleep."""

    def woke_from_sleep(self) -> bool:
        return _woke_from_sleep()

    def sleep(self, ms: int) -> None:
        import machine

        machine.deepsleep(ms)  # type: ignore[attr-defined]  # no-return


class LightSleep:
    """USB stays alive between cycles.  Use for dev builds.

    Uses uasyncio.ThreadSafeFlag to wait for a button press or timeout
    without entering any hardware sleep state, so USB stays connected.
    On button press, the direction is persisted to flash so
    read_wake_button() can recover it after the deepsleep(1) reset.
    """

    def woke_from_sleep(self) -> bool:
        return _woke_from_sleep()

    def sleep(self, ms: int) -> None:
        import logging

        import machine  # type: ignore[import]
        import uasyncio as asyncio  # type: ignore[import]

        from lib import buttons

        logging.info("light sleep %ds (USB alive)", ms // 1000)
        flag, pressed_pin, prev_pin, next_pin = buttons.register_irq_handlers()
        woke_by_button = asyncio.run(self._wait_for_wake(flag, ms))
        if woke_by_button:
            self._record_button_intent(pressed_pin[0], prev_pin, next_pin)
        machine.deepsleep(1)  # type: ignore[attr-defined]  # no-return; stamps DEEPSLEEP_RESET

    async def _wait_for_wake(self, flag: object, ms: int) -> bool:
        """Wait up to *ms* milliseconds for a button press.

        Returns True if a button woke us, False on timeout.
        """
        import uasyncio as asyncio  # type: ignore[import]

        try:
            await asyncio.wait_for(flag.wait(), ms / 1000)  # type: ignore[attr-defined]
            return True
        except asyncio.TimeoutError:
            return False

    def _record_button_intent(
        self, pin_at_irq: object, prev_pin: object, next_pin: object
    ) -> None:
        """Debounce and persist the pressed direction to flash for the next boot."""
        from lib.buttons import direction_from_press, save_intent

        time.sleep_ms(20)  # type: ignore[attr-defined]  # debounce
        direction = direction_from_press(pin_at_irq, prev_pin, next_pin)  # type: ignore[arg-type]
        if direction is not None:
            save_intent(direction)


def make_sleeper(mode: str) -> "DeepSleep | LightSleep":
    """Return the sleeper for *mode* (``'deep'`` or ``'light'``)."""
    if mode == "light":
        return LightSleep()
    return DeepSleep()
