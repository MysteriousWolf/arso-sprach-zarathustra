import re

import requests
from html2image import Html2Image

from utils.log import get_logger

logger = get_logger("table_generator")


class TableGenerator:
    tablematcher = re.compile("(<table(.|\n\r|\n|\r|\r\n)+table>)", re.MULTILINE)

    def __init__(self, folder, url, css):
        self.folder = folder
        self.url = url
        self.css = css
        self.hti = Html2Image(output_path=folder, browser_executable="chromium-headless-shell")

    def generate_napoved(self, file):
        return self.generate_table(
            file, f"{self.url}/fcast_SLOVENIA_MIDDLE_latest.html", self.css, [(370 + 16, 202 + 16)]
        )

    def generate_shorthand(self, file):
        return self.generate_table(
            file,
            f"{self.url}/fcast_SI_OSREDNJESLOVENSKA_latest.html",
            self.css,
            [(470 + 16, 176 + 16)],
        )

    def generate_table(self, file, html_url, css_url, crop=None):
        if crop is None:
            crop = []
        logger.debug(f"GET {css_url}")
        x = requests.get(css_url)
        if x.status_code != 200:
            logger.warning(f"HTTP {x.status_code} fetching CSS {css_url}")
        csstxt = bytes(x.text, x.encoding or "utf-8").decode("utf-8", "ignore")

        logger.debug(f"GET {html_url}")
        x = requests.get(html_url)
        if x.status_code != 200:
            logger.warning(f"HTTP {x.status_code} fetching HTML {html_url}")
        htmltxt = (
            bytes(x.text, x.encoding or "utf-8")
            .decode("utf-8", "ignore")
            .replace('src="/', 'src="https://meteo.arso.gov.si/')
        )
        match = re.search(self.tablematcher, htmltxt)
        assert match is not None, f"No table found in {html_url}"
        htmltable = match.group(1)

        logger.debug(f"rendering screenshot → {file}")
        result = self.hti.screenshot(html_str=htmltable, css_str=csstxt, save_as=file, size=crop)[0]
        logger.debug(f"screenshot saved: {result}")
        return result
