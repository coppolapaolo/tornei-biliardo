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
from utils.permissions import feature_required
from utils.route_helpers import (
    ajax_error,
    handle_ajax_service_action,
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
def challenge_catalog():
    """Display challenge catalog for current user."""
    try:
        catalog_data = ChallengeService.get_catalog_data(current_user.id)
        return render_template("challenge/catalog.html", **catalog_data)
    except Exception:
        # All'utente il messaggio tradotto, nel log l'errore vero: prima
        # finiva a schermo il testo dell'eccezione, in inglese.
        current_app.logger.exception("Catalogo challenge non caricato")
        flash(_("Non è stato possibile caricare gli esercizi."), "danger")
        return redirect(url_for("dashboard.dashboard"))


@challenge_bp.route("/create", methods=["GET", "POST"])
@director_required
def create_challenge():
    """Create new challenge (directors only)."""
    if request.method == "GET":
        return render_template("challenge/create.html")

    try:
        if request.is_json:
            data = request.get_json()
            image_filename = data.get("image_path")
            if not image_filename:
                raise ValueError("Immagine obbligatoria per creare una challenge")
        else:
            data = request.form
            # Handle image upload
            image_file = request.files.get("image")
            image_filename = save_challenge_image(image_file) if image_file else None

        # Validate that image is provided or use default for testing
        if not image_filename:
            # Use default path for testing scenarios
            image_filename = "default_challenge.jpg"

        # Convert filename to proper database path
        from utils.image_paths import ImagePathManager

        image_path = ImagePathManager.get_challenge_db_path(image_filename)

        pass_fail_only = data.get("pass_fail_only", "false").lower() == "true"
        challenge = ChallengeService.create_challenge(
            title=data.get("title"),
            description=data["description"],
            image_path=image_path,
            pass_fail_only=pass_fail_only,
            created_by_id=current_user.id,
            max_score=_parse_max_score(data, pass_fail_only),
        )

        if request.is_json:
            return jsonify(
                {
                    "success": True,
                    "challenge_id": challenge.id,
                    "message": "Challenge created successfully",
                }
            )
        else:
            flash(_("Esercizio creato."), "success")
            return redirect(
                url_for("challenge.challenge_detail", challenge_id=challenge.id)
            )

    except ValueError as e:
        error_msg = f"Error creating challenge: {str(e)}"
        if request.is_json:
            return jsonify({"success": False, "error": error_msg}), 400
        else:
            flash(error_msg, "danger")
            return render_template("challenge/create.html")


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

    return render_template(
        "player/challenge_detail.html",
        challenge=challenge,
        user_attempts=user_attempts,
        user_best=user_best,
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
            challenge=challenge,
            attempts=_recent_attempts(challenge_id),
            best_score=_best_score(challenge),
        )

    data = (request.get_json(silent=True) if request.is_json else request.form) or {}
    score, passed, notes = _parse_complete_attempt_payload(data)

    def _record():
        attempt = ChallengeService.record_attempt(
            user_id=current_user.id,
            challenge_id=challenge_id,
            score=score,
            passed=passed,
            notes=notes,
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
        }

    return handle_ajax_service_action(
        action=_annulla,
        redirect_url=url_for("challenge.training_session", challenge_id=challenge_id),
        success_message=_("Prova annullata."),
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
    """Edit challenge (directors only)."""
    challenge = db.get_or_404(Challenge, challenge_id)

    # Check if user can edit (admin can edit all, directors can edit their own)
    can_edit = current_user.is_admin or (
        current_user.is_director and challenge.created_by_id == current_user.id
    )
    if not can_edit:
        abort(403)

    if request.method == "GET":
        return render_template(
            "challenge/create.html", challenge=challenge, edit_mode=True
        )

    from models.challenge.services import ChallengeService
    from utils.route_helpers import handle_ajax_service_action

    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    # Handle image upload if provided (filesystem concern, before service call)
    new_image_path = None
    if not request.is_json:
        image_file = request.files.get("image")
        if image_file:
            image_filename = save_challenge_image(image_file)
            if image_filename:
                if challenge.image_filename:
                    delete_challenge_image(challenge.image_filename)
                from utils.image_paths import ImagePathManager

                new_image_path = ImagePathManager.get_challenge_db_path(image_filename)

    description = data["description"]
    # Campo assente = non si tocca. Col default a "false" ogni salvataggio
    # **disattivava** la challenge, che sparisce dal catalogo: il modulo di
    # modifica `is_active` non lo manda, quindi bastava correggere un refuso
    # per far fuori il drill, senza nessun messaggio.
    is_active = (
        data.get("is_active").lower() == "true"
        if data.get("is_active") is not None
        else None
    )
    # `.get` e non `[...]`: chi non manda il campo non voleva toccare il titolo,
    # chi lo manda vuoto vuole toglierlo. Sono due cose diverse.
    title = data.get("title")

    return handle_ajax_service_action(
        action=lambda: ChallengeService.update_challenge(
            challenge_id=challenge_id,
            title=title,
            description=description,
            is_active=is_active,
            image_path=new_image_path,
        ),
        redirect_url=url_for("challenge.challenge_detail", challenge_id=challenge.id),
        success_message=_("Esercizio aggiornato."),
    )


# Error handlers
@challenge_bp.errorhandler(404)
def challenge_not_found(error):
    """Handle 404 errors in challenge blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Challenge not found"}), 404
    else:
        flash(_("Esercizio non trovato."), "danger")
        return redirect(url_for("challenge.challenge_catalog"))


@challenge_bp.errorhandler(403)
def challenge_access_denied(error):
    """Handle 403 errors in challenge blueprint."""
    if request.is_json:
        return jsonify({"success": False, "error": "Access denied"}), 403
    else:
        flash(_("Non hai i permessi per questo esercizio."), "danger")
        return redirect(url_for("challenge.challenge_catalog"))
