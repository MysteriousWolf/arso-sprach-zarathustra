import re

newlinepat = re.compile('((\n\r|\n|\r|\r\n)(\n\r|\n|\r|\r\n))+')

htmlpat = re.compile('<.*?>')
htmlpar = '<p>(.*)</p>'


def strip_html(txt):
    stripped = re.sub(htmlpat, "", txt)
    # shortened = re.sub(self.newlinepat, "", stripped)
    return stripped.strip()


def array_to_lines(arr):
    return "\n".join(arr)
