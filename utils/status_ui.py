"""
Module: utils/status_ui
Purpose: Presenter + registrazione filtri Jinja per visualizzare gli *status*
         (badge CSS e testo) senza logica nei model.
Data Structures: StatusPresenter
Dependencies: Flask (jinja_env), markupsafe.Markup, models.status_enum
ADR Reference: docs/ADR/ADR-0018-state-machine-and-status-enums.md

Copertura ambito Sprint 4 estesa:
- Prova (persistito + real_status derivato)
- Tournament (stato derivato)
- Match
- DirectorRequest
- Playoff.confirmation_status (legacy)

Nota fix: oltre ai *filtri* Jinja, qui esponiamo anche **funzioni globali**
`status_badge`, `status_badge_class`, `status_text` per consentire l'uso diretto
nei template come `{{ status_badge(obj, 'prova') }}` senza importare macro.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from markupsafe import Markup, escape

# Enum centralizzati (string-based, DB invariato)
from models.status_enum import (
    ProvaStatus,
    ProvaDerivedStatus,
    TournamentStatus,
    MatchStatus,
    DirectorRequestStatus,
    PlayoffConfirmationStatus,
)

# Opzionale: funzione pura per stato torneo (se presente)
try:  # import soft per evitare hard dependency
    from models.tournament.services import compute_tournament_status  # type: ignore
except Exception:  # pragma: no cover - fallback su metodo del model
    compute_tournament_status = None  # type: ignore


class StatusPresenter:
    """Mappa gli status applicativi verso (badge_class, text).

    Tutte le funzioni accettano sia una *stringa* di stato sia un *oggetto* model.
    Ritorno: tuple (css_class, text)
    """

    # --------------------- PROVA ---------------------
    @staticmethod
    def prova(o: Any) -> Tuple[str, str]:
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

        s = real_value or status_value or ProvaStatus.SETUP.value

        mapping: Dict[str, Tuple[str, str]] = {
            # Derived/UI
            ProvaDerivedStatus.INSCRIPTION_CLOSED.value: (
                "bg-secondary",
                "Iscrizioni Chiuse",
            ),
            ProvaDerivedStatus.READY_TO_START.value: (
                "bg-primary",
                "Pronta per Iniziare",
            ),
            ProvaDerivedStatus.ROUND_COMPLETED.value: ("bg-info", "Turno Completato"),
            ProvaDerivedStatus.TOURNAMENT_COMPLETED.value: (
                "bg-dark",
                "Torneo Completato",
            ),
            # Persistiti
            ProvaStatus.SETUP.value: ("bg-warning", "Setup"),
            ProvaStatus.INSCRIPTION.value: ("bg-info", "Iscrizioni Aperte"),
            ProvaStatus.PLAYING.value: ("bg-success", "In Corso"),
            ProvaStatus.COMPLETED.value: ("bg-dark", "Completata"),
        }
        return mapping.get(s, ("bg-secondary", "Sconosciuto"))

    # ------------------- TOURNAMENT -------------------
    @staticmethod
    def tournament(o: Any) -> Tuple[str, str]:
        # Preferisci funzione pura se disponibile, altrimenti delega al model
        if compute_tournament_status is not None:
            try:
                s = compute_tournament_status(o)
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
            TournamentStatus.SETUP.value: ("bg-warning", "Setup"),
            TournamentStatus.REGISTRATION_OPEN.value: ("bg-info", "Iscrizioni Aperte"),
            TournamentStatus.IN_PROGRESS.value: ("bg-primary", "In Corso"),
            TournamentStatus.COMPLETED.value: ("bg-success", "Completato"),
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
            MatchStatus.PENDING.value: ("bg-secondary", "In Attesa"),
            MatchStatus.PLAYING.value: ("bg-primary", "In Corso"),
            MatchStatus.COMPLETED.value: ("bg-success", "Completato"),
            MatchStatus.VALIDATED.value: ("bg-dark", "Validato"),
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
            DirectorRequestStatus.PENDING.value: ("bg-warning", "In Valutazione"),
            DirectorRequestStatus.APPROVED.value: ("bg-success", "Approvata"),
            DirectorRequestStatus.REJECTED.value: ("bg-danger", "Respinta"),
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
            PlayoffConfirmationStatus.PENDING.value: ("bg-secondary", "In Attesa"),
            PlayoffConfirmationStatus.CONFIRMED.value: ("bg-success", "Confermato"),
            PlayoffConfirmationStatus.DECLINED.value: ("bg-danger", "Rifiutato"),
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
    if "prova" in n:
        return "prova"
    if "tournament" in n:
        return "tournament"
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
    if k == "prova":
        return StatusPresenter.prova(obj)
    if k == "tournament":
        return StatusPresenter.tournament(obj)
    if k == "match":
        return StatusPresenter.match(obj)
    if k == "director_request":
        return StatusPresenter.director_request(obj)
    if k == "playoff_confirmation":
        return StatusPresenter.playoff_confirmation(obj)
    return ("bg-secondary", "Sconosciuto")


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
    # Filtri Jinja
    app.jinja_env.filters["status_badge"] = filter_status_badge
    app.jinja_env.filters["status_badge_class"] = filter_status_badge_class
    app.jinja_env.filters["status_text"] = filter_status_text

    # Funzioni globali (per uso come {{ status_badge(obj, 'prova') }})
    app.jinja_env.globals["status_badge"] = filter_status_badge
    app.jinja_env.globals["status_badge_class"] = filter_status_badge_class
    app.jinja_env.globals["status_text"] = filter_status_text
