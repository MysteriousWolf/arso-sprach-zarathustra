from datetime import datetime

import requests

from parsers.ObetiParser import ObetiParser
from parsers.TableGenerator import TableGenerator


class ARSO:
    css = "https://meteo.arso.gov.si/uploads/meteo/style/css/webmet.css"

    def __init__(self, tempdir, url='https://meteo.arso.gov.si/uploads/probase/www/fproduct/text/sl'):
        self.tempdir = tempdir
        self.url = url
        self.op = ObetiParser()
        self.tg = TableGenerator(tempdir, url, self.css)

    def parse_txt_url(self, url):
        x = requests.get(url)
        reencoded = bytes(x.text, x.encoding).decode("utf-8", 'ignore')
        if x.status_code == 200:
            self.op.feed(reencoded)
            return self.op.get_obeti()
        return {
            "header": "Napaka!",
            "title": "Napaka!",
            "body": f"Prišlo je do napake {x.status_code}",
            "author": "you dummy",
            "timestamp": datetime.now()
        }

    def get_forecast(self):
        return self.parse_txt_url(f"{self.url}/fcast_SLOVENIA_d1-d2_text.html")

    def get_obeti(self):
        return self.parse_txt_url(f"{self.url}/fcast_SLOVENIA_d3-d5_text.html")

    def get_3day_table(self):
        return self.tg.generate_napoved("napoved_tabela.png")

    def get_morn_even_table(self):
        return self.tg.generate_shorthand("morn_tabela.png")
