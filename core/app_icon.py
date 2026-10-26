"""Generate EDITH's fixed E-monogram desktop application icon.

Only the application icon is generated. This does not replace the existing
EDITH UI/HUD artwork, theme, or the system tray.
"""
from __future__ import annotations

from pathlib import Path


def build_edith_icon(out_path: Path) -> bool:
    """Write a multi-resolution ICO with an EDITH E glyph and rounded border."""
    try:
        import PIL.Image
        import PIL.ImageDraw
    except ImportError:
        return False

    def render(size: int):
        scale = 4
        side = size * scale
        image = PIL.Image.new("RGBA", (side, side), (0, 0, 0, 0))
        draw = PIL.ImageDraw.Draw(image)
        pad = 2 * scale
        width = max(2, int(side * 0.075))
        draw.rounded_rectangle(
            (pad, pad, side - pad - 1, side - pad - 1),
            radius=int(side * 0.24),
            fill=(11, 13, 18, 255),
            outline=(165, 180, 252, 255),
            width=width,
        )
        x0, x1 = int(side * 0.34), int(side * 0.70)
        y0, y1 = int(side * 0.28), int(side * 0.72)
        bar = max(3, int(side * 0.075))
        draw.line((x0, y0, x0, y1), fill=(233, 236, 255, 255), width=bar)
        for y in (y0, side // 2, y1):
            draw.line((x0, y, x1, y), fill=(233, 236, 255, 255), width=bar)
        return image.resize((size, size), PIL.Image.Resampling.LANCZOS)

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sizes = (256, 128, 64, 48, 32, 16)
        frames = [render(s) for s in sizes]
        frames[0].save(
            out_path, format="ICO", append_images=frames[1:],
            sizes=[(s, s) for s in sizes],
        )
        return out_path.is_file() and out_path.stat().st_size > 0
    except (OSError, ValueError) as exc:
        print(f"[EDITH] Icon generation failed: {type(exc).__name__}: {exc}")
        return False
