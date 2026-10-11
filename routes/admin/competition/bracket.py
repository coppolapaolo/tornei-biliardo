# routes/admin/competition/bracket.py
"""Vista tabellone della gara (US-13, Step 10).

Pagina propria e non linguetta dentro `gara_detail`: il tabellone e' largo
per natura — una colonna per turno, e nella formula FISBB una lavagna per
girone — mentre la pagina della gara vive dentro due colonne. Averla per se'
la rende anche condivisibile: e' la schermata che il direttore proietta o
manda in giro, non una sezione di un'altra.

**Visibile agli anonimi** come la pagina pubblica della gara: chi segue un
torneo senza avere un account e' il primo lettore del tabellone.

Nel girone all'italiana col tabellone dopo i gironi (ADR-081) la pagina
esiste dal sorteggio del tabellone, e sotto il tabellone mostra le
classifiche dei gironi da cui viene: mentre si giocano i gironi, o col girone
unico, non c'e' nessun tabellone e la pagina non esiste.
"""

from flask import abort, render_template
from flask_login import current_user

from models import db, Gara, Inscription, Match
from models.competition.tabellone_della_gara import (
    albero_della_gara,
    tabellone_della_gara,
)

from . import competition_bp


@competition_bp.route("/<int:gara_id>/tabellone")
def gara_bracket(gara_id):
    """Il tabellone della gara, in sola lettura, per chiunque."""
    gara = db.get_or_404(Gara, gara_id)

    matches = (
        Match.query.filter_by(gara_id=gara_id)
        .order_by(Match.round_number, Match.bracket_slot, Match.id)
        .all()
    )

    # Il tabellone esiste solo per i formati che ne producono uno, e per il
    # girone all'italiana dal sorteggio del tabellone finale: su una gara ad
    # Amalfi, a girone unico o ancora nei gironi non c'e' nulla di parziale
    # da mostrare, quindi la pagina non esiste invece di aprirsi vuota.
    quale = tabellone_della_gara(gara, matches)
    if not quale.da_mostrare:
        abort(404)

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

    # L'albero intero, con i nodi dei turni non ancora nati (issue #240): dopo
    # il sorteggio il percorso di ciascuno si legge in anticipo.
    tabellone = albero_della_gara(gara, matches)

    # Le classifiche dei gironi da cui viene il tabellone: quelle scritte,
    # senza ricalcolare (la pagina la apre anche chi non ha un account).
    gironi = []
    if quale.dopo_i_gironi:
        from models.classification.gironi_in_pagina import (
            dividi_per_girone,
            segna_il_taglio,
        )
        from models.competition.fase_finale_service import chi_va_al_tabellone
        from models.competition.showcase_service import classifica_gia_calcolata

        gironi = segna_il_taglio(
            dividi_per_girone(classifica_gia_calcolata(gara.id)),
            chi_va_al_tabellone(gara, matches),
        )

    return render_template(
        "gara_bracket.html",
        gara=gara,
        boards=tabellone.lavagne if tabellone else [],
        has_bracket=tabellone is not None,
        user_can_manage=user_can_manage,
        forfeit_user_ids=forfeit_user_ids,
        dopo_i_gironi=quale.dopo_i_gironi,
        gironi=gironi,
    )
