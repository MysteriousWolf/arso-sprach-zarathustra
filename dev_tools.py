#!/usr/bin/env python3
"""Dev helpers — output goes to dev/ (gitignored)."""

import shutil
import sys
import tempfile
from pathlib import Path

DEV = Path(__file__).parent / "dev"
DEV.mkdir(exist_ok=True)


def gradient() -> None:
    import datetime

    from PIL import Image, ImageDraw

    from utils.ColorUtils import ColorUtils

    cu = ColorUtils()
    W, H = 720, 60
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    tz = cu.city.tzinfo
    base = datetime.datetime.now(tz).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    for x in range(W):
        t = base + datetime.timedelta(minutes=x * 2)  # 2 min/px = 24 h
        c = cu.get_color_for_time(t)
        r, g, b = (
            round(c.get_red() * 255),
            round(c.get_green() * 255),
            round(c.get_blue() * 255),
        )
        draw.line([(x, 0), (x, H - 1)], fill=(r, g, b))
    out = DEV / "gradient.png"
    img.save(out)
    print(f"saved {out}")


def obeti() -> None:
    from arso import ARSO

    tmp = tempfile.mkdtemp()
    arso = ARSO(tmp)
    f = arso.get_3day_table()
    out = DEV / "obeti.png"
    shutil.copy(f, out)
    print(f"saved {out}")


def vreme() -> None:
    from arso import ARSO

    tmp = tempfile.mkdtemp()
    arso = ARSO(tmp)
    f = arso.get_morn_even_table()
    out = DEV / "vreme.png"
    shutil.copy(f, out)
    print(f"saved {out}")


_CMDS = {"gradient": gradient, "obeti": obeti, "vreme": vreme}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in _CMDS:
        print(f"usage: dev_tools.py [{' | '.join(_CMDS)}]")
        sys.exit(1)
    _CMDS[cmd]()
