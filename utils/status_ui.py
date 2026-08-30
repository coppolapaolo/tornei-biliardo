"""
Module: utils/status_ui
Purpose: Presenter + registrazione filtri Jinja per visualizzare gli *status*
         (badge CSS e testo) senza logica nei model.
Data Structures: StatusPresenter
Dependencies: Flask (jinja_env), markupsafe.Markup, models.status_enum


Copertura ambito Sprint 4 estesa:
- Gara (persistito + real_status derivato)
- Campionato (stato derivato)
- Match
- DirectorRequest
- Playoff.confirmation_status (legacy)

Nota fix: oltre ai *filtri* Jinja, qui esponiamo anche **funzioni globali**
`status_badge`, `status_badge_class`, `status_text` per consentire l'uso diretto
nei template come `{{ status_badge(obj, 'gara') }}` senza importare macro.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from markupsafe import Markup, escape
from flask_babel import gettext as _

# Enum centralizzati (string-based, DB invariato)
from models.status_enum import (
    GaraStatus,
    ProvaDerivedStatus,
    TournamentStatus,
    MatchStatus,
    DirectorRequestStatus,
    PlayoffConfirmationStatus,
)

# Opzionale: funzione pura per stato campionato (se presente)
try:  # import soft per evitare hard dependency
    from models.campionato.services import compute_campionato_status  # type: ignore
except Exception:  # pragma: no cover - fallback su metodo del model
    compute_campionato_status = None  # type: ignore


class StatusPresenter:
    """Mappa gli status applicativi verso (badge_class, text).

    Tutte le funzioni accettano sia una *stringa* di stato sia un *oggetto* model.
    Ritorno: tuple (css_class, text)
    """

    # --------------------- GARA ---------------------
    @staticmethod
    def gara(o: Any) -> Tuple[str, str]:
        # Persistito: setup/inscription/playing/completed
        # UI: si usa il "real status" se disponibile
        status_value: Optional[str] = None
        real_value: Optional[str] = None

        # Estraggo status/real_status dall'oggetto se possibile
        if hasattr(o, "status"):
            status_value = getattr(o, "status")
        if hasattr(o, "get_real_status") and callable(getattr(o, "get_real_status")):
            try:
                real_value = o.get_real_status()  # preferito in UI
            except Exception:
                real_value = None

        s = real_value or status_value or GaraStatus.SETUP.value

        mapping: Dict[str, Tuple[str, str]] = {
            # Derived/UI
            # Senza questa entry una gara in INSCRIPTION con apertura futura
            # (real status `inscription_not_yet_open`) cadeva sul fallback e
            # mostrava "Sconosciuto" in homepage, riquadro di gestione ed
            # elenco gare del campionato (issue #65).
            ProvaDerivedStatus.INSCRIPTION_NOT_YET_OPEN.value: (
                "bg-secondary",
                _("Iscrizioni Programmate"),
            ),
            ProvaDerivedStatus.INSCRIPTION_CLOSED.value: (
                "bg-secondary",
                _("Iscrizioni Chiuse"),
            ),
            ProvaDerivedStatus.READY_TO_START.value: (
                "bg-primary",
                _("Pronta per Iniziare"),
            ),
            ProvaDerivedStatus.ROUND_COMPLETED.value: (
                "bg-info",
                _("Turno Completato"),
            ),
            ProvaDerivedStatus.TOURNAMENT_COMPLETED.value: (
                "bg-dark",
                _("Gara Completata"),
            ),
            # Persistiti
            GaraStatus.SETUP.value: ("bg-warning", _("Setup")),
            GaraStatus.INSCRIPTION.value: ("bg-info", _("Iscrizioni Aperte")),
            GaraStatus.PLAYING.value: ("bg-success", _("In Corso")),
            GaraStatus.AWAITING_SSR.value: ("bg-warning", _("Spareggi")),
            GaraStatus.COMPLETED.value: ("bg-dark", _("Completata")),
        }
        return mapping.get(s, ("bg-secondary", _("Sconosciuto")))

    # ------------------- CAMPIONATO -------------------
    @staticmethod
    def campionato(o: Any) -> Tuple[str, str]:
        # Uno stato già calcolato si accetta com'è. Senza questo ramo, passare
        # una stringa faceva cadere `compute_campionato_status` sul suo default
        # (`gare` vuote → SETUP), quindi il presidio
        # `test_status_presenter_copre_gli_stati` non poteva fallire: qualunque
        # stato gli si desse, la risposta era "Setup".
        if isinstance(o, str):
            return StatusPresenter._campionato_mapping().get(
                o, ("bg-secondary", _("Sconosciuto"))
            )
        # Preferisci funzione pura se disponibile, altrimenti delega al model
        if compute_campionato_status is not None:
            try:
                s = compute_campionato_status(o)
            except Exception:
                s = None
        else:
            s = None
        if (
            s is None
            and hasattr(o, "get_status")
            and callable(getattr(o, "get_status"))
        ):
            try:
                s = o.get_status()
            except Exception:
                s = TournamentStatus.SETUP.value

        return StatusPresenter._campionato_mapping().get(
            s or TournamentStatus.SETUP.value, ("bg-secondary", _("Sconosciuto"))
        )

    @staticmethod
    def _campionato_mapping() -> Dict[str, Tuple[str, str]]:
        return {
            TournamentStatus.SETUP.value: ("bg-warning", _("Setup")),
            TournamentStatus.REGISTRATION_OPEN.value: (
                "bg-info",
                _("Iscrizioni Aperte"),
            ),
            TournamentStatus.IN_PROGRESS.value: ("bg-primary", _("In Corso")),
            # I due stati non finali dicono *cosa* si sta aspettando: il badge
            # lo legge anche il visitatore anonimo, a cui un "Da chiudere" non
            # direbbe niente di utile. Vedi la docstring di TournamentStatus.
            TournamentStatus.AWAITING_CLOSURE.value: (
                "bg-secondary",
                _("In attesa di chiusura"),
            ),
            TournamentStatus.AWAITING_PLAYOFF.value: (
                "bg-dark",
                _("In attesa dei playoff"),
            ),
            TournamentStatus.COMPLETED.value: ("bg-success", _("Completato")),
        }

    # --------------------- MATCH ---------------------
    @staticmethod
    def match(o: Any) -> Tuple[str, str]:
        s: Optional[str] = None
        if isinstance(o, str):
            s = o
        elif hasattr(o, "status"):
            s = getattr(o, "status")
        mapping: Dict[str, Tuple[str, str]] = {
            MatchStatus.PENDING.value: ("bg-secondary", _("In Attesa")),
            MatchStatus.PLAYING.value: ("bg-primary", _("In Corso")),
            # Gli stati delle **sfide individuali**, che mancavano tutti e tre.
            # I match di gara vanno PENDING → PLAYING, le sfide individuali
            # SCHEDULED → IN_PROGRESS: due percorsi sullo stesso enum, e qui
            # era mappato solo il primo. Ogni sfida individuale mostrava così
            # «Sconosciuto» nel pallino di stato — in corso, da giocare o
            # annullata che fosse.
            MatchStatus.SCHEDULED.value: ("bg-secondary", _("Da giocare")),
            MatchStatus.IN_PROGRESS.value: ("bg-primary", _("In Corso")),
            MatchStatus.CANCELLED.value: ("bg-secondary", _("Annullata")),
            MatchStatus.CLOSED_UNILATERALLY.value: ("bg-success", _("Completato")),
            # Diceva «Validato», che è proprio il fraintendimento da cui è
            # nato il rinomino dell'enum: questo stato non è la validazione
            # del direttore — quella è la riga sopra — ma la chiusura decisa
            # dai due giocatori, che hanno confermato entrambi.
            MatchStatus.CONFIRMED_BY_BOTH.value: (
                "bg-dark",
                _("Confermato dai giocatori"),
            ),
        }
        return mapping.get(
            s or MatchStatus.PENDING.value, ("bg-secondary", _("Sconosciuto"))
        )

    # -------------- DIRECTOR REQUEST -----------------
    @staticmethod
    def director_request(o: Any) -> Tuple[str, str]:
        s: Optional[str] = None
        if isinstance(o, str):
            s = o
        elif hasattr(o, "status"):
            s = getattr(o, "status")
        mapping: Dict[str, Tuple[str, str]] = {
            DirectorRequestStatus.PENDING.value: ("bg-warning", _("In Valutazione")),
            DirectorRequestStatus.APPROVED.value: ("bg-success", _("Approvata")),
            DirectorRequestStatus.REJECTED.value: ("bg-danger", _("Respinta")),
        }
        return mapping.get(
            s or DirectorRequestStatus.PENDING.value,
            ("bg-secondary", _("Sconosciuto")),
        )

    # ---------------------- PLAYOFF -------------------
    @staticmethod
    def playoff_confirmation(o: Any) -> Tuple[str, str]:
        s: Optional[str] = None
        if isinstance(o, str):
            s = o
        elif hasattr(o, "confirmation_status"):
            s = getattr(o, "confirmation_status")
        mapping: Dict[str, Tuple[str, str]] = {
            PlayoffConfirmationStatus.PENDING.value: ("bg-secondary", _("In Attesa")),
            PlayoffConfirmationStatus.CONFIRMED.value: ("bg-success", _("Confermato")),
            PlayoffConfirmationStatus.DECLINED.value: ("bg-danger", _("Rifiutato")),
        }
        return mapping.get(
            s or PlayoffConfirmationStatus.PENDING.value,
            ("bg-secondary", _("Sconosciuto")),
        )


# ---------------------- JINJA FILTERS & GLOBALS ----------------------


def _resolve_kind(obj: Any, kind: Optional[str]) -> str:
    """Tenta di dedurre il *kind* se non esplicito."""
    if kind:
        return kind
    # hint per deduzione automatica
    n = obj.__class__.__name__.lower() if hasattr(obj, "__class__") else ""
    if "gara" in n:
        return "gara"
    if "campionato" in n:
        return "campionato"
    if "match" in n:
        return "match"
    if "directorrequest" in n or "director_request" in n:
        return "director_request"
    if "playoff" in n:
        return "playoff_confirmation"
    # fallback generico
    return "match"


def _present(obj: Any, kind: Optional[str]) -> Tuple[str, str]:
    k = _resolve_kind(obj, kind)
    if k == "gara":
        return StatusPresenter.gara(obj)
    if k == "campionato":
        return StatusPresenter.campionato(obj)
    if k == "match":
        return StatusPresenter.match(obj)
    if k == "director_request":
        return StatusPresenter.director_request(obj)
    if k == "playoff_confirmation":
        return StatusPresenter.playoff_confirmation(obj)
    return ("bg-secondary", _("Sconosciuto"))


def _badge_html(css_class: str, text: str) -> Markup:
    return Markup(f'<span class="badge {escape(css_class)}">{escape(text)}</span>')


def filter_status_badge(obj: Any, kind: Optional[str] = None) -> Markup:
    css, text = _present(obj, kind)
    return _badge_html(css, text)


def filter_status_badge_class(obj: Any, kind: Optional[str] = None) -> str:
    css, _ = _present(obj, kind)
    return css


def filter_status_text(obj: Any, kind: Optional[str] = None) -> str:
    _, text = _present(obj, kind)
    return text


def match_scoring_state(match: Any, user: Any) -> Dict[str, Any]:
    """A che punto è la partita, per chi la sta guardando.

    Esiste perché le due viste del segnapunti — quella verticale
    (``_unified_rack_input.html``) e il tabellone orizzontale
    (``_match_scoreboard.html``) — devono rispondere alle stesse domande:
    si può ancora segnare? il risultato aspetta una conferma, e di chi?
    Finché ognuna se lo calcolava per conto suo con i propri ``{% set %}``,
    le due divergevano: la verticale spegneva i ``+1`` a distanza raggiunta
    (sessione di debug del 2026-08-17, punti 6 e 7) e il tabellone no, perché
    quella correzione lì non era mai arrivata.

    Non duplica il calcolo della distanza: passa da ``match.distance_config``
    (ADR-027), così gli override per turno valgono anche qui.

    Chiavi ritornate:

    ``in_progress``            partita ancora in corso
    ``at_distance``            distanza raggiunta (il risultato è pronto)
    ``can_add``                si può segnare un altro rack
    ``you_confirmed``          il lettore ha già confermato il risultato
    ``opponent_confirmed``     l'avversario ha già confermato
    ``awaiting_you``           tocca al lettore accettare o rifiutare
    ``closed_by_players``      chiusa con la doppia conferma (reversibile)
    ``finished``               in uno dei due stati finali
    ``winner_id``              vincitore, se determinato dal punteggio
    ``is_player``              il lettore è uno dei due giocatori
    """
    status_str = getattr(match.status, "value", match.status)
    in_progress = status_str in ("in_progress", "playing")
    closed_by_players = status_str == MatchStatus.CONFIRMED_BY_BOTH.value

    p1 = match.player1_score or 0
    p2 = match.player2_score or 0

    # Distanza: unica fonte è il VO (ADR-027), che tiene conto degli override
    # per turno. Il formato libero non ha traguardo, quindi non finisce mai
    # "a distanza".
    at_distance = False
    distance = getattr(match, "distance_config", None)
    if getattr(match, "is_multi_set", False):
        # Nel multi-set i due punteggi sono **set vinti**, non rack: il
        # traguardo è `match_distance`, e `distance_config` descrive il
        # singolo set. Leggere lì il traguardo direbbe "finita" a metà.
        winning_sets = getattr(match, "match_distance", None)
        if winning_sets:
            if getattr(match, "is_race_to_sets", True):
                at_distance = p1 >= winning_sets or p2 >= winning_sets
            else:
                at_distance = (p1 + p2) >= winning_sets
    elif distance is not None:
        if distance.is_race_to_racks:
            winning = distance.get_winning_racks()
            at_distance = p1 >= winning or p2 >= winning
        else:
            at_distance = (p1 + p2) >= distance.racks

    user_id = (
        getattr(user, "id", None) if getattr(user, "is_authenticated", False) else None
    )
    is_p1 = user_id is not None and user_id == match.player1_id
    is_p2 = user_id is not None and user_id == getattr(match, "player2_id", None)

    you_confirmed = bool(
        (is_p1 and match.player1_confirmed) or (is_p2 and match.player2_confirmed)
    )
    opponent_confirmed = bool(
        (is_p1 and match.player2_confirmed) or (is_p2 and match.player1_confirmed)
    )

    # Un tavolo non assegnato blocca il punteggio tanto quanto la distanza
    # raggiunta: in entrambi i casi il rack non va segnato.
    needs_table = hasattr(match, "table_assignment") and not match.table_assignment
    can_add = in_progress and not at_distance and not needs_table

    winner_id = None
    if at_distance or MatchStatus.is_finished(status_str):
        if p1 > p2:
            winner_id = match.player1_id
        elif p2 > p1:
            winner_id = getattr(match, "player2_id", None)

    return {
        "in_progress": in_progress,
        "at_distance": at_distance,
        "can_add": can_add,
        "you_confirmed": you_confirmed,
        "opponent_confirmed": opponent_confirmed,
        "awaiting_you": (is_p1 or is_p2) and at_distance and not you_confirmed,
        "closed_by_players": closed_by_players,
        "finished": MatchStatus.is_finished(status_str),
        "winner_id": winner_id,
        "is_player": is_p1 or is_p2,
    }


def register_status_filters(app) -> None:
    """Registra filtri **e** funzioni globali nel jinja_env dell'app Flask."""
    # Stato del segnapunti, condiviso fra vista verticale e tabellone (8b).
    app.jinja_env.globals["match_scoring_state"] = match_scoring_state
    # Filtri Jinja per status
    app.jinja_env.filters["status_badge"] = filter_status_badge
    app.jinja_env.filters["status_badge_class"] = filter_status_badge_class
    app.jinja_env.filters["status_text"] = filter_status_text

    # Funzioni globali (per uso come {{ status_badge(obj, 'gara') }})
    app.jinja_env.globals["status_badge"] = filter_status_badge
    app.jinja_env.globals["status_badge_class"] = filter_status_badge_class
    app.jinja_env.globals["status_text"] = filter_status_text

    # Filtri Jinja per date (formattazione locale nel browser)
    from utils.jinja import (
        format_date_local,
        format_datetime_input,
        format_datetime_local,
        format_time_local,
        format_discipline,
        format_tpa,
        parse_json,
    )

    app.jinja_env.filters["date_local"] = format_date_local
    app.jinja_env.filters["datetime_local"] = format_datetime_local
    app.jinja_env.filters["time_local"] = format_time_local
    # Controparte in scrittura di `datetime_local`: ripopola un
    # `<input type="datetime-local">` con l'ora che l'utente aveva digitato.
    app.jinja_env.filters["datetime_input"] = format_datetime_input
    app.jinja_env.filters["discipline_display"] = format_discipline
    # Il TPA in millesimi -> come si scrive sul referto (`.780`, `1.000`)
    app.jinja_env.filters["tpa_display"] = format_tpa
    # Payload JSON dei flash "di trasporto" (vedi utils/page_modal.py)
    app.jinja_env.filters["fromjson"] = parse_json
