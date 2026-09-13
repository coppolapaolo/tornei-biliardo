# routes/admin/competition/impostazioni.py
"""«Impostazioni gara»: cio' che il direttore tocca in ogni fase.

Nella pagina della gara a fasi (canvas «Pagina gara del direttore», decisione
2) la gestione non ha piu' una linguetta: direttori, vetrina, tavoli, squadre
e categorie stanno in questa pagina, raggiungibile dalla testata sul desktop
e da una riga in fondo sul telefono. Turni, distanze, esercizi, accoppiamento
e chi riposa si fissano prima dell'avvio: da li' in poi qui si leggono.

Il contesto della direzione (chi si puo' aggiungere, chi puo' farlo) e' lo
stesso della pagina della gara: `contesto_direzione` in `detail.py`.
"""

from flask import render_template
from flask_login import login_required

from models import db, Gara
from models.competition.direttore_view import contesto_campionato
from models.status_enum import GaraStatus
from utils import gara_manager_required

from . import competition_bp
from .detail import contesto_direzione


@competition_bp.route("/<int:gara_id>/impostazioni")
@login_required
@gara_manager_required
def gara_impostazioni(gara_id):
    gara = db.get_or_404(Gara, gara_id)
    contesto = contesto_direzione(gara)
    return render_template(
        "direttore/impostazioni.html",
        gara=gara,
        user_can_manage=True,
        in_preparazione=gara.status == GaraStatus.SETUP.value,
        campionato_ctx=contesto_campionato(gara),
        **contesto,
    )
