import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

import pyfiglet

_REPO = "https://github.com/MysteriousWolf/arso-sprach-zarathustra"
_AUTHOR_URL = "https://github.com/MysteriousWolf"

with open(Path(__file__).parent / "pyproject.toml", "rb") as _f:
    BOT_VERSION: str = tomllib.load(_f)["project"]["version"]

try:
    GIT_COMMIT: str | None = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).parent,
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()
except Exception:
    GIT_COMMIT = None

_BLUE = "\033[38;2;0;130;188m"
_YELLOW = "\033[93m"
_FADED = "\033[2;3m"
_RESET = "\033[0m"
_HIDE = "\033[?25l"
_SHOW = "\033[?25h"

# (char, ansi_color, hyperlink_url)
Cell = tuple[str, str, str]


def _span(text: str, color: str = "", url: str = "") -> list[Cell]:
    return [(ch, color, url) for ch in text]


def _figlet(text: str) -> list[str]:
    lines = pyfiglet.figlet_format(text, font="straight").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _lightning(n: int = 2) -> list[str]:
    """Canonical codegolf lightning bolt — 3n+2 lines total.
    codegolf.stackexchange.com/q/51284
    """
    rows = ["__", "\\ \\", " \\ \\"]
    for _ in range(n - 1):
        rows += ["__\\ \\", "\\  __\\", " \\ \\"]
    rows += ["  \\ \\", "   \\/"]
    return rows


def _version_suffix(short_commit: str | None, start_str: str) -> list[Cell]:
    parts = _span("  ") + _span(f"v{BOT_VERSION}", "", _REPO)
    if short_commit:
        commit_url = f"{_REPO}/commit/{GIT_COMMIT}"
        parts += _span(" (") + _span(short_commit, "", commit_url) + _span(")")
    parts += _span(f"     {start_str}")
    return parts


def _draw(styled: list[list[Cell]], glint: int | None = None) -> None:
    current_color = ""
    current_url = ""
    for row, line in enumerate(styled):
        for col, (ch, color, url) in enumerate(line):
            if url != current_url:
                sys.stdout.write(f"\033]8;;{url}\033\\" if url else "\033]8;;\033\\")
                current_url = url
            if glint is not None:
                dist = abs((col - row) - glint)
                if dist == 0:
                    cell_color = "\033[1;97m"
                elif dist <= 2:
                    cell_color = "\033[1m" + color
                else:
                    cell_color = color
            else:
                cell_color = color
            if cell_color != current_color:
                sys.stdout.write(_RESET + cell_color)
                current_color = cell_color
            sys.stdout.write(ch)
        if current_url:
            sys.stdout.write("\033]8;;\033\\")
            current_url = ""
        sys.stdout.write("\n")


def print_banner() -> None:
    short_commit = GIT_COMMIT[:7] if GIT_COMMIT else None
    start_str = datetime.now().strftime("%b %d, %Y  %H:%M")

    arso_lines = _figlet("ARSO")
    rest_lines = _figlet("Sprach Zarathustra")

    arso_width = max(len(line) for line in arso_lines)
    while len(arso_lines) < len(rest_lines):
        arso_lines.append("")
    arso_padded = [line.ljust(arso_width) for line in arso_lines]

    bolt_rows = _lightning()
    bolt_width = max(len(row) for row in bolt_rows) + 1
    bolt_padded = [row.ljust(bolt_width) for row in bolt_rows]
    n_bolt = len(bolt_padded)

    _margin = "    "
    n_text = len(rest_lines)
    n_pad_top = max(0, (n_bolt - 3 - n_text) // 2)

    text_area_width = max(
        len(arso_padded[fi]) + len(rest_lines[fi].rstrip())
        + (len(f"  v{BOT_VERSION}") + (len(f" ({short_commit})") if short_commit else 0) + len(f"     {start_str}") if fi == n_text - 1 else 0)
        for fi in range(n_text)
    )

    styled: list[list[Cell]] = []
    for i in range(n_bolt - 3):
        fi = i - n_pad_top
        if 0 <= fi < n_text:
            row_cells: list[Cell] = (
                _span(arso_padded[fi], _BLUE)
                + _span(rest_lines[fi].rstrip())
                + (_version_suffix(short_commit, start_str) if fi == n_text - 1 else [])
            )
        else:
            row_cells = []
        styled.append(_span(_margin) + _span(bolt_padded[i], _YELLOW) + _span(_margin) + row_cells)

    # Row n_bolt-3: description centered
    desc = "Unofficial ARSO Discord weather bot"
    desc_pad = max(0, (text_area_width - len(desc)) // 2)
    styled.append(
        _span(_margin) + _span(bolt_padded[n_bolt - 3], _YELLOW) + _span(_margin)
        + _span(" " * desc_pad + desc)
    )

    # Row n_bolt-2: blank separator
    styled.append(_span(_margin) + _span(bolt_padded[n_bolt - 2], _YELLOW))

    # Row n_bolt-1: credits right-aligned on the tip row
    credits = "by MysteriousWolf"
    credits_pad = text_area_width - len(credits) - len(_margin)
    styled.append(
        _span(_margin) + _span(bolt_padded[n_bolt - 1], _YELLOW) + _span(_margin)
        + _span(" " * credits_pad)
        + _span("by ", _FADED)
        + _span("MysteriousWolf", _FADED, _AUTHOR_URL)
    )

    n = len(styled)
    max_col = max(len(line) for line in styled)

    time.sleep(0.3)
    sys.stdout.write(_HIDE + "\n" * n + f"\033[{n}A")
    _draw(styled)
    sys.stdout.flush()

    for g in range(-2, max_col + n, 3):
        sys.stdout.write(f"\033[{n}A")
        _draw(styled, glint=g)
        sys.stdout.flush()
        time.sleep(0.018)

    sys.stdout.write(f"\033[{n}A")
    _draw(styled)
    sys.stdout.write(_RESET + _SHOW + "\n")
    sys.stdout.flush()
