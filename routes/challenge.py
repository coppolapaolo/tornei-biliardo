"""
Module: routes/challenge.py
Purpose: Challenge domain HTTP routes and API endpoints
Requirements: Challenge system for individual skill testing with RESTful interface
"""

from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
)
from flask_babel import gettext as _
from flask_login import login_required, current_user

from models import (
    db,
    Challenge,
    ChallengeAttempt,
)
from models.exceptions import ValidationError
from utils import (
    director_required,
    challenge_player_required,
    challenge_attempt_player_required,
)
from models.challenge.services import ChallengeService
from utils.feature_flags import is_endpoint_visible
from utils.permissions import feature_required
from utils.route_helpers import (
    ajax_error,
    handle_ajax_service_action,
    handle_service_action,
    safe_json_error,
)
from utils.image_paths import ImagePathManager

# Blueprint initialization
challenge_bp = Blueprint("challenge", __name__)


# Convenience aliases for image operations (delegated to ImagePathManager)
save_challenge_image = ImagePathManager.save_challenge_image
delete_challenge_image = ImagePathManager.delete_challenge_image


@challenge_bp.route("/")
@login_required
def today():
    """«Oggi»: la porta d'ingresso degli esercizi (D3).

    Dice da dove ripartire — l'ultimo esercizio, i preferiti, i più provati — e
    ha dietro il catalogo. L'amministratore non si allena: va dritto al
    catalogo, che per lui è uno strumento di gestione.
    """
    if current_user.is_admin:
        return redirect(url_for("challenge.challenge_catalog"))

    from datetime import timezone

    from babel.dates import format_date
    from flask_babel import get_locale

    from models.base import utc_now
    from models.challenge.catalog_view import build_today
    from utils.local_time import resolve_timezone

    try:
        oggi = utc_now().replace(tzinfo=timezone.utc).astimezone(resolve_timezone())
        today_label = format_date(
            oggi, format="EEEE d MMMM", locale=str(get_locale() or "it")
        ).capitalize()
        return render_template(
            "challenge/today.html",
            today=build_today(current_user.id),
            today_label=today_label,
            # La seduta lasciata a metà sale in cima a «Oggi»: è la cosa più
            # probabile che chi apre l'app stia per fare (ADR-067, fase 6c).
            seduta_aperta=_seduta_da_riprendere(current_user.id),
            # E sotto, se uno si è dato un traguardo, il motivo per cui è qui.
            obiettivi=_obiettivi_aperti(current_user.id),
        )
    except Exception:
        current_app.logger.exception("«Oggi» degli esercizi non caricata")
        flash(_("Non è stato possibile caricare gli esercizi."), "danger")
        return redirect(url_for("dashboard.dashboard"))


def _seduta_da_riprendere(user_id):
    """La seduta di scheda lasciata aperta, se ce n'è una (ADR-067).

    Una sola, la più recente: due sedute aperte su due schede diverse sono
    possibili, ma «riprendi» è un invito, non un elenco — e chi ne ha due le
    trova entrambe nella stanza delle schede.
    """
    from models.training_sheet.models import TrainingSession

    return (
        TrainingSession.query.filter_by(user_id=user_id, ended_at=None)
        .order_by(TrainingSession.started_at.desc())
        .first()
    )


@challenge_bp.route("/catalog")
@login_required
def challenge_catalog():
    """Il catalogo che si filtra: abilità, gesto, livello, voto.

    I filtri arrivano dalla query string — ogni pillola è un collegamento —
    quindi un filtro ha un indirizzo, si può mandare a qualcuno e il tasto
    indietro lo disfa.
    """
    from models.challenge.catalog_view import (
        RATING_FLOORS,
        CatalogFilter,
        build_catalog,
    )
    from models.challenge.vocabulary import Abilita, Gesto

    try:
        return render_template(
            "challenge/catalog.html",
            catalog=build_catalog(
                current_user.id, CatalogFilter.from_args(request.args)
            ),
            abilita_choices=list(Abilita),
            gesto_choices=list(Gesto),
            rating_floors=sorted(RATING_FLOORS),
        )
    except Exception:
        # All'utente il messaggio tradotto, nel log l'errore vero: prima
        # finiva a schermo il testo dell'eccezione, in inglese.
        current_app.logger.exception("Catalogo challenge non caricato")
        flash(_("Non è stato possibile caricare gli esercizi."), "danger")
        return redirect(url_for("dashboard.dashboard"))


@challenge_bp.route("/andamento")
@login_required
def andamento():
    """«Il tuo allenamento»: dove sei forte, dove no, e se stai salendo (#181).

    Due interruttori, entrambi collegamenti come i filtri del catalogo: il
    periodo e l'asse. I radar sono **due**, uno per vocabolario, perché anche le
    categorie sono due (decisione dell'utente del 19/09) — ma è la stessa
    pagina, e cambiare asse è cambiare indirizzo.
    """
    from models.andamento import MIN_OSSERVAZIONI, Periodo, build_andamento
    from models.challenge.vocabulary import CategoryAxis
    from models.obiettivo import MAX_ATTIVI

    asse = CategoryAxis.ABILITA
    if str(request.args.get("asse") or "").strip().lower() == CategoryAxis.GESTO.value:
        asse = CategoryAxis.GESTO

    try:
        return render_template(
            "challenge/andamento.html",
            andamento=build_andamento(
                current_user.id, Periodo.parse(request.args.get("periodo")), asse
            ),
            periodi=list(Periodo),
            assi=list(CategoryAxis),
            min_osservazioni=MIN_OSSERVAZIONI,
            obiettivi=_obiettivi_aperti(current_user.id),
            max_obiettivi=MAX_ATTIVI,
        )
    except Exception:
        current_app.logger.exception("Andamento dell'allenamento non caricato")
        flash(_("Non è stato possibile caricare l'andamento."), "danger")
        return redirect(url_for("challenge.today"))


def _obiettivi_aperti(user_id):
    """Gli obiettivi aperti, già timbrati se nel frattempo sono stati raggiunti.

    Il `refresh` è una scrittura dentro una lettura, e va detto: non calcola
    niente — registra che una cosa derivata è successa, una volta sola per
    obiettivo. Senza, «raggiunto» sarebbe uno stato che si accende e si spegne
    col variare della media, e la data non esisterebbe.
    """
    from models.obiettivo import TrainingGoalService, build_all

    TrainingGoalService.refresh(user_id)
    return build_all(TrainingGoalService.active(user_id))


@challenge_bp.route("/obiettivi/nuovo", methods=["GET", "POST"])
@login_required
def nuovo_obiettivo():
    """«Imposta un obiettivo» (#316).

    Il tipo è un **collegamento**, come i filtri del catalogo: le tre forme
    chiedono cose diverse, e un modulo che le mostra tutte e tre insieme chiede
    di ignorarne due. Così ogni forma ha il suo indirizzo e funziona senza
    JavaScript.
    """
    from models.andamento import Periodo, build_andamento
    from models.challenge.vocabulary import Abilita, CategoryAxis, Gesto
    from models.obiettivo import (
        FINESTRA_MEDIA,
        MAX_ATTIVI,
        MAX_SETTIMANE,
        MAX_VOLTE,
        MIN_SETTIMANE,
        MIN_VOLTE,
        GoalDeadline,
        GoalKind,
        GoalRule,
        TrainingGoalService,
    )

    tipo = GoalKind.parse(request.args.get("tipo")) or GoalKind.ESERCIZIO

    if request.method == "POST":
        # Non passa da `handle_service_action` perché le due destinazioni sono
        # diverse: riuscito si va all'andamento, rifiutato si torna al modulo
        # con il tipo che si stava compilando — altrimenti il messaggio d'errore
        # arriva su una pagina che non ha il campo da correggere.
        inviato = GoalKind.parse(request.form.get("tipo"))
        tipo = inviato or tipo
        try:
            TrainingGoalService.create(
                current_user.id,
                inviato,
                challenge_id=_intero(request.form.get("challenge_id")),
                rule=GoalRule.parse(request.form.get("regola")),
                **_categoria(request.form.get("categoria")),
                per_week=_intero(request.form.get("volte")),
                target=_intero(request.form.get("traguardo")),
                deadline=GoalDeadline.parse(request.form.get("scadenza")),
            )
            flash(_("Obiettivo salvato."), "success")
            return redirect(url_for("challenge.andamento"))
        except ValueError as errore:
            flash(str(errore), "error")
            return redirect(url_for("challenge.nuovo_obiettivo", tipo=tipo.value))
        except Exception:
            current_app.logger.exception("Obiettivo non salvato")
            flash(_("Non è stato possibile salvare l'obiettivo."), "error")
            return redirect(url_for("challenge.nuovo_obiettivo", tipo=tipo.value))

    andamento = build_andamento(current_user.id, Periodo.MESE, CategoryAxis.ABILITA)
    gesti = build_andamento(current_user.id, Periodo.MESE, CategoryAxis.GESTO)
    return render_template(
        "challenge/obiettivo.html",
        tipo=tipo,
        tipi=list(GoalKind),
        regole=list(GoalRule),
        scadenze=list(GoalDeadline),
        esercizi=_esercizi_per_obiettivo(current_user.id),
        abilita_choices=list(Abilita),
        gesto_choices=list(Gesto),
        dove_sei={
            CategoryAxis.ABILITA.value: {
                riga.value.value: riga.pct for riga in andamento.radar_rows
            },
            CategoryAxis.GESTO.value: {
                riga.value.value: riga.pct for riga in gesti.radar_rows
            },
        },
        aperti=len(TrainingGoalService.active(current_user.id)),
        max_obiettivi=MAX_ATTIVI,
        finestra_media=FINESTRA_MEDIA,
        min_volte=MIN_VOLTE,
        max_volte=MAX_VOLTE,
        min_settimane=MIN_SETTIMANE,
        max_settimane=MAX_SETTIMANE,
    )


def _intero(valore):
    try:
        return int(str(valore).strip())
    except (TypeError, ValueError):
        return None


def _categoria(valore):
    """«abilita:tiro» → l'asse e la voce.

    Arrivano insieme da un campo solo perché i due vocabolari non hanno voci in
    comune: «stop» dice già di essere un gesto. Due campi separati avrebbero
    permesso di inviare «abilita» + «stop», che non esiste.
    """
    from models.challenge.vocabulary import CategoryAxis

    asse, _sep, voce = str(valore or "").strip().lower().partition(":")
    try:
        return {"axis": CategoryAxis(asse), "axis_value": voce or None}
    except ValueError:
        return {"axis": None, "axis_value": None}


def _esercizi_per_obiettivo(user_id):
    """Gli esercizi su cui si può porre un obiettivo, i già provati per primi.

    Fuori restano quelli **superato/non superato**: lì non c'è un punteggio a
    cui arrivare, e offrirli vorrebbe dire far scegliere una cosa che il
    servizio poi rifiuta.
    """
    from models.challenge.catalog_view import build_catalog, CatalogFilter

    catalogo = build_catalog(user_id, CatalogFilter())
    card = [c for c in catalogo.cards if not c.challenge.pass_fail_only]
    return sorted(
        card, key=lambda c: (not c.mine.tried, c.challenge.get_display_name())
    )


@challenge_bp.route("/obiettivi/<int:goal_id>/lascia", methods=["POST"])
@login_required
def lascia_obiettivo(goal_id):
    """Lasciare un obiettivo. La riga resta: è successo."""
    from models.obiettivo import TrainingGoalService

    return handle_service_action(
        lambda: TrainingGoalService.abandon(goal_id, current_user.id),
        success_message=_("Obiettivo lasciato."),
        redirect_url=url_for("challenge.andamento"),
    )


def _can_author(challenge) -> bool:
    """Chi corregge o duplica un esercizio: l'admin, o il direttore che l'ha creato."""
    return current_user.is_admin or (
        current_user.is_director and challenge.created_by_id == current_user.id
    )


def _render_challenge_form(
    mode, *, challenge=None, source=None, draft=None, decision=None
):
    """Il modulo unico: `mode` è «create», «edit» o «duplicate».

    `decision` rende il foglio «ha già delle prove» già aperto: serve a chi
    arriva senza JavaScript, dove non c'è nessuno che lo apra sopra il modulo.
    """
    from models.challenge.authoring import ChallengeAuthoringService
    from models.challenge.recording import MAX_SHOTS, MIN_SHOTS
    from models.challenge.target import target_from_scene
    from models.challenge.vocabulary import MAX_ABILITA, Abilita, Gesto
    from routes.challenge_form import draft_from_challenge

    subject = challenge or source
    if draft is None and subject is not None:
        draft = draft_from_challenge(subject, as_copy=mode == "duplicate")
    return render_template(
        "challenge/form.html",
        mode=mode,
        challenge=challenge,
        source=source,
        draft=draft,
        decision=decision,
        evidence=(
            ChallengeAuthoringService.evidence(challenge.id) if challenge else None
        ),
        abilita_choices=list(Abilita),
        gesto_choices=list(Gesto),
        max_abilita=MAX_ABILITA,
        # Colpo per colpo si può scegliere solo se il disegno ha un bersaglio
        # (ADR-066): il modulo lo dice invece di offrire una voce che il
        # salvataggio rifiuterebbe.
        target=target_from_scene(subject.diagram_scene) if subject else None,
        shots_range=(MIN_SHOTS, MAX_SHOTS),
    )


def _save_challenge_form(mode, *, challenge=None, source=None):
    """Salva il modulo unico. Risponde in JSON a `fetch`, con un redirect agli altri.

    La foto è un fatto del disco e si sistema qui, prima e dopo il servizio: si
    salva quella nuova (o si duplica quella dell'originale, per una copia) e, se
    il servizio rifiuta, il file appena scritto si toglie — altrimenti ogni
    salvataggio fallito lascerebbe un orfano.
    """
    from models.challenge.authoring import (
        ChallengeAuthoringService,
        EvidenceDecisionRequired,
        OnEvidence,
    )
    from routes.challenge_form import describe_decision, parse_challenge_draft
    from utils.image_paths import ImagePathManager
    from utils.route_helpers import http_status_for_exception, is_ajax_request

    wants_json = is_ajax_request() or request.is_json
    data = request.get_json() if request.is_json else request.form
    written = []
    draft = None

    def _db_path(filename):
        return ImagePathManager.get_challenge_db_path(filename)

    def _uploaded():
        if request.is_json:
            return data.get("image_path") or None
        image_file = request.files.get("image")
        if not image_file or not image_file.filename:
            return None
        filename = save_challenge_image(image_file)
        if not filename:
            raise ValidationError(_("La foto non è un'immagine che si possa leggere"))
        written.append(filename)
        return filename

    def _copied(original):
        filename = ImagePathManager.copy_challenge_image(original.image_filename)
        if filename:
            written.append(filename)
        return filename

    try:
        draft = parse_challenge_draft(data)
        on_evidence = OnEvidence.parse(data.get("on_evidence"))
        new_image = _uploaded()
        old_image = None

        if mode == "edit":
            copy_image = None
            if on_evidence == OnEvidence.COPY and not new_image:
                copy_image = _copied(challenge)
            old_image = challenge.image_filename
            esito = ChallengeAuthoringService.update(
                challenge.id,
                draft,
                acting_user_id=current_user.id,
                image_path=_db_path(new_image) if new_image else None,
                copy_image_path=_db_path(copy_image) if copy_image else None,
                on_evidence=on_evidence,
            )
            saved = esito.challenge
            if esito.copied:
                message = _(
                    "Ho creato una copia con le tue modifiche: "
                    "l'originale è rimasto com'era."
                )
            else:
                message = _("Esercizio aggiornato.")
                # La foto di prima non serve più a nessuno.
                if new_image and old_image and old_image != new_image:
                    delete_challenge_image(old_image)
        else:
            image = new_image
            scene = None
            if mode == "duplicate" and not image:
                image = _copied(source)
                scene = source.diagram_scene
            if not image:
                if request.is_json or current_app.config.get("TESTING"):
                    # Le API e i test creano esercizi senza file: storico.
                    image = "default_challenge.jpg"
                else:
                    raise ValidationError(_("Serve la foto della disposizione"))
            saved = ChallengeAuthoringService.create(
                draft,
                image_path=_db_path(image),
                created_by_id=current_user.id,
                diagram_scene=scene,
            )
            message = (
                _("Copia creata.") if mode == "duplicate" else _("Esercizio creato.")
            )

        if (
            data.get("then") == "diagram"
            and saved.diagram_scene
            and is_endpoint_visible("challenge.edit_diagram", current_user)
        ):
            target = url_for("challenge.edit_diagram", challenge_id=saved.id)
        else:
            target = url_for("challenge.challenge_detail", challenge_id=saved.id)

        if wants_json:
            return jsonify(
                {
                    "success": True,
                    "challenge_id": saved.id,
                    "redirect_url": target,
                    "message": message,
                }
            )
        flash(message, "success")
        return redirect(target)

    except EvidenceDecisionRequired as fermo:
        for filename in written:
            delete_challenge_image(filename)
        decision = describe_decision(fermo)
        if wants_json:
            return jsonify({"success": False, "needs_decision": True, **decision}), 409
        # Senza JavaScript il foglio non si può aprire sopra il modulo com'è:
        # lo si rende già aperto, con quello che era stato scritto.
        return (
            _render_challenge_form(
                mode,
                challenge=challenge,
                source=source,
                draft=draft,
                decision=decision,
            ),
            409,
        )
    except ValueError as e:
        for filename in written:
            delete_challenge_image(filename)
        if wants_json:
            return (
                jsonify({"success": False, "error": str(e)}),
                http_status_for_exception(e),
            )
        flash(str(e), "danger")
        return _render_challenge_form(
            mode,
            challenge=challenge,
            source=source,
            draft=draft,
        )


@challenge_bp.route("/create", methods=["GET", "POST"])
@director_required
def create_challenge():
    """Un esercizio nuovo (direttori)."""
    if request.method == "GET":
        return _render_challenge_form("create")
    return _save_challenge_form("create")


@challenge_bp.route("/<int:challenge_id>/duplicate", methods=["GET", "POST"])
@director_required
def duplicate_challenge(challenge_id):
    """Un esercizio nuovo a partire da uno che c'è (#253).

    Il modulo si apre con i dati dell'originale; salvando nasce un record a sé,
    di chi duplica, senza prove né voti né preferiti, con la **sua** immagine —
    un file nuovo — e, se l'originale è disegnato, la sua scena.
    """
    source = db.get_or_404(Challenge, challenge_id)
    if not _can_author(source):
        abort(403)
    if request.method == "GET":
        return _render_challenge_form("duplicate", source=source)
    return _save_challenge_form("duplicate", source=source)


@challenge_bp.route("/<int:challenge_id>/delete", methods=["POST"])
@director_required
def delete_challenge(challenge_id):
    """Delete challenge (soft delete - mark as inactive)."""
    challenge = db.get_or_404(Challenge, challenge_id)

    # Check if user can delete (admin can delete all, directors can delete their own)
    can_delete = current_user.is_admin or (
        current_user.is_director and challenge.created_by_id == current_user.id
    )
    if not can_delete:
        abort(403)

    def action():
        if challenge.image_filename:
            delete_challenge_image(challenge.image_filename)
        ChallengeService.delete_challenge(challenge_id)

    return handle_ajax_service_action(
        action=action,
        redirect_url=url_for("challenge.challenge_catalog"),
        success_message="Challenge eliminata con successo",
        error_prefix=None,
    )


@challenge_bp.route("/<int:challenge_id>")
@login_required
@challenge_player_required
def challenge_detail(challenge_id):
    """Dettaglio sfida"""
    challenge = db.get_or_404(Challenge, challenge_id)

    # I tentativi di chi guarda: la pagina li mostra come elenco (prototipo
    # 9b·2). Interrogare la relazione dal template funzionerebbe — `attempts`
    # e' lazy="dynamic" — ma metterebbe una query dentro il markup.
    user_attempts = (
        challenge.attempts.filter_by(user_id=current_user.id, completed=True)
        .order_by(ChallengeAttempt.attempted_at.desc())
        .limit(10)
        .all()
    )
    user_best = challenge.get_user_best_attempt(current_user.id)

    from models.challenge.catalog_view import build_card, variant_lines
    from models.challenge.rating_service import ChallengeRatingService

    return render_template(
        "player/challenge_detail.html",
        challenge=challenge,
        user_attempts=user_attempts,
        user_best=user_best,
        card=build_card(challenge, current_user.id),
        variant_lines=variant_lines(challenge, current_user.id),
        my_rating=ChallengeRatingService.get(current_user.id, challenge_id),
    )


@challenge_bp.route("/<int:challenge_id>/attempt", methods=["GET", "POST"])
@login_required
def start_attempt(challenge_id):
    """Start a new challenge attempt."""
    challenge = db.get_or_404(Challenge, challenge_id)

    # Check if challenge is active
    if not challenge.is_active:
        flash(_("Questo esercizio non è più disponibile."), "warning")
        return redirect(url_for("challenge.challenge_catalog"))

    # Prevent admins from attempting challenges
    if current_user.is_admin:
        flash(_("Gli amministratori non possono provare gli esercizi."), "warning")
        return redirect(
            url_for("challenge.challenge_detail", challenge_id=challenge_id)
        )

    if request.method == "GET":
        return render_template("challenge/start_attempt.html", challenge=challenge)

    try:
        data = request.get_json() if request.is_json else request.form

        attempt = ChallengeService.start_challenge_attempt(
            user_id=current_user.id,
            challenge_id=challenge_id,
            gara_id=int(data["gara_id"]) if data.get("gara_id") else None,
            round_number=(
                int(data["round_number"]) if data.get("round_number") else None
            ),
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "attempt_id": attempt.id,
                    "message": "Challenge attempt started",
                }
            )
        else:
            flash(_("Tentativo iniziato."), "success")
            return redirect(url_for("challenge.attempt_detail", attempt_id=attempt.id))

    except ValueError as e:
        error_msg = f"Error starting attempt: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(
                url_for("challenge.challenge_detail", challenge_id=challenge_id)
            )


def _save_from_builder(challenge_id=None):
    """Salva un drill disegnato: l'immagine **e** la scena, insieme.

    Le due cose fanno mestieri diversi e vanno scritte nello stesso gesto. Se
    si salvasse la sola scena il catalogo non avrebbe niente da mostrare (e
    ``image_path`` è NOT NULL, quindi il drill non nascerebbe proprio); se si
    salvasse la sola immagine, correggere una bilia vorrebbe dire ridisegnare
    tutto da capo — cioè il motivo per cui esiste questa colonna.

    L'immagine arriva **già renderizzata dal browser**: è il builder l'unico
    posto che sa come va disegnata una scena, e riprodurne le regole lato
    server significherebbe tenerne due copie destinate a divergere al primo
    ritocco grafico. Quello che il server non delega è il resto: la scena
    passa da ``parse_scene``, e il file dall'ordinario ``save_challenge_image``
    che ridimensiona e normalizza come per qualsiasi foto caricata.
    """
    from models.challenge.diagram import parse_scene
    from utils.image_paths import ImagePathManager

    data = request.form
    scene = parse_scene(data.get("diagram_scene"))
    if scene is None:
        raise ValidationError("Il drill non ha un disegno da salvare")

    image_file = request.files.get("image")
    image_filename = save_challenge_image(image_file) if image_file else None
    if not image_filename:
        raise ValidationError("L'immagine del drill non è arrivata")
    image_path = ImagePathManager.get_challenge_db_path(image_filename)

    pass_fail_only = (data.get("pass_fail_only") or "false").lower() == "true"
    description = (data.get("description") or "").strip()
    if not description:
        raise ValidationError("Servono le istruzioni per chi esegue il drill")
    # Facoltativo, ma inviato sempre: la stringa vuota **toglie** il titolo, ed
    # e' quello che deve succedere a chi svuota la casella e risalva.
    title = (data.get("title") or "").strip()

    max_score = _parse_max_score(data, pass_fail_only)

    if challenge_id is None:
        challenge = ChallengeService.create_challenge(
            title=title,
            description=description,
            image_path=image_path,
            pass_fail_only=pass_fail_only,
            created_by_id=current_user.id,
            diagram_scene=scene,
            max_score=max_score,
        )
    else:
        previous = db.session.get(Challenge, challenge_id)
        old_image = previous.image_filename if previous else None
        max_score = _max_score_from_target(previous, scene, max_score)
        _refuse_meaning_change_from_builder(
            previous, description, pass_fail_only, max_score
        )
        challenge = ChallengeService.update_challenge(
            challenge_id=challenge_id,
            title=title,
            description=description,
            image_path=image_path,
            pass_fail_only=pass_fail_only,
            diagram_scene=scene,
            max_score=max_score,
            # Il modulo manda sempre il campo: vuoto vuol dire «togli il
            # tetto», non «non l'ho toccato».
            clear_max_score=max_score is None,
        )
        # Il disegno precedente non serve più a nessuno: senza questa riga ogni
        # ritocco lascerebbe un file orfano sul disco, per sempre.
        if old_image and old_image != image_filename:
            delete_challenge_image(old_image)

    return {
        "challenge_id": challenge.id,
        "redirect_url": url_for(
            "challenge.challenge_detail", challenge_id=challenge.id
        ),
    }


def _max_score_from_target(challenge, scene, max_score):
    """Su un esercizio colpo per colpo il massimo lo dà il bersaglio (ADR-066).

    Il disegnatore è il posto in cui il bersaglio si tocca: cambiare il valore
    di un anello cambia il massimo, e toglierlo lascerebbe un esercizio che non
    sa più dare punti a un colpo.
    """
    from models.challenge.recording import RecordingMode
    from models.challenge.target import target_from_scene

    if challenge is None or not (
        RecordingMode.parse(challenge.recording_mode).is_sequence
    ):
        return max_score
    bersaglio = target_from_scene(scene)
    if bersaglio is None:
        raise ValidationError(
            _(
                "Questo esercizio si registra colpo per colpo: il bersaglio "
                "serve. Per toglierlo, cambia prima «Come si registra»."
            )
        )
    return (challenge.shots_count or 0) * bersaglio.max_points


def _refuse_meaning_change_from_builder(
    challenge, description, pass_fail_only, max_score
):
    """Dal disegnatore non si cambia il senso di prove già registrate.

    Il disegnatore salva anche istruzioni, tipo e massimo, ma non ha il foglio
    che chiede «ne faccio una copia?» (#252): senza questo controllo resterebbe
    una porta sul retro, e il massimo di un esercizio con cento prove si
    cambierebbe ritoccando una bilia. Qui il disegno si salva sempre; per il
    resto si manda al modulo, che la domanda la sa fare.
    """
    from models.challenge.authoring import ChallengeAuthoringService, ChallengeDraft
    from models.exceptions import ConflictError

    if challenge is None:
        return
    # Il disegnatore non tocca il modo di registrare: si confronta col suo.
    bozza = ChallengeDraft(
        description=description,
        pass_fail_only=pass_fail_only,
        max_score=max_score,
        recording_mode=challenge.recording_mode,
        shots_count=challenge.shots_count,
    )
    if ChallengeAuthoringService.meaning_changes(
        challenge, bozza
    ) and ChallengeAuthoringService.evidence(challenge.id):
        raise ConflictError(
            _(
                "Questo esercizio ha già delle prove: istruzioni e punteggio si "
                "cambiano da «Modifica l'esercizio», qui salva solo il disegno."
            )
        )


@challenge_bp.route("/builder", methods=["GET", "POST"])
@director_required
@feature_required("use_drill_builder")
def diagram_builder():
    """Disegna un drill nuovo invece di fotografarlo.

    È l'alternativa al caricamento della foto, non il suo sostituto: chi la
    foto ce l'ha continua a caricarla dal modulo di creazione.
    """
    if request.method == "GET":
        # Chi arriva da «Non hai una foto?» ha già scritto qualcosa nel modulo
        # di creazione, e quel modulo se lo porta dietro nella query string.
        # Leggerlo qui è il pezzo che mancava: senza, il passaggio di consegne
        # esisteva solo lato JS e il testo appena scritto spariva.
        return render_template(
            "challenge/builder.html",
            challenge=None,
            prefill={
                "title": request.args.get("title", ""),
                "description": request.args.get("description", ""),
                "pass_fail_only": request.args.get("pass_fail_only", "") == "true",
                "max_score": request.args.get("max_score", ""),
            },
            save_url=url_for("challenge.diagram_builder"),
            cancel_url=url_for("challenge.challenge_catalog"),
        )

    return handle_ajax_service_action(
        action=lambda: _save_from_builder(),
        redirect_url=url_for("challenge.challenge_catalog"),
        success_message=_("Esercizio creato."),
        error_prefix=None,
    )


@challenge_bp.route("/<int:challenge_id>/builder", methods=["GET", "POST"])
@director_required
@feature_required("use_drill_builder")
def edit_diagram(challenge_id):
    """Riapre il disegno di un drill costruito.

    Solo per i drill che una scena ce l'hanno: da un drill fotografato non c'è
    niente da riaprire, e proporre il builder lì vorrebbe dire offrire di
    ridisegnarlo da zero spacciandolo per una modifica.
    """
    challenge = db.get_or_404(Challenge, challenge_id)

    can_edit = current_user.is_admin or (
        current_user.is_director and challenge.created_by_id == current_user.id
    )
    if not can_edit:
        abort(403)

    if not challenge.diagram_scene:
        flash(
            _("Questo esercizio nasce da una foto: non c'è un disegno da modificare."),
            "warning",
        )
        return redirect(
            url_for("challenge.challenge_detail", challenge_id=challenge_id)
        )

    if request.method == "GET":
        return render_template(
            "challenge/builder.html",
            challenge=challenge,
            prefill=None,
            save_url=url_for("challenge.edit_diagram", challenge_id=challenge_id),
            cancel_url=url_for("challenge.challenge_detail", challenge_id=challenge_id),
        )

    return handle_ajax_service_action(
        action=lambda: _save_from_builder(challenge_id),
        redirect_url=url_for("challenge.challenge_detail", challenge_id=challenge_id),
        success_message=_("Disegno aggiornato."),
        error_prefix=None,
    )


@challenge_bp.route("/<int:challenge_id>/train", methods=["GET", "POST"])
@login_required
def training_session(challenge_id):
    """Ci si allena qui: una schermata sola, una prova dopo l'altra.

    Non c'è nessuna entità «sessione»: è solo navigazione. Quello che resta a
    DB sono i singoli ``ChallengeAttempt``, ciascuno già completo — il gruppo
    «le prove di stasera» non è un fatto di dominio, e inventargli una tabella
    avrebbe voluto dire aprirla, chiuderla e poi ripulire quelle rimaste
    aperte quando uno chiude il browser a metà.

    La POST registra **una prova intera** e risponde in JSON: la pagina resta
    dov'è. Il percorso della gara (drill al posto del bye) non passa di qui —
    ha un contesto e conseguenze in classifica, e continua da
    ``start_attempt``.
    """
    challenge = db.get_or_404(Challenge, challenge_id)

    if not challenge.is_active:
        flash(_("Questo esercizio non è più disponibile."), "warning")
        return redirect(url_for("challenge.challenge_catalog"))

    if current_user.is_admin:
        flash(_("Gli amministratori non provano gli esercizi."), "warning")
        return redirect(
            url_for("challenge.challenge_detail", challenge_id=challenge_id)
        )

    if request.method == "GET":
        return render_template(
            "challenge/training.html",
            attempts=_recent_attempts(challenge_id),
            best_score=_best_score(challenge),
            is_shots=_is_shots(challenge),
            **_run_context(challenge),
        )

    data = (request.get_json(silent=True) if request.is_json else request.form) or {}
    score, passed, notes = _parse_complete_attempt_payload(data)
    # Con quale variante (destra/sinistra, A/B): facoltativa anche quando
    # l'esercizio ne ha. Che sia di **questo** esercizio lo verifica il servizio.
    variant_id = _payload_int(data, "variant_id")

    def _record():
        attempt = ChallengeService.record_attempt(
            user_id=current_user.id,
            challenge_id=challenge_id,
            score=score,
            passed=passed,
            notes=notes,
            variant_id=variant_id,
        )
        # Il dict torna al chiamante dentro la risposta JSON: la pagina
        # aggiorna in posto l'elenco e il record, senza ricaricarsi.
        return {
            "attempt": {
                "id": attempt.id,
                "score": attempt.score,
                "passed": attempt.passed,
                "notes": attempt.notes,
                "attempted_at": attempt.attempted_at.isoformat(),
                "variant": attempt.variant.label if attempt.variant else None,
            },
            "attempts_count": ChallengeAttempt.query.filter_by(
                user_id=current_user.id, challenge_id=challenge_id, completed=True
            ).count(),
            "best_score": _best_score(challenge),
            # Sui superato/non superato il secondo contatore mostra le riuscite,
            # non il record: senza questo campo restava fermo al valore
            # renderizzato dal server, e chi registrava dieci prove di fila
            # vedeva salire solo il totale. Si ricalcola dal DB invece di
            # incrementarlo a schermo, cosi' due schede aperte non divergono.
            "passed_count": _passed_count(challenge_id),
            "progress_html": _progress_html(challenge),
        }

    return handle_ajax_service_action(
        action=_record,
        redirect_url=url_for("challenge.training_session", challenge_id=challenge_id),
        success_message=_("Prova registrata."),
        error_prefix=None,
    )


@challenge_bp.route("/<int:challenge_id>/train/undo", methods=["POST"])
@login_required
def training_undo(challenge_id):
    """Annulla l'ultima prova registrata su questo esercizio.

    **Perche' esiste.** La schermata di allenamento registra con un tocco: il
    tasto sbagliato si preme, e in una sessione da dieci prove un «superato»
    di troppo falsa il conto senza lasciare traccia di com'e' successo. Senza
    via d'uscita l'unico rimedio sarebbe compensare a mano, sbagliando due
    volte invece di una.

    Annulla **l'ultima**, non una a scelta: qui si sta giocando, e l'errore che
    si corregge col telefono in mano e' quello appena fatto. Cancellare una
    prova qualsiasi e' un gesto da scrivania, e vive nello storico del profilo.

    La restituzione dell'XP la fa il servizio: senza, registra-e-annulla
    sarebbe un modo banale di salire di livello.
    """
    ultima = (
        ChallengeAttempt.query.filter_by(
            user_id=current_user.id, challenge_id=challenge_id, completed=True
        )
        .order_by(ChallengeAttempt.attempted_at.desc(), ChallengeAttempt.id.desc())
        .first()
    )
    if ultima is None:
        return ajax_error(_("Non c'è nessuna prova da annullare."), 404)

    challenge = db.get_or_404(Challenge, challenge_id)

    def _annulla():
        ChallengeService.delete_attempt(
            attempt_id=ultima.id,
            actor_id=current_user.id,
            actor_is_admin=bool(current_user.is_admin),
        )
        return {
            "attempts_count": ChallengeAttempt.query.filter_by(
                user_id=current_user.id, challenge_id=challenge_id, completed=True
            ).count(),
            "best_score": _best_score(challenge),
            "passed_count": _passed_count(challenge_id),
            "progress_html": _progress_html(challenge),
        }

    return handle_ajax_service_action(
        action=_annulla,
        redirect_url=url_for("challenge.training_session", challenge_id=challenge_id),
        success_message=_("Prova annullata."),
        error_prefix=None,
    )


def _progress(challenge):
    """Come sta andando, per chi guarda, nel **suo** giorno (ADR-043)."""
    from models.challenge.execution_view import build_progress
    from utils.local_time import resolve_timezone

    return build_progress(challenge, current_user.id, tz=resolve_timezone())


def _is_shots(challenge) -> bool:
    from models.challenge.recording import RecordingMode

    return RecordingMode.parse(challenge.recording_mode).is_sequence


def _run_context(challenge):
    """Tutto ciò che la cornice mostra: oggi, la prova in corso, il bersaglio.

    Uno solo, e lo usano sia il caricamento della pagina sia ogni risposta
    JSON: due letture diverse dello stesso stato darebbero una pagina che dopo
    un colpo dice una cosa diversa da quella che direbbe ricaricandola.
    """
    from models.challenge.run_view import build_run
    from models.challenge.shot_service import ShotRunService
    from models.challenge.target import target_from_scene

    a_colpi = _is_shots(challenge)
    run = (
        build_run(ShotRunService.current(current_user.id, challenge.id))
        if a_colpi
        else None
    )
    return {
        "challenge": challenge,
        "progress": _progress(challenge),
        "run": run,
        # Il panno da toccare prima del primo colpo: dopo lo porta `run`.
        "cloth_target": (
            target_from_scene(challenge.diagram_scene)
            if a_colpi and run is None
            else None
        ),
    }


def _progress_html(challenge, context=None):
    """Lo stesso pezzo che la pagina ha ricevuto al caricamento, ridisegnato.

    Viaggia dentro la risposta JSON di ogni prova registrata o annullata: il
    grafico e la frase hanno così un disegnatore solo, il server, e nel browser
    non si compone nessun testo tradotto.
    """
    return render_template(
        "challenge/_run_progress.html", **(context or _run_context(challenge))
    )


def _shots_payload(challenge):
    """I due pezzi che cambiano a ogni colpo: come sta andando, e i comandi.

    Anche i comandi li ridisegna il server — dopo l'ultimo colpo compare
    «Chiudi la prova» — perché due stati da tenere in pari nel browser sono due
    stati che prima o poi divergono.
    """
    context = _run_context(challenge)
    return {
        "progress_html": _progress_html(challenge, context),
        "dock_html": render_template(
            "challenge/_run_shots_dock.html",
            run=context["run"],
            challenge=challenge,
        ),
    }


def _shot_payload_field(data, key):
    """Un numero facoltativo dal JSON del colpo: assente e vuoto sono lo stesso."""
    valore = data.get(key)
    if valore in (None, ""):
        return None
    try:
        return float(valore)
    except (TypeError, ValueError):
        raise ValidationError(_("Il punto sul panno non è leggibile."))


@challenge_bp.route("/<int:challenge_id>/train/shot", methods=["POST"])
@login_required
def training_shot(challenge_id):
    """Un colpo in più nella prova aperta; il primo la apre (ADR-066).

    Il punteggio non passa di qui: lo decide il bersaglio, che il server ha e
    il browser no. Dal browser arrivano solo l'esito e, quando la bilia è
    entrata, il punto in cui si è fermata la battente.
    """
    from models.challenge.shot_service import ShotRunService

    challenge = db.get_or_404(Challenge, challenge_id)
    data = (request.get_json(silent=True) if request.is_json else request.form) or {}
    made = str(data.get("made")).lower() == "true" or data.get("made") is True
    variant = _payload_int(data, "variant_id")

    def _registra():
        ShotRunService.record_shot(
            current_user.id,
            challenge_id,
            made=made,
            x=_shot_payload_field(data, "x"),
            y=_shot_payload_field(data, "y"),
            variant_id=variant,
        )
        return _shots_payload(challenge)

    return handle_ajax_service_action(
        action=_registra,
        redirect_url=url_for("challenge.training_session", challenge_id=challenge_id),
        success_message=None,
        error_prefix=None,
    )


@challenge_bp.route("/<int:challenge_id>/train/draw", methods=["POST"])
@login_required
def training_draw(challenge_id):
    """La consegna del colpo che sta per essere giocato (#452).

    La prima estrazione apre la prova: con l'estrazione cominciare è un atto —
    ti dice che cosa fare — mentre col bersaglio il primo dato è già il primo
    colpo. Chiamarla di nuovo non riestrae: la consegna in attesa è quella.
    """
    from models.challenge.shot_service import ShotRunService

    challenge = db.get_or_404(Challenge, challenge_id)

    def _estrai():
        ShotRunService.draw_next(current_user.id, challenge_id)
        return _shots_payload(challenge)

    return handle_ajax_service_action(
        action=_estrai,
        redirect_url=url_for("challenge.training_session", challenge_id=challenge_id),
        success_message=None,
        error_prefix=None,
    )


@challenge_bp.route("/<int:challenge_id>/train/outcome", methods=["POST"])
@login_required
def training_outcome(challenge_id):
    """Com'è andato il colpo estratto: una voce della scala (#452).

    Dal browser arriva **quale** voce, non quanto vale: la scala ce l'ha il
    server, e un punteggio che passasse di qui sarebbe scrivibile a mano.
    """
    from models.challenge.shot_service import ShotRunService

    challenge = db.get_or_404(Challenge, challenge_id)
    data = (request.get_json(silent=True) if request.is_json else request.form) or {}

    def _registra():
        ShotRunService.record_outcome(
            current_user.id, challenge_id, outcome_index=data.get("outcome_index")
        )
        return _shots_payload(challenge)

    return handle_ajax_service_action(
        action=_registra,
        redirect_url=url_for("challenge.training_session", challenge_id=challenge_id),
        success_message=None,
        error_prefix=None,
    )


@challenge_bp.route("/<int:challenge_id>/train/shot/undo", methods=["POST"])
@login_required
def training_shot_undo(challenge_id):
    """Annulla l'ultimo colpo. Tolto l'unico, la prova aperta sparisce."""
    from models.challenge.shot_service import ShotRunService

    challenge = db.get_or_404(Challenge, challenge_id)

    def _annulla():
        ShotRunService.undo_last(current_user.id, challenge_id)
        return _shots_payload(challenge)

    return handle_ajax_service_action(
        action=_annulla,
        redirect_url=url_for("challenge.training_session", challenge_id=challenge_id),
        success_message=None,
        error_prefix=None,
    )


@challenge_bp.route("/<int:challenge_id>/train/shot/restart", methods=["POST"])
@login_required
def training_shot_restart(challenge_id):
    """Butta la prova aperta e i suoi colpi. Le prove chiuse non si toccano."""
    from models.challenge.shot_service import ShotRunService

    challenge = db.get_or_404(Challenge, challenge_id)

    def _ricomincia():
        ShotRunService.restart(current_user.id, challenge_id)
        return _shots_payload(challenge)

    return handle_ajax_service_action(
        action=_ricomincia,
        redirect_url=url_for("challenge.training_session", challenge_id=challenge_id),
        success_message=_("Prova annullata."),
        error_prefix=None,
    )


@challenge_bp.route("/<int:challenge_id>/train/shot/close", methods=["POST"])
@login_required
def training_shot_close(challenge_id):
    """Chiude la prova: il punteggio è la somma dei colpi.

    Da qui in poi la prova è una come le altre — entra nelle «prove di oggi»,
    nel record, nello storico — e la pagina torna al principio, pronta per la
    prossima.
    """
    from models.challenge.shot_service import ShotRunService

    # L'esercizio si carica per dare 404 su un id che non esiste, prima di
    # parlare di prove aperte.
    db.get_or_404(Challenge, challenge_id)

    def _chiudi():
        chiusa = ShotRunService.close(current_user.id, challenge_id)
        # Chiudere porta al riepilogo: la nuvola dei punti d'arrivo e che cosa
        # dice sono la fine della sessione, non una riga in più nell'elenco.
        return {
            "redirect_url": url_for("challenge.training_summary", attempt_id=chiusa.id)
        }

    return handle_ajax_service_action(
        action=_chiudi,
        redirect_url=url_for("challenge.training_session", challenge_id=challenge_id),
        success_message=_("Prova registrata."),
        error_prefix=None,
    )


@challenge_bp.route("/train/summary/<int:attempt_id>")
@login_required
def training_summary(attempt_id):
    """La fine della sessione: la nuvola, che cosa dice, i numeri (fase 5d).

    Una prova sola, e solo la propria: il riepilogo racconta come si sbaglia,
    che è la cosa più personale che questa app scriva.
    """
    from models.challenge.summary_view import build_summary

    attempt = db.get_or_404(ChallengeAttempt, attempt_id)
    if attempt.user_id != current_user.id:
        abort(404)
    if not attempt.completed or not attempt.shots:
        # Una prova aperta non ha una fine da raccontare, e una senza colpi non
        # è passata di qui: si torna dove la si sta giocando.
        return redirect(
            url_for("challenge.training_session", challenge_id=attempt.challenge_id)
        )

    return render_template(
        "challenge/summary.html",
        challenge=attempt.challenge,
        summary=build_summary(attempt),
    )


@challenge_bp.route("/train/summary/<int:attempt_id>/notes", methods=["POST"])
@login_required
def training_notes(attempt_id):
    """Le note della sessione: «tavolo 4, panno lento».

    Spiegano un punteggio meglio di qualunque statistica, ma solo se si
    scrivono adesso. Stanno sulla prova, dov'erano già previste.
    """
    attempt = db.get_or_404(ChallengeAttempt, attempt_id)
    # Il permesso lo verifica anche il servizio: qui si guadagna solo il 404
    # invece di un messaggio d'errore su una prova che non è di chi scrive.
    if attempt.user_id != current_user.id:
        abort(404)

    def _salva():
        ChallengeService.set_attempt_notes(
            attempt_id=attempt_id,
            user_id=current_user.id,
            notes=request.form.get("notes", ""),
        )
        return {}

    return handle_service_action(
        action=_salva,
        redirect_url=url_for("challenge.training_summary", attempt_id=attempt_id),
        success_message=_("Note salvate."),
        error_prefix=None,
    )


def _passed_count(challenge_id):
    """Quante prove riuscite su questo esercizio, per chi sta guardando.

    Serve solo ai superato/non superato: e' il numero che il contatore mostra
    al posto del record, e dopo un annulla va ricalcolato dal DB invece che
    decrementato a schermo — se due schede sono aperte, il conto tenuto in
    pagina diverge e nessuno se ne accorge.
    """
    return ChallengeAttempt.query.filter_by(
        user_id=current_user.id,
        challenge_id=challenge_id,
        completed=True,
        passed=True,
    ).count()


def _recent_attempts(challenge_id, limit=10):
    """Le ultime prove di chi sta guardando, la più recente per prima.

    Sopravvive a un ricaricamento della pagina proprio perché è ricavata dai
    tentativi e non da uno stato di sessione: chi torna sul drill domani
    ritrova comunque com'era andata.
    """
    return (
        ChallengeAttempt.query.filter_by(
            user_id=current_user.id, challenge_id=challenge_id, completed=True
        )
        .order_by(ChallengeAttempt.attempted_at.desc(), ChallengeAttempt.id.desc())
        .limit(limit)
        .all()
    )


def _best_score(challenge):
    """Il record personale, o ``None`` se il drill è riuscita-o-no.

    Su un pass/fail il punteggio è solo la rappresentazione 1/0 dell'esito:
    mostrarlo come «record» direbbe «il tuo record è 1», che non vuol dire
    niente.
    """
    if challenge.pass_fail_only:
        return None
    best = challenge.get_user_best_attempt(current_user.id)
    return best.score if best else None


@challenge_bp.route("/attempt/<int:attempt_id>")
@login_required
@challenge_attempt_player_required
def attempt_detail(attempt_id):
    """Dettaglio tentativo di sfida"""
    attempt = db.get_or_404(ChallengeAttempt, attempt_id)

    # Il record personale mentre si registra il punteggio: e' il riferimento
    # che dice se questo tentativo e' andato meglio (prototipo 9b·3).
    best = attempt.challenge.get_user_best_attempt(attempt.user_id)
    user_best_score = (
        best.score
        if best and best.id != attempt.id and not attempt.challenge.pass_fail_only
        else None
    )

    # Un tentativo che sostituisce una X si chiude da un'altra parte: solo
    # `complete_x_replacement` scrive il punteggio sul match del turno
    # (SPECIFICHE.md riga 65). Inviare al `complete_attempt` generico registra
    # il tentativo e lascia la classifica a zero — era la seconda meta' della
    # issue #221, e non si vedeva perche' le due strade *sembrano* la stessa.
    from models.competition.gara_bye_challenge import GaraByeChallenge

    is_x_replacement = (
        GaraByeChallenge.query.filter_by(challenge_attempt_id=attempt.id).first()
        is not None
    )

    return render_template(
        "player/challenge_attempt_detail.html",
        attempt=attempt,
        user_best_score=user_best_score,
        is_x_replacement=is_x_replacement,
    )


def _payload_int(data, key, *, required=False):
    """Estrae un int da un payload dict (JSON) o MultiDict (form).

    NON usa il kwarg `type=` di MultiDict.get: su un dict JSON
    `dict.get(key, type=int)` solleva TypeError (non catturato da
    `except ValueError`) → 500. Ritorna None se il valore è assente o non
    numerico; se `required=True` solleva ValueError (mappata a 400 dalle route)
    quando manca o non è convertibile.
    """
    raw = data.get(key)
    if raw in (None, ""):
        if required:
            raise ValueError(f"Missing required field: {key}")
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        if required:
            raise ValueError(f"Invalid integer for field: {key}")
        return None


def _parse_max_score(data, pass_fail_only):
    """Il tetto di punteggio dal modulo: facoltativo, e vuoto vuol dire assente.

    Non usa il kwarg ``type=int`` di MultiDict per la stessa ragione degli
    altri parser di questo file: su un body JSON quel kwarg solleva TypeError
    (500), e la casella vuota — il caso normale — arriva come "".

    Su un esercizio superato/non superato il campo si ignora invece di
    sollevare: la casella e' nascosta dal modulo, quindi un valore che arriva
    lo stesso e' residuo di un cambio di tipo a schermo, non una richiesta.
    """
    if pass_fail_only:
        return None
    grezzo = (data.get("max_score") or "").strip() if hasattr(data, "get") else ""
    if not grezzo:
        return None
    try:
        return int(grezzo)
    except (TypeError, ValueError):
        raise ValidationError("Il punteggio massimo deve essere un numero")


def _parse_complete_attempt_payload(data):
    """Estrae (score, passed, notes) dal payload di completamento tentativo.

    Funziona sia con un dict semplice (body JSON) sia con un MultiDict
    (request.form). NON usa il kwarg `type=` di MultiDict.get:
    - su un dict JSON `dict.get("score", type=int)` solleva TypeError → 500;
    - `MultiDict.get("passed", type=bool)` fa bool("false") == True, segnando
      come PASSATO un tentativo pass/fail in realtà fallito.

    Lo score viene coerciato a int (None se assente/non numerico). `passed`
    è True/False solo su valori esplicitamente riconosciuti; None se assente
    o non riconosciuto (challenge numeriche, placeholder "" di un <select>,
    payload spurio): in questi casi NON si registra un fallimento implicito.
    """
    raw_score = data.get("score")
    try:
        score = int(raw_score) if raw_score not in (None, "") else None
    except (TypeError, ValueError):
        score = None

    raw_passed = data.get("passed")
    if isinstance(raw_passed, bool):
        passed = raw_passed
    elif raw_passed is None:
        passed = None
    else:
        token = str(raw_passed).strip().lower()
        if token in ("true", "1", "yes", "on"):
            passed = True
        elif token in ("false", "0", "no", "off"):
            passed = False
        else:
            # Valore non riconosciuto (es. "" del placeholder): non fornito.
            passed = None

    return score, passed, data.get("notes")


@challenge_bp.route("/attempt/<int:attempt_id>/complete", methods=["POST"])
@login_required
def complete_attempt(attempt_id):
    """Complete a challenge attempt with results."""
    try:
        attempt = ChallengeAttempt.query.get_or_404(attempt_id)

        # Verify user owns this attempt
        if attempt.user_id != current_user.id:
            return jsonify({"success": False, "error": "Access denied"}), 403

        data = request.get_json() if request.is_json else request.form
        score, passed, notes = _parse_complete_attempt_payload(data)

        completed_attempt = ChallengeService.complete_challenge_attempt(
            attempt_id=attempt_id,
            score=score,
            passed=passed,
            notes=notes,
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "final_score": completed_attempt.score,
                    "passed": completed_attempt.passed,
                    "message": "Challenge completed successfully",
                }
            )
        else:
            flash(_("Tentativo registrato."), "success")
            return redirect(
                url_for(
                    "challenge.challenge_detail",
                    challenge_id=completed_attempt.challenge_id,
                )
            )

    except ValueError as e:
        error_msg = f"Error completing attempt: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("challenge.attempt_detail", attempt_id=attempt_id))


@challenge_bp.route("/<int:challenge_id>/favorite", methods=["POST"])
@login_required
def toggle_favorite(challenge_id):
    """Toggle challenge as favorite."""
    try:
        is_favorited = ChallengeService.toggle_favorite(current_user.id, challenge_id)

        action = "added to" if is_favorited else "removed from"
        message = f"Challenge {action} favorites"

        if request.is_json:
            return jsonify(
                {"success": True, "is_favorite": is_favorited, "message": message}
            )
        else:
            flash(message, "success")
            return redirect(
                url_for("challenge.challenge_detail", challenge_id=challenge_id)
            )

    except Exception as e:
        if request.is_json:
            return safe_json_error(e, "toggling favorite")
        else:
            flash(_("Non è stato possibile aggiornare i preferiti."), "danger")
            return redirect(
                url_for("challenge.challenge_detail", challenge_id=challenge_id)
            )


@challenge_bp.route("/<int:challenge_id>/rate", methods=["POST"])
@login_required
@challenge_player_required
def rate_challenge(challenge_id):
    """Il voto da 1 a 5 (D6). Un voto vuoto lo toglie.

    Chi può votare lo decide il servizio — solo chi ha provato l'esercizio — e
    non il fatto che la scheda gli abbia mostrato le bilie.
    """
    from models.challenge.rating_service import ChallengeRatingService

    data = (request.get_json(silent=True) if request.is_json else request.form) or {}
    rating = data.get("rating")

    def _vota():
        if rating in (None, "", 0, "0"):
            numeri = ChallengeRatingService.clear(current_user.id, challenge_id)
            mio = None
        else:
            numeri = ChallengeRatingService.rate(current_user.id, challenge_id, rating)
            mio = int(rating)
        return {
            "rating": mio,
            "rating_average": numeri.rating_average,
            "rating_count": numeri.rating_count,
            "players": numeri.players,
        }

    return handle_ajax_service_action(
        action=_vota,
        redirect_url=url_for("challenge.challenge_detail", challenge_id=challenge_id),
        success_message=_("Voto registrato."),
        error_prefix=None,
    )


@challenge_bp.route("/<int:challenge_id>/statistics")
@director_required
def challenge_statistics(challenge_id):
    """View challenge statistics (directors only)."""
    try:
        challenge = Challenge.query.get_or_404(challenge_id)
        statistics = challenge.get_statistics()

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "challenge": {
                        "id": challenge.id,
                        "description": challenge.description,
                    },
                    "statistics": statistics,
                }
            )
        else:
            return render_template(
                "challenge/statistics.html", challenge=challenge, statistics=statistics
            )

    except Exception as e:
        # Solo per chi chiede JSON. Alla pagina un errore deve restare un
        # errore: qui un `except` generico ha nascosto per mesi che
        # `challenge/statistics.html` non esisteva — il TemplateNotFound
        # diventava «non è stato possibile caricare» e un redirect.
        if request.is_json:
            return safe_json_error(e, "loading challenge statistics")
        raise


@challenge_bp.route("/x-replacement/<int:gara_id>/<int:round_number>", methods=["POST"])
@login_required
def create_x_replacement(gara_id, round_number):
    """Create challenge attempt for X replacement in campionato."""
    try:
        data = request.get_json() if request.is_json else request.form

        attempt = ChallengeService.create_x_replacement_attempt(
            user_id=current_user.id,
            gara_id=gara_id,
            round_number=round_number,
            challenge_id=_payload_int(data, "challenge_id"),
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "attempt_id": attempt.id,
                    "challenge_description": attempt.challenge.get_display_name(),
                    "message": "X replacement challenge created",
                }
            )
        else:
            flash(_("Esercizio di gara avviato."), "success")
            return redirect(url_for("challenge.attempt_detail", attempt_id=attempt.id))

    except ValueError as e:
        error_msg = f"Error creating X replacement: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("dashboard.dashboard"))


@challenge_bp.route("/x-replacement/<int:attempt_id>/complete", methods=["POST"])
@login_required
def complete_x_replacement(attempt_id):
    """Complete X replacement challenge attempt."""
    from models.competition.gara_bye_challenge import GaraByeChallenge

    try:
        attempt = ChallengeAttempt.query.get_or_404(attempt_id)

        # Check if this is an X replacement via GaraByeChallenge (new pattern)
        bye_challenge = GaraByeChallenge.query.filter_by(
            challenge_attempt_id=attempt_id
        ).first()

        # Verify user owns this attempt and it's for X replacement
        # Check both new pattern (GaraByeChallenge) and deprecated field (gara_id)
        is_x_replacement = bye_challenge is not None or attempt.gara_id is not None
        if attempt.user_id != current_user.id or not is_x_replacement:
            return jsonify({"success": False, "error": "Access denied"}), 403

        data = request.get_json() if request.is_json else request.form

        completed_attempt = ChallengeService.complete_x_replacement_attempt(
            attempt_id=attempt_id,
            score=_payload_int(data, "score", required=True),
            notes=data.get("notes"),
        )

        # Get gara_id for redirect (prefer GaraByeChallenge, fall back to
        # deprecated field)
        redirect_gara_id = bye_challenge.gara_id if bye_challenge else attempt.gara_id

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "final_score": completed_attempt.score,
                    "message": "X replacement completed successfully",
                }
            )
        else:
            flash(_("Esercizio di gara registrato."), "success")
            return redirect(
                url_for("admin.competition.gara_detail", gara_id=redirect_gara_id)
            )

    except ValueError as e:
        error_msg = f"Error completing X replacement: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return redirect(url_for("challenge.attempt_detail", attempt_id=attempt_id))


@challenge_bp.route("/<int:challenge_id>/edit", methods=["GET", "POST"])
@director_required
def edit_challenge(challenge_id):
    """Correggere un esercizio: lo stesso modulo con cui è nato (#252)."""
    challenge = db.get_or_404(Challenge, challenge_id)
    if not _can_author(challenge):
        abort(403)
    if request.method == "GET":
        return _render_challenge_form("edit", challenge=challenge)
    return _save_challenge_form("edit", challenge=challenge)


# Error handlers
@challenge_bp.errorhandler(404)
def challenge_not_found(error):
    """Handle 404 errors in challenge blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Challenge not found"}), 404
    else:
        flash(_("Esercizio non trovato."), "danger")
        return redirect(url_for("challenge.today"))


@challenge_bp.errorhandler(403)
def challenge_access_denied(error):
    """Handle 403 errors in challenge blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Access denied"}), 403
    else:
        flash(_("Non hai i permessi per questo esercizio."), "danger")
        return redirect(url_for("challenge.today"))
