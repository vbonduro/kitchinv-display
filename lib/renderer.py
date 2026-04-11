"""
Renderer for the KitchInv e-paper display.

All screens share a common chrome: a 3px border with "KITCHINV" centred
as a nameplate in the bottom edge.

The Renderer owns and initialises the Display on construction.

Public API
----------
    from lib.renderer import Renderer

    r = Renderer()
    r.show_ap_setup(ssid="KitchInv-Setup", ip="192.168.4.1")
    r.show_connecting(ssid="MyNetwork")
"""

import framebuf

from lib.display import HEIGHT, WIDTH, Display, make_framebuf

# Border thickness in pixels.
_BORDER = 3

# Padding between border and content.
_PAD = 24

# Nameplate label.
_BRAND = "KITCHINV"


# ---------------------------------------------------------------------------
# Internal drawing helpers (module-level, no display dependency)
# ---------------------------------------------------------------------------


def _draw_text_scaled(fb, text, x, y, color, scale):
    """Draw *text* at (*x*, *y*) scaled by *scale* (1 = 8×8 px per char)."""
    bg = 1 - color
    for i, ch in enumerate(text):
        cx = x + i * 8 * scale
        tmp_buf = bytearray(8)  # 8 px wide × 8 px tall / 8 = 8 bytes
        tmp = framebuf.FrameBuffer(tmp_buf, 8, 8, framebuf.MONO_HLSB)
        tmp.fill(bg)
        tmp.text(ch, 0, 0, color)
        for py in range(8):
            for px in range(8):
                if tmp.pixel(px, py) == color:
                    fb.fill_rect(cx + px * scale, y + py * scale, scale, scale, color)


def _text_width(text, scale):
    return len(text) * 8 * scale


def _draw_centered(fb, text, y, color, scale):
    x = (WIDTH - _text_width(text, scale)) // 2
    _draw_text_scaled(fb, text, x, y, color, scale)


def _draw_frame(fb):
    """Draw the 3px border and KITCHINV nameplate on *fb*."""
    fb.fill_rect(0, 0, WIDTH, _BORDER, 0)                          # top
    fb.fill_rect(0, 0, _BORDER, HEIGHT, 0)                         # left
    fb.fill_rect(WIDTH - _BORDER, 0, _BORDER, HEIGHT, 0)           # right

    # Bottom border in two segments with a gap for the nameplate.
    brand_w = _text_width(_BRAND, scale=2)
    brand_gap = brand_w + 20  # 10px breathing room each side
    gap_x = (WIDTH - brand_gap) // 2
    fb.fill_rect(0, HEIGHT - _BORDER, gap_x, _BORDER, 0)
    fb.fill_rect(gap_x + brand_gap, HEIGHT - _BORDER, WIDTH - (gap_x + brand_gap), _BORDER, 0)

    # Nameplate text — vertically centred on the bottom border line.
    brand_x = (WIDTH - brand_w) // 2
    brand_y = HEIGHT - _BORDER - (8 * 2 - _BORDER) // 2 - 8
    _draw_text_scaled(fb, _BRAND, brand_x, brand_y, 0, scale=2)


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class Renderer:
    def __init__(self):
        self._display = Display()

    def show_ap_setup(self, ssid, ip):
        """Show the captive portal setup screen.

        Instructs the user to connect to *ssid* and open *ip* in a browser.
        """
        fb = make_framebuf()
        fb.fill(1)
        _draw_frame(fb)

        inner_top = _BORDER + _PAD
        inner_bottom = HEIGHT - _BORDER - _PAD - 16
        content_height = (16 + 16) + 28 + (16 + 24) + 28 + (16 + 16)
        y = inner_top + (inner_bottom - inner_top - content_height) // 2

        _draw_centered(fb, "To configure this device:", y, 0, scale=2)
        y += 16 + 28

        _draw_centered(fb, "1. Connect to WiFi:", y, 0, scale=2)
        y += 16 + 8
        _draw_centered(fb, ssid, y, 0, scale=3)
        y += 24 + 28

        _draw_centered(fb, "2. Open browser to:", y, 0, scale=2)
        y += 16 + 8
        _draw_centered(fb, "http://" + ip, y, 0, scale=2)

        self._display.show(fb)

    def show_connecting(self, ssid):
        """Show a 'Connecting to <ssid>...' screen."""
        fb = make_framebuf()
        fb.fill(1)
        _draw_frame(fb)

        total_h = 16 + 16 + 24  # line1 + gap + line2
        y = (HEIGHT - total_h) // 2

        _draw_centered(fb, "Connecting to...", y, 0, scale=2)
        y += 16 + 16
        _draw_centered(fb, ssid, y, 0, scale=3)

        self._display.show(fb)
