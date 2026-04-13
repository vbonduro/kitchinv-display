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
    """USB stays alive between cycles.  Use for dev builds."""

    def woke_from_sleep(self) -> bool:
        return _woke_from_sleep()

    def sleep(self, ms: int) -> None:
        import logging

        import machine

        logging.info("light sleep %ds (USB alive)", ms // 1000)
        time.sleep_ms(ms)  # type: ignore[attr-defined]
        machine.deepsleep(1)  # type: ignore[attr-defined]  # no-return; stamps DEEPSLEEP_RESET


def make_sleeper(mode: str) -> "DeepSleep | LightSleep":
    """Return the sleeper for *mode* (``'deep'`` or ``'light'``)."""
    if mode == "light":
        return LightSleep()
    return DeepSleep()
