import io
import os
import re

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

from utils.ColorUtils import (
    TABLE_BG,
    TABLE_CELL_BG,
    TABLE_CELL_BG_ALT,
    TABLE_CELL_FG,
    TABLE_HEADER_BG,
    TABLE_HEADER_FG,
    TABLE_LABEL_BG,
    TABLE_LABEL_FG,
    TABLE_ROW_DIVIDER,
    TABLE_TMAX_FG,
    TABLE_TMIN_FG,
)
from utils.log import get_logger

logger = get_logger("table_generator")

_ARSO_BASE = "https://meteo.arso.gov.si"

_SCALE = 2
_FONT_SIZE = 14 * _SCALE
_PAD_H = 14 * _SCALE  # horizontal padding per cell side
_PAD_V = 8 * _SCALE  # vertical padding per cell side
_ICON_SIZE = 38 * _SCALE
_MIN_COL_W = 72 * _SCALE

_FONT_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/noto/NotoSans-Regular.ttf",
]

_BOLD_FONT_CANDIDATES = [
    # macOS — HelveticaNeue.ttc index 1 is bold
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
    ("/System/Library/Fonts/Helvetica.ttc", 1),
    # Linux explicit bold paths (no index needed)
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
    ("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", 0),
    ("/usr/share/fonts/noto/NotoSans-Bold.ttf", 0),
]

_Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


def _load_font(size: int) -> _Font:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    logger.warning(
        "no system font found — non-ASCII characters may not render correctly"
    )
    return ImageFont.load_default(size=size)


def _load_bold_font(size: int, fallback: _Font) -> _Font:
    for path, index in _BOLD_FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, index=index)
            except Exception:
                continue
    return fallback


def _text_w(font: _Font, s: str) -> int:
    if not s:
        return 0
    bb = font.getbbox(s)
    return int(bb[2] - bb[0])


def _text_h(font: _Font, s: str) -> int:
    bb = font.getbbox(s or "A")
    return int(bb[3] - bb[1])


class TableGenerator:
    tablematcher = re.compile(
        r"(<table(.|\n\r|\n|\r|\r\n)+?</table>)", re.MULTILINE
    )

    def __init__(self, folder, url, css):
        self.folder = folder
        self.url = url
        self._icon_cache: dict[str, Image.Image] = {}

    def generate_napoved(self, file):
        return self.generate_table(
            file, f"{self.url}/fcast_SLOVENIA_MIDDLE_latest.html"
        )

    def generate_shorthand(self, file):
        return self.generate_table(
            file, f"{self.url}/fcast_SI_OSREDNJESLOVENSKA_latest.html"
        )

    def generate_table(self, file, html_url, css_url=None, crop=None):
        logger.debug(f"GET {html_url}")
        r = requests.get(html_url, timeout=15)
        if r.status_code != 200:
            logger.warning(f"HTTP {r.status_code} fetching {html_url}")
        html = (
            bytes(r.text, r.encoding or "utf-8")
            .decode("utf-8", "ignore")
            .replace('src="/', f'src="{_ARSO_BASE}/')
        )

        match = re.search(self.tablematcher, html)
        assert match is not None, f"No table found in {html_url}"

        rows = self._parse(match.group(1))
        out_path = os.path.join(self.folder, file)
        self._render(rows, out_path)
        logger.debug(f"table saved: {out_path}")
        return out_path

    def _parse(self, html: str) -> list[list[dict]]:
        soup = BeautifulSoup(html, "html.parser")
        rows = []
        for tr in soup.find_all("tr"):
            row = []
            for cell in tr.find_all(["th", "td"]):
                cls = cell.get("class") or []
                cls_str = " ".join(cls) if isinstance(cls, list) else str(cls)
                img = cell.find("img")
                if img and img.get("src"):
                    src = str(img["src"])
                    if not src.startswith("http"):
                        src = _ARSO_BASE + src
                    row.append(
                        {
                            "type": "img",
                            "value": src,
                            "cls": cls_str,
                            "tag": cell.name,
                        }
                    )
                else:
                    text = cell.get_text(strip=True).replace("\xa0", "")
                    row.append(
                        {
                            "type": "text",
                            "value": text,
                            "cls": cls_str,
                            "tag": cell.name,
                        }
                    )
            if row:
                rows.append(row)
        return rows

    def _fetch_icon(self, url: str) -> Image.Image | None:
        if url in self._icon_cache:
            return self._icon_cache[url]
        try:
            logger.debug(f"GET {url}")
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                return None
            icon = Image.open(io.BytesIO(r.content)).convert("RGBA")
            icon = icon.resize(
                (_ICON_SIZE, _ICON_SIZE), Image.Resampling.LANCZOS
            )
            self._icon_cache[url] = icon
            return icon
        except Exception:
            logger.warning(f"failed to fetch icon {url}")
            return None

    def _measure_col_widths(
        self, rows: list[list[dict]], font: _Font, bold_font: _Font
    ) -> list[int]:
        n_cols = max(len(row) for row in rows)
        col_widths = [_MIN_COL_W] * n_cols
        for row in rows:
            for ci, cell in enumerate(row):
                if cell["type"] == "text" and cell["value"]:
                    f = bold_font if cell["tag"] == "th" else font
                    needed = _text_w(f, cell["value"]) + 2 * _PAD_H
                    col_widths[ci] = max(col_widths[ci], needed)
                elif cell["type"] == "img":
                    col_widths[ci] = max(
                        col_widths[ci], _ICON_SIZE + 2 * _PAD_H
                    )
        return col_widths

    @staticmethod
    def _row_height(row: list[dict], line_h: int) -> int:
        if any(c["tag"] == "th" for c in row):
            return line_h
        if any(c["type"] == "img" for c in row):
            return _ICON_SIZE + 2 * _PAD_V
        return line_h

    @staticmethod
    def _cell_bg(
        is_header: bool, is_label: bool, stripe: bool
    ) -> tuple[int, int, int]:
        if is_header:
            return TABLE_HEADER_BG
        if is_label:
            return TABLE_LABEL_BG
        if stripe:
            return TABLE_CELL_BG_ALT
        return TABLE_CELL_BG

    @staticmethod
    def _cell_fg(
        cell: dict, is_header: bool, is_label: bool
    ) -> tuple[int, int, int]:
        if is_header:
            return TABLE_HEADER_FG
        if "table-marker-text0" in cell["cls"]:
            return TABLE_TMAX_FG
        if "table-marker-text1" in cell["cls"]:
            return TABLE_TMIN_FG
        if is_label:
            return TABLE_LABEL_FG
        return TABLE_CELL_FG

    def _draw_cell_content(
        self,
        draw: ImageDraw.ImageDraw,
        img: Image.Image,
        cell: dict,
        x: int,
        y: int,
        cw: int,
        rh: int,
        font: _Font,
        is_header: bool,
        is_label: bool,
    ) -> None:
        if cell["type"] == "img":
            icon = self._fetch_icon(cell["value"])
            if icon:
                ix = x + (cw - icon.width) // 2
                iy = y + (rh - icon.height) // 2
                img.paste(icon, (ix, iy), icon)
        elif cell["value"]:
            fg = self._cell_fg(cell, is_header, is_label)
            bb = font.getbbox(cell["value"])
            tw = bb[2] - bb[0]
            th = bb[3] - bb[1]
            draw.text(
                (x + (cw - tw) // 2 - bb[0], y + (rh - th) // 2 - bb[1]),
                cell["value"],
                fill=fg,
                font=font,
            )

    def _render(self, rows: list[list[dict]], out_path: str) -> None:
        if not rows:
            return

        font = _load_font(_FONT_SIZE)
        bold_font = _load_bold_font(_FONT_SIZE, font)
        lh = max(_text_h(font, "Ag"), _text_h(bold_font, "Ag"))
        line_h = lh + 2 * _PAD_V

        col_widths = self._measure_col_widths(rows, font, bold_font)
        row_heights = [self._row_height(row, line_h) for row in rows]
        width, height = sum(col_widths), sum(row_heights)

        img = Image.new("RGB", (width, height), TABLE_BG)
        draw = ImageDraw.Draw(img)

        data_row_index = 0
        y = 0
        for ri, row in enumerate(rows):
            rh = row_heights[ri]
            is_header_row = any(c["tag"] == "th" for c in row)
            stripe = not is_header_row and (data_row_index % 2 == 1)
            if not is_header_row:
                data_row_index += 1

            x = 0
            for ci, cell in enumerate(row):
                cw = col_widths[ci]
                is_header = cell["tag"] == "th"
                is_label = "meteoSI-th" in cell["cls"]
                draw.rectangle(
                    [x, y, x + cw, y + rh],
                    fill=self._cell_bg(is_header, is_label, stripe),
                )
                self._draw_cell_content(
                    draw,
                    img,
                    cell,
                    x,
                    y,
                    cw,
                    rh,
                    bold_font if is_header else font,
                    is_header,
                    is_label,
                )
                x += cw

            if ri < len(rows) - 1:
                draw.line(
                    [(0, y + rh), (width, y + rh)],
                    fill=TABLE_ROW_DIVIDER,
                    width=_SCALE,
                )
            y += rh

        img.save(out_path, "PNG")
