"""Génère toutes les icônes d'Ancora à partir de assets/icon.svg et assets/icon-square.svg.

Sorties :
- app/mobile/static/ : favicon.ico, favicon.svg, icons/ (PNG 16 à 512, apple-touch-icon, maskable)
- assets/ : favicon.svg, icon-512.png (page_icon Streamlit), social-preview.png (1280x640, GitHub)

Usage : python scripts/generate_icons.py
Prérequis : pip install playwright pillow  (et un Chromium : playwright install chromium)
"""
import io
import os
import shutil
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
STATIC = ROOT / "app" / "mobile" / "static"
ICONS = STATIC / "icons"

SQUIRCLE = (ASSETS / "icon.svg").read_text(encoding="utf-8")        # coins arrondis, fond transparent
SQUARE = (ASSETS / "icon-square.svg").read_text(encoding="utf-8")   # plein cadre, fond noir
LOGO = (ASSETS / "logo.svg").read_text(encoding="utf-8")


def page(body: str, background: str = "transparent", size: tuple[int, int] = (100, 100)) -> str:
    return (f"<html><body style='margin:0;background:{background};width:{size[0]}px;height:{size[1]}px;"
            f"display:flex;align-items:center;justify-content:center'>{body}</body></html>")


def fit(svg: str, width: int, height: int | None = None) -> str:
    return svg.replace("<svg ", f'<svg style="width:{width}px;height:{height or width}px" ', 1)


def render(browser, html: str, width: int, height: int, transparent: bool = True) -> Image.Image:
    tab = browser.new_page(viewport={"width": width, "height": height})
    tab.set_content(html)
    data = tab.screenshot(omit_background=transparent, type="png")
    tab.close()
    return Image.open(io.BytesIO(data)).convert("RGBA")


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        # CHROMIUM_PATH : navigateur déjà installé (sinon celui de « playwright install chromium »).
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)

        def save(image: Image.Image, path: Path) -> None:
            image.save(path)
            print("  ", path.relative_to(ROOT))

        for size in (16, 32, 48, 64, 192, 512):  # icône à coins arrondis, fond transparent
            save(render(browser, page(fit(SQUIRCLE, size), size=(size, size)), size, size), ICONS / f"icon-{size}.png")
        # iOS arrondit lui-même : carré plein cadre, sans transparence.
        save(render(browser, page(fit(SQUARE, 180), "#000", (180, 180)), 180, 180, False).convert("RGB"),
             ICONS / "apple-touch-icon.png")
        # « Maskable » (Android) : le motif reste dans la zone sûre (80 % du centre).
        inner = fit(SQUARE, 512 * 8 // 10)
        save(render(browser, page(inner, "#000", (512, 512)), 512, 512, False).convert("RGB"),
             ICONS / "icon-maskable-512.png")
        save(render(browser, page(fit(SQUIRCLE, 512), size=(512, 512)), 512, 512), ASSETS / "icon-512.png")
        # Aperçu de partage GitHub / réseaux : logo centré sur fond blanc.
        card = page(fit(LOGO, 640, 640 * 0.28), "#FFFFFF", (1280, 640))
        save(render(browser, card, 1280, 640, False).convert("RGB"), ASSETS / "social-preview.png")
        browser.close()

    # favicon.ico multi-tailles (16, 32, 48) à la racine de la web-app : certains navigateurs le demandent d'office.
    base = Image.open(ICONS / "icon-48.png")
    base.save(STATIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    shutil.copy(ASSETS / "icon.svg", STATIC / "favicon.svg")
    shutil.copy(ASSETS / "icon.svg", ASSETS / "favicon.svg")
    print("   app/mobile/static/favicon.ico, favicon.svg")


if __name__ == "__main__":
    main()
