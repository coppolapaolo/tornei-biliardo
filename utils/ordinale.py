"""La posizione scritta come la scrive chi legge: «1°» in italiano, «1st» in inglese.

Nei testi tradotti la posizione non può portarsi dietro il suo segno: in
italiano basta un «°» dopo il numero, in inglese il suffisso cambia col
numero (1st, 2nd, 3rd, 4th, 11th, 21st). Un «%(pos)s°» nel catalogo diventava
in inglese un numero nudo — «(1 in group B)» — perché il traduttore non poteva
scegliere il suffisso al posto del numero. Il segno lo mette quindi questo
filtro, e il testo da tradurre riceve la posizione già scritta.
"""

from __future__ import annotations

from typing import Optional

_SUFFISSI_INGLESI = {1: "st", 2: "nd", 3: "rd"}


def _lingua_corrente() -> str:
    try:
        from flask_babel import get_locale

        locale = get_locale()
        return locale.language if locale is not None else "it"
    except Exception:
        # Fuori da una richiesta e senza app: la lingua della piattaforma.
        return "it"


def ordinale(numero: object, lingua: Optional[str] = None) -> str:
    """«3°», «3rd»: la posizione nella lingua di chi legge.

    Un valore che non è un intero torna com'è: meglio il dato grezzo che una
    pagina in errore.
    """
    try:
        n = int(str(numero))
    except (TypeError, ValueError):
        return str(numero)
    if (lingua or _lingua_corrente()) != "en":
        return f"{n}°"
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{_SUFFISSI_INGLESI.get(n % 10, 'th')}"
