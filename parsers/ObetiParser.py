from datetime import datetime
from enum import Enum
from html.parser import HTMLParser

import utils.RegexUtils as ru


class OST(Enum):
    IDLE = 0
    HEADER1 = 1
    HEADER2 = 2
    PARAGRAPH = 3
    SOURCE = 5
    TIME_W = 6
    TIME = 7
    DONE = 999


class ObetiParser(HTMLParser):
    state = OST.IDLE

    header = "not parsed"
    title = "not parsed"
    body = ["not parsed", ]
    author = "not parsed"
    timestamp = datetime.strptime("2000-01-01 00:00", "%Y-%m-%d %H:%M")

    def __init__(self):
        super().__init__()

    def handle_starttag(self, tag, attrs):
        if self.state == OST.IDLE:
            match tag.lower():
                case "html":
                    self.title = ""
                    self.body = []
                    self.author = ""
                case "h1":
                    self.state = OST.HEADER1
                case "h2":
                    self.state = OST.HEADER2
                case "p":
                    self.state = OST.PARAGRAPH
                case "sup":
                    self.state = OST.SOURCE
        elif self.state == OST.TIME_W and tag.lower() == "sup":
            self.state = OST.TIME

    def handle_endtag(self, tag):
        match tag.lower():
            case "h1":
                if self.state == OST.HEADER1:
                    self.state = OST.IDLE
            case "h2":
                if self.state == OST.HEADER2:
                    self.state = OST.IDLE
            case "p":
                if self.state == OST.PARAGRAPH:
                    self.state = OST.IDLE
            case "sup":
                match self.state:
                    case OST.SOURCE:
                        self.state = OST.TIME_W
                    case OST.TIME:
                        self.state = OST.IDLE

    def handle_data(self, data):
        match self.state:
            case OST.HEADER1:
                self.header += data
            case OST.HEADER2:
                self.title += data
            case OST.PARAGRAPH:
                self.body.append(data)
            case OST.SOURCE:
                self.author += data
            case OST.TIME:
                self.timestamp = datetime.strptime(ru.strip_html(data), "%Y-%m-%d %H:%M")

    def get_obeti(self):
        return {
            "header": ru.strip_html(self.header),
            "title": ru.strip_html(self.title),
            "body": ru.strip_html(ru.array_to_lines(self.body)),
            "author": ru.strip_html(self.author),
            "timestamp": self.timestamp
        }
