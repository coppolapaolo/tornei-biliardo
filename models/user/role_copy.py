"""I testi con cui un ruolo concedibile si concede e si revoca (ADR-041).

Stavano dentro due template dell'amministrazione, scritti a mano ruolo per
ruolo. Il difetto non era l'estetica: **aggiungere un ruolo al meccanismo non
bastava a farlo comparire dove lo si assegna**, e un ruolo che nessuno può
concedere non parte mai — nemmeno il primo titolare, da cui poi la catena si
propaga.

Qui i testi stanno una volta sola e le due schermate li ciclano su
``GRANT_POLICY``. Sono **pigri** (`lazy_gettext`) perché il modulo si importa
all'avvio, quando non c'è nessuna richiesta e quindi nessuna lingua.

I testi italiani sono quelli di prima, parola per parola: cambiarli avrebbe
buttato via le traduzioni inglesi già scritte, che il catalogo tiene per
``msgid``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from flask_babel import lazy_gettext as _l

from .role_enum import GrantableRole


@dataclass(frozen=True)
class RoleCopy:
    """Come si racconta un ruolo a chi lo assegna."""

    icona: str
    concedi: Any
    concedi_conferma: Any
    revoca: Any
    revoca_conferma: Any
    #: La riga della scheda utente: «Esaminatore:», «Istruttore:».
    etichetta: Any


ROLE_COPY: Dict[GrantableRole, RoleCopy] = {
    GrantableRole.EXAMINER: RoleCopy(
        icona="fa-user-graduate",
        concedi=_l("Rendi esaminatore"),
        concedi_conferma=_l("Promuovere a Esaminatore?"),
        revoca=_l("Revoca esaminatore"),
        revoca_conferma=_l(
            "Revocare il ruolo di Esaminatore? Gli esami creati e le "
            "certificazioni rilasciate restano validi."
        ),
        etichetta=_l("Esaminatore:"),
    ),
    GrantableRole.INSTRUCTOR: RoleCopy(
        icona="fa-chalkboard-user",
        concedi=_l("Rendi istruttore"),
        concedi_conferma=_l(
            "Renderlo istruttore? Potrà essere trovato dagli allievi che "
            "scelgono a chi aprire una scheda, e potrà nominare altri "
            "istruttori."
        ),
        revoca=_l("Revoca istruttore"),
        revoca_conferma=_l(
            "Revocare il ruolo di Istruttore? Le schede che gli allievi gli "
            "hanno aperto restano aperte: quelle le chiudono loro."
        ),
        etichetta=_l("Istruttore:"),
    ),
    GrantableRole.BETA_TESTER: RoleCopy(
        icona="fa-flask",
        concedi=_l("Rendi beta tester"),
        concedi_conferma=_l(
            "Fargli vedere le funzioni non ancora aperte? Non vedrà comunque "
            "l'amministrazione."
        ),
        revoca=_l("Togli beta"),
        revoca_conferma=_l(
            "Togliere l'accesso alle funzioni in prova? Tornerà a vedere "
            "quello che vede il suo ruolo."
        ),
        etichetta=_l("Beta tester:"),
    ),
}


def copy_for(role: GrantableRole) -> RoleCopy:
    """I testi del ruolo. Un ruolo senza voce prende un ripiego onesto.

    Il ripiego non è decorativo: è ciò che impedisce che aggiungere un ruolo a
    ``GRANT_POLICY`` e dimenticare questa tabella faccia sparire il pulsante —
    che è esattamente il difetto da cui nasce questo modulo.
    """
    voce = ROLE_COPY.get(role)
    if voce is not None:
        return voce
    nome = role.value.replace("_", " ")
    return RoleCopy(
        icona="fa-user-shield",
        concedi=_l("Concedi il ruolo «%(ruolo)s»", ruolo=nome),
        concedi_conferma=_l("Concedere il ruolo «%(ruolo)s»?", ruolo=nome),
        revoca=_l("Revoca il ruolo «%(ruolo)s»", ruolo=nome),
        revoca_conferma=_l("Revocare il ruolo «%(ruolo)s»?", ruolo=nome),
        etichetta=_l("%(ruolo)s:", ruolo=nome),
    )
