import re
import requests


class ARSO:
    def __init__(self, url='https://meteo.arso.gov.si/uploads/probase/www/fproduct/text/sl'):
        self.url = url
        self.ar = ARSORegex()

    def get_forecast(self):
        x = requests.get(f"{self.url}/fcast_SLOVENIA_d1-d2_text.html")
        reencoded = bytes(x.text, x.encoding).decode("utf-8", 'ignore')
        if x.status_code == 200:
            forc = self.ar.strip_forecast(reencoded)
            return forc
        return {
            "title": "Napaka!",
            "body": f"Prišlo je do napake {x.status_code}",
            "author": "you dummy",
            "timestamp": "like right now"
        }


class ARSORegex:
    newlinepat = re.compile('((\n\r|\n|\r|\r\n)(\n\r|\n|\r|\r\n))+')

    htmlpat = re.compile('<.*?>')
    htmlpar = '<p>(.*)</p>'

    htmlh1 = re.compile('<h1>((.|\n\r|\n|\r|\r\n)*?)</h1>', re.MULTILINE)
    htmlh2 = re.compile('<h2>((.|\n\r|\n|\r|\r\n)*?)</h2>', re.MULTILINE)
    htmlsup = re.compile('<sup>((.|\n\r|\n|\r|\r\n)*?)</sup>', re.MULTILINE)

    forecastPattern = re.compile('</h2>((.|\n\r|\n|\r|\r\n)*?)<sup>', re.MULTILINE)

    def strip_html(self, txt):
        stripped = re.sub(self.htmlpat, "", txt)
        shortened = re.sub(self.newlinepat, "", stripped)
        return shortened.strip()

    def strip_forecast(self, html):
        title = re.search(self.htmlh2, html).group(1)
        cuthtml = re.search(self.forecastPattern, html).group(1)
        sups = re.findall(self.htmlsup, html)

        return {
            "title": self.strip_html(title),
            "body": self.strip_html(cuthtml),
            "author": self.strip_html(sups[0][0]),
            "timestamp": self.strip_html(sups[1][0])
        }
