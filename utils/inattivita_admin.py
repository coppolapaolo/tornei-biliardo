"""L'admin viene scollegato dopo un periodo di inattività (ADR-063).

Solo l'admin: può fare tutto, quindi una sessione dimenticata aperta su un
computer condiviso è quella che costa di più. Direttori e giocatori restano
come prima — un direttore al tavolo col telefono in tasca fra un turno e
l'altro verrebbe scollegato in piena gara.

L'ultima attività sta nel **cookie di sessione**, non in `user_session`:
quella tabella misura le permanenze e non autentica nessuno (ADR-055). Il
cookie è firmato, quindi l'orario non si falsifica, e viaggia con la sessione
che deve proteggere.

I **poll non contano** come attività: una scheda aperta che interroga il
server ogni pochi secondi terrebbe viva la sessione per sempre, cioè proprio
il caso da chiudere. Scaduto il limite, il primo poll riceve 401 e la pagina
mostra l'avviso «La sessione è scaduta» (`static/js/polling.js`).
"""

from __future__ import annotations

import time
from typing import Optional

from flask import current_app, flash, redirect, request, session, url_for
from flask_babel import gettext as _
from flask_login import current_user, logout_user
from werkzeug.wrappers import Response

from models.user.role_enum import UserRole
from utils.safe_redirect import safe_next_url

CHIAVE = "_admin_ultima_attivita"

# Riscrivere l'orario a ogni richiesta rimanderebbe il cookie a ogni risposta
# senza aggiungere precisione utile: sul limite di mezz'ora, un minuto di
# approssimazione non si vede.
PASSO_AGGIORNAMENTO_SECONDI = 60


def _adesso() -> float:
    """Secondi epoch, indipendenti dal fuso.

    Non `utc_now().timestamp()`: `utc_now()` restituisce un datetime **naive**,
    e `timestamp()` su un naive lo interpreta come ora locale del server.
    Funzionerebbe finché il server sta in UTC, e sbaglierebbe di ore il
    giorno in cui non ci sta.
    """
    return time.time()


def _limite_secondi() -> float:
    return current_app.config["ADMIN_IDLE_TIMEOUT"].total_seconds()


def _e_admin(utente) -> bool:
    return bool(getattr(utente, "is_authenticated", False)) and (
        getattr(utente, "role", None) == UserRole.ADMIN.value
    )


def segna_accesso(utente) -> None:
    """All'accesso l'orario riparte da adesso.

    Senza, una chiave vecchia rimasta nel cookie da una sessione precedente
    scollegherebbe l'admin alla prima pagina dopo il login.
    """
    if _e_admin(utente):
        session[CHIAVE] = _adesso()
    else:
        session.pop(CHIAVE, None)


def controlla_inattivita_admin() -> Optional[Response]:
    """`before_request`: scollega l'admin fermo da troppo, o ne segna l'attività."""
    if request.endpoint == "static" or not _e_admin(current_user):
        return None

    adesso = _adesso()
    poll = request.blueprint == "sse"
    ultima = session.get(CHIAVE)

    # Sessione aperta prima che esistesse questo controllo: la si prende in
    # carico da adesso invece di scollegarla senza sapere da quanto è ferma.
    if not isinstance(ultima, (int, float)):
        session[CHIAVE] = adesso
        return None

    if adesso - ultima > _limite_secondi():
        session.pop(CHIAVE, None)
        logout_user()
        if poll:
            # L'utente ora è anonimo: la view del poll risponde 401 da sé.
            return None
        flash(
            _(
                "Sessione chiusa dopo %(minuti)s minuti di inattività: "
                "accedi di nuovo.",
                minuti=int(_limite_secondi() // 60),
            ),
            "warning",
        )
        # Il `next` solo per le pagine: dopo il login il browser farebbe un
        # GET, e riportarlo su un indirizzo che accetta solo POST darebbe 405.
        next_url = None
        if request.method == "GET":
            next_url = safe_next_url(request.full_path.rstrip("?"))
        return redirect(url_for("auth.login", next=next_url))

    if not poll and adesso - ultima >= PASSO_AGGIORNAMENTO_SECONDI:
        session[CHIAVE] = adesso
    return None
