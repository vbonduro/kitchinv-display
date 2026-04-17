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


def register_irq_handlers() -> tuple:
    """Set up both button pins with a shared IRQ handler for active-mode use.

    Registers falling-edge IRQs on both pins, waits 200 ms for spurious
    IRQs to settle, then clears the flag so only presses that arrive after
    this call are counted.

    Returns (flag, pressed_pin, prev_pin, next_pin) where:
      flag         — uasyncio.ThreadSafeFlag set by the handler
      pressed_pin  — single-element list; handler writes the triggering Pin
      prev_pin     — the PREV Pin object (for live-value reads)
      next_pin     — the NEXT Pin object (for live-value reads)
    """
    import time

    import uasyncio as asyncio  # type: ignore[import]

    flag = asyncio.ThreadSafeFlag()
    pressed_pin: list = [None]

    def _handler(pin: object) -> None:
        pressed_pin[0] = pin
        flag.set()

    prev_pin = Pin(PREV_PIN, Pin.IN, Pin.PULL_UP)
    next_pin = Pin(NEXT_PIN, Pin.IN, Pin.PULL_UP)
    prev_pin.irq(trigger=Pin.IRQ_FALLING, handler=_handler)
    next_pin.irq(trigger=Pin.IRQ_FALLING, handler=_handler)

    time.sleep_ms(200)  # type: ignore[attr-defined]  # settle spurious IRQs
    flag.clear()  # type: ignore[attr-defined]
    pressed_pin[0] = None

    return flag, pressed_pin, prev_pin, next_pin


def direction_from_press(
    pin_at_irq: object, prev_pin: "Pin", next_pin: "Pin"
) -> "str | None":
    """Resolve a button press to a Direction, or None for spurious IRQs.

    Uses *pin_at_irq* (captured at interrupt time) as the primary source,
    falling back to a live pin read for presses that arrive while a previous
    render is still running.
    """
    if pin_at_irq is prev_pin or prev_pin.value() == 0:
        return Direction.PREV
    if pin_at_irq is next_pin or next_pin.value() == 0:
        return Direction.NEXT
    return None


def configure_wake() -> None:
    """Register both button pins as deepsleep wake sources.

    Pin.irq() without a handler registers the falling edge as a hardware
    wake source for machine.deepsleep() on RP2350.  Call immediately before
    machine.deepsleep() so either button press wakes the device in addition
    to the sleep timer.
    """
    Pin(PREV_PIN, Pin.IN, Pin.PULL_UP).irq(trigger=Pin.IRQ_FALLING)
    Pin(NEXT_PIN, Pin.IN, Pin.PULL_UP).irq(trigger=Pin.IRQ_FALLING)
