import colorsys
import datetime
import io
import math
import time
from dataclasses import dataclass
from importlib import resources

import discord
from astral import LocationInfo
from astral.sun import sun
from colour import Color
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence

from utils.log import get_logger

RGB = tuple[int, int, int]


def _mix(base: RGB, factor: float) -> RGB:
    """Shift base toward white (+) or black (-). factor in (-1, 1)."""
    target = (255, 255, 255) if factor >= 0 else (0, 0, 0)
    f = abs(factor)
    return (
        round(base[0] + (target[0] - base[0]) * f),
        round(base[1] + (target[1] - base[1]) * f),
        round(base[2] + (target[2] - base[2]) * f),
    )


# ARSO brand colors
ARSO_PRIMARY: RGB = (0, 130, 188)  # #0082BC
ARSO_NEON: RGB = (0, 176, 255)  # #00B0FF


@dataclass(frozen=True)
class TablePalette:
    BG: RGB
    HEADER_BG: RGB
    HEADER_FG: RGB
    LABEL_BG: RGB
    LABEL_FG: RGB
    CELL_BG: RGB
    CELL_BG_ALT: RGB
    CELL_FG: RGB
    TMAX_FG: RGB
    TMIN_FG: RGB
    ROW_DIVIDER: RGB


LIGHT_PALETTE = TablePalette(
    BG=(255, 255, 255),
    HEADER_BG=ARSO_PRIMARY,
    HEADER_FG=(255, 255, 255),
    LABEL_BG=_mix(ARSO_PRIMARY, +0.88),  # very light ARSO tint
    LABEL_FG=_mix(ARSO_PRIMARY, -0.60),  # deep ARSO blue
    CELL_BG=(255, 255, 255),
    CELL_BG_ALT=_mix(ARSO_PRIMARY, +0.96),  # barely-there zebra stripe
    CELL_FG=_mix(ARSO_PRIMARY, -0.80),  # near-black body text
    TMAX_FG=(185, 80, 60),  # subtle warm terracotta
    TMIN_FG=(60, 100, 170),  # subtle cool slate
    ROW_DIVIDER=_mix(ARSO_PRIMARY, +0.73),  # soft ARSO blue border
)

DARK_PALETTE = TablePalette(
    BG=(25, 27, 30),  # deep dark background
    HEADER_BG=_mix(ARSO_PRIMARY, -0.35),  # darkened ARSO blue header
    HEADER_FG=(255, 255, 255),
    LABEL_BG=(35, 40, 48),  # blue-tinted dark surface for labels
    LABEL_FG=(140, 190, 230),  # light ARSO tint
    CELL_BG=(25, 27, 30),
    CELL_BG_ALT=(33, 36, 41),  # visible zebra stripe
    CELL_FG=(210, 215, 220),  # near-white body text
    TMAX_FG=(200, 105, 85),  # lighter warm for dark bg
    TMIN_FG=(110, 160, 225),  # lighter cool for dark bg
    ROW_DIVIDER=(60, 68, 82),  # clearly visible blue-tinted divider
)


# ---------------------------------------------------------------------------
# Image colour utilities
# ---------------------------------------------------------------------------


def invert_icon_lightness(icon: Image.Image) -> Image.Image:
    """Invert brightness while preserving hue and saturation (L → 1−L in HLS)."""
    r_ch, g_ch, b_ch, a_ch = icon.split()
    inv = ImageOps.invert(Image.merge("RGB", (r_ch, g_ch, b_ch)))
    pixels = list(inv.getdata())  # type: ignore[arg-type]
    out = []
    for r, g, b in pixels:
        h, li, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
        h = (h + 0.5) % 1.0
        nr, ng, nb = colorsys.hls_to_rgb(h, li, s)
        out.append((round(nr * 255), round(ng * 255), round(nb * 255)))
    rgb_out = Image.new("RGB", inv.size)
    rgb_out.putdata(out)  # type: ignore[arg-type]
    return Image.merge("RGBA", (*rgb_out.split(), a_ch))


# ---------------------------------------------------------------------------
# Radar GIF dark-mode recolouring
# ---------------------------------------------------------------------------

_RADAR_WHITE: RGB = (255, 255, 255)
_RADAR_GREY: RGB = (186, 186, 186)  # #BABABA — scan-border grey

_gif_logger = get_logger("gif_recolor")


def _gif_remap(palette: TablePalette) -> dict[RGB, RGB]:
    return {_RADAR_WHITE: palette.BG, _RADAR_GREY: palette.HEADER_BG}


def _apply_color_table_remap(
    buf: bytearray, start: int, count: int, remap: dict[RGB, RGB]
) -> None:
    """Rewrite count RGB palette entries in-place; invert lightness of unmapped entries."""
    for i in range(count):
        off = start + i * 3
        rgb = (buf[off], buf[off + 1], buf[off + 2])
        if rgb in remap:
            buf[off], buf[off + 1], buf[off + 2] = remap[rgb]
        else:
            h, li, s = colorsys.rgb_to_hls(
                rgb[0] / 255, rgb[1] / 255, rgb[2] / 255
            )
            r, g, b = (
                round(v * 255) for v in colorsys.hls_to_rgb(h, 1 - li, s)
            )
            buf[off], buf[off + 1], buf[off + 2] = r, g, b


def recolor_radar_gif(data: bytes, palette: TablePalette) -> io.BytesIO:
    """Rewrite every GIF colour table for dark mode; pixel indices untouched."""
    t_start = time.monotonic()
    buf = bytearray(data)
    remap = _gif_remap(palette)

    packed = buf[10]
    has_gct = bool(packed & 0x80)
    gct_count = 2 ** ((packed & 0x07) + 1)
    pos = 13

    if has_gct:
        _apply_color_table_remap(buf, pos, gct_count, remap)
        pos += gct_count * 3

    n_frames = n_lct = 0
    while pos < len(buf):
        b = buf[pos]
        if b == 0x3B:
            break
        elif b == 0x21:
            pos += 2
            while pos < len(buf):
                sz = buf[pos]
                pos += 1
                if sz == 0:
                    break
                pos += sz
        elif b == 0x2C:
            n_frames += 1
            img_packed = buf[pos + 9]
            has_lct = bool(img_packed & 0x80)
            lct_count = 2 ** ((img_packed & 0x07) + 1)
            pos += 10
            if has_lct:
                n_lct += 1
                _apply_color_table_remap(buf, pos, lct_count, remap)
                pos += lct_count * 3
            pos += 1
            while pos < len(buf):
                sz = buf[pos]
                pos += 1
                if sz == 0:
                    break
                pos += sz
        else:
            break

    elapsed = (time.monotonic() - t_start) * 1000
    _gif_logger.info(
        f"recolor_radar_gif: {n_frames} frames, GCT={'yes' if has_gct else 'no'}, "
        f"LCTs={n_lct}, {elapsed:.2f}ms"
    )
    return io.BytesIO(bytes(buf))


# GIF geographic bounds: NW corner (lat_max, lng_min), SE corner (lat_min, lng_max)
_GIF_LAT_MAX = 47.6
_GIF_LNG_MIN = 12.1
_GIF_LAT_MIN = 44.65
_GIF_LNG_MAX = 17.45

_CROSS_COLOR_LIGHT = (210, 20, 20, 255)
_CROSS_COLOR_DARK = (255, 70, 70, 255)
_CROSS_ARM = 4
_CROSS_WIDTH = 2  # number of 1px passes per diagonal, offset by 1px each, for symmetric thickness

# Easter egg — purely a joke, not meant to offend or imply any territorial claim.
_TRIESTE_TEXT = "TRST JE NAŠ!"
_TRIESTE_FONT_NAME = "NotoSans-Variable.ttf"
_TRIESTE_FONT_SIZE = 80


def _load_trieste_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Resolve the font as a packaged resource, not a source-tree-relative
    # path: when installed (uv/pip wheel) the source layout is gone, but the
    # ttf ships as package-data under the `assets` namespace package.
    try:
        data = (
            resources.files("assets").joinpath(_TRIESTE_FONT_NAME).read_bytes()
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return ImageFont.load_default()
    font = ImageFont.truetype(io.BytesIO(data), _TRIESTE_FONT_SIZE)
    font.set_variation_by_axes([900, 100])  # Black weight, normal width
    return font


def draw_cross_on_gif(
    data: bytes,
    lat: float,
    lng: float,
    trieste_fallback: bool = False,
    dark_mode: bool = False,
) -> bytes:
    """Overlay a red X at (lat, lng) on every frame of the animated GIF."""
    color = _CROSS_COLOR_DARK if dark_mode else _CROSS_COLOR_LIGHT
    src = Image.open(io.BytesIO(data))
    w, h = src.size

    px = round((lng - _GIF_LNG_MIN) / (_GIF_LNG_MAX - _GIF_LNG_MIN) * w)
    py = round((_GIF_LAT_MAX - lat) / (_GIF_LAT_MAX - _GIF_LAT_MIN) * h)
    px = max(_CROSS_ARM, min(w - _CROSS_ARM - 1, px))
    py = max(_CROSS_ARM, min(h - _CROSS_ARM - 1, py))

    font = _load_trieste_font() if trieste_fallback else None

    durations: list[int] = []
    frames: list[Image.Image] = []
    for frame in ImageSequence.Iterator(src):
        durations.append(frame.info.get("duration", 100))
        f = frame.convert("RGBA")
        draw = ImageDraw.Draw(f)
        for dx in range(_CROSS_WIDTH):
            draw.line(
                [
                    px - _CROSS_ARM + dx,
                    py - _CROSS_ARM,
                    px + _CROSS_ARM + dx,
                    py + _CROSS_ARM,
                ],
                fill=color,
                width=1,
            )
            draw.line(
                [
                    px - _CROSS_ARM + dx,
                    py + _CROSS_ARM,
                    px + _CROSS_ARM + dx,
                    py - _CROSS_ARM,
                ],
                fill=color,
                width=1,
            )
        if trieste_fallback and font is not None:
            draw.text(
                (w // 2, h // 2),
                _TRIESTE_TEXT,
                fill=color,
                font=font,
                anchor="mm",
            )
        frames.append(f.quantize(method=Image.Quantize.FASTOCTREE))

    out = io.BytesIO()
    frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=durations,
        optimize=False,
    )
    return out.getvalue()


class ColorUtils:
    dawn_c = Color("#718EC4")
    sunrise_c = Color("#FF6700")
    noon_c = Color(  # type: ignore[arg-type]
        rgb=tuple(v / 255 for v in ARSO_PRIMARY)
    )
    sunset_c = Color("#FFB301")
    dusk_c = Color("#6A6492")
    midnight_c = Color("#10112B")

    def __init__(self):
        self.city: LocationInfo
        self.s: dict[str, datetime.datetime]
        self.day_start: datetime.datetime
        self.midnight: datetime.datetime
        self.refresh_sun_data()

    def refresh_sun_data(self):
        self.city = LocationInfo(
            "Ljubljana", "Slovenia", "Europe/Ljubljana", 46.0658, 14.5172
        )
        self.s = sun(self.city.observer, date=datetime.date.today())
        self.day_start = datetime.datetime.now(self.city.tzinfo).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self.midnight = datetime.datetime.now(self.city.tzinfo).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

    def get_color_for_time(self, time):
        self.refresh_sun_data()
        if time < self.s["dawn"]:
            color = time_blend_color(
                self.midnight_c,
                self.dawn_c,
                self.day_start,
                self.s["dawn"],
                time,
                iexp,
            )
        elif time < self.s["sunrise"]:
            color = time_blend_color(
                self.dawn_c,
                self.sunrise_c,
                self.s["dawn"],
                self.s["sunrise"],
                time,
                linear,
            )
        elif time < self.s["noon"]:
            color = time_blend_color(
                self.sunrise_c,
                self.noon_c,
                self.s["sunrise"],
                self.s["noon"],
                time,
                exp,
            )
        elif time < self.s["sunset"]:
            color = time_blend_color(
                self.noon_c,
                self.sunset_c,
                self.s["noon"],
                self.s["sunset"],
                time,
                iexp,
            )
        elif time < self.s["dusk"]:
            color = time_blend_color(
                self.sunset_c,
                self.dusk_c,
                self.s["sunset"],
                self.s["dusk"],
                time,
                linear,
            )
        elif time < self.midnight:
            color = time_blend_color(
                self.dusk_c,
                self.midnight_c,
                self.s["dusk"],
                self.midnight,
                time,
                exp,
            )
        else:
            color = self.midnight_c
        return color

    def get_current_color(self):
        time = datetime.datetime.now(self.city.tzinfo)
        return self.get_color_for_time(time)


def time_blend_color(color0, color1, time0, time1, now, interpolation_func):
    """time1 > now > time0"""
    tdts = time1 - time0
    tt0ts = now - time0
    td = float(tdts.total_seconds())
    tt0 = float(tt0ts.total_seconds())
    coef0 = 1.0 - (tt0 / td)
    return blend_color(color0, color1, coef0, interpolation_func)


def blend_color(color0, color1, coef, func):
    k = func(coef)
    coef0 = k
    coef1 = 1 - k

    red = color0.get_red() * coef0 + color1.get_red() * coef1
    green = color0.get_green() * coef0 + color1.get_green() * coef1
    blue = color0.get_blue() * coef0 + color1.get_blue() * coef1

    return Color(rgb=(red, green, blue))


def linear(x):
    return x


def iexp(x, tau=0.2):
    return 1 - math.exp(-x / tau)


def exp(x, tau=0.2):
    return math.exp((x - 1) / tau)


def color_to_discord(c):
    return discord.Color.from_rgb(
        round(c.get_red() * 255),
        round(c.get_green() * 255),
        round(c.get_blue() * 255),
    )
