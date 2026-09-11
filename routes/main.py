# routes/main.py - AGGIORNATO per correggere import path
from urllib.parse import urljoin

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
)
from flask_login import current_user, logout_user
from models import db, Campionato, Gara, User

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Homepage pubblica; se autenticato → dashboard utente"""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    from models.dashboard.dashboard_service import DashboardService

    # La home dell'ospite è la sua dashboard: stessi elenchi, stesse tessere
    # (regola 1 del 2026-09-10), senza nessun fatto suo.
    vm = DashboardService.for_guest()
    if not vm.ha_qualcosa_da_mostrare:
        return render_template("no_campionato.html")

    return render_template("index.html", vm=vm)


@main_bp.route("/privacy")
def privacy_policy():
    """Informativa privacy e cookie - pagina pubblica.

    Necessaria perché il sito usa uno strumento di analisi del traffico
    (Google Analytics). Il template legge da sé `config.GA_MEASUREMENT_ID`
    per mostrare la sezione sui cookie analitici solo quando il tracking è
    effettivamente attivo.
    """
    return render_template("privacy.html")


@main_bp.route("/reset")
def reset_database():
    """Reset completo del database - SOLO in modalità debug"""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Reset non disponibile in produzione", 403

    from utils.reset_manager import ResetManager

    manager = ResetManager()
    reset_options = manager.get_reset_options()

    return render_template("reset.html", reset_options=reset_options)


@main_bp.route("/reset/confirm", methods=["POST"])
def reset_database_confirm():
    """Conferma reset database"""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Reset non disponibile in produzione", 403

    password = request.form.get("password", "")
    reset_type = request.form.get("reset_type", "base")

    if password != "RESET_DB_CONFIRM":
        flash("Password di conferma errata!")
        return redirect(url_for("main.reset_database"))

    try:
        # LOGOUT dell'utente corrente prima del reset
        if current_user.is_authenticated:
            logout_user()

        from utils.reset_manager import ResetManager

        manager = ResetManager()
        result = manager.execute_reset(reset_type)

        if result["status"] == "success":
            flash(result["message"])
            flash("Sei stato disconnesso automaticamente. Rieffettua il login.", "info")
        else:
            flash(f"Errore: {result['message']}", "danger")

        return redirect(url_for("main.index"))

    except Exception as e:
        flash(f"Errore durante il reset: {str(e)}")
        return redirect(url_for("main.reset_database"))


@main_bp.route("/debug/login/<username>")
def quick_login(username):
    """Quick login per debug - SOLO in modalità debug"""
    from flask_login import login_user

    if not current_app.config.get("DEBUG_MODE", False):
        return "Quick login non disponibile in produzione", 403

    user = User.query.filter_by(username=username).first()
    if not user:
        flash(f"Utente {username} non trovato!")
        return redirect(url_for("main.index"))

    login_user(user)
    flash(f"Quick login effettuato come {username}!")

    return redirect(url_for("dashboard.dashboard"))


@main_bp.route("/campionatos")
def public_campionatos_list():
    """Lista pubblica dei campionati - visibile ai guest.

    Supporta filtro di stato derivato (in_corso/completati/terminati/all) e
    ricerca per nome. Lo stato è calcolato da `compute_campionato_status`
    via `Campionato.get_status()` e quindi va filtrato in Python — non c'è
    una colonna SQL equivalente.
    """
    from models.status_enum import TournamentStatus

    raw_status = (request.args.get("status") or "all").strip().lower()
    raw_query = (request.args.get("q") or "").strip()

    valid_statuses = {"all", "in_corso", "completati", "terminati"}
    status_filter = raw_status if raw_status in valid_statuses else "all"

    # is_deleted=False include i terminated come archivio storico
    # (vedi ADR-030 §"Scope"). is_active=False (terminated) appare
    # sotto filtro status="terminati".
    # Eager-load playoff config + tournament SEMPRE: get_status() viene chiamato
    # sia dal filtro per status sotto, sia dal template (badge status_badge_class
    # / status_text per OGNI campionato), e per i terminated consulta queste
    # relationship → senza eager-load resterebbe N+1 anche con status=all.
    from sqlalchemy.orm import joinedload
    from models.playoff.models import PlayoffConfiguration

    query = Campionato.query.filter_by(is_deleted=False).options(
        joinedload(Campionato.playoff_configurations).joinedload(
            PlayoffConfiguration.playoff_campionato
        )
    )
    if raw_query:
        query = query.filter(Campionato.name.ilike(f"%{raw_query}%"))

    campionatos = query.order_by(Campionato.created_at.desc()).all()

    if status_filter != "all":
        wanted = {
            "in_corso": {
                TournamentStatus.SETUP.value,
                TournamentStatus.REGISTRATION_OPEN.value,
                TournamentStatus.IN_PROGRESS.value,
                # Gare finite ma campionato non chiuso: la classifica generale
                # non è consolidata, quindi per chi legge è ancora in corso.
                # Senza questa riga sparirebbe da ogni secchiello tranne
                # "Tutti", perché prima si spacciava per COMPLETED.
                TournamentStatus.AWAITING_CLOSURE.value,
            },
            "completati": {TournamentStatus.COMPLETED.value},
            # La chiave dell'URL resta "terminati" per non rompere i link già
            # in giro; l'etichetta nel selettore dice ora cosa significa.
            "terminati": {TournamentStatus.AWAITING_PLAYOFF.value},
        }[status_filter]
        campionatos = [c for c in campionatos if c.get_status() in wanted]

    # La spia della partecipazione: è lo storico dei campionati, e chi
    # guarda deve riconoscere i suoi fra quelli di tutti.
    from models.storico.campionati import spie_partecipazione

    user_id = current_user.id if current_user.is_authenticated else None

    return render_template(
        "public/campionatos_list.html",
        campionatos=campionatos,
        status_filter=status_filter,
        search_query=raw_query,
        spie=spie_partecipazione(campionatos, user_id),
    )


@main_bp.route("/campionato/<int:campionato_id>/public")
def campionato_detail_public(campionato_id):
    """Dettaglio campionato pubblico - visibile ai guest"""
    from models.campionato.services import TournamentService
    from models.status_enum import GaraStatus

    campionato = db.get_or_404(Campionato, campionato_id)

    # Tutte le gare del campionato
    gare = Gara.query.filter_by(campionato_id=campionato_id).order_by(Gara.number).all()

    # Calculate general classification using the service (handles Amalfi, Random, etc.)
    campionato_service = TournamentService()
    general_classification = campionato_service.calculate_general_classification(
        campionato_id
    )

    # Determine last completed gara number
    last_completed_gara_number = None
    gare_concluse = [g for g in gare if g.status == GaraStatus.COMPLETED.value]
    if gare_concluse:
        last_completed_gara_number = max(g.number for g in gare_concluse)

    return render_template(
        "public/campionato_detail.html",
        campionato=campionato,
        gare=gare,
        general_classification=general_classification,
        last_completed_gara_number=last_completed_gara_number,
    )


@main_bp.route("/garas")
def public_garas_list():
    """Lista pubblica delle gare standalone - visibile ai guest.

    B5: split active vs completed gare so the guest sees two distinct
    sections instead of completed gare mixed with active ones.
    """
    from models.status_enum import GaraStatus
    from datetime import date as _date
    from sqlalchemy import and_, or_

    # SETUP con data passata = zombie, visibili solo al director (ADR-030
    # rev 2026-05-14). Le SETUP con data futura/NULL restano visibili al
    # pubblico come "in preparazione".
    today = _date.today()
    standalone_garas = (
        Gara.query.filter_by(campionato_id=None)
        .filter(
            or_(
                Gara.status != GaraStatus.SETUP.value,
                and_(
                    Gara.status == GaraStatus.SETUP.value,
                    or_(Gara.date.is_(None), Gara.date >= today),
                ),
            )
        )
        .order_by(Gara.date.desc())
        .all()
    )

    completed_status = GaraStatus.COMPLETED.value
    active_garas = [g for g in standalone_garas if g.status != completed_status]
    completed_garas = [g for g in standalone_garas if g.status == completed_status]

    return render_template(
        "public/garas_list.html",
        active_garas=active_garas,
        completed_garas=completed_garas,
    )


@main_bp.route("/storico")
def storico_gare():
    """Lo storico delle gare concluse, di tutti (regola 2 del 2026-09-10).

    La dashboard e la home tengono l'ultima conclusa e quelle dell'ultimo
    mese; il resto sta qui, con la ricerca e i filtri. Le regole — cosa è
    concluso, cosa vuol dire «mio» — stanno in `models/storico/gare.py`:
    qui si leggono i parametri e si formano le etichette dei mesi, nella
    lingua di chi legge.
    """
    from datetime import date as _date

    from flask_babel import format_date, gettext

    from models.storico.gare import (
        SCELTE_PRIMI,
        FiltriStorico,
        costruisci_storico,
    )

    filtri = FiltriStorico.da_parametri(request.args)
    user_id = current_user.id if current_user.is_authenticated else None
    storico = costruisci_storico(filtri, user_id)
    gruppi = [
        (
            (
                format_date(_date(anno, mese, 1), "LLLL yyyy").capitalize()
                if anno
                else gettext("Senza data")
            ),
            righe,
        )
        for (anno, mese), righe in storico.gruppi
    ]
    return render_template(
        "public/storico_gare.html",
        storico=storico,
        filtri=filtri,
        gruppi=gruppi,
        scelte_primi=SCELTE_PRIMI,
    )


def _render_vetrina(gara, identificatore: str):
    """La pagina-vetrina di una gara, con i meta che i social leggono.

    L'immagine e l'indirizzo sono **assoluti** (`_external=True`): lo scraper
    di Facebook o WhatsApp non risolve i percorsi relativi, e un `og:image`
    che comincia per `/static/` gli risulta semplicemente assente — l'unico
    sintomo è un'anteprima senza figura, che in sviluppo non si vede mai.
    """
    from models.competition.showcase_view import costruisci_vetrina, descrizione_social

    vetrina = costruisci_vetrina(gara)

    # Un solo ripiego, deciso dalla vista: quello che finisce nei meta è
    # esattamente l'immagine che apre la pagina.
    immagine = urljoin(request.url_root, vetrina.banner_url.lstrip("/"))

    # Il sopratitolo porta alla vetrina del campionato, se ce n'è una da
    # aprire. Un campionato eliminato o senza indirizzo pubblico lascia il
    # sopratitolo inerte: meglio un testo che non si clicca di un link che
    # porta a un 404.
    url_campionato = None
    campionato = gara.campionato
    if campionato is not None and not campionato.is_deleted:
        indirizzo_campionato = campionato.public_slug_or_token
        if indirizzo_campionato:
            url_campionato = url_for(
                "main.campionato_invite", identificatore=indirizzo_campionato
            )

    return render_template(
        "public/vetrina_gara.html",
        vetrina=vetrina,
        gara=gara,
        url_campionato=url_campionato,
        social_title=vetrina.titolo,
        social_description=descrizione_social(vetrina),
        social_image=immagine,
        social_url=url_for("main.gara_invite", token=identificatore, _external=True),
        # Dove porta «Iscriviti» per chi non ha ancora un account: al login,
        # con il ritorno **qui**. Da autenticato questo stesso indirizzo
        # riporta al flusso di iscrizione di sempre, quindi il giro si chiude
        # da solo senza una seconda route da tenere allineata.
        url_iscrizione=url_for(
            "auth.login",
            next=url_for("main.gara_invite", token=identificatore),
        ),
        # Dove va chi arriva su una gara a cui non può più iscriversi. Non è
        # un ripiego: è la persona più interessata alle prossime che questa
        # pagina incontrerà, e mandarla in un vicolo cieco sarebbe uno spreco.
        url_altre_gare=url_for("main.public_garas_list"),
    )


@main_bp.route("/g/<token>")
def gara_invite(token):
    """Link pubblico di una gara: vetrina per chi arriva, iscrizione per chi c'è.

    È l'indirizzo che il direttore stampa su una locandina o incolla in un
    post — `/g/<token>` o, se ne ha scelto uno, `/g/<nome-leggibile>`: sono
    due nomi per la stessa pagina e restano validi entrambi, così una
    locandina già stampata non smette di funzionare.

    **Chi non è autenticato vede la vetrina** (issue #235): nome, formato,
    quando, dove, quanto costa, quanti posti restano, e un pulsante
    «Iscriviti» che lo porta a registrarsi e lo riporta esattamente qui. Fino
    al 2026-08 questo indirizzo rispondeva a un anonimo con un redirect al
    login, e siccome è quello che il direttore condivide, era anche quello che
    lo scraper di WhatsApp o Facebook trovava: l'anteprima del link mostrava
    la pagina di accesso, e nessun meta Open Graph avrebbe potuto rimediare.

    Chi è autenticato prosegue come sempre — dialog di stato e pagina della
    gara — perché lì l'iscrizione è a un click e la vetrina sarebbe un
    passaggio in più. Con `?anteprima=1` vede comunque la vetrina: serve al
    direttore per controllare cosa sta pubblicando.

    Chi lo segue arriva sulla pagina della gara con l'iscrizione in
    evidenza e conferma con un click. Chi non è autenticato passa da
    login/registrazione e torna qui, allo stesso punto.

    L'iscrizione non avviene aprendo il link. Quell'indirizzo è pubblico per
    costruzione, quindi chiunque lo conosca potrebbe incorporarlo altrove
    (`<img src="...">`) e iscrivere a sua insaputa chi passa di lì con la
    sessione aperta, sottraendo un posto a qualcun altro; il token casuale
    protegge dall'indovinarlo, non da questo. Resta la POST protetta da CSRF.

    Ogni altro caso (gara inesistente, iscrizioni non ancora aperte o già
    chiuse, gara in corso o conclusa) risponde con una dialog che dice cosa
    sta succedendo: chi arriva da una locandina non ha altro contesto.
    """
    from flask_babel import gettext as _
    from models.competition.invite_service import (
        GaraInviteService,
        InviteOutcome,
    )
    from models.competition.showcase_service import resolve_public_identifier
    from utils.jinja import format_datetime_local_text
    from utils.page_modal import flash_page_modal

    gara = resolve_public_identifier(token)
    if gara is None:
        # Il token non dice se la gara non è mai esistita o è stata
        # cancellata, e va bene così: la pagina non deve fare da oracolo.
        return render_template("public/invite_not_found.html"), 404

    vuole_anteprima = request.args.get("anteprima") == "1"
    if not current_user.is_authenticated or vuole_anteprima:
        return _render_vetrina(gara, token)

    result = GaraInviteService.evaluate(gara, current_user)

    gara_name = gara.display_name
    # Le due date vanno trattate una per una: `format_datetime_local_text`
    # rende "N/A" su None, e una finestra con una sola data impostata
    # diventerebbe "Iscrizioni dal N/A al 12/09" — peggio che tacere.
    inscription_window = None
    if gara.inscription_start and gara.inscription_end:
        inscription_window = _(
            "Iscrizioni dal %(start)s al %(end)s.",
            start=format_datetime_local_text(gara.inscription_start),
            end=format_datetime_local_text(gara.inscription_end),
        )
    elif gara.inscription_end:
        inscription_window = _(
            "Iscrizioni aperte fino al %(end)s.",
            end=format_datetime_local_text(gara.inscription_end),
        )
    elif gara.inscription_start:
        inscription_window = _(
            "Iscrizioni aperte dal %(start)s.",
            start=format_datetime_local_text(gara.inscription_start),
        )

    if result.outcome == InviteOutcome.ALREADY_INSCRIBED:
        flash_page_modal(
            title=_("Sei già iscritto"),
            body=_("Risulti iscritto a %(gara)s.", gara=gara_name),
            variant="success",
            icon="fa-circle-check",
        )
    elif result.outcome == InviteOutcome.ALREADY_WAITLISTED:
        flash_page_modal(
            title=_("Sei in lista d'attesa"),
            body=_(
                "Sei in lista d'attesa per %(gara)s, in posizione "
                "%(position)s. Se si libera un posto entri automaticamente.",
                gara=gara_name,
                position=result.waitlist_position,
            ),
            variant="warning",
            icon="fa-hourglass-half",
        )
    elif result.outcome == InviteOutcome.CONFIRM_NEEDED:
        flash_page_modal(
            title=_("Puoi iscriverti"),
            body=_(
                "Le iscrizioni a %(gara)s sono aperte: premi «Iscriviti» "
                "per confermare.",
                gara=gara_name,
            ),
            variant="info",
            icon="fa-user-plus",
            detail=inscription_window,
        )
    elif result.outcome == InviteOutcome.NOT_OPEN_YET:
        flash_page_modal(
            title=_("Iscrizioni non ancora aperte"),
            body=_(
                "Le iscrizioni a %(gara)s non sono ancora aperte.",
                gara=gara_name,
            ),
            variant="info",
            icon="fa-clock",
            detail=inscription_window,
        )
    elif result.outcome == InviteOutcome.CLOSED:
        flash_page_modal(
            title=_("Iscrizioni chiuse"),
            body=_("Le iscrizioni a %(gara)s sono chiuse.", gara=gara_name),
            variant="warning",
            icon="fa-lock",
            detail=inscription_window,
        )
    elif result.outcome == InviteOutcome.IN_PROGRESS:
        flash_page_modal(
            title=_("Gara già iniziata"),
            body=_(
                "%(gara)s è già iniziata: non è più possibile iscriversi, "
                "ma puoi seguire i risultati da questa pagina.",
                gara=gara_name,
            ),
            variant="info",
            icon="fa-play",
        )
    elif result.outcome == InviteOutcome.COMPLETED:
        flash_page_modal(
            title=_("Gara conclusa"),
            body=_(
                "%(gara)s è conclusa: qui trovi la classifica finale.",
                gara=gara_name,
            ),
            variant="info",
            icon="fa-flag-checkered",
        )
    elif result.outcome == InviteOutcome.CANCELLED:
        flash_page_modal(
            title=_("Gara annullata"),
            body=_("%(gara)s è stata annullata.", gara=gara_name),
            variant="danger",
            icon="fa-ban",
        )
    elif result.outcome == InviteOutcome.ERROR:
        flash_page_modal(
            title=_("Iscrizione non riuscita"),
            body=_(
                "Non è stato possibile iscriverti a %(gara)s. Riprova dal "
                "pulsante «Iscriviti».",
                gara=gara_name,
            ),
            variant="danger",
            icon="fa-triangle-exclamation",
        )
    # InviteOutcome.NOT_ELIGIBLE: admin, direttore della gara o playoff.
    # Nessuna dialog — la pagina che si apre gli dice già tutto quello che
    # può fare, e un avviso "non puoi iscriverti" al direttore che apre il
    # proprio link sarebbe rumore.

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara.id))


@main_bp.route("/c/<identificatore>")
def campionato_invite(identificatore):
    """Link pubblico di un campionato: la sua vetrina (issue #235).

    `/c/<token>` o, se il direttore ne ha scelto uno, `/c/<nome-leggibile>`:
    due nomi per la stessa pagina, entrambi validi per sempre, come per le
    gare.

    A differenza di `/g/<token>` **non cambia in base a chi guarda**: qui non
    c'è un'azione da compiere sul campionato — ci si iscrive alle sue prove,
    non a lui — quindi la vetrina è la pagina giusta anche per chi è già
    autenticato, e non c'è un flusso alternativo da saltare.
    """
    from models.campionato.showcase_view import (
        costruisci_vetrina_campionato,
        descrizione_social_campionato,
    )
    from models.competition.showcase_service import (
        resolve_public_identifier_campionato,
    )

    campionato = resolve_public_identifier_campionato(identificatore)
    if campionato is None:
        return render_template("public/invite_not_found.html"), 404

    vetrina = costruisci_vetrina_campionato(campionato)

    # Assoluti, come per la gara: uno scraper non risolve i relativi, e il
    # sintomo di un `og:image` relativo è un'anteprima senza figura — nessun
    # errore, niente nei log, invisibile in sviluppo.
    # Un solo ripiego, deciso dalla vista: quello che finisce nei meta è
    # esattamente l'immagine che apre la pagina.
    immagine = urljoin(request.url_root, vetrina.banner_url.lstrip("/"))

    return render_template(
        "public/vetrina_campionato.html",
        vetrina=vetrina,
        campionato=campionato,
        social_title=vetrina.titolo,
        social_description=descrizione_social_campionato(vetrina),
        social_image=immagine,
        social_url=url_for(
            "main.campionato_invite", identificatore=identificatore, _external=True
        ),
    )


@main_bp.route("/gara/<int:gara_id>")
@main_bp.route("/public/gara/<int:gara_id>")
def gara_detail_public(gara_id):
    """
    DEPRECATED: Redirect to unified gara_detail view.
    La vista unificata in admin.competition.gara_detail si adatta
    automaticamente in base ai permessi dell'utente (anche per guest).
    """
    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@main_bp.route("/reset/save", methods=["POST"])
def save_reset_snapshot():
    """Salva lo stato corrente del database come snapshot"""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    name = request.form.get("name", "")
    description = request.form.get("description", "")

    if not name:
        flash("Il nome dello snapshot è obbligatorio!", "danger")
        return redirect(request.referrer or url_for("main.reset_database"))

    from utils.reset_manager import ResetManager

    manager = ResetManager()
    result = manager.save_current_state(name, description)

    if result["status"] == "success":
        flash(result["message"], "success")
    else:
        flash(result["message"], "danger")

    return redirect(request.referrer or url_for("main.reset_database"))


@main_bp.route("/debug/create_player")
def debug_create_player():
    """Crea un nuovo player con username 'player N' - SOLO in modalità debug"""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    from models.user.models import User

    # Trova il prossimo numero disponibile
    counter = 1
    while True:
        username = f"player{counter}"
        existing = User.query.filter_by(username=username).first()
        if not existing:
            break
        counter += 1

    # Crea il nuovo utente usando il servizio
    from models.user.services import UserService

    UserService.create_user(
        username=username,
        email=f"{username}@debug.local",
        role="player",
        password="123456",  # Il servizio si occupa dell'hashing
        send_verification_email=False,  # Skip email for debug users
    )

    flash(f"Player '{username}' creato con successo! Password: 123456", "success")
    return redirect(request.referrer or url_for("dashboard.dashboard"))


def _available_quick_login_players(gara_id: int):
    """Quick-login players (role=PLAYER) non già iscritti alla gara,
    in ordine quick-login (admin/director esclusi)."""
    from models.competition.models import Inscription
    from utils.database_utils import get_quick_login_users
    from models.user.role_enum import UserRole

    inscribed_ids = {
        i.user_id for i in Inscription.query.filter_by(gara_id=gara_id).all()
    }
    return [
        u
        for u in get_quick_login_users(limit=32)
        if u.role == UserRole.PLAYER.value and u.id not in inscribed_ids
    ]


def _current_active_inscriptions(gara_id: int) -> int:
    from models.competition.models import Inscription

    return Inscription.query.filter_by(
        gara_id=gara_id, is_waitlist=False, is_withdrawn=False
    ).count()


@main_bp.route("/debug/fill_gara/<int:gara_id>")
def debug_fill_gara(gara_id):
    """Riempi la gara fino al MIN partecipanti pescando dai quick-login."""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    gara = Gara.query.get_or_404(gara_id)
    current_active = _current_active_inscriptions(gara_id)

    min_required = gara.min_participants or 0
    if min_required <= 0:
        flash(
            "min_participants non impostato per questa gara: nulla da fare.",
            "info",
        )
        return redirect(request.referrer or url_for("dashboard.dashboard"))

    slots_needed = max(0, min_required - current_active)
    if slots_needed == 0:
        flash(
            f"Minimo già raggiunto ({current_active}/{min_required}).",
            "info",
        )
        return redirect(request.referrer or url_for("dashboard.dashboard"))

    # Rispetta anche il limite massimo, se più stringente
    if gara.max_participants and gara.max_participants > 0:
        slots_needed = min(slots_needed, gara.max_participants - current_active)

    candidates = _available_quick_login_players(gara_id)
    if not candidates:
        flash(
            "Nessun giocatore quick-login disponibile da iscrivere.",
            "info",
        )
        return redirect(request.referrer or url_for("dashboard.dashboard"))

    from models.competition.inscription_service import InscriptionService

    new_inscriptions = 0
    for player in candidates[:slots_needed]:
        inscription = InscriptionService.inscribe_user(player.id, gara_id)
        if inscription:
            new_inscriptions += 1

    flash(
        f"Aggiunti {new_inscriptions} iscritti dai quick-login. "
        f"Totale attivi: {current_active + new_inscriptions}/{min_required}",
        "success",
    )
    return redirect(
        request.referrer or url_for("admin.competition.gara_detail", gara_id=gara_id)
    )


@main_bp.route("/debug/inscribe_next_player/<int:gara_id>")
def debug_inscribe_next_player(gara_id):
    """Iscrive il prossimo quick-login player non ancora iscritto."""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    gara = Gara.query.get_or_404(gara_id)
    current_active = _current_active_inscriptions(gara_id)

    if gara.max_participants and current_active >= gara.max_participants:
        flash(
            f"Massimo raggiunto ({current_active}/{gara.max_participants}).",
            "info",
        )
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    candidates = _available_quick_login_players(gara_id)
    if not candidates:
        flash(
            "Nessun giocatore quick-login disponibile da iscrivere.",
            "info",
        )
        return redirect(
            request.referrer
            or url_for("admin.competition.gara_detail", gara_id=gara_id)
        )

    from models.competition.inscription_service import InscriptionService

    player = candidates[0]
    inscription = InscriptionService.inscribe_user(player.id, gara_id)

    if inscription:
        flash(
            f"Iscritto '{player.username}'. "
            f"Totale attivi: {current_active + 1}"
            f"{'/' + str(gara.max_participants) if gara.max_participants else ''}",
            "success",
        )
    else:
        flash(f"Iscrizione di '{player.username}' fallita.", "warning")

    return redirect(
        request.referrer or url_for("admin.competition.gara_detail", gara_id=gara_id)
    )


def _debug_torna_alla_gara(gara_id: int):
    return redirect(
        request.referrer or url_for("admin.competition.gara_detail", gara_id=gara_id)
    )


def _debug_simula(gara_id: int, azione: str):
    """Le tre azioni di debug sui risultati passano dal servizio della prova.

    Nate qui come `_debug_*`, vivono ora in
    `models/prova/simulation_service.py` (ADR-058, tappa 2): una sola
    implementazione, e i pulsanti della competizione di prova la usano in
    produzione. Qui resta il guard `DEBUG_MODE` e la traduzione dell'esito in
    un messaggio.
    """
    from models.exceptions import DomainError
    from models.prova.simulation_service import SimulationService

    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    Gara.query.get_or_404(gara_id)
    try:
        # Il footer serve a far avanzare la gara: chiude anche le partite che
        # nella prova resterebbero in attesa del direttore.
        if azione == "simula_gara":
            esito = SimulationService.simula_gara(gara_id)
        else:
            esito = getattr(SimulationService, azione)(gara_id, chiudi_tutto=True)
    except DomainError as errore:
        flash(str(errore), "warning")
        return _debug_torna_alla_gara(gara_id)

    if esito.partite_chiuse == 0 and esito.turni_avviati == 0:
        flash("Nessuna partita da simulare.", "info")
    elif azione == "simula_partita":
        flash(
            f"Completato 1 match (#{esito.partita_id}) del turno {esito.turno} "
            f"({esito.tavoli_riassegnati} tavoli riassegnati).",
            "success",
        )
    elif azione == "simula_turno":
        flash(
            f"Completati {esito.partite_chiuse} match del turno {esito.turno} "
            f"({esito.tavoli_riassegnati} tavoli riassegnati ai turni successivi).",
            "success",
        )
    else:
        flash(
            f"Complete gara: {esito.partite_chiuse} match completati, "
            f"{esito.turni_avviati} turni avanzati.",
            "success",
        )
        if esito.fermata:
            flash(f"Stop {esito.fermata}.", "warning")
    return _debug_torna_alla_gara(gara_id)


@main_bp.route("/debug/complete_current_round/<int:gara_id>")
def debug_complete_current_round(gara_id):
    """Completa i match del primo round attivo con risultati simulati."""
    return _debug_simula(gara_id, "simula_turno")


@main_bp.route("/debug/complete_next_match/<int:gara_id>")
def debug_complete_next_match(gara_id):
    """Completa UN match al tavolo con un risultato simulato."""
    return _debug_simula(gara_id, "simula_partita")


@main_bp.route("/debug/complete_gara/<int:gara_id>")
def debug_complete_gara(gara_id):
    """Completa l'intera gara: cicla sui turni fino alla fine."""
    return _debug_simula(gara_id, "simula_gara")


@main_bp.route("/reset/delete/<snapshot_id>", methods=["POST"])
def delete_reset_snapshot(snapshot_id):
    """Elimina uno snapshot salvato"""
    if not current_app.config.get("DEBUG_MODE", False):
        return "Funzione non disponibile in produzione", 403

    from utils.reset_manager import ResetManager

    manager = ResetManager()
    result = manager.delete_snapshot(snapshot_id)

    if result["status"] == "success":
        flash(result["message"], "success")
    else:
        flash(result["message"], "danger")

    return redirect(url_for("main.reset_database"))
