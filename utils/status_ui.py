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
            ProvaDerivedStatus.INSCRIPTION_CLOSED.value: (
                "bg-secondary",
                _("Iscrizioni Chiuse"),
            ),
            ProvaDerivedStatus.READY_TO_START.value: (
                "bg-primary",
                _("Pronta per Iniziare"),
            ),
            ProvaDerivedStatus.ROUND_COMPLETED.value: ("bg-info", _("Turno Completato")),
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
        return mapping.get(s, ("bg-secondary", "Sconosciuto"))

    # ------------------- CAMPIONATO -------------------
    @staticmethod
    def campionato(o: Any) -> Tuple[str, str]:
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

        mapping: Dict[str, Tuple[str, str]] = {
            TournamentStatus.SETUP.value: ("bg-warning", _("Setup")),
            TournamentStatus.REGISTRATION_OPEN.value: ("bg-info", _("Iscrizioni Aperte")),
            TournamentStatus.IN_PROGRESS.value: ("bg-primary", _("In Corso")),
            TournamentStatus.COMPLETED.value: ("bg-success", _("Completato")),
            TournamentStatus.TERMINATED.value: ("bg-dark", _("Terminato")),
        }
        return mapping.get(
            s or TournamentStatus.SETUP.value, ("bg-secondary", "Sconosciuto")
        )

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
            MatchStatus.COMPLETED.value: ("bg-success", _("Completato")),
            MatchStatus.VALIDATED.value: ("bg-dark", _("Validato")),
        }
        return mapping.get(
            s or MatchStatus.PENDING.value, ("bg-secondary", "Sconosciuto")
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
            s or DirectorRequestStatus.PENDING.value, ("bg-secondary", "Sconosciuto")
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
            ("bg-secondary", "Sconosciuto"),
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


def register_status_filters(app) -> None:
    """Registra filtri **e** funzioni globali nel jinja_env dell'app Flask."""
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
        format_datetime_local,
        format_time_local,
        format_discipline,
    )

    app.jinja_env.filters["date_local"] = format_date_local
    app.jinja_env.filters["datetime_local"] = format_datetime_local
    app.jinja_env.filters["time_local"] = format_time_local
    app.jinja_env.filters["discipline_display"] = format_discipline
