"""
Button input handling for the KitchInv e-paper display.

Hardware (Waveshare Pico 7.5" adapter):
  GP2 — PREV  (navigate to previous area / page)
  GP3 — NEXT  (navigate to next area / wake early)

Both buttons are active-low: pulled high internally, grounded when pressed.

Deepsleep wake
--------------
Call configure_wake() before machine.deepsleep() to register both pins as
wake sources.  On the subsequent boot, call read_wake_button() as early as
possible — before the user releases the button — to detect which button
triggered the wake.
"""

from machine import Pin  # type: ignore[import]

PREV_PIN = 2
NEXT_PIN = 3


class Direction:
    NEXT = "next"
    PREV = "prev"


# Written by LightSleep when a button is pressed during the sleep interval;
# read by read_wake_button() on the following boot.
_INTENT_FILE = "/button_intent.txt"


def save_intent(direction: "str") -> None:
    """Persist a button direction to flash for the next boot to consume.

    Called by LightSleep after detecting a button press so the intent
    survives the subsequent machine.deepsleep(1) reset.
    """
    try:
        with open(_INTENT_FILE, "w") as f:
            f.write(direction)
    except OSError:
        pass


def read_wake_button() -> "str | None":
    """Return NEXT, PREV, or None indicating which button woke the device.

    Checks two sources in order:
    1. Persisted intent file — written by LightSleep before deepsleep(1).
    2. Live pin state — for DeepSleep wake where the user may still be
       holding the button (boot from deepsleep takes ~1-2 s on RP2350;
       a brief 20 ms settle is included to let the pin stabilise).
    """
    import uos  # type: ignore[import]
    import utime  # type: ignore[import]

    # Check persisted intent first (LightSleep path).
    try:
        with open(_INTENT_FILE) as f:
            direction = f.read().strip()
        uos.remove(_INTENT_FILE)
        if direction in (Direction.PREV, Direction.NEXT):
            return direction
    except OSError:
        pass

    # Fall back to live pin read (DeepSleep path).
    prev = Pin(PREV_PIN, Pin.IN, Pin.PULL_UP)
    nxt = Pin(NEXT_PIN, Pin.IN, Pin.PULL_UP)
    utime.sleep_ms(20)
    if prev.value() == 0:
        return Direction.PREV
    if nxt.value() == 0:
        return Direction.NEXT
    return None


class ButtonContext:
    """IRQ-driven button context for active-mode and light-sleep use.

    Creating an instance registers falling-edge IRQs on both pins and
    settles for 200 ms so spurious IRQs at construction time are ignored.

    Usage::

        ctx = ButtonContext()
        direction = asyncio.run(ctx.wait(30_000))
        # direction is Direction.PREV, Direction.NEXT, or None on timeout
    """

    def __init__(self) -> None:
        import time

        import uasyncio as asyncio  # type: ignore[import]

        self._flag = asyncio.ThreadSafeFlag()
        self._pressed_pin: list = [None]
        self._prev_pin = Pin(PREV_PIN, Pin.IN, Pin.PULL_UP)
        self._next_pin = Pin(NEXT_PIN, Pin.IN, Pin.PULL_UP)

        def _handler(pin: object) -> None:
            self._pressed_pin[0] = pin
            self._flag.set()

        self._prev_pin.irq(trigger=Pin.IRQ_FALLING, handler=_handler)
        self._next_pin.irq(trigger=Pin.IRQ_FALLING, handler=_handler)

        time.sleep_ms(200)  # type: ignore[attr-defined]  # settle spurious IRQs
        self._flag.clear()  # type: ignore[attr-defined]
        self._pressed_pin[0] = None

    async def wait(self, timeout_ms: int) -> "str | None":
        """Wait up to *timeout_ms* for a button press.

        Returns Direction.PREV, Direction.NEXT, or None on timeout.
        A 20 ms debounce delay is applied after a press before reading
        the live pin state.
        """
        import uasyncio as asyncio  # type: ignore[import]
        import utime  # type: ignore[import]

        try:
            await asyncio.wait_for(self._flag.wait(), timeout_ms / 1000)  # type: ignore[attr-defined]
        except asyncio.TimeoutError:
            return None

        pin_at_irq = self._pressed_pin[0]
        self._flag.clear()  # type: ignore[attr-defined]
        self._pressed_pin[0] = None

        utime.sleep_ms(20)  # debounce

        if pin_at_irq is self._prev_pin or self._prev_pin.value() == 0:
            return Direction.PREV
        if pin_at_irq is self._next_pin or self._next_pin.value() == 0:
            return Direction.NEXT
        return None


async def wait_for_button(timeout_ms: int) -> "str | None":
    """Create a ButtonContext and wait for a single button press.

    Convenience wrapper for callers that do not need to reuse the context
    across multiple wait calls.  Returns Direction.PREV, Direction.NEXT,
    or None on timeout.
    """
    return await ButtonContext().wait(timeout_ms)


def configure_wake() -> None:
    """Register both button pins as deepsleep wake sources.

    Pin.irq() without a handler registers the falling edge as a hardware
    wake source for machine.deepsleep() on RP2350.  Call immediately before
    machine.deepsleep() so either button press wakes the device in addition
    to the sleep timer.
    """
    Pin(PREV_PIN, Pin.IN, Pin.PULL_UP).irq(trigger=Pin.IRQ_FALLING)
    Pin(NEXT_PIN, Pin.IN, Pin.PULL_UP).irq(trigger=Pin.IRQ_FALLING)
