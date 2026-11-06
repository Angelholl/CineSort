# -*- coding: utf-8 -*-
"""从 A 方案 SVG 母版生成 assets/icon/cinesort.ico。

尺寸分工：256/64 用主版（cinesort-icon-a.svg），32/16 用简化 glyph
（cinesort-icon-a-small.svg，去动势线、加粗槽体，保证小尺寸可读）。

用法：py -3.12 tools/make_icon.py   （依赖 cairosvg + Pillow）
"""
from __future__ import annotations

import io
from pathlib import Path

import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "assets" / "icon"

# (svg 母版, (尺寸...))：主版出大尺寸，简化版出小尺寸
SOURCES = [
    ("cinesort-icon-a.svg", (256, 64, 48)),
    ("cinesort-icon-a-small.svg", (32, 16)),
]


def main() -> None:
    images = []
    for name, sizes in SOURCES:
        svg = ICON_DIR / name
        for s in sizes:
            png = cairosvg.svg2png(url=str(svg), output_width=s, output_height=s)
            images.append(Image.open(io.BytesIO(png)))
    out = ICON_DIR / "cinesort.ico"
    images[0].save(
        str(out), format="ICO",
        sizes=[(i.width, i.height) for i in images],
        append_images=images[1:],
    )
    print(f"written {out} sizes={sorted((i.width, i.height) for i in images)}")


if __name__ == "__main__":
    main()
