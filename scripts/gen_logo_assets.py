#!/usr/bin/env python3
"""Regenerate every logo derivative from the single source-of-truth SVG.

Source of truth: ``docs/assets/samba-logo.svg`` — a themeable SVG whose artwork
fills with ``currentColor`` (default off-black, auto-lightened for dark UIs, and
recolourable at runtime when inlined). This script renders fixed-colour variants
and all raster derivatives so the brand stays in sync from one file:

    docs/assets/samba-logo-black.svg / -white.svg   static mono SVGs
    docs/assets/samba-logo-black.png / -white.png    transparent PNGs (512px tall)
    ui/public/samba-logo.svg                         copy of the source (web favicon)
    ui/public/favicon.ico                            multi-size .ico (brand colour)
    ui/src-tauri/icons/*                             desktop app icons (via tauri CLI)

Requirements: Inkscape (SVG rendering) and Pillow. The Tauri icon set also needs
the Tauri CLI (``npx tauri``); that step is skipped with a warning if missing.

Usage: ``python scripts/gen_logo_assets.py`` (or ``just logo``).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "assets" / "samba-logo.svg"

# Brand palette. BRAND is the default off-black; BLACK/WHITE are the mono variants.
BRAND = "#1a1a1a"
BLACK = "#000000"
WHITE = "#ffffff"

# The themed <style> block in the source, replaced wholesale to force a fixed fill.
_STYLE_RE = re.compile(r'<style id="logo-theme">.*?</style>', re.DOTALL)


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        sys.exit(f"error: required tool '{tool}' not found on PATH")
    return path


def variant_svg(color: str) -> str:
    """Return the source SVG with its theme replaced by a single fixed *color*."""
    text = SOURCE.read_text(encoding="utf-8")
    new, n = _STYLE_RE.subn(f'<style id="logo-theme">svg{{color:{color}}}</style>', text)
    if n != 1:
        sys.exit('error: could not find <style id="logo-theme"> in the source SVG')
    return new


def render_png(svg_text: str, out: Path, height: int) -> None:
    """Render *svg_text* to a transparent PNG *height* px tall (aspect preserved)."""
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as fh:
        fh.write(svg_text)
        tmp = Path(fh.name)
    try:
        subprocess.run(
            [
                INKSCAPE,
                str(tmp),
                "--export-type=png",
                f"--export-filename={out}",
                "-h",
                str(height),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        tmp.unlink(missing_ok=True)


def square(svg_text: str, size: int, pad_frac: float, out: Path) -> None:
    """Render *svg_text* centred on a transparent *size*x*size* canvas."""
    with tempfile.TemporaryDirectory() as d:
        raw = Path(d) / "raw.png"
        render_png(svg_text, raw, height=1024)
        logo = Image.open(raw).convert("RGBA")
        inner = round(size * (1 - 2 * pad_frac))
        scale = inner / max(logo.size)
        logo = logo.resize((round(logo.width * scale), round(logo.height * scale)), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(logo, ((size - logo.width) // 2, (size - logo.height) // 2))
        canvas.save(out)


def gen_tauri_icons(master: Path) -> None:
    """Regenerate the Tauri desktop icon set from a square master PNG."""
    npx = shutil.which("npx")
    if not npx:
        print("warn: 'npx' not found — skipping Tauri icons (run `npx tauri icon` later)")
        return
    ui = ROOT / "ui"
    try:
        subprocess.run(
            [npx, "--no-install", "tauri", "icon", str(master)],
            cwd=ui,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"warn: `tauri icon` failed — skipping Tauri icons\n{exc.stderr}")
        return
    # Desktop-only app: drop the mobile icon sets the CLI also emits.
    for mobile in ("android", "ios"):
        shutil.rmtree(ui / "src-tauri" / "icons" / mobile, ignore_errors=True)
    print("  ui/src-tauri/icons/* (Tauri desktop set)")


def main() -> None:
    global INKSCAPE
    INKSCAPE = _require("inkscape")
    if not SOURCE.exists():
        sys.exit(f"error: source SVG not found: {SOURCE}")

    docs = ROOT / "docs" / "assets"
    ui_public = ROOT / "ui" / "public"

    black, white = variant_svg(BLACK), variant_svg(WHITE)
    print("generating logo assets from", SOURCE.relative_to(ROOT))

    # Static mono SVGs + PNGs (brand kit).
    (docs / "samba-logo-black.svg").write_text(black, encoding="utf-8")
    (docs / "samba-logo-white.svg").write_text(white, encoding="utf-8")
    render_png(black, docs / "samba-logo-black.png", height=512)
    render_png(white, docs / "samba-logo-white.png", height=512)
    print("  docs/assets/samba-logo-{black,white}.{svg,png}")

    # Web favicon: copy the themeable source, plus a multi-size brand .ico.
    shutil.copyfile(SOURCE, ui_public / "samba-logo.svg")
    with tempfile.TemporaryDirectory() as d:
        ico_master = Path(d) / "favicon.png"
        square(variant_svg(BRAND), 256, pad_frac=0.02, out=ico_master)
        Image.open(ico_master).save(
            ui_public / "favicon.ico",
            format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    print("  ui/public/samba-logo.svg, ui/public/favicon.ico")

    # Desktop app icons from a padded brand master.
    with tempfile.TemporaryDirectory() as d:
        master = Path(d) / "app-icon.png"
        square(variant_svg(BRAND), 1024, pad_frac=0.08, out=master)
        gen_tauri_icons(master)

    print("done.")


if __name__ == "__main__":
    main()
