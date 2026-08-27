"""Create the multi-resolution Windows icon used by the app and installer."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def make_icon(source: Path, destination: Path) -> None:
    image = Image.open(source).convert("RGBA")
    alpha_bounds = image.getchannel("A").getbbox()
    if alpha_bounds:
        image = image.crop(alpha_bounds)

    side = max(image.size)
    padding = max(1, round(side * 0.08))
    canvas = Image.new("RGBA", (side + padding * 2, side + padding * 2))
    canvas.alpha_composite(
        image,
        ((canvas.width - image.width) // 2, (canvas.height - image.height) // 2),
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="ICO", sizes=[(size, size) for size in ICON_SIZES])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    make_icon(args.source, args.destination)


if __name__ == "__main__":
    main()
