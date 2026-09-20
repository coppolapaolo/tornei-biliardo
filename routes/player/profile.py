# routes/player/profile.py
"""User profile display and editing routes.

Privacy, account deletion, and export routes have been split into:
- privacy.py: Privacy settings and hide/show routes
- account.py: Account deletion
- exports.py: CSV and GDPR data export
"""

from flask import (
    current_app,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from flask_login import login_required, current_user, login_user
from flask_babel import gettext as _

from models import db, Gara, Inscription
from models.status_enum import GaraStatus
from models.campionato.models import Campionato
from models.user.models import User
from models.user.services import UserService
from models.user.permission_service import UserPermissionService
from models.user.runout_stats import runout_summary
from utils import feature_required, player_only
from utils.route_helpers import handle_service_action

from . import player_bp

# ============ PROFILO UTENTE E GESTIONE ACCOUNT ============


def _training_overview(user_id: int) -> dict:
    """Storico d'allenamento per il profilo, o un guscio vuoto (US-P9).

    Il profilo si deve aprire anche se questa sezione non si carica: è un
    riquadro, non la pagina. L'errore però si **scrive** — è la lezione del bug
    che l'ha tenuta vuota per mesi senza lasciare traccia da nessuna parte.
    """
    from models.challenge.training_service import TrainingHistoryService

    try:
        return TrainingHistoryService.get_training_overview(user_id)
    except Exception:
        current_app.logger.warning(
            "Storico d'allenamento non caricato per il profilo", exc_info=True
        )
        return {"stats": None, "history": [], "drills": [], "exams": []}


@player_bp.route("/profile")
@login_required
@player_only
def profile():
    """Profilo personale del giocatore"""
    from models.classification.models import Classification
    from models.player.history_service import HistoryFilters, PlayerHistoryService

    # Iscrizioni dell'utente (incluse gare standalone)
    inscriptions = (
        Inscription.query.filter_by(user_id=current_user.id)
        .join(Gara)
        .outerjoin(Campionato)  # LEFT JOIN per includere gare standalone
        .order_by(Campionato.created_at.desc().nullslast(), Gara.date.desc())
        .all()
    )

    # Partite e statistiche: dalla **fonte unica** dello storico.
    #
    # Qui c'era una query sul solo `match`, con `join(Gara)` e il filtro sul
    # solo `CLOSED_UNILATERALLY`. Due errori sovrapposti, tutt'e due nella
    # tabella delle trappole di `CLAUDE.md`:
    #
    # - le sfide individuali stanno su `individual_match`, un'altra tabella:
    #   qui non potevano comparire in nessun modo;
    # - `CLOSED_UNILATERALLY` è la chiusura del **direttore**. Una partita
    #   chiusa dai due giocatori (`CONFIRMED_BY_BOTH`) non veniva contata — ed
    #   è esattamente così che finisce ogni sfida individuale.
    #
    # Lo storico completo faceva già la cosa giusta: il profilo mostrava meno
    # partite di quelle giocate, e senza errori da nessuna parte.
    pagina_partite, match_stats = PlayerHistoryService.get_unified_match_history(
        user_id=current_user.id,
        filters=HistoryFilters(),
        page=1,
        per_page=10,
    )
    recent_matches = pagina_partite.items

    # Classifiche per campionato
    classifications = (
        Classification.query.filter_by(user_id=current_user.id)
        .join(Campionato)
        .order_by(Campionato.created_at.desc())
        .all()
    )

    # Conta solo i campionati con gare completate dove l'utente ha partecipato
    completed_tournaments = set(
        [
            insc.gara.campionato_id
            for insc in inscriptions
            if insc.gara.campionato_id is not None
            and insc.gara.status == GaraStatus.COMPLETED.value
        ]
    )

    # Conta solo le gare completate
    completed_gare = len(
        [
            insc
            for insc in inscriptions
            if insc.gara.status == GaraStatus.COMPLETED.value
        ]
    )

    # Allenamento: drill (catalogo + gare) ed esami, da fonte unica (US-P9).
    # Prima questo blocco leggeva **solo** i drill giocati in gara, quindi
    # quelli del catalogo non comparivano da nessuna parte; e la vista del
    # profilo altrui ne costruiva una versione diversa, con un'altra forma.
    training = _training_overview(current_user.id)

    stats = {
        "total_inscriptions": len(inscriptions),
        "total_matches": match_stats.total_matches,
        "won_matches": match_stats.won_matches,
        "lost_matches": match_stats.lost_matches,
        "win_percentage": match_stats.win_percentage,
        "tournaments_played": len(completed_tournaments),
        "gare_played": completed_gare,
    }

    # Privacy context for template consistency (own profile always has full access)
    from models.user.privacy_service import PrivacyService
    from models.tpa.stats_service import TpaStatsService

    privacy = PrivacyService.get_privacy_settings(current_user.id)

    # TPA: compare a chi ha sbloccato il referto oppure a chi ha gia' giocato
    # una partita in cui qualcun altro lo teneva. `None` = qui non ci va.
    tpa_stats = TpaStatsService.profile_summary(current_user.id, user=current_user)

    # Runout: un numero, due fonti — il trattino sul tabellone e il tally del
    # referto TPA, che non convivono mai sulla stessa partita (ADR-056).
    # `tpa_stats` si passa perché è già stato calcolato qui sopra: ricalcolarlo
    # vorrebbe dire rigiocare ogni referto una seconda volta.
    stats["runouts"] = runout_summary(current_user.id, tpa_stats)

    return render_template(
        "player/profile.html",
        user=current_user,
        tpa_stats=tpa_stats,
        inscriptions=inscriptions,
        matches=recent_matches,
        classifications=classifications,
        stats=stats,
        challenge_stats=training["stats"],
        challenge_history=training["history"],
        training_drills=training["drills"],
        training_exams=training["exams"],
        # Privacy context for template
        privacy=privacy,
        is_admin=current_user.is_admin,
        is_own_profile=True,
    )


@player_bp.route("/ruoli")
@login_required
@player_only
def roles():
    """«I tuoi ruoli»: cosa sei, cosa puoi chiedere, cosa stai aspettando.

    Una pagina sua e non un riquadro del profilo: il profilo racconta come si
    gioca, questa dice che cosa si è. È anche il posto dove si diventa
    istruttore, con lo stesso percorso di «Diventa esaminatore» (ADR-069).
    """
    from models.user.role_enum import GrantableRole
    from models.user.role_grant_service import GRANT_POLICY, RoleGrantService
    from models.user.roles_view import build_roles_view

    user = db.session.get(User, current_user.id)
    if user is None:
        flash(_("Utente non trovato"), "danger")
        return redirect(url_for("dashboard.dashboard"))

    # La scuola si mostra a chi insegna o sta chiedendo di farlo: a chiunque
    # altro sarebbe un campo senza risposta a una domanda che non si è fatto.
    istruttore = GrantableRole.INSTRUCTOR
    mostra_scuola = bool(
        user.organization
        or RoleGrantService.has_role(user.id, istruttore)
        or RoleGrantService.get_pending_request(user.id, istruttore)
    )

    return render_template(
        "player/roles.html",
        user=user,
        righe=build_roles_view(user),
        mostra_scuola=mostra_scuola,
        # Chi può concedere un ruolo ha una coda di richieste da valutare, ed è
        # qui che la trova: prima stava solo nel catalogo esercizi, dichiarata
        # per il solo esaminatore (ADR-041, em. del 20/09).
        puo_valutare=any(
            RoleGrantService.can_grant(user, ruolo) for ruolo in GRANT_POLICY
        ),
    )


@player_bp.route("/ruoli/scuola", methods=["POST"])
@login_required
@player_only
def save_organization():
    """Salva (o cancella) la scuola o l'associazione di chi insegna."""
    scuola = (request.form.get("organization") or "").strip()[:120]

    return handle_service_action(
        action=lambda: UserService.update_user(
            current_user.id, organization=scuola or None
        ),
        redirect_url=url_for("player.roles"),
        success_message=_("Salvato."),
        error_prefix=None,
    )


@player_bp.route("/profile/<int:user_id>")
def view_profile(user_id):
    """View another player's public profile with privacy controls."""
    from models.user.models import User
    from models.competition.models import Gara, Inscription
    from models.campionato.models import Campionato
    from models.user.privacy_service import PrivacyService

    user = db.get_or_404(User, user_id)

    # Privacy context
    viewer_id = current_user.id if current_user.is_authenticated else None
    is_admin = current_user.is_authenticated and current_user.is_admin
    is_own_profile = viewer_id == user_id

    # Get privacy settings
    privacy = PrivacyService.get_privacy_settings(user_id)

    # Inscriptions (always loaded for statistics)
    inscriptions = (
        Inscription.query.filter_by(user_id=user.id)
        .join(Gara)
        .outerjoin(Campionato)
        .order_by(Campionato.created_at.desc().nullslast(), Gara.date.desc())
        .all()
    )

    # Partite: stessa fonte del profilo proprio, per la stessa ragione (vedi
    # `profile()`). Il profilo altrui contava e mostrava per conto suo, quindi
    # aveva entrambi i difetti in copia.
    from models.player.history_service import HistoryFilters, PlayerHistoryService

    tutte, _ = PlayerHistoryService.get_unified_match_history(
        user_id=user.id,
        filters=HistoryFilters(),
        page=1,
        per_page=1000,
    )

    # Le partite nascoste dal proprietario restano nascoste. L'elenco degli id
    # nascosti riguarda le partite di **gara**: una sfida individuale non si può
    # ancora nascondere, e gli id delle due tabelle si sovrappongono — filtrare
    # senza guardare la provenienza ne nasconderebbe una a caso.
    voci = PlayerHistoryService.filter_visible_entries(
        user_id=user_id,
        viewer_id=viewer_id,
        entries=tutte.items,
        is_admin=is_admin,
    )

    match_stats = PlayerHistoryService.stats_of(voci)
    total_matches = match_stats.total_matches
    won_matches = match_stats.won_matches
    win_percentage = match_stats.win_percentage

    # Partite recenti (ultime 10 visibili)
    recent_matches = voci[:10]

    # Completed tournaments count
    visible_inscriptions = PrivacyService.filter_visible_inscriptions(
        user_id=user_id,
        viewer_id=viewer_id,
        inscriptions=inscriptions,
        is_admin=is_admin,
    )

    completed_tournaments = set(
        [
            insc.gara.campionato_id
            for insc in visible_inscriptions
            if insc.gara.campionato_id is not None
            and insc.gara.status == GaraStatus.COMPLETED.value
        ]
    )

    completed_gare = len(
        [
            insc
            for insc in visible_inscriptions
            if insc.gara.status == GaraStatus.COMPLETED.value
        ]
    )

    stats = {
        "total_inscriptions": len(visible_inscriptions),
        "total_matches": total_matches,
        "won_matches": won_matches,
        "lost_matches": match_stats.lost_matches,
        "win_percentage": win_percentage,
        "tournaments_played": len(completed_tournaments),
        "gare_played": completed_gare,
    }

    # Allenamento: stessa fonte del profilo proprio. Prima qui si leggeva solo
    # il catalogo e si passavano al template gli oggetti ORM grezzi, che il
    # componente non sa leggere: le righe uscivano vuote, senza errore.
    training = _training_overview(user.id)

    from models.tpa.stats_service import TpaStatsService

    tpa_stats = TpaStatsService.profile_summary(user.id, user=user)
    stats["runouts"] = runout_summary(user.id, tpa_stats)

    return render_template(
        "player/profile.html",
        user=user,
        tpa_stats=tpa_stats,
        inscriptions=visible_inscriptions,
        matches=recent_matches,
        stats=stats,
        challenge_stats=training["stats"],
        challenge_history=training["history"],
        training_drills=training["drills"],
        training_exams=training["exams"],
        classifications=[],
        # Privacy context for template
        privacy=privacy,
        is_admin=is_admin,
        is_own_profile=is_own_profile,
    )


#: I campi che la schermata del profilo sa modificare.
#:
#: `squadra` è testo libero e la scrive solo il giocatore (US-1): non produce
#: alcun effetto da sé, serve a precompilare l'iscrizione alle gare che hanno
#: attivato le squadre.
CAMPI_PROFILO = (
    "username",
    "email",
    "phone",
    "home_city",
    "squadra",
    "first_name",
    "last_name",
)


@player_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
@player_only
def edit_profile():
    """Modifica username, email e telefono dell'utente corrente."""
    if request.method == "POST":
        # Si passano al service **solo i campi che il form ha davvero
        # mandato**. Prima si leggevano tutti con `request.form.get(...) or ""`
        # e si passavano sempre: una richiesta parziale — un form ridotto, una
        # chiamata che tocca il solo telefono, un campo rimosso dal template —
        # arrivava quindi con username ed email a stringa vuota, che il
        # service normalizza a `None`. Risultato: l'utente restava senza nome
        # e senza indirizzo, cioè senza modo di autenticarsi né di recuperare
        # la password. Un campo assente non è un campo svuotato, e le due cose
        # non vanno confuse.
        #
        # Un campo *presente e vuoto* resta invece una cancellazione voluta,
        # per quelli in cui ha senso: telefono, città e squadra sono
        # facoltativi e si tolgono così. Su username ed email il service
        # rifiuta il vuoto, perché lì non è mai un gesto sensato.
        aggiornamenti = {
            campo: request.form[campo].strip()
            for campo in CAMPI_PROFILO
            if campo in request.form
        }

        try:
            user = UserService.update_user(current_user.id, **aggiornamenti)
            # If the email changed, update_user revoked is_verified and queued
            # a verification token. Send the email AFTER the transaction commits
            # (i.e. now, post-@transactional return) to avoid I/O under DB lock.
            if hasattr(user, "_pending_verification_email"):
                from models.user.profile_service import UserProfileService

                UserProfileService.send_pending_verification_email(user)
                flash(
                    _(
                        "Informazioni aggiornate. Abbiamo inviato una "
                        "nuova email di verifica al nuovo indirizzo."
                    ),
                    "success",
                )
            else:
                flash(_("Informazioni aggiornate correttamente."), "success")
            return redirect(url_for("player.profile"))
        except ValueError as e:
            flash(str(e), "error")
        except Exception:
            flash(_("Si è verificato un errore durante l'aggiornamento."), "error")

    # GET o POST fallito → ripresenta il form
    return render_template("player/profile_edit.html", user=current_user)


@player_bp.route("/profile/verify-email", methods=["POST"])
@login_required
@player_only
def request_verification_email():
    """Richiede l'invio di una nuova email di verifica."""
    if current_user.is_verified:
        flash(_("La tua email è già verificata."), "info")
        return redirect(url_for("player.edit_profile"))

    from models.user.profile_service import UserProfileService

    try:
        # Use existing service method to generate token and send email
        if UserProfileService.request_verification_email(current_user):
            flash(
                _("Email di verifica inviata. Controlla la tua casella di posta."),
                "success",
            )
        else:
            flash(_("Impossibile inviare l'email. Riprova più tardi."), "error")
    except Exception as e:
        flash(_("Errore durante l'invio: %(detail)s", detail=str(e)), "error")

    return redirect(url_for("player.edit_profile"))


@player_bp.route("/profile/change_password", methods=["POST"])
@login_required
@player_only
def change_password():
    """Cambia la password dell'utente corrente."""
    current = request.form.get("current_password") or ""
    new = request.form.get("new_password") or ""
    confirm = request.form.get("confirm_password") or ""

    if new != confirm:
        flash(_("La nuova password e la conferma non coincidono."), "error")
        return redirect(url_for("player.profile"))

    ok = UserService.change_password(current_user.id, current, new)
    if ok:
        # La sessione e' legata alla credenziale (`User.get_id()`): cambiata la
        # password, il cookie in corso non vale piu' e al prossimo click si
        # finirebbe alla pagina di login. Si rinnova subito, cosi' chi cambia
        # la **propria** password resta dentro — mentre le altre sessioni
        # aperte altrove, che e' il punto, cadono.
        utente = db.session.get(User, current_user.id)
        if utente is not None:
            login_user(utente)
        flash(_("Password aggiornata correttamente."), "success")
    else:
        flash(_("Password attuale errata o nuova password non valida."), "error")

    return redirect(url_for("player.profile"))


@player_bp.route("/request_director", methods=["POST"])
@login_required
@player_only
@feature_required("request_director")
def request_director():
    """Richiede la promozione a direttore di gara"""
    return handle_service_action(
        action=lambda: UserPermissionService.request_director_promotion(
            user_id=current_user.id
        ),
        redirect_url=url_for("player.profile"),
        success_message="Richiesta inviata. Sarai contattato dall'amministratore.",
    )
