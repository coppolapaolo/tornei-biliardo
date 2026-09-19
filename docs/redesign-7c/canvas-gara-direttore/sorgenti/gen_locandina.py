#!/usr/bin/env python3
"""La locandina di prova per lo schermo in sala (3.10): 1200x630, il formato
che admin/gara_vetrina.html chiede per l'anteprima social. Nel canvas va in
testa a tutta larghezza, ritagliata al centro come fanno le anteprime.

Flat, pochi colori: il PNG resta sotto i 40 KB (il canvas rimanda tutto a
ogni salvataggio). Si rigenera con `python3 sorgenti/gen_locandina.py`;
richiede Pillow (c'e' nel venv del progetto)."""

import pathlib

from PIL import Image, ImageDraw, ImageFont

SRC = pathlib.Path(__file__).resolve().parent
W, H = 1200, 630
ACCENT, BRIGHT, INK, DIM = (44, 74, 82), (143, 205, 232), (27, 33, 36), (169, 196, 199)


def font(size, bold=True):
    for nome in ("JetBrainsMono-ExtraBold.ttf", "JetBrainsMono-Bold.ttf"):
        p = pathlib.Path.home() / "Library" / "Fonts" / nome
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def main():
    img = Image.new("RGB", (W, H), ACCENT)
    d = ImageDraw.Draw(img)
    # la palla 8, grande, a destra: il soggetto della locandina
    cx, cy, r = 930, 315, 230
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK)
    d.ellipse((cx - 92, cy - 92, cx + 92, cy + 92), fill=(242, 245, 244))
    d.text((cx, cy + 6), "8", font=font(150), fill=INK, anchor="mm")
    # il testo a sinistra, centrato in altezza: la fascia dello schermo in
    # sala mostra la banda centrale (circa 200 px su 630), e un titolo
    # centrato sopravvive al ritaglio
    d.text((72, 246), "GARA 3", font=font(100), fill=(242, 245, 244))
    d.text((72, 334), "GIOVEDI'", font=font(62), fill=BRIGHT)
    d.text((72, 60), "BILIARDO MIMMO", font=font(28), fill=DIM)
    d.text(
        (72, 540),
        "3 SETTEMBRE  ·  ORE 20  ·  PALLA 8  ·  AL 5",
        font=font(30),
        fill=DIM,
    )
    out = SRC / "locandina.png"
    img.save(out, optimize=True)
    print(f"{out.name}: {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
