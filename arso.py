from datetime import datetime

import requests
import io

from requests.adapters import HTTPAdapter, Retry

from parsers.ObetiParser import ObetiParser
from parsers.TableGenerator import TableGenerator


class ARSO:
    css = "https://meteo.arso.gov.si/uploads/meteo/style/css/webmet.css"

    def __init__(self, tempdir, url='https://meteo.arso.gov.si/uploads/probase/www/fproduct/text/sl'):
        self.tempdir = tempdir
        self.url = url
        self.op = ObetiParser()
        self.tg = TableGenerator(tempdir, url, self.css)

        self.s = requests.Session()
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[404, 502, 503, 504])
        self.s.mount('https://', HTTPAdapter(max_retries=retries))

    def parse_txt_url(self, url, paragraphs=-1):
        x = self.s.get(url)
        reencoded = bytes(x.text, x.encoding).decode("utf-8", 'ignore')
        if x.status_code == 200:
            self.op.feed(reencoded)
            return self.op.parse_arso_txt(paragraphs)
        return {
            "header": "Napaka!",
            "title": "Napaka!",
            "body": f"Prišlo je do napake {x.status_code}",
            "author": "you dummy",
            "timestamp": datetime.now()
        }

    def get_forecast(self, paragraphs=-1):
        return self.parse_txt_url(f"{self.url}/fcast_SLOVENIA_d1-d2_text.html", paragraphs)

    def get_obeti(self):
        return self.parse_txt_url(f"{self.url}/fcast_SLOVENIA_d3-d5_text.html")

    def get_3day_table(self):
        return self.tg.generate_napoved("napoved_tabela.png")

    def get_morn_even_table(self):
        return self.tg.generate_shorthand("morn_tabela.png")
        
    def get_percipitation_gif(self):
        res = self.s.get("https://meteo.arso.gov.si/uploads/probase/www/observ/radar/si0-rm-anim.gif")
        if res.status_code == 200:
            image_data = io.BytesIO(res.content)
            return image_data
        return {
            "header": "Napaka!",
            "title": "Napaka!",
            "body": f"Prišlo je do napake {res.status_code}",
            "author": "you dummy",
            "timestamp": datetime.now()
        }
        return 
