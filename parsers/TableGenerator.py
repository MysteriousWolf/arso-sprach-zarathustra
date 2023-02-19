import os
import re

import requests
from html2image import Html2Image


class TableGenerator:
    tablematcher = re.compile("(<table(.|\n\r|\n|\r|\r\n)+table>)", re.MULTILINE)
    hti = None

    def __init__(self, folder, url, css):
        self.folder = folder
        self.url = url
        self.css = css
        self.hti = Html2Image(output_path=folder)

    def generate_napoved(self, file):
        return self.generate_table(file, f"{self.url}/fcast_SLOVENIA_MIDDLE_latest.html", self.css,
                                   [(370 + 16, 202 + 16)])

    def generate_shorthand(self, file):
        return self.generate_table(file, f"{self.url}/fcast_SI_OSREDNJESLOVENSKA_latest.html", self.css,
                                   [(470 + 16, 176 + 16)])

    def generate_table(self, file, html_url, css_url, crop=None):
        if crop is None:
            crop = []
        x = requests.get(css_url)
        csstxt = bytes(x.text, x.encoding).decode("utf-8", 'ignore')

        x = requests.get(html_url)
        htmltxt = bytes(x.text, x.encoding).decode("utf-8", 'ignore').replace('src="/',
                                                                              'src="https://meteo.arso.gov.si/')
        htmltable = re.search(self.tablematcher, htmltxt).group(1)

        return self.hti.screenshot(html_str=htmltable, css_str=csstxt, save_as=file, size=crop)[0]

        # return os.path.join(self.folder, file)
