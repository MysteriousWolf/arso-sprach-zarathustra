#!/usr/bin/env python3
"""Generate assets/banner.svg. Run: uv run dev/gen_banner_svg.py"""

from pathlib import Path
import sys
import xml.sax.saxutils as esc

sys.path.insert(0, str(Path(__file__).parent.parent))

from banner import _BLUE, _FADED, _YELLOW, _figlet, _lightning, _span  # noqa: E402

BG = "#0d1117"
FG = "#e6edf3"
DIM = "#7d8590"
COLORS = {_BLUE: "#0082bc", _YELLOW: "#ffd700", _FADED: DIM, "": FG}

FONT_SIZE = 14
CHAR_W = 8.41
LINE_H = 20
PAD_X, PAD_Y = 14, 8


def _tspan(text: str, color: str) -> str:
    fill = COLORS.get(color, FG)
    return f'<tspan fill="{fill}">{esc.escape(text)}</tspan>'


def _svg_line(cells: list[tuple[str, str, str]], y: float) -> str:
    spans, cur_color, buf = [], None, ""
    for ch, color, _ in cells:
        if color != cur_color:
            if buf:
                spans.append(_tspan(buf, cur_color or ""))
            cur_color, buf = color, ch
        else:
            buf += ch
    if buf:
        spans.append(_tspan(buf, cur_color or ""))
    return f'<text x="{PAD_X}" y="{y}" xml:space="preserve">{"".join(spans)}</text>'


def main() -> None:
    arso_lines = _figlet("ARSO")
    rest_lines = _figlet("Sprach Zarathustra")

    arso_width = max(len(l) for l in arso_lines)
    while len(arso_lines) < len(rest_lines):
        arso_lines.append("")
    arso_padded = [l.ljust(arso_width) for l in arso_lines]

    bolt_rows = _lightning()
    bolt_w = max(len(r) for r in bolt_rows) + 1
    bolt_padded = [r.ljust(bolt_w) for r in bolt_rows]
    n_bolt = len(bolt_padded)

    mg = "    "
    n_text = len(rest_lines)
    n_pad_top = max(0, (n_bolt - 3 - n_text) // 2)
    text_w = max(len(arso_padded[fi]) + len(rest_lines[fi].rstrip()) for fi in range(n_text))

    svg_lines: list[list[tuple[str, str, str]]] = []

    for i in range(n_bolt - 3):
        fi = i - n_pad_top
        body = (
            _span(arso_padded[fi], _BLUE) + _span(rest_lines[fi].rstrip())
            if 0 <= fi < n_text else []
        )
        svg_lines.append(_span(mg) + _span(bolt_padded[i], _YELLOW) + _span(mg) + body)

    desc = "Unofficial ARSO Discord weather bot"
    desc_pad = max(0, (text_w - len(desc)) // 2)
    svg_lines.append(_span(mg) + _span(bolt_padded[n_bolt - 3], _YELLOW) + _span(mg) + _span(" " * desc_pad + desc))
    svg_lines.append(_span(mg) + _span(bolt_padded[n_bolt - 2], _YELLOW))

    credits = "by MysteriousWolf"
    svg_lines.append(
        _span(mg) + _span(bolt_padded[n_bolt - 1], _YELLOW) + _span(mg)
        + _span(" " * (text_w - len(credits) - len(mg)))
        + _span("by ", _FADED) + _span("MysteriousWolf", _FADED)
    )

    max_chars = max(sum(len(ch) for ch, _, _ in row) for row in svg_lines)
    w = round(PAD_X * 2 + max_chars * CHAR_W)
    h = PAD_Y * 2 + FONT_SIZE + (len(svg_lines) - 1) * LINE_H + (LINE_H - FONT_SIZE)

    style = (
        f'<style>text{{font-family:"Cascadia Code","Fira Code","Courier New",monospace;'
        f'font-size:{FONT_SIZE}px;line-height:{LINE_H}px}}</style>'
    )
    text_els = "\n".join(
        _svg_line(row, PAD_Y + FONT_SIZE + i * LINE_H) for i, row in enumerate(svg_lines)
    )
    svg = (
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">\n'
        f'<rect width="{w}" height="{h}" fill="{BG}"/>\n'
        f'{style}\n{text_els}\n</svg>'
    )

    out = Path(__file__).parent.parent / "assets" / "banner.svg"
    out.parent.mkdir(exist_ok=True)
    out.write_text(svg)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
