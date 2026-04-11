"""
Display driver for the Waveshare 7.5" 800x480 B&W e-paper module (Pico variant).

Hardware connections (module plugs directly onto Pico headers):
  SPI1  MOSI → GP11   SCK → GP10
  RST        → GP12
  DC         → GP8
  CS         → GP9
  BUSY       → GP13

Usage
-----
    from lib import display

    d = display.Display()       # initialises panel and clears to white

    fb = display.make_framebuf()
    fb.fill(1)                  # white background (1 = white, 0 = black)
    fb.text("Hello", 10, 10, 0)
    d.show(fb)                  # full refresh (~2-3 s)
    d.show_fast(fb)             # fast refresh (slight ghosting, ~0.5 s)
    d.sleep()                   # deep-sleep before power-off
"""

import framebuf

from lib.epd7in5 import EPD_7in5

WIDTH = 800
HEIGHT = 480


def make_framebuf():
    """Return a correctly-sized MONO_HLSB FrameBuffer for this display.

    The caller owns the buffer and uses it for drawing.  Pass it to
    Display.show() or Display.show_fast() when ready to render.
    Multiple framebuffers can coexist (e.g. one for status, one for inventory).
    """
    buf = bytearray(WIDTH * HEIGHT // 8)
    return framebuf.FrameBuffer(buf, WIDTH, HEIGHT, framebuf.MONO_HLSB)


class Display:
    def __init__(self):
        """Initialise the e-paper panel and clear it to white."""
        self._epd = EPD_7in5()
        self.clear()

    def clear(self):
        """Fill the panel white."""
        self._epd.Clear()

    def show(self, fb):
        """Push *fb* to the panel using a full refresh (~2-3 s).

        *fb* must be a MONO_HLSB FrameBuffer of size WIDTH × HEIGHT,
        as returned by make_framebuf().
        """
        self._epd.display(fb)

    def show_fast(self, fb):
        """Push *fb* using the fast-refresh LUT (~0.5 s, slight ghosting).

        Switches the panel into fast-refresh mode before sending the frame.
        Call show() for the next full-quality update if ghosting becomes an issue.
        """
        self._epd.init_fast()
        self._epd.display(fb)

    def sleep(self):
        """Put the panel into deep sleep.  Call Display() again to wake it."""
        self._epd.sleep()
