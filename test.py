import datetime, sys

from colour import Color

from PIL import Image, ImageDraw

from utils.ColorUtils import ColorUtils, time_blend_color


async def test():
    print("hi")


def rgb_to_int(color):
    red = int(color[0] * 255)
    green = int(color[1] * 255)
    blue = int(color[2] * 255)
    return red, green, blue, 255


if __name__ == '__main__':
    cu = ColorUtils()

    curtime = datetime.datetime.now(cu.city.tzinfo).replace(hour=0, minute=0, second=0, microsecond=0)
    with Image.open("dev/gradient.png") as im:
        draw = ImageDraw.Draw(im)

        for i in range(0, im.size[0]):
            hour = int(i / im.size[0] * 24)
            minute = int((i / im.size[0] * 24) % 1 * 60)
            curtime = curtime.replace(hour=hour, minute=minute, second=0,
                                      microsecond=0)
            draw.line((i, im.size[1], i, 0), fill=rgb_to_int(cu.get_color_for_time(curtime).get_rgb()))

        im.show()
