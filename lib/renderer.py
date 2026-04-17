"""
Renderer for the KitchInv e-paper display.

All screens share a common chrome: a 3px border with "KITCHINV" centred
as a nameplate in the bottom edge.

The Renderer builds FrameBuf objects; the caller owns the Display and decides
when to push each frame to the panel.

Public API
----------
    from lib.display import Display
    from lib.renderer import Renderer
    from lib.kitchinv import Area

    display = Display()
    r = Renderer()

    display.show(r.render_text_centered("To configure:", "1. Connect to WiFi: KitchInv-Setup"))

    pages = r.render_area(area)   # list[FrameBuf], one per page
    display.show(pages[0])
"""

import framebuf

from lib.display import HEIGHT, WIDTH, FrameBuf, make_framebuf
from lib.kitchinv import Area

# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------

# Border thickness in pixels.
_BORDER = 3

# Padding between border and content area.
_PAD = 24

# Text scale used for body copy — each character is 8*scale × 8*scale pixels.
_BODY_SCALE = 2

# Character cell height at body scale.
_CHAR_H = 8 * _BODY_SCALE

# Gap between body-text lines.
_LINE_GAP = 12

# Total row height (character + gap).
_ROW_H = _CHAR_H + _LINE_GAP

# Nameplate label burned into the bottom border.
_BRAND = "KITCHINV"

# Scale used for the area-name header.
_HEADER_SCALE = 3

# Maximum number of item columns.
_MAX_COLS = 2

# Pixel gap between adjacent columns.
_COL_GAP = 20

# ---------------------------------------------------------------------------
# Derived layout geometry (computed once from the constants above)
# ---------------------------------------------------------------------------

# Left edge and width of the content area (inside border + padding).
_CONTENT_X = _BORDER + _PAD
_CONTENT_W = WIDTH - 2 * (_BORDER + _PAD)

# Top of the area-name header.
_HEADER_Y = _BORDER + _PAD
_HEADER_H = 8 * _HEADER_SCALE

# Horizontal rule sits 4 px below the header text.
_RULE_Y = _HEADER_Y + _HEADER_H + 4

# Item list starts 6 px below the rule.
_ITEMS_Y = _RULE_Y + 6

# Bottom of the content area (above border + padding).
_CONTENT_BOTTOM = HEIGHT - _BORDER - _PAD


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
# Screen-chrome helpers
# ---------------------------------------------------------------------------


def _draw_frame(fb: FrameBuf) -> None:
    """Draw the 3 px border and KITCHINV nameplate onto *fb*."""
    fb.fill_rect(0, 0, WIDTH, _BORDER, 0)  # top
    fb.fill_rect(0, 0, _BORDER, HEIGHT, 0)  # left
    fb.fill_rect(WIDTH - _BORDER, 0, _BORDER, HEIGHT, 0)  # right

    # Bottom border split around the nameplate.
    brand_w = _text_width(_BRAND, scale=2)
    brand_gap = brand_w + 20
    gap_x = (WIDTH - brand_gap) // 2
    fb.fill_rect(0, HEIGHT - _BORDER, gap_x, _BORDER, 0)
    fb.fill_rect(gap_x + brand_gap, HEIGHT - _BORDER, WIDTH - gap_x - brand_gap, _BORDER, 0)

    brand_x = (WIDTH - brand_w) // 2
    brand_y = HEIGHT - _BORDER - (8 * 2 - _BORDER) // 2 - 8
    _draw_text_scaled(fb, _BRAND, brand_x, brand_y, 0, scale=2)


def _draw_area_header(fb: FrameBuf, area_name: str, page_indicator: str | None) -> None:
    """Draw the area name, optional page indicator, and horizontal rule."""
    _draw_text_scaled(fb, area_name, _CONTENT_X, _HEADER_Y, 0, _HEADER_SCALE)

    if page_indicator is not None:
        indicator_w = _text_width(page_indicator, _BODY_SCALE)
        indicator_x = _CONTENT_X + _CONTENT_W - indicator_w
        indicator_y = _HEADER_Y + (_HEADER_H - _CHAR_H) // 2
        _draw_text_scaled(fb, page_indicator, indicator_x, indicator_y, 0, _BODY_SCALE)

    fb.hline(_CONTENT_X, _RULE_Y, _CONTENT_W, 0)


# ---------------------------------------------------------------------------
# Page builders
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


def _make_status_page(area_name: str, message: str) -> FrameBuf:
    """Render a single-page frame with *message* centred in the item area."""
    fb = make_framebuf()
    fb.fill(1)
    _draw_frame(fb)
    _draw_area_header(fb, _ascii_safe(area_name), None)
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
) -> FrameBuf:
    """Render one page of an area item list into a new FrameBuf."""
    fb = make_framebuf()
    fb.fill(1)
    _draw_frame(fb)

    indicator = "{} / {}".format(page + 1, total_pages) if total_pages > 1 else None
    _draw_area_header(fb, _ascii_safe(area_name), indicator)

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
# Renderer
# ---------------------------------------------------------------------------


class Renderer:
    def render_text_centered(self, *lines: str) -> FrameBuf:
        """Return a FrameBuf with *lines* of text centred on screen."""
        fb = make_framebuf()
        fb.fill(1)
        _draw_frame(fb)

        block_h = len(lines) * _CHAR_H + (len(lines) - 1) * _LINE_GAP
        y = (HEIGHT - block_h) // 2
        for line in lines:
            _draw_text_centered(fb, line, y, 0, _BODY_SCALE)
            y += _ROW_H

        return fb

    def render_area(self, area: Area, page: int = 0) -> tuple:
        """Return (FrameBuf, RenderCursor | None) for *page* of *area*.

        The cursor holds the layout state needed to render subsequent pages.
        It is None when the area has no items (single status page, no paging).

        *page* is clamped to the valid range — safe to pass a stale index
        from RTC memory if the area's item count has changed since last boot.

        Only one FrameBuf is allocated; callers should del it before calling
        next_page() to keep peak heap usage to a single 48 KB frame.

        Selects the fewest columns (1–_MAX_COLS) that fit all items on one
        page, falling back to _MAX_COLS + pagination for very long lists.
        """
        if not area.items:
            return _make_status_page(area.name, "No items"), None

        rows_per_col = max(1, (_CONTENT_BOTTOM - _ITEMS_Y) // _ROW_H)

        # Use the minimum columns needed across ALL pages for consistent
        # pagination, then re-evaluate for the specific page being rendered
        # so that a sparsely-populated last page doesn't waste space.
        num_cols = _MAX_COLS
        for candidate in range(1, _MAX_COLS + 1):
            if rows_per_col * candidate >= len(area.items):
                num_cols = candidate
                break

        items_per_page = rows_per_col * num_cols
        total_pages = max(1, (len(area.items) + items_per_page - 1) // items_per_page)

        page = min(page, total_pages - 1)  # clamp stale index

        # Recalculate columns for the actual items on this page so the last
        # page uses the fewest columns needed rather than the global maximum.
        page_item_count = len(area.items[page * items_per_page : (page + 1) * items_per_page])
        render_cols = num_cols
        for candidate in range(1, num_cols + 1):
            if rows_per_col * candidate >= page_item_count:
                render_cols = candidate
                break

        col_w = (_CONTENT_W - (render_cols - 1) * _COL_GAP) // render_cols
        max_chars_per_col = col_w // _char_width(_BODY_SCALE)

        cursor = RenderCursor(
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
        fb = _make_items_page(
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
        return fb, cursor

    def next_page(self, cursor: RenderCursor) -> tuple:
        """Return (FrameBuf, cursor) for the next page.

        Advances the cursor in-place and renders the new page.  The caller
        should del the previous FrameBuf before calling this to avoid holding
        two 48 KB frames simultaneously.

        Caller must check cursor.has_next before calling.
        """
        cursor.page += 1
        fb = _make_items_page(
            cursor.area_name,
            cursor.items,
            cursor.page,
            cursor.total_pages,
            cursor._rows_per_col,
            cursor._num_cols,
            cursor._col_w,
            cursor._max_chars_per_col,
            cursor._items_per_page,
        )
        return fb, cursor
