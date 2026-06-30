import io
import time
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter, Retry

from parsers.ObetiParser import ObetiParser
from parsers.TableGenerator import TableGenerator
from utils.ColorUtils import recolor_radar_gif
from utils.log import get_logger

logger = get_logger("arso")

_BASE_URL = "https://meteo.arso.gov.si/uploads/probase/www/fproduct/text/sl"
_RADAR_GIF_URL = "https://meteo.arso.gov.si/uploads/probase/www/observ/radar/si0-rm-anim.gif"
HOME_URL = "https://meteo.arso.gov.si/"
RADAR_AUTHOR_URL = "https://meteo.arso.gov.si/met/sl/weather/observ/radar/"
THUMBNAIL_URL = "https://pbs.twimg.com/profile_images/798099496139915264/cSjEl4nm_400x400.jpg"


class ARSO:
    def __init__(self, tempdir, url=_BASE_URL, dark_mode: bool = True):
        self.tempdir = tempdir
        self.url = url
        self.dark_mode = dark_mode
        self.op = ObetiParser()
        self.tg = TableGenerator(tempdir, url, dark_mode=dark_mode)

        self.s = requests.Session()
        retries = Retry(
            total=5, backoff_factor=1, status_forcelist=[404, 502, 503, 504]
        )
        self.s.mount("https://", HTTPAdapter(max_retries=retries))

    def parse_txt_url(self, url, paragraphs=-1):
        logger.debug(f"GET {url}")
        t0 = time.monotonic()
        x = self.s.get(url)
        elapsed = time.monotonic() - t0
        if x.status_code != 200:
            logger.warning(
                f"HTTP {x.status_code} fetching {url} ({elapsed:.2f}s)"
            )
            return {
                "header": "Napaka!",
                "title": "Napaka!",
                "body": f"Prišlo je do napake {x.status_code}",
                "author": "you dummy",
                "timestamp": datetime.now(),
            }
        logger.debug(f"HTTP {x.status_code} {url} ({elapsed:.2f}s)")
        reencoded = bytes(x.text, x.encoding or "utf-8").decode(
            "utf-8", "ignore"
        )
        self.op.feed(reencoded)
        return self.op.parse_arso_txt(paragraphs)

    def get_forecast(self, paragraphs=-1):
        return self.parse_txt_url(
            f"{self.url}/fcast_SLOVENIA_d1-d2_text.html", paragraphs
        )

    def get_obeti(self):
        return self.parse_txt_url(f"{self.url}/fcast_SLOVENIA_d3-d5_text.html")

    def get_3day_table(self):
        return self.tg.generate_napoved("napoved_tabela.png")

    def get_morn_even_table(self):
        return self.tg.generate_shorthand("morn_tabela.png")

    def get_percipitation_gif(self) -> io.BytesIO:
        url = _RADAR_GIF_URL
        logger.debug(f"GET {url}")
        t0 = time.monotonic()
        res = self.s.get(url)
        elapsed = time.monotonic() - t0
        if res.status_code != 200:
            logger.error(f"HTTP {res.status_code} {url} ({elapsed:.2f}s)")
            raise RuntimeError(f"Prišlo je do napake {res.status_code}")
        logger.debug(f"HTTP {res.status_code} {url} ({elapsed:.2f}s)")
        if not self.dark_mode:
            return io.BytesIO(res.content)
        return recolor_radar_gif(res.content, self.tg.p)
