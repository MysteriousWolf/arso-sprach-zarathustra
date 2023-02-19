import asyncio
import datetime
import zoneinfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from colour import Color

from utils.ColorUtils import ColorUtils, blend_color


async def test():
    print("hi")


if __name__ == '__main__':
    cu = ColorUtils()

    c0 = Color(rgb=(1, 1, 1))
    c1 = Color(rgb=(1, 0, 0))
    start = datetime.datetime.fromtimestamp(1000)
    stop = datetime.datetime.fromtimestamp(2000)
    time = datetime.datetime.fromtimestamp(1900)

    print(blend_color(c0, c1, start, stop, time))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(test, 'interval', seconds=1)
    scheduler.start()

    asyncio.get_event_loop().run_forever()
