"""Salvataggio di un'immagine caricata: ridimensionamento e formato.

Stava dentro `routes/admin/venue.py` come funzione privata, e ci sarebbe
rimasta se le locandine della vetrina (issue #235) non avessero avuto bisogno
esattamente delle stesse quattro attenzioni — rotazione EXIF, trasparenza
appiattita, ridimensionamento proporzionale, salvataggio ottimizzato — con
misure diverse. Copiarla avrebbe prodotto due copie destinate a divergere
sulla prima correzione.
"""

from __future__ import annotations

import os
from typing import Tuple

from PIL import Image, ImageOps

#: Estensioni accettate. Non è una difesa di sicurezza — il nome del file lo
#: sceglie chi carica — ma il filtro che evita di dare in pasto a Pillow un
#: PDF e di mostrare all'utente un errore incomprensibile.
ESTENSIONI_AMMESSE = {"png", "jpg", "jpeg", "gif"}


def estensione_ammessa(filename: str) -> bool:
    """Il nome del file finisce con un'estensione di immagine che accettiamo?"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ESTENSIONI_AMMESSE


def salva_immagine_ridimensionata(
    file,
    save_path: str,
    max_size: Tuple[int, int] = (400, 300),
    quality: int = 80,
) -> None:
    """Ridimensiona e salva l'immagine caricata; se non ci riesce, non salva.

    `thumbnail` mantiene le proporzioni e non ingrandisce mai: `max_size` è un
    tetto, non una misura da raggiungere.

    Se Pillow non riesce a leggere o a salvare il file si rilancia e **su
    disco non resta niente**. Fino al 2026-11-10 il contenuto grezzo veniva
    scritto comunque: nessun chiamante lo usava — tutti mostrano l'errore e
    non salvano il percorso — ma restava nella cartella servita dal sito, col
    contenuto scelto da chi l'aveva caricato. È Pillow, non l'estensione, a
    dire che cos'è un'immagine.
    """
    try:
        image = Image.open(file.stream)

        # RGBA e palette su fondo bianco: un JPEG non ha canale alfa, e senza
        # questo passaggio le zone trasparenti diventano nere.
        if image.mode in ("RGBA", "P"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1])
            image = background

        # Le foto scattate col telefono portano l'orientamento nell'EXIF: senza
        # applicarlo si salvano coricate.
        image = ImageOps.exif_transpose(image)

        image.thumbnail(max_size, Image.Resampling.LANCZOS)

        formati = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".gif": "GIF"}
        formato = formati.get(os.path.splitext(save_path)[1].lower(), "JPEG")

        if formato == "JPEG":
            image.save(save_path, format=formato, quality=quality, optimize=True)
        elif formato == "PNG":
            image.save(save_path, format=formato, optimize=True)
        else:
            image.save(save_path, format=formato)

    except Exception:
        # Niente resta su disco: un salvataggio interrotto a metà lascerebbe
        # un file monco, e quello che Pillow non sa leggere non è un'immagine.
        if os.path.exists(save_path):
            os.remove(save_path)
        raise
