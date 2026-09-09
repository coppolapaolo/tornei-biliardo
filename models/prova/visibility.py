"""Chi vede le competizioni di prova (ADR-058).

Gemello di `models/soft_delete/filter.py`: un listener su `do_orm_execute`
aggiunge a ogni SELECT esplicita un criterio su `Gara`, `Campionato` e
`User`, così che le prove e i loro giocatori fittizi **non compaiano** a chi
non le dirige — anche nelle query che verranno scritte fra un anno senza
pensarci. Deny-by-default, come l'allowlist ADR-028.

Il criterio non è un semplice «non di prova»: è

    is_prova = false  OR  id IN (le prove che l'utente corrente dirige)

L'insieme delle prove dirette (l'**ambito**) si calcola una volta per
richiesta dall'utente di sessione e si tiene in `request.environ` — non in
`g`, che in questa suite di test sopravvive alla richiesta (vedi
`project_test_flask_login_state_leak`), e senza passare da `current_user`
(vedi `_calcola_ambito`). Admin: tutte. Direttore: le sue, per
`director_id` e `DirectorAssignment`. Chiunque altro, e fuori da una
richiesta: nessuna.

Due scelte da conoscere:

* il filtro **non propaga ai caricamenti di relazione**: `match.gara` e
  `inscription.user` funzionano sempre, anche fuori richiesta. Altrimenti un
  ricalcolo ELO in uno script troverebbe `match.gara is None` su una partita
  di prova e morirebbe in un punto che non c'entra niente;
* chi lavora fuori da una richiesta — il servizio, il job di scadenza, i
  test — chiede le prove esplicitamente con `prova_visibili()` o con
  `execution_options(include_prova=True)`. È lo stesso onere di
  `with_deleted()` per il soft delete.

Ricorsione: calcolare l'ambito esegue query — l'utente di sessione, le sue
prove — che passano da questo stesso listener. Mentre l'ambito è in calcolo
il listener non filtra (flag in `request.environ`).
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, FrozenSet, Iterator, Tuple

from flask import has_request_context, request
from sqlalchemy import event, or_, select
from sqlalchemy.orm import with_loader_criteria

_CHIAVE_AMBITO = "tornei.prova.ambito"
_CHIAVE_IN_CORSO = "tornei.prova.ambito_in_corso"

#: Opt-in per chi lavora fuori da una richiesta (o dentro, ma per conto del
#: sistema): dentro `prova_visibili()` il filtro non si applica.
_forzato: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "prova_visibili", default=False
)


@dataclass(frozen=True)
class Ambito:
    """Le prove che l'utente corrente può vedere."""

    tutte: bool = False
    gare: FrozenSet[int] = frozenset()
    campionati: FrozenSet[int] = frozenset()


NESSUNA = Ambito()
TUTTE = Ambito(tutte=True)


@contextmanager
def prova_visibili() -> Iterator[None]:
    """Dentro questo blocco le prove e i fittizi sono visibili a ogni query."""
    token = _forzato.set(True)
    try:
        yield
    finally:
        _forzato.reset(token)


def invalida_ambito() -> None:
    """Da chiamare dopo aver creato una prova dentro una richiesta.

    L'ambito è calcolato una volta per richiesta: una prova nata dopo il
    calcolo non ci sarebbe, e una query esplicita che la cerca subito dopo
    non la troverebbe.
    """
    if has_request_context():
        request.environ.pop(_CHIAVE_AMBITO, None)


def ambito_corrente() -> Ambito:
    """L'ambito della richiesta corrente, calcolato al primo uso."""
    if not has_request_context():
        return NESSUNA
    environ = request.environ
    if environ.get(_CHIAVE_IN_CORSO):
        # Stiamo calcolando: le query di servizio non vanno filtrate, o non
        # troverebbero l'utente ne' le sue prove.
        return TUTTE
    cache = environ.get(_CHIAVE_AMBITO)
    if cache is not None:
        return cache
    environ[_CHIAVE_IN_CORSO] = True
    try:
        ambito, definitivo = _calcola_ambito()
    finally:
        environ[_CHIAVE_IN_CORSO] = False
    if definitivo:
        environ[_CHIAVE_AMBITO] = ambito
    return ambito


def _calcola_ambito() -> Tuple[Ambito, bool]:
    """(ambito, definitivo): chi è l'utente, letto **dalla sessione**.

    Non da `current_user`, di proposito. Questo codice gira dentro una query,
    e la prima query di una richiesta può essere proprio quella con cui
    Flask-Login carica l'utente: chiedere `current_user` da qui farebbe
    partire quel caricamento come effetto collaterale di una SELECT, e ne
    lascerebbe l'esito su `g` — dove, in questa suite di test, sopravvive
    alla richiesta e rende anonime tutte le richieste successive. La
    sessione dice la stessa cosa senza toccare niente: `User.from_session_id`
    verifica l'impronta della credenziale esattamente come `load_user`.

    `definitivo` è False quando la sessione non ha ancora l'utente ma c'è un
    cookie «ricordami»: Flask-Login sta per popolarla, e un ambito vuoto
    messo in cache adesso nasconderebbe le prove per tutta la richiesta.
    """
    from flask import current_app, session

    grezzo = session.get("_user_id")
    if grezzo is None:
        nome_cookie = current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
        return NESSUNA, request.cookies.get(nome_cookie) is None

    from models.user.models import User

    utente = User.from_session_id(str(grezzo))
    if utente is None:
        return NESSUNA, True
    if utente.is_admin:
        return TUTTE, True
    if not utente.is_director:
        return NESSUNA, True
    return ambito_del_direttore(utente.id), True


def ambito_del_direttore(user_id: int) -> Ambito:
    """Le prove che questo direttore dirige, come `director_id` o assegnato."""
    from models.base import db
    from models.campionato.models import Campionato
    from models.competition.models import Gara
    from models.user.models import DirectorAssignment

    opzioni = {"include_prova": True}

    campionati_assegnati = select(DirectorAssignment.entity_id).where(
        DirectorAssignment.entity_type == "campionato",
        DirectorAssignment.user_id == user_id,
    )
    campionati = frozenset(
        db.session.execute(
            select(Campionato.id)
            .where(
                Campionato.is_prova.is_(True),
                Campionato.id.in_(campionati_assegnati),
            )
            .execution_options(**opzioni)
        ).scalars()
    )

    gare_assegnate = select(DirectorAssignment.entity_id).where(
        DirectorAssignment.entity_type == "gara",
        DirectorAssignment.user_id == user_id,
    )
    condizioni = [Gara.director_id == user_id, Gara.id.in_(gare_assegnate)]
    if campionati:
        condizioni.append(Gara.campionato_id.in_(campionati))
    gare = frozenset(
        db.session.execute(
            select(Gara.id)
            .where(Gara.is_prova.is_(True), or_(*condizioni))
            .execution_options(**opzioni)
        ).scalars()
    )
    return Ambito(gare=gare, campionati=campionati)


# ---------------------------------------------------------------------------
# Il listener
# ---------------------------------------------------------------------------


def _clausola_gara(ambito: Ambito, cls: Any) -> Any:
    if ambito.gare:
        return or_(cls.is_prova.is_(False), cls.id.in_(sorted(ambito.gare)))
    return cls.is_prova.is_(False)


def _clausola_campionato(ambito: Ambito, cls: Any) -> Any:
    if ambito.campionati:
        return or_(cls.is_prova.is_(False), cls.id.in_(sorted(ambito.campionati)))
    return cls.is_prova.is_(False)


def _clausola_utente(ambito: Ambito, cls: Any) -> Any:
    parti = [cls.is_fittizio.is_(False)]
    if ambito.gare:
        parti.append(cls.prova_gara_id.in_(sorted(ambito.gare)))
    if ambito.campionati:
        parti.append(cls.prova_campionato_id.in_(sorted(ambito.campionati)))
    return or_(*parti) if len(parti) > 1 else parti[0]


def register_prova_filters(db_session_class: Any) -> None:
    """Installa il filtro sulla classe di sessione (una volta sola)."""
    flag = "_prova_filter_installed"
    if getattr(db_session_class, flag, False):
        return
    try:
        setattr(db_session_class, flag, True)
    except Exception:
        pass

    @event.listens_for(db_session_class, "do_orm_execute")
    def _filtra_le_prove(state: Any) -> None:
        if not state.is_select:
            return
        # I caricamenti di relazione e di colonna passano sempre: vedi la
        # docstring del modulo.
        if state.is_relationship_load or state.is_column_load:
            return
        if state.execution_options.get("include_prova", False) or _forzato.get():
            return

        ambito = ambito_corrente()
        if ambito.tutte:
            return

        from models.campionato.models import Campionato
        from models.competition.models import Gara
        from models.user.models import User

        # Espressioni concrete e non lambda: una lambda che chiude su un
        # insieme di id non e' cacheabile per SQLAlchemy («closure variable
        # ... does not refer to a cacheable SQL element»), e con
        # `track_closure_variables=False` gli id resterebbero quelli della
        # prima richiesta. Gli `in_` su liste sono bind «expanding», quindi
        # la cache delle compilazioni resta valida al variare degli id.
        state.statement = state.statement.options(
            with_loader_criteria(
                Gara,
                _clausola_gara(ambito, Gara),
                include_aliases=True,
                propagate_to_loaders=False,
            ),
            with_loader_criteria(
                Campionato,
                _clausola_campionato(ambito, Campionato),
                include_aliases=True,
                propagate_to_loaders=False,
            ),
            with_loader_criteria(
                User,
                _clausola_utente(ambito, User),
                include_aliases=True,
                propagate_to_loaders=False,
            ),
        )
