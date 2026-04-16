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
    The IRQ handler sets the flag; the asyncio event loop wakes on it.
    On button press, the direction is persisted to flash so
    read_wake_button() can recover it after the deepsleep(1) reset.
    """

    def woke_from_sleep(self) -> bool:
        return _woke_from_sleep()

    def sleep(self, ms: int) -> None:
        import logging

        import machine
        import uasyncio as asyncio  # type: ignore[import]
        from machine import Pin

        from lib.buttons import NEXT, NEXT_PIN, PREV, PREV_PIN, save_intent

        logging.info("light sleep %ds (USB alive)", ms // 1000)

        flag = asyncio.ThreadSafeFlag()
        pressed: list = [None]

        def _handler(pin: object) -> None:
            pressed[0] = pin
            flag.set()

        prev_pin = Pin(PREV_PIN, Pin.IN, Pin.PULL_UP)
        next_pin = Pin(NEXT_PIN, Pin.IN, Pin.PULL_UP)
        prev_pin.irq(trigger=Pin.IRQ_FALLING, handler=_handler)
        next_pin.irq(trigger=Pin.IRQ_FALLING, handler=_handler)
        time.sleep_ms(200)  # type: ignore[attr-defined]  # let spurious IRQs settle
        flag.clear()  # type: ignore[attr-defined]
        pressed[0] = None

        async def _wait() -> None:
            try:
                await asyncio.wait_for(flag.wait(), ms / 1000)
                # Button woke us — determine direction from current pin state
                # (handler pin reference may not be reliable across contexts).
                time.sleep_ms(20)  # type: ignore[attr-defined]  # debounce settle
                if prev_pin.value() == 0:
                    save_intent(PREV)
                elif next_pin.value() == 0:
                    save_intent(NEXT)
            except asyncio.TimeoutError:
                pass  # normal timer expiry

        asyncio.run(_wait())
        machine.deepsleep(1)  # type: ignore[attr-defined]  # no-return; stamps DEEPSLEEP_RESET


def make_sleeper(mode: str) -> "DeepSleep | LightSleep":
    """Return the sleeper for *mode* (``'deep'`` or ``'light'``)."""
    if mode == "light":
        return LightSleep()
    return DeepSleep()
