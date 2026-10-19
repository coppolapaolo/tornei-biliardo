"""L'indirizzo del sito da scrivere nei link delle email.

Un link in un'email porta un token: verifica dell'indirizzo, recupero
password, attivazione di un giocatore non registrato. Se l'origine del link
venisse dalla richiesta (``request.host_url``), chi fa partire l'email con un
header ``Host`` falsificato manderebbe alla vittima un link verso il proprio
dominio: lei lo apre, e il token arriva a lui, che si prende l'account.

Per questo l'origine si legge da ``PUBLIC_BASE_URL`` (``Config.
environment_settings``), che in produzione vale sempre il sito vero. Il
ripiego sulla richiesta resta solo dove la configurazione non c'è — sviluppo e
test — e dove quindi non c'è un sito vero da proteggere.

Un modulo solo, usato da tutti i punti che compongono link per email.
"""

from __future__ import annotations

from flask import current_app, has_app_context, has_request_context, request


def indirizzo_per_le_email() -> str:
    """L'origine dei link nelle email, senza la barra finale."""
    configurato = (
        current_app.config.get("PUBLIC_BASE_URL") if has_app_context() else None
    )
    if configurato:
        return str(configurato).rstrip("/")
    if has_request_context():
        return request.host_url.rstrip("/")
    return ""
