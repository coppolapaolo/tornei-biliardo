"""Genera i tagli delle icone dell'app installabile da una o due immagini master.

I sistemi operativi vogliono la stessa icona in cinque formati diversi, con
regole che si contraddicono a vicenda: Android ritaglia (serve margine), iOS
arrotonda da sé (servono angoli quadri) e non tollera la trasparenza (la
renderebbe nera), la favicon deve restare leggibile a 16 pixel. Ritagliarli a
mano ogni volta che il logo cambia è il modo sicuro per ritrovarsi con cinque
icone leggermente diverse fra loro.

Uso::

    python scripts/genera_icone_app.py --master static/img/app/master.png
    python scripts/genera_icone_app.py --master m.png --maskable mask.png

Senza `--maskable` la variante per Android viene derivata dal master
aggiungendo il margine di sicurezza (contenuto dentro il cerchio dell'80%)
sul colore di sfondo.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

# Fondo pagina del design system 7c (`--c7-bg`), lo stesso di `theme_color` e
# `background_color` nel manifest: così la schermata di avvio non lampeggia.
SFONDO_DEFAULT = "#E4E8E7"

DESTINAZIONE = Path("static/img/app")

# Quota del lato occupata dal contenuto in un'icona maskable: Android può
# ritagliare fino al cerchio inscritto, quindi tutto ciò che conta deve stare
# nell'80% centrale.
QUOTA_SICURA = 0.8


def _apri(percorso: Path) -> Image.Image:
    immagine = Image.open(percorso)
    return immagine.convert("RGBA")


def _su_sfondo(immagine: Image.Image, sfondo: str) -> Image.Image:
    """Appiattisce la trasparenza su un fondo pieno (iOS e favicon .ico)."""
    piano = Image.new("RGBA", immagine.size, sfondo)
    piano.alpha_composite(immagine)
    return piano.convert("RGB")


def _ridimensiona(immagine: Image.Image, lato: int) -> Image.Image:
    return immagine.resize((lato, lato), Image.LANCZOS)


def _rendi_maskable(master: Image.Image, sfondo: str) -> Image.Image:
    """Master centrato dentro il margine di sicurezza, su fondo pieno."""
    lato = max(master.size)
    contenuto = _ridimensiona(master, int(lato * QUOTA_SICURA))
    tela = Image.new("RGBA", (lato, lato), sfondo)
    scarto = (lato - contenuto.size[0]) // 2
    tela.alpha_composite(contenuto, (scarto, scarto))
    return tela


def genera(master_path: Path, maskable_path: Path | None, sfondo: str) -> list[Path]:
    DESTINAZIONE.mkdir(parents=True, exist_ok=True)
    master = _apri(master_path)
    if master.size[0] != master.size[1]:
        raise SystemExit(f"Il master deve essere quadrato, non {master.size}.")

    maskable = (
        _apri(maskable_path) if maskable_path else _rendi_maskable(master, sfondo)
    )

    scritti: list[Path] = []

    def salva(immagine: Image.Image, nome: str) -> None:
        percorso = DESTINAZIONE / nome
        immagine.save(percorso, "PNG", optimize=True)
        scritti.append(percorso)

    for lato in (192, 512):
        salva(_ridimensiona(master, lato), f"icon-{lato}.png")
        salva(_ridimensiona(maskable, lato), f"icon-maskable-{lato}.png")

    # iOS: niente trasparenza (diventerebbe nera) e niente angoli arrotondati
    # disegnati da noi, li mette il sistema.
    apple = _su_sfondo(_ridimensiona(master, 180), sfondo)
    percorso_apple = DESTINAZIONE / "apple-touch-icon.png"
    apple.save(percorso_apple, "PNG", optimize=True)
    scritti.append(percorso_apple)

    for lato in (16, 32):
        salva(_ridimensiona(master, lato), f"favicon-{lato}.png")

    ico = _su_sfondo(master, sfondo)
    percorso_ico = DESTINAZIONE / "favicon.ico"
    ico.save(percorso_ico, "ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    scritti.append(percorso_ico)

    return scritti


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--master",
        required=True,
        type=Path,
        help="PNG quadrato ad alta risoluzione (consigliato 1024x1024).",
    )
    parser.add_argument(
        "--maskable",
        type=Path,
        help="Variante per Android col contenuto dentro l'80%% centrale. "
        "Se manca, viene derivata dal master.",
    )
    parser.add_argument(
        "--sfondo",
        default=SFONDO_DEFAULT,
        help="Colore di fondo per iOS/favicon e per il margine "
        f"(default {SFONDO_DEFAULT}).",
    )
    argomenti = parser.parse_args()

    for percorso in genera(argomenti.master, argomenti.maskable, argomenti.sfondo):
        print(percorso)


if __name__ == "__main__":
    main()
