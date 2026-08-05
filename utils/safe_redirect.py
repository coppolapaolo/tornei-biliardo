"""Validazione del parametro `next` nei redirect dopo il login.

Un `next` preso dalla query string e passato a `redirect()` senza controlli è
un open redirect: `?next=https://sito-falso/login` porta l'utente fuori dal
sito subito dopo aver inserito le credenziali, su una pagina che può imitare
la nostra. Qui passano solo i percorsi interni.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse


def safe_next_url(candidate: Optional[str]) -> Optional[str]:
    """Restituisce `candidate` se è un percorso interno, altrimenti None.

    Ammette solo percorsi relativi alla radice (`/gare`, `/g/abc?confirm=1`).
    Rifiuta URL assoluti, protocol-relative (`//host`) e le varianti con
    backslash che alcuni browser normalizzano in `//`.
    """
    if not candidate:
        return None

    # I browser trattano `\` come `/` nell'autority: `/\evil.com` diventa
    # `//evil.com`. urlparse invece lo lascia nel path, quindi va escluso qui.
    if "\\" in candidate:
        return None

    if not candidate.startswith("/") or candidate.startswith("//"):
        return None

    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return None

    return candidate
