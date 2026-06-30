import io
import os
import re

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

from utils.ColorUtils import (
    DARK_PALETTE,
    LIGHT_PALETTE,
    TablePalette,
    invert_icon_lightness,
)
from utils.log import get_logger

logger = get_logger("table_generator")

_ARSO_BASE = "https://meteo.arso.gov.si"

_SCALE = 2
_FONT_SIZE = 14 * _SCALE
_PAD_H = 14 * _SCALE  # horizontal padding per cell side
_PAD_V = 8 * _SCALE  # vertical padding per cell side
_ICON_SIZE = 38 * _SCALE
_WIND_ICON_SIZE = 38  # no _SCALE — wind icons stay compact
_MIN_COL_W = 72 * _SCALE

_DAY_ABBR = {
    "Ponedeljek": "Pon",
    "Torek": "Tor",
    "Sreda": "Sre",
    "Četrtek": "Čet",
    "Petek": "Pet",
    "Sobota": "Sob",
    "Nedelja": "Ned",
}

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
    tablematcher = re.compile(r"(<table.+?</table>)", re.DOTALL)

    def __init__(self, folder, url, dark_mode: bool = True):
        self.folder = folder
        self.url = url
        self.dark_mode = dark_mode
        self.p: TablePalette = DARK_PALETTE if dark_mode else LIGHT_PALETTE
        self._icon_cache: dict[tuple[str, int, bool], Image.Image] = {}

    def generate_napoved(self, file):
        return self.generate_table(
            file, f"{self.url}/fcast_SLOVENIA_MIDDLE_latest.html"
        )

    def generate_shorthand(self, file):
        return self.generate_table(
            file, f"{self.url}/fcast_SI_OSREDNJESLOVENSKA_latest.html"
        )

    def generate_table(self, file, html_url):
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
                cls: list[str] | str = cell.get("class") or []
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
        return self._post_process_rows(rows)

    def _post_process_rows(self, rows: list[list[dict]]) -> list[list[dict]]:
        def _label(row: list[dict]) -> str:
            return row[0].get("value", "") if row else ""

        # Merge Megla/Nevihte overlay into Vreme/Pojavi row
        vreme_idx = next(
            (i for i, r in enumerate(rows) if _label(r).startswith("Vreme")),
            None,
        )
        megla_idx = next(
            (i for i, r in enumerate(rows) if "Megla" in _label(r)),
            None,
        )
        if vreme_idx is not None and megla_idx is not None:
            vreme_row = rows[vreme_idx]
            megla_row = rows[megla_idx]
            for ci in range(1, min(len(vreme_row), len(megla_row))):
                if megla_row[ci]["type"] == "img":
                    vreme_row[ci]["overlay"] = megla_row[ci]["value"]
            vreme_row[0]["value"] = "Vreme"
            rows.pop(megla_idx)

        # Move units from row label into each data cell
        unit_re = re.compile(r"^(.+?)\s*\[(.+?)\]$")
        for row in rows:
            m = unit_re.match(_label(row))
            if m:
                name, unit = m.group(1), m.group(2)
                sep = "" if unit.startswith("°") else " "
                row[0]["value"] = name
                for cell in row[1:]:
                    if cell["type"] == "text" and cell["value"]:
                        cell["value"] = f"{cell['value']}{sep}{unit}"

        # Merge Tmax and Tmin into one Temperatura row
        tmax_idx = next(
            (i for i, r in enumerate(rows) if _label(r) == "Tmax"), None
        )
        tmin_idx = next(
            (i for i, r in enumerate(rows) if _label(r) == "Tmin"), None
        )
        if tmax_idx is not None and tmin_idx is not None:
            tmax_row = rows[tmax_idx]
            tmin_row = rows[tmin_idx]
            for ci in range(1, min(len(tmax_row), len(tmin_row))):
                tmin_val = tmin_row[ci].get("value", "")
                if tmin_val:
                    tmax_row[ci]["tmin"] = tmin_val
            tmax_row[0]["value"] = "Temperatura"
            for cell in tmax_row:
                cell["temp_combined"] = True
            rows.pop(tmin_idx)

        # Merge Temperatura into Vreme row (icon + temp below)
        vreme_idx2 = next(
            (i for i, r in enumerate(rows) if _label(r) == "Vreme"), None
        )
        temp_idx = next(
            (i for i, r in enumerate(rows) if _label(r) == "Temperatura"),
            None,
        )
        if vreme_idx2 is not None and temp_idx is not None:
            vreme_row2 = rows[vreme_idx2]
            temp_row = rows[temp_idx]
            for ci in range(1, min(len(vreme_row2), len(temp_row))):
                t = temp_row[ci]
                if t.get("value"):
                    vreme_row2[ci]["temp"] = t["value"]
                if "tmin" in t:
                    vreme_row2[ci]["tmin"] = t["tmin"]
            for cell in vreme_row2:
                cell["vreme_combined"] = True
            rows.pop(temp_idx)

        # Merge Hitrost vetra speed into Veter row, then drop Hitrost vetra
        veter_idx = next(
            (i for i, r in enumerate(rows) if _label(r) == "Veter"), None
        )
        hitrost_idx = next(
            (
                i
                for i, r in enumerate(rows)
                if _label(r).startswith("Hitrost vetra")
            ),
            None,
        )
        if veter_idx is not None and hitrost_idx is not None:
            veter_row = rows[veter_idx]
            hitrost_row = rows[hitrost_idx]
            for ci in range(1, min(len(veter_row), len(hitrost_row))):
                speed_val = hitrost_row[ci].get("value", "")
                if speed_val:
                    veter_row[ci]["speed"] = speed_val
            for cell in veter_row:
                cell["wind"] = True
                cell["wind_combined"] = True
            rows.pop(hitrost_idx)

        # Shorten header cell text
        for row in rows:
            if not any(c["tag"] == "th" for c in row):
                continue
            first_val = row[0].get("value", "") if row else ""
            is_obeti = "Slovenija" in first_val
            for cell in row:
                val = cell["value"]
                if is_obeti:
                    val = val.replace("Slovenija / osrednja", "Slo. osrednja")
                else:
                    val = val.replace("Ljubljana in okolica", "Ljubljana")
                    val = val.replace("popoldne", "pop.").replace(
                        "zjutraj", "zjut."
                    )
                    for full, abbr in _DAY_ABBR.items():
                        val = val.replace(full, abbr)
                cell["value"] = val

        return rows

    def _fetch_icon(
        self, url: str, size: int = _ICON_SIZE, invert: bool = False
    ) -> Image.Image | None:
        key = (url, size, invert)
        if key in self._icon_cache:
            return self._icon_cache[key]
        try:
            logger.debug(f"GET {url}")
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                return None
            icon = Image.open(io.BytesIO(r.content)).convert("RGBA")
            icon = icon.resize((size, size), Image.Resampling.LANCZOS)
            if invert:
                icon = invert_icon_lightness(icon)
            self._icon_cache[key] = icon
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
                    if "speed" in cell:
                        needed = _text_w(font, cell["speed"]) + 2 * _PAD_H
                        col_widths[ci] = max(col_widths[ci], needed)
        return col_widths

    @staticmethod
    def _row_height(row: list[dict], line_h: int) -> int:
        if any(c["tag"] == "th" for c in row):
            return line_h
        if any(c.get("vreme_combined") for c in row):
            has_tmin = any("tmin" in c for c in row)
            return _ICON_SIZE + (2 * line_h if has_tmin else line_h + _PAD_V)
        if any(c.get("wind_combined") for c in row):
            return _WIND_ICON_SIZE + line_h + 2 * _PAD_V
        if any(c.get("wind") for c in row):
            return _WIND_ICON_SIZE + 2 * _PAD_V
        if any(c["type"] == "img" for c in row):
            return _ICON_SIZE + 2 * _PAD_V
        return line_h

    def _cell_bg(
        self, is_header: bool, is_label: bool, stripe: bool
    ) -> tuple[int, int, int]:
        if is_header:
            return self.p.HEADER_BG
        if is_label:
            return self.p.LABEL_BG
        if stripe:
            return self.p.CELL_BG_ALT
        return self.p.CELL_BG

    def _cell_fg(
        self, cell: dict, is_header: bool, is_label: bool
    ) -> tuple[int, int, int]:
        if is_header:
            return self.p.HEADER_FG
        if "table-marker-text0" in cell["cls"]:
            return self.p.TMAX_FG
        if "table-marker-text1" in cell["cls"]:
            return self.p.TMIN_FG
        if is_label:
            return self.p.LABEL_FG
        return self.p.CELL_FG

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
            icon_size = _WIND_ICON_SIZE if cell.get("wind") else _ICON_SIZE
            ix = x + (cw - icon_size) // 2
            top_align = cell.get("wind_combined") or cell.get("vreme_combined")
            iy = y + _PAD_V if top_align else y + (rh - icon_size) // 2
            is_wind = bool(cell.get("wind"))
            icon = self._fetch_icon(
                cell["value"], icon_size, invert=is_wind and self.dark_mode
            )
            if icon:
                img.paste(icon, (ix, iy), icon)
            if "overlay" in cell:
                overlay = self._fetch_icon(cell["overlay"], icon_size)
                if overlay:
                    img.paste(overlay, (ix, iy), overlay)
            if "temp" in cell:
                temp_val = cell["temp"]
                has_tmin = "tmin" in cell
                bb = font.getbbox(temp_val)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                ty = y + _PAD_V + icon_size + _PAD_V
                draw.text(
                    (x + (cw - tw) // 2 - bb[0], ty - bb[1]),
                    temp_val,
                    fill=self.p.TMAX_FG if has_tmin else self.p.CELL_FG,
                    font=font,
                )
                if has_tmin:
                    bb2 = font.getbbox(cell["tmin"])
                    tw2 = bb2[2] - bb2[0]
                    draw.text(
                        (
                            x + (cw - tw2) // 2 - bb2[0],
                            ty + th + _PAD_V - bb2[1],
                        ),
                        cell["tmin"],
                        fill=self.p.TMIN_FG,
                        font=font,
                    )
            if "speed" in cell:
                bb = font.getbbox(cell["speed"])
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                draw.text(
                    (
                        x + (cw - tw) // 2 - bb[0],
                        y + _PAD_V + icon_size + _PAD_V - bb[1],
                    ),
                    cell["speed"],
                    fill=self._cell_fg(cell, is_header, is_label),
                    font=font,
                )
        elif cell.get("speed"):
            # wind cell with no direction icon — draw speed at same vertical
            # position as speed text in icon cells
            bb = font.getbbox(cell["speed"])
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            draw.text(
                (
                    x + (cw - tw) // 2 - bb[0],
                    y + _PAD_V + _WIND_ICON_SIZE + _PAD_V - bb[1],
                ),
                cell["speed"],
                fill=self._cell_fg(cell, is_header, is_label),
                font=font,
            )
        elif "tmin" in cell:
            # Temperatura combined: tmax on top, tmin below
            tmax_val = cell["value"]
            tmin_val = cell["tmin"]
            bb = font.getbbox(tmax_val)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            draw.text(
                (x + (cw - tw) // 2 - bb[0], y + _PAD_V - bb[1]),
                tmax_val,
                fill=self.p.TMAX_FG,
                font=font,
            )
            bb2 = font.getbbox(tmin_val)
            tw2 = bb2[2] - bb2[0]
            draw.text(
                (
                    x + (cw - tw2) // 2 - bb2[0],
                    y + _PAD_V + th + _PAD_V - bb2[1],
                ),
                tmin_val,
                fill=self.p.TMIN_FG,
                font=font,
            )
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

        img = Image.new("RGB", (width, height), self.p.BG)
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
                    fill=self.p.ROW_DIVIDER,
                    width=_SCALE * 2,
                )
            y += rh

        img.save(out_path, "PNG")
