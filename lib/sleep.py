"""
Sleep implementations selected by the sleep_mode feature flag.

Both implementations are effectively no-return — DeepSleep via
machine.deepsleep() (hardware reset on wake) and LightSleep via
machine.reset() after the timed sleep (soft restart, USB stays alive
during the sleep interval so mpremote can connect at any time).
"""

import time


class DeepSleep:
    """Maximum battery life.  USB drops for the duration of the sleep."""

    def woke_from_sleep(self) -> bool:
        """True when this boot is a wake from deep sleep (not first power-on)."""
        import machine

        deepsleep_reset = getattr(machine, "DEEPSLEEP_RESET", 7)
        cause = machine.reset_cause()  # type: ignore[attr-defined]
        import logging

        logging.info("reset_cause=%d deepsleep_reset=%d", cause, deepsleep_reset)
        return cause == deepsleep_reset

    def sleep(self, ms: int) -> None:
        import machine

        machine.deepsleep(ms)  # type: ignore[attr-defined]  # no-return


class LightSleep:
    """USB stays alive between cycles.  Use for dev builds."""

    def woke_from_sleep(self) -> bool:
        """Always False — light sleep uses machine.reset(), not deepsleep."""
        return False

    def sleep(self, ms: int) -> None:
        import logging

        import machine

        logging.info("light sleep %ds (USB alive)", ms // 1000)
        time.sleep_ms(ms)  # type: ignore[attr-defined]
        machine.reset()  # type: ignore[attr-defined]  # no-return


def make_sleeper(mode: str) -> "DeepSleep | LightSleep":
    """Return the sleeper for *mode* (``'deep'`` or ``'light'``)."""
    if mode == "light":
        return LightSleep()
    return DeepSleep()
