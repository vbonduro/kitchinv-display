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
    total = r.render_area("Pantry", items)        # returns total page count
    r.render_area("Pantry", items, page=1)        # render second page
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

# Header scale for area name.
_HEADER_SCALE = 3

# Maximum number of columns for item layout.
_MAX_COLS = 3


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
    fb.fill_rect(0, 0, WIDTH, _BORDER, 0)  # top
    fb.fill_rect(0, 0, _BORDER, HEIGHT, 0)  # left
    fb.fill_rect(WIDTH - _BORDER, 0, _BORDER, HEIGHT, 0)  # right

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


def _truncate(text: str, max_chars: int) -> str:
    """Truncate *text* to *max_chars*, appending '>' if shortened."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + ">"


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

    def render_area(self, area_name: str, items, page: int = 0) -> int:
        """Render an inventory area onto the display.

        Automatically selects the fewest columns needed to avoid pagination.
        Falls back to _MAX_COLS columns with pagination if the list is too long.

        *items* may be:
          - a list of Item objects  — normal render
          - an empty list           — shows "No items"
          - None                    — shows "Fetch failed"

        Returns the total number of pages so the caller can decide whether to
        offer page-forward/back controls.
        """
        fb = make_framebuf()
        fb.fill(1)
        _draw_frame(fb)

        x0 = _BORDER + _PAD
        content_w = WIDTH - 2 * (_BORDER + _PAD)
        content_bottom = HEIGHT - _BORDER - _PAD

        # --- Header row ---
        header_h = 8 * _HEADER_SCALE
        y_header = _BORDER + _PAD
        _draw_text_scaled(fb, area_name, x0, y_header, 0, _HEADER_SCALE)

        # --- Body start (below header + rule) ---
        y_rule = y_header + header_h + 4
        fb.hline(x0, y_rule, content_w, 0)
        y_body = y_rule + 6

        # --- Status screens (no item list) ---
        if items is None:
            _draw_centered(fb, "Fetch failed", (y_body + content_bottom - _LINE_H) // 2, 0, _SCALE)
            self._display.show(fb)
            return 1

        if not items:
            _draw_centered(fb, "No items", (y_body + content_bottom - _LINE_H) // 2, 0, _SCALE)
            self._display.show(fb)
            return 1

        # --- Choose column count ---
        avail_h = content_bottom - y_body
        row_h = _LINE_H + _LINE_GAP
        rows_per_col = max(1, avail_h // row_h)

        num_cols = 1
        for candidate in range(1, _MAX_COLS + 1):
            if rows_per_col * candidate >= len(items):
                num_cols = candidate
                break
        else:
            num_cols = _MAX_COLS

        col_w = content_w // num_cols
        max_chars = col_w // (8 * _SCALE)
        items_per_page = rows_per_col * num_cols
        total_pages = max(1, (len(items) + items_per_page - 1) // items_per_page)

        # --- Pagination indicator (only when needed) ---
        if total_pages > 1:
            indicator = "{} / {}".format(page + 1, total_pages)
            ind_w = _text_width(indicator, _SCALE)
            ind_x = x0 + content_w - ind_w
            ind_y = y_header + (header_h - _LINE_H) // 2  # vertically centred on header
            _draw_text_scaled(fb, indicator, ind_x, ind_y, 0, _SCALE)

        # --- Item list ---
        start = page * items_per_page
        page_items = items[start : start + items_per_page]

        for i, item in enumerate(page_items):
            col = i // rows_per_col
            row = i % rows_per_col
            x = x0 + col * col_w
            y = y_body + row * row_h
            label = _truncate(item.name, max_chars)
            _draw_text_scaled(fb, label, x, y, 0, _SCALE)

        self._display.show(fb)
        return total_pages
