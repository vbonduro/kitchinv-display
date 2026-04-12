"""
Renderer for the KitchInv e-paper display.

All screens share a common chrome: a 3px border with "KITCHINV" centred
as a nameplate in the bottom edge.

The Renderer owns and initialises the Display on construction.

Public API
----------
    from lib.renderer import Renderer

    r = Renderer()
    r.show_centered("To configure this device:", "1. Connect to WiFi: KitchInv-Setup")
"""

import framebuf

from lib.display import HEIGHT, WIDTH, Display, FrameBuf, make_framebuf

# Border thickness in pixels.
_BORDER = 3

# Padding between border and content.
_PAD = 24

# Text scale — each character is 8*scale × 8*scale pixels.
_SCALE = 2

# Line height in pixels.
_LINE_H = 8 * _SCALE

# Gap between lines.
_LINE_GAP = 12

# Nameplate label.
_BRAND = "KITCHINV"


# ---------------------------------------------------------------------------
# Internal drawing helpers
# ---------------------------------------------------------------------------


def _draw_text_scaled(fb: FrameBuf, text: str, x: int, y: int, color: int, scale: int) -> None:
    """Draw *text* at (*x*, *y*) scaled by *scale* (1 = 8×8 px per char)."""
    bg = 1 - color
    for i, ch in enumerate(text):
        cx = x + i * 8 * scale
        tmp_buf = bytearray(8)
        tmp = framebuf.FrameBuffer(tmp_buf, 8, 8, framebuf.MONO_HLSB)
        tmp.fill(bg)
        tmp.text(ch, 0, 0, color)
        for py in range(8):
            for px in range(8):
                if tmp.pixel(px, py) == color:
                    fb.fill_rect(cx + px * scale, y + py * scale, scale, scale, color)


def _text_width(text: str, scale: int) -> int:
    return len(text) * 8 * scale


def _draw_centered(fb: FrameBuf, text: str, y: int, color: int, scale: int) -> None:
    x = (WIDTH - _text_width(text, scale)) // 2
    _draw_text_scaled(fb, text, x, y, color, scale)


def _draw_frame(fb: FrameBuf) -> None:
    """Draw the 3px border and KITCHINV nameplate on *fb*."""
    fb.fill_rect(0, 0, WIDTH, _BORDER, 0)                          # top
    fb.fill_rect(0, 0, _BORDER, HEIGHT, 0)                         # left
    fb.fill_rect(WIDTH - _BORDER, 0, _BORDER, HEIGHT, 0)           # right

    # Bottom border in two segments with a gap for the nameplate.
    brand_w = _text_width(_BRAND, scale=2)
    brand_gap = brand_w + 20
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
    def __init__(self) -> None:
        self._display = Display()

    def show_centered(self, *lines: str) -> None:
        """Render *lines* of text centred on screen, equally spaced as a block."""
        fb = make_framebuf()
        fb.fill(1)
        _draw_frame(fb)

        total_h = len(lines) * _LINE_H + (len(lines) - 1) * _LINE_GAP
        y = (HEIGHT - total_h) // 2

        for line in lines:
            _draw_centered(fb, line, y, 0, _SCALE)
            y += _LINE_H + _LINE_GAP

        self._display.show(fb)
