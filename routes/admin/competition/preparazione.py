# routes/admin/competition/preparazione.py
"""I passi della preparazione di una gara, uno per pagina sul telefono.

Canvas «Pagina gara del direttore», fase 1 (schermate 1.2–1.7): turni e
distanze, tavoli, esercizi fra i turni, direzione di gara, vetrina. Sul
telefono ogni passo e' una pagina con «avanti» e «indietro»; sul desktop la
preparazione e' una pagina sola che scorre (1.9) e da qui si aprono solo
turni ed esercizi (1.10). La vetrina ha gia' la sua pagina
(`vetrina.py`) ed e' l'ultimo passo.

Le pagine esistono finche' la gara e' in preparazione o a iscrizioni
aperte: dopo, direttori e tavoli si toccano da «Impostazioni gara» e turni
ed esercizi sono fissati.
"""

from flask import abort, render_template, url_for
from flask_babel import lazy_gettext as _l
from flask_login import login_required

from models import db, Gara
from models.status_enum import Discipline, GaraStatus
from utils import gara_manager_required

from . import competition_bp
from .detail import contesto_direzione

#: I passi nell'ordine della preparazione: chiave, etichetta, endpoint.
PASSI = [
    ("turni", _l("Turni"), "admin.competition.gara_preparazione"),
    ("tavoli", _l("Tavoli"), "admin.competition.gara_preparazione"),
    ("esercizi", _l("Esercizi"), "admin.competition.gara_preparazione"),
    ("direttori", _l("Direttori"), "admin.competition.gara_preparazione"),
    ("vetrina", _l("Vetrina"), "admin.competition.gara_vetrina"),
]


def passi_della_preparazione(gara: Gara) -> list[dict]:
    """I passi con il loro indirizzo, per la navigazione fra un passo e l'altro.

    Gli esercizi fra i turni ci sono solo dove valgono
    (`Gara.ammette_esercizi_fra_i_turni`); la vetrina non c'e' nelle prove
    (ADR-058), che da fuori non esistono.
    """
    passi = []
    for chiave, etichetta, endpoint in PASSI:
        if chiave == "esercizi" and not gara.ammette_esercizi_fra_i_turni:
            continue
        if chiave == "vetrina" and gara.is_prova:
            continue
        if endpoint == "admin.competition.gara_preparazione":
            url = url_for(endpoint, gara_id=gara.id, passo=chiave)
        else:
            url = url_for(endpoint, gara_id=gara.id)
        passi.append({"chiave": chiave, "etichetta": etichetta, "url": url})
    return passi


def navigazione(gara: Gara, chiave: str) -> dict:
    """Dove si e' e dove si va: precedente, successivo, «n di N»."""
    passi = passi_della_preparazione(gara)
    chiavi = [p["chiave"] for p in passi]
    if chiave not in chiavi:
        abort(404)
    i = chiavi.index(chiave)
    return {
        "passi": passi,
        "corrente": passi[i],
        "indice": i + 1,
        "totale": len(passi),
        "precedente": passi[i - 1] if i > 0 else None,
        "successivo": passi[i + 1] if i + 1 < len(passi) else None,
    }


@competition_bp.route("/<int:gara_id>/preparazione/<passo>")
@login_required
@gara_manager_required
def gara_preparazione(gara_id, passo):
    gara = db.get_or_404(Gara, gara_id)
    if passo not in ("turni", "tavoli", "esercizi", "direttori"):
        abort(404)
    if gara.status not in (GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value):
        abort(404)
    contesto = contesto_direzione(gara)
    return render_template(
        "direttore/preparazione.html",
        gara=gara,
        user_can_manage=True,
        passo=passo,
        nav=navigazione(gara, passo),
        in_preparazione=gara.status == GaraStatus.SETUP.value,
        discipline_choices=Discipline.get_choices(),
        **contesto,
    )
