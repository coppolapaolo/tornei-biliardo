"""Misura le altezze vere: senza support.js <x-dc> e' un elemento qualunque,
ma CSS e layout sono gli stessi. Serve a non consegnare schermate tagliate.

    venv/bin/python measure.py     dopo `python3 gen.py`, da questa cartella

Scrive uno screenshot per artboard in shots/ e segna «SBORDA» dove il
contenuto supera il limite (la barra in basso, o l'altezza dell'artboard).
"""

import json
import pathlib

from playwright.sync_api import sync_playwright

QUI = pathlib.Path(__file__).resolve().parent
ROOT = QUI / "root" / "project"
SHOTS = QUI / "shots"

MISURA = """() => {
  const r = document.querySelector('.phone,.app');
  const c = r.querySelector('.content .stack, .dcontent');
  const dock = r.querySelector('.dock, .actionbar, .mobilenav');
  const cb = c.getBoundingClientRect().bottom;
  return {content: Math.round(cb),
          limit: dock ? Math.round(dock.getBoundingClientRect().top) : null,
          sw: document.body.scrollWidth}; }"""


def main():
    idx = json.loads((ROOT / "canvas.json").read_text())
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, fr in idx["boards"].items():
            pg = b.new_page(
                viewport={"width": fr["w"], "height": fr["h"]}, device_scale_factor=1
            )
            pg.goto("file://" + str((ROOT / name).resolve()))
            pg.wait_for_timeout(500)
            m = pg.evaluate(MISURA)
            # La barra in basso fa da limite solo dove l'artboard e' alto uno
            # schermo (telefono 844) o e' un desktop: gli artboard lunghi scorrono.
            barra_conta = fr["h"] == 844 or fr["w"] > 1000
            lim = m["limit"] if (m["limit"] and barra_conta) else fr["h"]
            sborda = m["content"] > lim or m["sw"] > fr["w"]
            flag = "  <<< SBORDA" if sborda else ""
            print(
                f'{name:28} h={fr["h"]:5} contenuto={m["content"]:5} '
                f'limite={lim} sw={m["sw"]}{flag}'
            )
            shot = SHOTS / (name.replace(".dc.html", "") + ".png")
            pg.screenshot(path=str(shot), full_page=True)
        b.close()


if __name__ == "__main__":
    main()
