# routes/admin/competition/vetrina.py
"""Come si presenta una gara quando il direttore la condivide (issue #235).

Tre decisioni, e nessuna riguarda il gioco: la **locandina**, un **link
esterno** (regolamento, pagina della sala) e l'**indirizzo leggibile** da
dettare al telefono al posto del token.

Perché una schermata a parte e non tre campi nel modulo della gara: quel
modulo è già lungo, si compila una volta prima di aprire le iscrizioni e parla
solo di regole di gioco. Queste tre cose invece si ritoccano dopo — la
locandina arriva quando il grafico l'ha finita, il link quando il regolamento
è pubblicato — e vanno raggiunte dalla pagina della gara con un click, non
riaprendo la configurazione di una gara già avviata.

Le regole di scrittura (normalizzazione dello slug, unicità contro token e
slug, rifiuto di un `javascript:`) stanno in `models/competition/
showcase_service.py`: qui c'è solo la traduzione fra richiesta e servizio.
"""

import os

from flask import flash, redirect, render_template, request, url_for
from flask_babel import _
from flask_login import login_required
from werkzeug.utils import secure_filename

from models import db, Gara
from models.base import utc_now
from models.competition.showcase_service import (
    set_gara_banner,
    update_gara_showcase,
)
from models.exceptions import DomainError
from utils import gara_manager_required
from utils.image_paths import ImagePathManager
from utils.image_upload import estensione_ammessa, salva_immagine_ridimensionata

from . import competition_bp

#: La locandina si salva alla misura dell'anteprima social. Più grande non
#: servirebbe a niente — i client la ricomprimono comunque — e su una
#: connessione mobile la pagina la aspetterebbe.
MISURA_BANNER = (1200, 630)


def _torna_alla_vetrina(gara_id: int) -> str:
    return url_for("admin.competition.gara_vetrina", gara_id=gara_id)


@competition_bp.route("/<int:gara_id>/vetrina")
@login_required
@gara_manager_required
def gara_vetrina(gara_id):
    """La schermata da cui si cura la pagina pubblica della gara."""
    gara = db.get_or_404(Gara, gara_id)

    from models.competition.services import GaraService

    token = gara.public_token or GaraService.ensure_public_token(gara_id)
    indirizzo = gara.slug or token

    banner_proprio = (
        ImagePathManager.url_from_db_path(gara.banner_path)
        if gara.banner_path
        else None
    )
    banner_effettivo = (
        ImagePathManager.url_from_db_path(gara.effective_banner_path)
        if gara.effective_banner_path
        else None
    )

    return render_template(
        "admin/gara_vetrina.html",
        gara=gara,
        banner_proprio=banner_proprio,
        banner_effettivo=banner_effettivo,
        # Il banner **ereditato** si distingue da quello proprio: il direttore
        # deve sapere se sta guardando la grafica del campionato o una scelta
        # sua, altrimenti «Rimuovi» sembra non funzionare.
        banner_ereditato=banner_effettivo is not None and banner_proprio is None,
        url_pubblica=url_for("main.gara_invite", token=indirizzo, _external=True),
        url_anteprima=url_for("main.gara_invite", token=indirizzo, anteprima=1),
    )


@competition_bp.route("/<int:gara_id>/vetrina", methods=["POST"])
@login_required
@gara_manager_required
def salva_gara_vetrina(gara_id):
    """Indirizzo leggibile e link esterno."""
    db.get_or_404(Gara, gara_id)
    try:
        update_gara_showcase(
            gara_id,
            slug=request.form.get("slug"),
            external_url=request.form.get("external_url"),
            external_label=request.form.get("external_label"),
        )
        flash(_("Vetrina aggiornata."), "success")
    except DomainError as errore:
        flash(str(errore), "danger")
    return redirect(_torna_alla_vetrina(gara_id))


@competition_bp.route("/<int:gara_id>/vetrina/banner", methods=["POST"])
@login_required
@gara_manager_required
def carica_banner_gara(gara_id):
    """Carica la locandina di una gara."""
    db.get_or_404(Gara, gara_id)

    file = request.files.get("banner")
    if file is None or not file.filename:
        flash(_("Nessuna immagine selezionata."), "warning")
        return redirect(_torna_alla_vetrina(gara_id))

    if not estensione_ammessa(file.filename):
        flash(_("Formato non supportato. Usa JPG, PNG o GIF."), "danger")
        return redirect(_torna_alla_vetrina(gara_id))

    try:
        # Il nome porta l'id e il momento del caricamento: due locandine per la
        # stessa gara non si sovrascrivono, e una pagina già aperta da qualcuno
        # continua a mostrare quella che stava vedendo invece di un'immagine
        # cambiata sotto i piedi.
        nome = secure_filename(
            f"gara_{gara_id}_{utc_now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        )
        ImagePathManager.ensure_banner_upload_dir()
        percorso = os.path.join(ImagePathManager.get_banner_upload_dir(), nome)
        salva_immagine_ridimensionata(file, percorso, max_size=MISURA_BANNER)
        set_gara_banner(gara_id, ImagePathManager.get_banner_db_path(nome))
        flash(_("Locandina caricata."), "success")
    except Exception as errore:  # noqa: BLE001 — il messaggio va all'utente
        flash(
            _("Non è stato possibile caricare l'immagine: %(errore)s", errore=errore),
            "danger",
        )

    return redirect(_torna_alla_vetrina(gara_id))


@competition_bp.route("/<int:gara_id>/vetrina/banner/rimuovi", methods=["POST"])
@login_required
@gara_manager_required
def rimuovi_banner_gara(gara_id):
    """Toglie la locandina propria della gara.

    Il file su disco resta: potrebbe essere ancora servito a chi ha la pagina
    aperta, e non vale la pena rischiare un 404 su un'immagine per recuperare
    qualche decina di kilobyte.
    """
    db.get_or_404(Gara, gara_id)
    set_gara_banner(gara_id, None)
    flash(
        _("Locandina rimossa: la gara torna a usare quella del campionato, se c'è."),
        "info",
    )
    return redirect(_torna_alla_vetrina(gara_id))
