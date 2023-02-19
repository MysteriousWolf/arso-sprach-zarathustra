import datetime

import discord
from astral import LocationInfo
from astral.sun import sun

from colour import Color


class ColorUtils:
    dawn_c = Color("#718EC4")
    sunrise_c = Color("#FF6700")
    noon_c = Color("#0082BC")  # ARSO color
    sunset_c = Color("#FFB301")
    dusk_c = Color("#10112B")

    def __init__(self):
        self.city = LocationInfo("Ljubljana", "Slovenia", "Europe/Ljubljana", 46.0658, 14.5172)
        self.s = sun(self.city.observer, date=datetime.date.today())

    def get_current_color(self):
        time = datetime.datetime.now(self.city.tzinfo)
        if time < self.s["dawn"]:
            color = blend_color(self.dusk_c, self.dawn_c, self.s["dusk"], self.s["dawn"], time)
        elif time < self.s["sunrise"]:
            color = blend_color(self.dawn_c, self.sunrise_c, self.s["dawn"], self.s["sunrise"], time)
        elif time < self.s["noon"]:
            color = blend_color(self.sunrise_c, self.noon_c, self.s["sunrise"], self.s["noon"], time)
        elif time < self.s["sunset"]:
            color = blend_color(self.noon_c, self.sunset_c, self.s["noon"], self.s["sunset"], time)
        elif time < self.s["dusk"]:
            color = blend_color(self.sunset_c, self.dusk_c, self.s["sunset"], self.s["dusk"], time)
        else:
            color = self.noon_c
        return color


def blend_color(color0, color1, time0, time1, now):
    """time1 > now > time0"""
    tdts = time1 - time0
    tt0ts = now - time0
    tt1ts = time1 - now
    td = float(tdts.total_seconds())
    tt0 = float(tt0ts.total_seconds())
    tt1 = float(tt1ts.total_seconds())
    coef0 = 1.0 - (tt0 / td)
    coef1 = 1.0 - (tt1 / td)
    red = color0.get_red() * coef0 + color1.get_red() * coef1
    green = color0.get_green() * coef0 + color1.get_green() * coef1
    blue = color0.get_blue() * coef0 + color1.get_blue() * coef1
    return Color(rgb=(red, green, blue))


def color_to_discord(c):
    return discord.Color.from_rgb(round(c.get_red() * 255), round(c.get_green() * 255), round(c.get_blue() * 255))
