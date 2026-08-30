"""L'immagine che i social mostrano quando una gara non ha una locandina.

Quando qualcuno incolla il link di una gara su WhatsApp o Facebook, lo scraper
chiede un `og:image`. Se il direttore ha caricato una locandina si usa quella;
se non l'ha caricata serve comunque un'immagine, altrimenti l'anteprima resta
un rettangolo grigio con il dominio — che è esattamente il problema da cui
nasce la issue #235.

Si **disegna**, come le icone dell'app (`scripts/disegna_icona_app.py`), per le
stesse ragioni: colori esatti del design system, e la possibilità di rifarla
quando l'accento cambia invece di ridisegnarla a mano.

Nessun testo, e non è una rinuncia: il nome della gara lo mostra già il social
sotto l'immagine, preso da `og:title`. Scriverlo anche dentro la figura lo
raddoppierebbe, e obbligherebbe a generare un'immagine diversa per ogni gara —
con un font di sistema che su un altro computer non c'è, e un testo lungo che
prima o poi esce dal riquadro.

Uso::

    python scripts/disegna_vetrina_default.py

Scrive `static/img/social/vetrina-default.png`, che va committato: in
produzione questo script non gira mai.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from disegna_icona_app import SFONDO, _rack

#: 1200×630 è il formato che Facebook, WhatsApp, Telegram e X ritagliano di
#: meno: sotto i 600px di larghezza alcuni client degradano l'anteprima da
#: "grande" a miniatura quadrata, che è metà dell'effetto.
LARGHEZZA = 1200
ALTEZZA = 630

#: Il rack occupa poco più di metà dell'altezza: l'anteprima viene ritagliata
#: dai client in modi che non si controllano, e un segno grande al centro
#: sopravvive a qualunque taglio.
QUOTA_SEGNO = 0.62


def disegna() -> Image.Image:
    tela = Image.new("RGB", (LARGHEZZA, ALTEZZA), SFONDO)

    lato = int(ALTEZZA * QUOTA_SEGNO)
    segno = _rack(lato=lato, righe=3, con_telaio=True, quota=0.92)

    tela.paste(
        segno,
        ((LARGHEZZA - lato) // 2, (ALTEZZA - lato) // 2),
        segno if segno.mode == "RGBA" else None,
    )
    return tela


def main() -> None:
    radice = Path(__file__).resolve().parent.parent
    destinazione = radice / "static" / "img" / "social" / "vetrina-default.png"
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    disegna().save(destinazione, format="PNG", optimize=True)
    print(f"✓ {destinazione.relative_to(radice)}")


if __name__ == "__main__":
    main()
