"""La revisione delle partite dopo il riscatto (emendamento del 2026-10-18).

Chi ha riscattato un giocatore non registrato trova qui le partite che altri
avevano registrato contro di lui: le riconosce tutte, le contesta tutte o ne
sceglie alcune da contestare. La regola sta in
``models/individual_match/revisione.py``; qui c'è il modulo.

La pagina si apre dall'invito che arriva col riscatto, dall'avviso in «Le mie
sfide» e dalla pagina di ciascuna sfida, che ha i suoi due pulsanti e manda
qui la stessa richiesta con una partita sola.
"""

from flask import flash, redirect, render_template, request, url_for
from flask_babel import gettext as _
from flask_babel import ngettext
from flask_login import current_user

from models.exceptions import DomainError
from models.individual_match.revisione import RevisioneService
from models.user.permissions import RoleRequirement
from utils.safe_redirect import safe_next_url

from . import individual_match_bp

#: I tre esiti del modulo: riconoscerle tutte, contestarle tutte, o
#: contestare solo quelle spuntate (e riconoscere le altre).
RICONOSCI_TUTTE = "riconosci_tutte"
CONTESTA_TUTTE = "contesta_tutte"
SCEGLI = "scegli"


def _ids(nome: str) -> list:
    valori = []
    for valore in request.form.getlist(nome):
        try:
            valori.append(int(valore))
        except (TypeError, ValueError):
            continue
    return valori


@individual_match_bp.route("/revisione", methods=["GET", "POST"])
@RoleRequirement.player_or_director_required
def review_matches():
    """Le partite da rivedere dopo il riscatto, e il gesto che le rivede."""
    if request.method == "POST":
        rivedute = _ids("partite")
        azione = request.form.get("azione")
        if azione == CONTESTA_TUTTE:
            contestate = rivedute
        elif azione == SCEGLI:
            contestate = [i for i in _ids("contesta") if i in rivedute]
        elif azione == RICONOSCI_TUTTE:
            contestate = []
        else:
            flash(_("Scegli cosa fare delle partite."), "warning")
            return redirect(url_for("individual_match.review_matches"))
        try:
            esito = RevisioneService.rivedi(current_user.id, rivedute, contestate)
        except DomainError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("individual_match.review_matches"))
        if esito.riconosciute:
            flash(
                ngettext(
                    "Hai riconosciuto una partita: ora è confermata.",
                    "Hai riconosciuto %(num)d partite: ora sono confermate.",
                    esito.riconosciute,
                ),
                "success",
            )
        if esito.contestate:
            flash(
                ngettext(
                    "Hai contestato una partita: non è più fra le tue.",
                    "Hai contestato %(num)d partite: non sono più fra le tue.",
                    esito.contestate,
                ),
                "info",
            )
        destinazione = safe_next_url(request.form.get("next"))
        return redirect(destinazione or url_for("individual_match.review_matches"))

    return render_template(
        "individual_match/revisione.html",
        matches=RevisioneService.da_rivedere(current_user.id),
        RICONOSCI_TUTTE=RICONOSCI_TUTTE,
        CONTESTA_TUTTE=CONTESTA_TUTTE,
        SCEGLI=SCEGLI,
    )
