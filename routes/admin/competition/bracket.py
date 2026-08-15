# routes/admin/competition/bracket.py
"""Vista tabellone della gara (US-13, Step 10).

Pagina propria e non linguetta dentro `gara_detail`: il tabellone e' largo
per natura — una colonna per turno, e nella formula FISBB una lavagna per
girone — mentre la pagina della gara vive dentro due colonne. Averla per se'
la rende anche condivisibile: e' la schermata che il direttore proietta o
manda in giro, non una sezione di un'altra.

**Visibile agli anonimi** come la pagina pubblica della gara: chi segue un
torneo senza avere un account e' il primo lettore del tabellone.
"""

from flask import abort, render_template
from flask_login import current_user

from models import db, Gara, Inscription, Match
from models.matchmaking.bracket_view import (
    build_bracket_boards,
    has_bracket_coordinates,
)
from models.matchmaking.configuration import BRACKET_STRATEGIES

from . import competition_bp


@competition_bp.route("/<int:gara_id>/tabellone")
def gara_bracket(gara_id):
    """Il tabellone della gara, in sola lettura, per chiunque."""
    gara = db.get_or_404(Gara, gara_id)

    # Il tabellone esiste solo per i formati che ne producono uno: su una
    # gara ad Amalfi o round robin non c'e' nulla di parziale da mostrare,
    # quindi la pagina non esiste proprio invece di aprirsi vuota.
    if gara.matchmaking_strategy not in BRACKET_STRATEGIES:
        abort(404)

    matches = (
        Match.query.filter_by(gara_id=gara_id)
        .order_by(Match.round_number, Match.bracket_slot, Match.id)
        .all()
    )

    user_can_manage = (
        current_user.is_authenticated and current_user.can_manage_competition(gara_id)
    )

    # I ritirati restano nel tabellone — non lo si tocca dopo il sorteggio
    # (R5b) — ma vanno riconoscibili: chi legge deve capire perche' un nodo
    # e' finito a tavolino.
    forfeit_user_ids = {
        inscription.user_id
        for inscription in Inscription.query.filter_by(gara_id=gara_id).all()
        if inscription.is_forfeit
    }

    return render_template(
        "gara_bracket.html",
        gara=gara,
        boards=build_bracket_boards(matches),
        has_bracket=has_bracket_coordinates(matches),
        user_can_manage=user_can_manage,
        forfeit_user_ids=forfeit_user_ids,
    )
