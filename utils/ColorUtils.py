import datetime
import math

import discord
from astral import LocationInfo
from astral.sun import sun
from colour import Color

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

# Table palette — all derived from ARSO_PRIMARY so changing it
# propagates everywhere
TABLE_BG: RGB = (255, 255, 255)
TABLE_HEADER_BG: RGB = ARSO_PRIMARY
TABLE_HEADER_FG: RGB = (255, 255, 255)
TABLE_LABEL_BG: RGB = _mix(ARSO_PRIMARY, +0.88)  # very light ARSO tint
TABLE_LABEL_FG: RGB = _mix(ARSO_PRIMARY, -0.60)  # deep ARSO blue
TABLE_CELL_BG: RGB = (255, 255, 255)
TABLE_CELL_BG_ALT: RGB = _mix(ARSO_PRIMARY, +0.96)  # barely-there zebra stripe
TABLE_CELL_FG: RGB = _mix(ARSO_PRIMARY, -0.80)  # near-black body text
TABLE_TMAX_FG: RGB = (220, 38, 38)  # temperature red — intentionally fixed
TABLE_TMIN_FG: RGB = (37, 99, 235)  # temperature blue — intentionally fixed
TABLE_ROW_DIVIDER: RGB = _mix(ARSO_PRIMARY, +0.73)  # soft ARSO blue border


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
