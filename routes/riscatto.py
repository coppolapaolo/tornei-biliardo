"""Riscatto di un giocatore non ancora registrato (ADR-086).

Il percorso di chi non ha ancora un account:

1. nella pagina pubblica di una gara, accanto a un giocatore non registrato,
   c'è «Sei tu? Riscatta» → ``main.riscatta_giocatore``;
2. i pulsanti **Accedi** e **Crea un account** sono un POST con CSRF che salva
   l'intenzione in sessione (``riscatto_in_sospeso``) e porta al login o alla
   registrazione, che a sua volta rimanda al login;
3. dopo ``login_user``, ``consuma_riscatto_in_sospeso`` toglie la chiave e
   chiama ``ClaimService.richiedi``: la richiesta parte senza un altro clic.

La richiesta non nasce mai da un GET: un link preparato da qualcun altro la
farebbe partire all'insaputa di chi accede. Chi è già collegato fa il POST
direttamente.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models.base import db
from models.exceptions import DomainError
from models.user.claim_request import ClaimRequest
from models.user.claim_service import ClaimService, utente_anche_cancellato
from models.user.models import User
from routes.main import main_bp

riscatto_bp = Blueprint("riscatto", __name__)

#: La chiave di sessione con l'intenzione di chi ha premuto «Accedi» o «Crea
#: un account». Scade: lasciata in un browser condiviso, non deve far partire
#: la richiesta per il prossimo che entra.
CHIAVE_IN_SOSPESO = "riscatto_in_sospeso"
DURATA_IN_SOSPESO = 60 * 60


def _utente() -> Any:
    return current_user._get_current_object()  # type: ignore[attr-defined]


def _salva_intenzione(giocatore_id: int) -> None:
    session[CHIAVE_IN_SOSPESO] = {
        "giocatore": int(giocatore_id),
        "scade": int(time.time()) + DURATA_IN_SOSPESO,
    }


def dimentica_riscatto_in_sospeso() -> None:
    session.pop(CHIAVE_IN_SOSPESO, None)


def _invia(giocatore_id: int, user: Any):
    """Chiede il riscatto e dice com'è andata. Redirect in ogni caso."""
    try:
        richiesta = ClaimService.richiedi(giocatore_id, user)
    except DomainError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("main.riscatta_giocatore", user_id=giocatore_id))
    flash(
        _(
            "Richiesta inviata a %(chi)s: quando la conferma, le partite "
            "passano al tuo account.",
            chi=ClaimService.a_chi(richiesta),
        ),
        "success",
    )
    return redirect(url_for("riscatto.richiesta", request_id=richiesta.id))


def consuma_riscatto_in_sospeso(user: Any) -> Optional[Any]:
    """Dopo il login: se c'era un riscatto in sospeso, lo chiede.

    Restituisce il redirect da usare al posto di quello del login, oppure
    ``None`` se non c'era niente in sospeso (o era scaduto).
    """
    dato = session.pop(CHIAVE_IN_SOSPESO, None)
    if not isinstance(dato, dict):
        return None
    try:
        giocatore_id = int(dato["giocatore"])
        scade = int(dato["scade"])
    except (KeyError, TypeError, ValueError):
        return None
    if scade < time.time():
        return None
    return _invia(giocatore_id, user)


# ──────────────────────────────────────────────────────────────── pubblica


@main_bp.route("/giocatori/<int:user_id>/riscatta", methods=["GET", "POST"])
def riscatta_giocatore(user_id: int):
    """«Sei tu?»: spiega il riscatto e lo chiede, o porta ad accedere."""
    giocatore = db.session.get(User, user_id)
    if giocatore is None or not giocatore.is_placeholder or giocatore.is_fittizio:
        abort(404)

    if request.method == "POST":
        if current_user.is_authenticated:
            return _invia(user_id, _utente())
        azione = request.form.get("azione")
        if azione not in ("accedi", "registrati"):
            abort(400)
        _salva_intenzione(user_id)
        pagina = url_for("main.riscatta_giocatore", user_id=user_id)
        destinazione = "auth.register" if azione == "registrati" else "auth.login"
        return redirect(url_for(destinazione, next=pagina))

    viewer = _utente() if current_user.is_authenticated else None
    in_attesa = ClaimService.richiesta_in_attesa(user_id)
    destinatari = ClaimService.destinatari(giocatore)
    conferma_admin = not destinatari or all(d.is_admin for d in destinatari)
    return render_template(
        "riscatto/giocatore.html",
        giocatore=giocatore,
        nome=giocatore.previous_username or giocatore.username,
        motivo=ClaimService.motivo_del_no(user_id, viewer),
        mia_in_attesa=(
            in_attesa
            if in_attesa is not None
            and viewer is not None
            and in_attesa.claimant_id == viewer.id
            else None
        ),
        conferma_admin=conferma_admin,
        creatore=None if conferma_admin else destinatari[0],
        n_gare=len([i for i in giocatore.inscriptions if not i.is_withdrawn]),
    )


# ─────────────────────────────────────────────────────────────── richieste


def _richiesta_o_404(request_id: int) -> ClaimRequest:
    richiesta = db.session.get(ClaimRequest, request_id)
    if richiesta is None:
        abort(404)
    return richiesta


@riscatto_bp.route("/riscatti", methods=["GET"])
@login_required
def richieste():
    """Le richieste da decidere e quelle fatte da chi guarda."""
    user = _utente()
    return render_template(
        "riscatto/richieste.html",
        da_decidere=ClaimService.da_decidere_per(user),
        mie=ClaimService.richieste_di(user),
    )


@riscatto_bp.route("/riscatti/<int:request_id>", methods=["GET"])
@login_required
def richiesta(request_id: int):
    """Una richiesta: chi chiede, chi è il giocatore, com'è finita."""
    richiesta = _richiesta_o_404(request_id)
    user = _utente()
    if not ClaimService.puo_vedere(richiesta, user):
        abort(404)
    placeholder = utente_anche_cancellato(richiesta.placeholder_id)
    claimant = db.session.get(User, richiesta.claimant_id)
    return render_template(
        "riscatto/richiesta.html",
        richiesta=richiesta,
        placeholder=placeholder,
        nome=(
            (placeholder.previous_username or placeholder.username)
            if placeholder
            else ""
        ),
        claimant=claimant,
        puo_decidere=richiesta.is_pending
        and ClaimService.puo_decidere(richiesta, user),
        a_chi=ClaimService.a_chi(richiesta),
        n_gare=(
            len([i for i in placeholder.inscriptions if not i.is_withdrawn])
            if placeholder
            else 0
        ),
    )


@riscatto_bp.route("/riscatti/<int:request_id>/decidi", methods=["POST"])
@login_required
def decidi(request_id: int):
    """Conferma o rifiuta un riscatto."""
    user = _utente()
    approva = request.form.get("decisione") == "approva"
    try:
        if approva:
            ClaimService.approve(request_id, user)
            flash(
                _("Riscatto confermato: le partite sono passate al suo account."),
                "success",
            )
        else:
            ClaimService.reject(request_id, user)
            flash(_("Riscatto rifiutato."), "info")
    except DomainError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("riscatto.richiesta", request_id=request_id))
    return redirect(url_for("riscatto.richieste"))


@riscatto_bp.route("/riscatti/sei-tu", methods=["GET"])
@login_required
def omonimi():
    """Il passo dell'onboarding: i non registrati che si chiamano come te."""
    user = _utente()
    candidati = ClaimService.omonimi(user)
    if not candidati:
        return redirect(url_for("dashboard.dashboard"))
    return render_template(
        "riscatto/omonimi.html",
        candidati=[
            {
                "giocatore": c,
                "motivo": ClaimService.motivo_del_no(c.id, user),
                "mia": (
                    lambda r: r if r is not None and r.claimant_id == user.id else None
                )(ClaimService.richiesta_in_attesa(c.id)),
                "n_gare": len([i for i in c.inscriptions if not i.is_withdrawn]),
            }
            for c in candidati
        ],
    )
