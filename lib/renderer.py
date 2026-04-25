"""
Renderer for the KitchInv e-paper display.

Each inventory screen has a compact status bar at the top showing the area
name, sleep/wake mode icon, and battery level.  The remaining space is
maximised for the inventory list.

Public API
----------
    from lib.display import Display
    from lib.renderer import Renderer
    from lib.kitchinv import Area

    display = Display()
    r = Renderer()

    display.show(r.render_text_centered("To configure:", "1. Connect to WiFi: KitchInv-Setup"))

    fb, cursor = r.render_area(area, is_deep_sleep=True, battery_pct=80)
    display.show(fb)
"""

import framebuf

from lib.display import HEIGHT, WIDTH, FrameBuf, make_framebuf
from lib.kitchinv import Area

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

# Padding between content and screen edge.
_PAD = 16

# Body text (inventory items).
_BODY_SCALE = 2
_CHAR_H = 8 * _BODY_SCALE
_LINE_GAP = 12
_ROW_H = _CHAR_H + _LINE_GAP

# Column layout.
_MAX_COLS = 2
_COL_GAP = 20

# Status bar.
_STATUS_H = 24       # total height of the status bar strip
_STATUS_SCALE = 2    # text scale for the area name

# Icon dimensions (8×8 bitmap drawn at _STATUS_ICON_SCALE).
_STATUS_ICON_SCALE = 2
_STATUS_ICON_W = 8 * _STATUS_ICON_SCALE  # 16 px

# Battery icon dimensions.
_BATT_W = 22
_BATT_H = 14
_BATT_NUB_W = 3
_BATT_NUB_H = 8

# ---------------------------------------------------------------------------
# Derived geometry
# ---------------------------------------------------------------------------

_CONTENT_X = _PAD
_CONTENT_W = WIDTH - 2 * _PAD

# Separator rule sits immediately below the status bar.
_RULE_Y = _STATUS_H

# Inventory items start 14 px below the rule — breathing room like Kobo chrome.
_ITEMS_Y = _RULE_Y + 14

# Content extends to the bottom of the display.
_CONTENT_BOTTOM = HEIGHT

# ---------------------------------------------------------------------------
# Status bar icon bitmaps (8×8, MSB-first row bytes, 1 = set pixel)
# ---------------------------------------------------------------------------

# Crescent moon (☾) — timer / deep-sleep wake.
_ICON_MOON = (0x3C, 0x60, 0xC0, 0xC0, 0xC0, 0xC0, 0x60, 0x3C)

# Sun (☀) — button / active wake.
_ICON_SUN = (0x24, 0x18, 0x99, 0x7E, 0x7E, 0x99, 0x18, 0x24)

# ---------------------------------------------------------------------------
# Low-level drawing primitives
# ---------------------------------------------------------------------------


def _draw_glyph_row(fb: FrameBuf, b: int, char_x: int, row_y: int, scale: int, color: int) -> None:
    """Draw one 8-pixel row of a glyph using run-length encoded fill_rect calls."""
    run_len = 0
    run_x = char_x
    col_x = char_x
    mask = 0x80
    for _ in range(8):
        if b & mask:
            if not run_len:
                run_x = col_x
            run_len += 1
        elif run_len:
            fb.fill_rect(run_x, row_y, run_len * scale, scale, color)
            run_len = 0
        mask >>= 1
        col_x += scale
    if run_len:
        fb.fill_rect(run_x, row_y, run_len * scale, scale, color)


def _draw_char_scaled(
    fb: FrameBuf,
    glyph_buf: bytearray,
    glyph: framebuf.FrameBuffer,
    ch: str,
    char_x: int,
    y: int,
    scale: int,
    color: int,
) -> None:
    """Render a single character glyph into *fb* at (*char_x*, *y*)."""
    glyph_buf[:] = b"\x00\x00\x00\x00\x00\x00\x00\x00"
    glyph.text(ch, 0, 0, 1)
    for row in range(8):
        b = glyph_buf[row]
        if b:
            _draw_glyph_row(fb, b, char_x, y + row * scale, scale, color)


def _draw_text_scaled(fb: FrameBuf, text: str, x: int, y: int, color: int, scale: int) -> None:
    """Draw *text* at (*x*, *y*) scaled by *scale* (1 = 8×8 px per char).

    Glyph rows are read as raw bytes and horizontal runs of set pixels are
    merged into a single fill_rect call, reducing Python→C call count by
    roughly 2-3x versus per-pixel rendering.
    """
    glyph_buf = bytearray(8)
    glyph = framebuf.FrameBuffer(glyph_buf, 8, 8, framebuf.MONO_HLSB)
    for i, ch in enumerate(text):
        _draw_char_scaled(fb, glyph_buf, glyph, ch, x + i * 8 * scale, y, scale, color)


def _char_width(scale: int) -> int:
    return 8 * scale


def _text_width(text: str, scale: int) -> int:
    return len(text) * _char_width(scale)


def _draw_text_centered(fb: FrameBuf, text: str, y: int, color: int, scale: int) -> None:
    x = (WIDTH - _text_width(text, scale)) // 2
    _draw_text_scaled(fb, text, x, y, color, scale)


# ---------------------------------------------------------------------------
# Icon drawing
# ---------------------------------------------------------------------------


def _draw_bitmap_scaled(
    fb: FrameBuf, rows: tuple, x: int, y: int, scale: int, color: int
) -> None:
    """Draw an 8×8 bitmap at (*x*, *y*) scaled by *scale*."""
    for i, b in enumerate(rows):
        _draw_glyph_row(fb, b, x, y + i * scale, scale, color)


def _draw_hamburger(fb: FrameBuf, x: int, y: int, color: int) -> None:
    """Draw a hamburger menu icon (≡) as three lines within a 16×16 px box."""
    fb.fill_rect(x, y + 3, 16, 2, color)
    fb.fill_rect(x, y + 7, 16, 2, color)
    fb.fill_rect(x, y + 11, 16, 2, color)


def _draw_battery(fb: FrameBuf, x: int, y: int, pct: "int | None", color: int) -> None:
    """Draw a battery icon at (*x*, *y*). *pct* is 0-100 or None (unknown)."""
    # Body outline.
    fb.hline(x, y, _BATT_W, color)
    fb.hline(x, y + _BATT_H - 1, _BATT_W, color)
    fb.vline(x, y, _BATT_H, color)
    fb.vline(x + _BATT_W - 1, y, _BATT_H, color)
    # Positive terminal nub on the right.
    nub_y = y + (_BATT_H - _BATT_NUB_H) // 2
    fb.fill_rect(x + _BATT_W, nub_y, _BATT_NUB_W, _BATT_NUB_H, color)
    # Charge level fill.
    if pct is not None and pct > 0:
        fill_w = (_BATT_W - 2) * pct // 100
        if fill_w > 0:
            fb.fill_rect(x + 1, y + 1, fill_w, _BATT_H - 2, color)


# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------


def _draw_status_bar(
    fb: FrameBuf,
    area_name: str,
    page_indicator: "str | None",
    is_deep_sleep: bool,
    battery_pct: "int | None",
) -> None:
    """Draw the full-width status bar at y=0 (black background, white content).

    Layout: ≡ area_name  (left) | page_indicator  sleep_icon  battery  (right)
    """
    icon_y = (_STATUS_H - _STATUS_ICON_W) // 2   # vertically centre 16-px icons
    text_y = (_STATUS_H - 8 * _STATUS_SCALE) // 2  # vertically centre scale-2 text

    # Left: hamburger + area name + optional page indicator.
    _draw_hamburger(fb, 8, icon_y, 0)
    name_x = 8 + _STATUS_ICON_W + 10
    _draw_text_scaled(fb, _ascii_safe(area_name), name_x, text_y, 0, _STATUS_SCALE)
    if page_indicator is not None:
        ind_x = name_x + _text_width(_ascii_safe(area_name), _STATUS_SCALE) + 6
        ind_y = (_STATUS_H - 8) // 2  # centre scale-1 (8 px) text
        _draw_text_scaled(fb, page_indicator, ind_x, ind_y, 0, 1)

    # Right: battery.
    batt_x = WIDTH - 8 - _BATT_W - _BATT_NUB_W
    batt_y = (_STATUS_H - _BATT_H) // 2
    _draw_battery(fb, batt_x, batt_y, battery_pct, 0)

    # Sleep/wake icon (left of battery with 8 px gap).
    sleep_x = batt_x - 8 - _STATUS_ICON_W
    bitmap = _ICON_MOON if is_deep_sleep else _ICON_SUN
    _draw_bitmap_scaled(fb, bitmap, sleep_x, icon_y, _STATUS_ICON_SCALE, 0)


# ---------------------------------------------------------------------------
# Accent / truncation helpers
# ---------------------------------------------------------------------------

# MicroPython's built-in font is 7-bit ASCII only.  Map common accented
# characters to their ASCII base so they render instead of showing as '?'.
_ACCENT_MAP = [
    ("àáâãäå", "a"),
    ("ÀÁÂÃÄÅ", "A"),
    ("èéêë", "e"),
    ("ÈÉÊË", "E"),
    ("ìíîï", "i"),
    ("ÌÍÎÏ", "I"),
    ("òóôõö", "o"),
    ("ÒÓÔÕÖ", "O"),
    ("ùúûü", "u"),
    ("ÙÚÛÜ", "U"),
    ("ýÿ", "y"),
    ("Ý", "Y"),
    ("ç", "c"),
    ("Ç", "C"),
    ("ñ", "n"),
    ("Ñ", "N"),
    ("ß", "ss"),
]


def _ascii_safe(text: str) -> str:
    """Replace accented characters with their ASCII equivalents."""
    for accented, base in _ACCENT_MAP:
        for ch in accented:
            if ch in text:
                text = text.replace(ch, base)
    return text


def _truncate(text: str, max_chars: int) -> str:
    """Truncate *text* to *max_chars*, appending '>' to mark the cut."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + ">"


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------


def _make_status_page(
    area_name: str,
    message: str,
    is_deep_sleep: bool,
    battery_pct: "int | None",
) -> FrameBuf:
    """Render a single-page frame with *message* centred in the item area."""
    fb = make_framebuf()
    fb.fill(1)
    _draw_status_bar(fb, area_name, None, is_deep_sleep, battery_pct)
    fb.hline(_CONTENT_X, _RULE_Y, _CONTENT_W, 0)
    message_y = (_ITEMS_Y + _CONTENT_BOTTOM - _CHAR_H) // 2
    _draw_text_centered(fb, message, message_y, 0, _BODY_SCALE)
    return fb


def _make_items_page(
    area_name: str,
    items: list,
    page: int,
    total_pages: int,
    rows_per_col: int,
    num_cols: int,
    col_w: int,
    max_chars_per_col: int,
    items_per_page: int,
    is_deep_sleep: bool,
    battery_pct: "int | None",
) -> FrameBuf:
    """Render one page of an area item list into a new FrameBuf."""
    fb = make_framebuf()
    fb.fill(1)

    indicator = "{}/{}".format(page + 1, total_pages) if total_pages > 1 else None
    _draw_status_bar(fb, area_name, indicator, is_deep_sleep, battery_pct)
    fb.hline(_CONTENT_X, _RULE_Y, _CONTENT_W, 0)

    page_items = items[page * items_per_page : (page + 1) * items_per_page]
    for i, item in enumerate(page_items):
        col = i // rows_per_col
        row = i % rows_per_col
        item_x = _CONTENT_X + col * (col_w + _COL_GAP)
        item_y = _ITEMS_Y + row * _ROW_H
        label = _truncate(_ascii_safe(item.name), max_chars_per_col)
        _draw_text_scaled(fb, label, item_x, item_y, 0, _BODY_SCALE)
    return fb


# ---------------------------------------------------------------------------
# Render cursor
# ---------------------------------------------------------------------------


class RenderCursor:
    """Tracks position within a multi-page area render.

    Holds the layout parameters computed once for the area so subsequent
    pages can be rendered without recomputing or re-fetching the area.
    The caller must keep the cursor alive between pages (it holds the item
    list reference), but only one FrameBuf needs to exist at a time.

    Check *has_next* before calling Renderer.next_page().
    """

    def __init__(
        self,
        area_name: str,
        items: list,
        page: int,
        total_pages: int,
        rows_per_col: int,
        num_cols: int,
        col_w: int,
        max_chars_per_col: int,
        items_per_page: int,
    ) -> None:
        self.area_name = area_name
        self.items = items
        self.page = page
        self.total_pages = total_pages
        self._rows_per_col = rows_per_col
        self._num_cols = num_cols
        self._col_w = col_w
        self._max_chars_per_col = max_chars_per_col
        self._items_per_page = items_per_page

    @property
    def has_next(self) -> bool:
        return self.page + 1 < self.total_pages


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------


def _min_cols_for(num_items: int, rows_per_col: int, max_cols: int = _MAX_COLS) -> int:
    """Return the fewest columns (up to *max_cols*) that fit *num_items*."""
    for cols in range(1, max_cols + 1):
        if rows_per_col * cols >= num_items:
            return cols
    return max_cols


def _build_cursor(area: Area, page: int) -> RenderCursor:
    """Compute layout parameters for *area* and return a RenderCursor.

    Uses the minimum columns needed across ALL pages for consistent
    pagination, then re-evaluates for the specific page so that a
    sparsely-populated last page doesn't waste horizontal space.
    """
    rows_per_col = max(1, (_CONTENT_BOTTOM - _ITEMS_Y) // _ROW_H)

    num_cols = _min_cols_for(len(area.items), rows_per_col)
    items_per_page = rows_per_col * num_cols
    total_pages = max(1, (len(area.items) + items_per_page - 1) // items_per_page)

    page = min(page, total_pages - 1)  # clamp stale index

    page_item_count = len(area.items[page * items_per_page : (page + 1) * items_per_page])
    render_cols = _min_cols_for(page_item_count, rows_per_col, num_cols)

    col_w = (_CONTENT_W - (render_cols - 1) * _COL_GAP) // render_cols
    max_chars_per_col = col_w // _char_width(_BODY_SCALE)

    return RenderCursor(
        area.name,
        area.items,
        page,
        total_pages,
        rows_per_col,
        render_cols,
        col_w,
        max_chars_per_col,
        items_per_page,
    )


def _render_page(
    cursor: RenderCursor, is_deep_sleep: bool, battery_pct: "int | None"
) -> FrameBuf:
    """Render the current page described by *cursor* into a new FrameBuf."""
    return _make_items_page(
        cursor.area_name,
        cursor.items,
        cursor.page,
        cursor.total_pages,
        cursor._rows_per_col,
        cursor._num_cols,
        cursor._col_w,
        cursor._max_chars_per_col,
        cursor._items_per_page,
        is_deep_sleep,
        battery_pct,
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class Renderer:
    def render_text_centered(self, *lines: str) -> FrameBuf:
        """Return a FrameBuf with *lines* of text centred on screen."""
        fb = make_framebuf()
        fb.fill(1)
        block_h = len(lines) * _CHAR_H + (len(lines) - 1) * _LINE_GAP
        y = (HEIGHT - block_h) // 2
        for line in lines:
            _draw_text_centered(fb, line, y, 0, _BODY_SCALE)
            y += _ROW_H
        return fb

    def render_area(
        self,
        area: Area,
        page: int = 0,
        *,
        is_deep_sleep: bool = True,
        battery_pct: "int | None" = None,
    ) -> tuple:
        """Return (FrameBuf, RenderCursor | None) for *page* of *area*.

        The cursor holds the layout state needed to render subsequent pages.
        It is None when the area has no items (single status page, no paging).

        *page* is clamped to the valid range — safe to pass a stale index
        from RTC memory if the area's item count has changed since last boot.

        Only one FrameBuf is allocated; callers should del it before calling
        next_page() to keep peak heap usage to a single 48 KB frame.
        """
        if not area.items:
            return _make_status_page(area.name, "No items", is_deep_sleep, battery_pct), None
        cursor = _build_cursor(area, page)
        return _render_page(cursor, is_deep_sleep, battery_pct), cursor

    def next_page(
        self,
        cursor: RenderCursor,
        *,
        is_deep_sleep: bool = True,
        battery_pct: "int | None" = None,
    ) -> tuple:
        """Return (FrameBuf, cursor) for the next page.

        Advances the cursor in-place and renders the new page.  The caller
        should del the previous FrameBuf before calling this to avoid holding
        two 48 KB frames simultaneously.

        Caller must check cursor.has_next before calling.
        """
        cursor.page += 1
        return _render_page(cursor, is_deep_sleep, battery_pct), cursor
