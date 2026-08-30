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
    """Ridimensiona e salva l'immagine caricata, con ripiego sul file grezzo.

    `thumbnail` mantiene le proporzioni e non ingrandisce mai: `max_size` è un
    tetto, non una misura da raggiungere.

    Se Pillow non riesce ad aprire il file lo si scrive comunque così com'è e
    **poi** si rilancia: chi chiama deve sapere che il ridimensionamento non è
    avvenuto, ma l'immagine resta a disposizione invece di sparire.
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
        file.seek(0)
        with open(save_path, "wb") as destinazione:
            destinazione.write(file.read())
        raise
