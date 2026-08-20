"""Disegna il master dell'icona dell'app: geometria, non illustrazione.

Un triangolo con delle biglie è fatto di cerchi e di tre segmenti, quindi non
serve un modello generativo: si calcola. Il vantaggio non è filosofico —
disegnandola si ottengono spessori regolari, spaziature identiche, i colori
**esatti** del design system e nessuno dei difetti tipici di un'immagine
generata (contorni doppi, angoli arrotondati di nascosto, alonature). E
soprattutto la si può rifare: se domani cambia l'accento, il master si
rigenera invece di essere ridisegnato a mano.

Uso::

    python scripts/disegna_icona_app.py --variante rack6
    python scripts/disegna_icona_app.py --variante tutte --provino

`--provino` affianca ogni variante a 256, 48, 32 e 16 px: è lì che si decide
se un'icona regge, non a grandezza naturale.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

# Palette del design system 7c (static/css/tokens-7c.css).
SFONDO = "#2C4A52"  # --c7-accent
SEGNO = "#F2F8F7"  # --c7-accent-ink
ACCENTO = "#8FCDE8"  # --c7-accent-bright

LATO = 1024
# Il segno occupa il 70% della tela: il resto è il margine che i sistemi si
# aspettano e che l'occhio legge come "icona" invece che come "figura".
QUOTA_SEGNO = 0.70
# Si disegna quattro volte più grandi e si rimpicciolisce: è il modo più
# semplice per avere bordi puliti senza dipendere dall'antialiasing di Pillow.
SOVRACAMPIONE = 4

RADICE3 = math.sqrt(3.0)


def _disco(disegno: ImageDraw.ImageDraw, x: float, y: float, r: float, colore: str):
    disegno.ellipse((x - r, y - r, x + r, y + r), fill=colore)


def _triangolo_stondato(
    disegno: ImageDraw.ImageDraw,
    centro: tuple[float, float],
    raggio_medio: float,
    spessore: float,
    colore: str,
):
    """Triangolo equilatero a punta in su, tratto unico e angoli tondi.

    Gli angoli si arrotondano con un disco su ogni vertice: `joint="curve"`
    ammorbidisce le giunzioni ma non chiude il profilo, e a 32 px la
    differenza fra i due si vede tutta.
    """
    cx, cy = centro
    circonraggio = 2.0 * raggio_medio
    vertici = []
    for i in range(3):
        angolo = -math.pi / 2 + i * (2 * math.pi / 3)
        vertici.append(
            (cx + circonraggio * math.cos(angolo), cy + circonraggio * math.sin(angolo))
        )
    disegno.line(
        vertici + [vertici[0]], fill=colore, width=int(spessore), joint="curve"
    )
    for vx, vy in vertici:
        _disco(disegno, vx, vy, spessore / 2.0, colore)


def _centri_rack(passo: float, righe: int) -> list[tuple[float, float]]:
    """Centri delle biglie in un rack a punta in su, riga per riga."""
    altezza = passo * RADICE3 / 2.0
    centri = []
    for riga in range(righe):
        for colonna in range(riga + 1):
            centri.append((-riga * passo / 2.0 + colonna * passo, riga * altezza))
    return centri


def _rack(lato: int, righe: int, con_telaio: bool) -> Image.Image:
    r = 1.0
    distanza = 0.30 if con_telaio else 0.40
    passo = 2 * r + distanza
    altezza = passo * RADICE3 / 2.0
    centri = _centri_rack(passo, righe)
    baricentro = (0.0, (righe - 1) * altezza * 2.0 / 3.0)

    if con_telaio:
        margine, spessore = 0.26, 1.05
        raggio_centri = (righe - 1) * passo * RADICE3 / 6.0
        raggio_medio = raggio_centri + r + margine + spessore / 2.0
        raggio_esterno = raggio_medio + spessore / 2.0
        larghezza = 2 * RADICE3 * raggio_esterno
        alto = 3 * raggio_esterno
    else:
        margine = spessore = raggio_medio = raggio_esterno = 0.0
        larghezza = (righe - 1) * passo + 2 * r
        alto = (righe - 1) * altezza + 2 * r

    tela = lato * SOVRACAMPIONE
    scala = (QUOTA_SEGNO * tela) / max(larghezza, alto)
    immagine = Image.new("RGB", (tela, tela), SFONDO)
    disegno = ImageDraw.Draw(immagine)

    # In un triangolo a punta in su l'incentro sta a due terzi dell'altezza:
    # centrare il disegno lì lo fa sembrare caduto in basso. Si centra il
    # rettangolo che contiene il segno.
    scarto_y = (raggio_esterno - 2 * raggio_esterno) / 2.0 if con_telaio else 0.0

    def punto(x: float, y: float) -> tuple[float, float]:
        return (
            tela / 2.0 + (x - baricentro[0]) * scala,
            tela / 2.0 + (y - baricentro[1] - scarto_y) * scala,
        )

    if con_telaio:
        _triangolo_stondato(
            disegno,
            punto(*baricentro),
            raggio_medio * scala,
            spessore * scala,
            SEGNO,
        )

    # La biglia in punta è quella diversa: è il vertice del triangolo, quindi
    # il punto in cui l'occhio cade per primo anche a icona rimpicciolita.
    for indice, (x, y) in enumerate(centri):
        px, py = punto(x, y)
        _disco(disegno, px, py, r * scala, ACCENTO if indice == 0 else SEGNO)

    return immagine.resize((lato, lato), Image.LANCZOS)


def _pieno(lato: int) -> Image.Image:
    """Triangolo pieno con le biglie ricavate in negativo."""
    r = 1.0
    passo = 2 * r + 0.45
    altezza = passo * RADICE3 / 2.0
    centri = _centri_rack(passo, 3)
    baricentro = (0.0, 2.0 * altezza * 2.0 / 3.0)
    raggio_interno = 2 * passo * RADICE3 / 6.0 + r + 0.5
    larghezza, alto = 2 * RADICE3 * raggio_interno, 3 * raggio_interno

    tela = lato * SOVRACAMPIONE
    scala = (QUOTA_SEGNO * tela) / max(larghezza, alto)
    immagine = Image.new("RGB", (tela, tela), SFONDO)
    disegno = ImageDraw.Draw(immagine)

    scarto_y = -raggio_interno / 2.0

    def punto(x: float, y: float) -> tuple[float, float]:
        return (
            tela / 2.0 + (x - baricentro[0]) * scala,
            tela / 2.0 + (y - baricentro[1] - scarto_y) * scala,
        )

    cx, cy = punto(*baricentro)
    # Si rientra di `raccordo` e si ripassa il profilo con un tratto tondo
    # dello stesso spessore: il risultato torna della misura giusta, con gli
    # angoli smussati come le card dell'interfaccia.
    raccordo = 0.13 * raggio_interno * scala
    circonraggio = 2.0 * raggio_interno * scala - 2.0 * raccordo
    vertici = []
    for i in range(3):
        angolo = -math.pi / 2 + i * (2 * math.pi / 3)
        vertici.append(
            (cx + circonraggio * math.cos(angolo), cy + circonraggio * math.sin(angolo))
        )
    disegno.polygon(vertici, fill=SEGNO)
    disegno.line(
        vertici + [vertici[0]], fill=SEGNO, width=int(2 * raccordo), joint="curve"
    )
    for vx, vy in vertici:
        _disco(disegno, vx, vy, raccordo, SEGNO)

    for indice, (x, y) in enumerate(centri):
        px, py = punto(x, y)
        _disco(disegno, px, py, r * scala, ACCENTO if indice == 0 else SFONDO)

    return immagine.resize((lato, lato), Image.LANCZOS)


VARIANTI = {
    "rack6": lambda: _rack(LATO, righe=3, con_telaio=True),
    "rack3": lambda: _rack(LATO, righe=2, con_telaio=False),
    "pieno": lambda: _pieno(LATO),
}


def provino(immagini: dict[str, Image.Image], destinazione: Path) -> Path:
    """Ogni variante alle misure in cui si usa davvero, una riga per variante."""
    misure = [256, 48, 32, 16]
    passo_x, passo_y = 300, 300
    foglio = Image.new(
        "RGB", (passo_x * len(misure), passo_y * len(immagini)), "#8A9296"
    )
    for riga, immagine in enumerate(immagini.values()):
        for colonna, misura in enumerate(misure):
            piccola = immagine.resize((misura, misura), Image.LANCZOS)
            foglio.paste(
                piccola,
                (
                    colonna * passo_x + (passo_x - misura) // 2,
                    riga * passo_y + (passo_y - misura) // 2,
                ),
            )
    foglio.save(destinazione, "PNG", optimize=True)
    return destinazione


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variante", default="tutte", choices=[*VARIANTI, "tutte"])
    parser.add_argument("--cartella", type=Path, default=Path("static/img/app"))
    parser.add_argument("--provino", action="store_true")
    argomenti = parser.parse_args()

    nomi = list(VARIANTI) if argomenti.variante == "tutte" else [argomenti.variante]
    argomenti.cartella.mkdir(parents=True, exist_ok=True)

    immagini = {}
    for nome in nomi:
        immagine = VARIANTI[nome]()
        percorso = argomenti.cartella / f"master-{nome}.png"
        immagine.save(percorso, "PNG", optimize=True)
        immagini[nome] = immagine
        print(percorso)

    if argomenti.provino:
        print(provino(immagini, argomenti.cartella / "provino.png"))


if __name__ == "__main__":
    main()
