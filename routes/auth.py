# routes/auth.py - Route di autenticazione
import json
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from markupsafe import Markup, escape
from flask_login import login_user, logout_user, login_required

from utils.activity_feedback_view import reset_activity_feedback_view
from flask_babel import gettext as _
from models.user.services import UserService
from models.user.profile_service import UserProfileService
from utils.analytics import AnalyticsEvent, track_event
from utils.rate_limiter import limiter
from utils.safe_redirect import safe_next_url

auth_bp = Blueprint("auth", __name__)


@auth_bp.after_request
def niente_cache(response):
    """Le pagine di questo blueprint non vanno mai servite da una cache.

    Ognuna contiene un token CSRF legato alla sessione di chi l'ha chiesta.
    Senza un `Cache-Control` esplicito (misurato in produzione: non c'era),
    browser e proxy possono applicare la cache euristica: la pagina di login
    riservita ripescata da lì porta il token di una sessione che non esiste
    più, e l'invio finisce sulla pagina 400 — l'ennesima causa che si traveste
    da «sessione scaduta». `no-store` chiude anche il caso della pagina
    ripescata dalla history del telefono giorni dopo.
    """
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_bp.route("/diagnosi")
def diagnosi_cookie():
    """Pagina che misura, sul dispositivo dell'utente, dove muore il cookie.

    Nata dal caso che il log da solo non può spiegare: righe «CSRF fallito …
    cookie=assente» da un telefono le cui impostazioni dicono di accettare i
    cookie. Il server vede solo che il cookie non è arrivato; se il browser
    non l'ha salvato, non l'ha rimandato, o qualcosa in mezzo l'ha tolto, lo
    si può stabilire solo da dentro il browser stesso. Questa pagina fa i
    test e mostra un verdetto leggibile — e interrogabile al telefono, senza
    chiedere all'utente di aprire strumenti da sviluppatore.
    """
    # Tocca la sessione: così questa risposta rimanda di sicuro il cookie,
    # e l'eco qui sotto misura un giro completo andata-e-ritorno.
    from flask_wtf.csrf import generate_csrf

    generate_csrf()
    return render_template("auth/diagnosi_cookie.html")


@auth_bp.route("/diagnosi/eco")
def diagnosi_eco():
    """L'altra metà della diagnosi: dice se il cookie è tornato indietro.

    GET di proposito: niente CSRF di mezzo — è proprio il meccanismo che
    stiamo diagnosticando — e nessuno stato cambiato.
    """
    nome_cookie = current_app.config.get("SESSION_COOKIE_NAME", "session")
    cookie_arrivato = nome_cookie in request.cookies
    sessione_valida = bool(session.get("csrf_token"))

    # La pagina allega l'esito dei test fatti DENTRO il browser (scrittura e
    # rilettura di un cookie di prova, tutta in locale): è l'informazione che
    # il server da solo non può avere, e che separa i due casi rimasti — il
    # browser che rifiuta di salvare, e qualcosa fra telefono e sito che
    # strappa l'header a un cookie salvato benissimo. Senza, dal log si
    # leggeva solo «cookie=assente» per entrambi (visto il 2026-08-20:
    # Samsung Internet e Chrome sullo stesso Android 10, indistinguibili).
    def _riferito(nome: str) -> str:
        valore = request.args.get(nome)
        return {"1": "si", "0": "no"}.get(valore or "", "?")

    # Nel log di produzione, accanto alle righe «CSRF fallito», così le
    # diagnosi degli utenti si possono correlare ai loro tentativi.
    current_app.logger.warning(
        "Diagnosi cookie: cookie=%s, sessione_valida=%s, "
        "browser_dichiara=%s, browser_salva=%s, UA=%r",
        "presente" if cookie_arrivato else "assente",
        sessione_valida,
        _riferito("dichiara"),
        _riferito("salva"),
        request.headers.get("User-Agent", ""),
    )
    return jsonify(cookie_arrivato=cookie_arrivato, sessione_valida=sessione_valida)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10/minute", methods=["POST"])
def login():
    """Pagina di login"""
    # `next`: dove tornare dopo il login. Serve a chi arriva su una pagina
    # riservata (o su un link pubblico di iscrizione, issue #61) prima di
    # autenticarsi — senza, dopo il login finirebbe sulla dashboard e
    # dovrebbe ritrovarsi il link da solo.
    next_url = safe_next_url(request.form.get("next") or request.args.get("next"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Use service layer for authentication
        user = UserService.authenticate_user(username, password)

        if user:
            login_user(user)

            # Il blocco «Come stai andando» si mostra una volta per sessione, e
            # «per sessione» qui vuol dire davvero da questo login: senza
            # questa riga chi esce e rientra dallo stesso browser non lo
            # rivedrebbe, perche' `logout_user()` toglie dalla sessione solo le
            # chiavi di Flask-Login.
            reset_activity_feedback_view()

            # Il fuso arriva da un campo nascosto riempito dal browser: da qui
            # in poi ogni orario della sessione è già quello giusto, senza la
            # pagina intermedia mostrata nel fuso vecchio. Non blocca il login
            # se qualcosa va storto — un fuso sbagliato è un fastidio, un login
            # che fallisce è una porta chiusa (ADR-043).
            try:
                UserService.remember_timezone(user.id, request.form.get("timezone"))
            except Exception:
                import logging

                logging.getLogger(__name__).warning(
                    "Fuso orario non registrato al login", exc_info=True
                )

            # Gamification: Welcome message
            try:
                from models.gamification.frontend_bridge import (
                    flash_gamification_event,
                    GamificationEventType,
                )

                flash_gamification_event(
                    GamificationEventType.WELCOME,
                    {
                        "username": user.username,
                        "title": _("Che piacere rivederti!"),
                        "subtitle": _("Tutto pronto per giocare?"),
                    },
                )

                # Check for feature nudges (unused unlocked features)
                from models.gamification.nudge_service import NudgeService

                NudgeService.check_login_nudges(user.id)

            except Exception as e:
                import logging

                logging.getLogger(__name__).warning(
                    f"Gamification welcome flash failed: {e}"
                )

            if not user.is_verified:
                # B11: explain real consequence (password recovery) + link to
                # the profile page where the resend form already lives. The
                # /verify-email route is POST-only (CSRF-protected), so we do
                # NOT link to it directly from a flash anchor.
                # NB: `Markup + str` re-escapes the str — keep every HTML chunk
                # wrapped in Markup() and rely on escape() for user-derived data.
                profile_url = url_for("player.edit_profile") + "#email"
                msg = (
                    escape(
                        _(
                            "Il tuo account non è ancora verificato. Senza "
                            "email confermata non potrai recuperare la "
                            "password se la dimentichi."
                        )
                    )
                    + Markup(' <a href="')
                    + escape(profile_url)
                    + Markup('" class="alert-link">')
                    + escape(_("Vai al profilo per verificare l'email"))
                    + Markup("</a>")
                )
                flash(msg, "warning")

            return redirect(next_url or url_for("dashboard.dashboard"))
        else:
            flash(_("Username o password errati."), "error")

    return render_template("login.html", next_url=next_url)


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5/minute", methods=["POST"])
def register():
    """Pagina di registrazione"""
    # `next` attraversa anche la registrazione: chi segue un link di
    # iscrizione senza avere un account passa da qui prima del login, e la
    # destinazione va conservata lungo tutto il percorso.
    next_url = safe_next_url(request.form.get("next") or request.args.get("next"))

    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        phone = request.form.get("phone", "")

        # Use service layer for user creation
        try:
            UserService.create_user(
                username=username,
                email=email,
                password=password,
                phone=phone if phone else None,
            )

            # Analytics: tracciato qui e non con un onclick sul bottone, così
            # nel conteggio finiscono solo le registrazioni davvero riuscite
            # (nessun dato personale viene inviato a Google).
            track_event(AnalyticsEvent.USER_REGISTERED)

            # Standard practice: don't auto-login on register; flash and send to
            # login page so the user goes through the verify-email flow first.

            flash(
                _(
                    "Registrazione completata! Controlla la tua email per "
                    "verificare l'account."
                ),
                "success",
            )

            # Show welcome gamification event on the login page
            welcome_payload = {
                "type": "welcome",
                "data": {
                    "username": username,
                    "title": _("Ti diamo il benvenuto!"),
                    "subtitle": _("Registrazione completata con successo."),
                },
            }
            flash(json.dumps(welcome_payload), category="gamification_event")

            return redirect(url_for("auth.login", next=next_url))

        except ValueError as e:
            flash(str(e))
            return render_template("register.html", next_url=next_url)

    return render_template("register.html", next_url=next_url)


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    """Logout utente"""
    logout_user()
    return redirect(url_for("main.index"))


@auth_bp.route("/verify-email/<token>", methods=["GET"])
def verify_email(token):
    """Verifica email tramite token"""
    if UserProfileService.verify_email(token):
        flash("Email verificata con successo! Ora puoi effettuare il login.", "success")
    else:
        flash("Link di verifica non valido o scaduto.", "error")

    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("3/minute", methods=["POST"])
def forgot_password():
    """Richiesta reset password"""
    if request.method == "POST":
        # `request.form["email"]` sollevava KeyError — cioe' un 400 secco senza
        # spiegazione — se il campo non arrivava (form parziale, client che non
        # rispetta il `required`).
        email = (request.form.get("email") or "").strip()
        if not email:
            flash(_("Inserisci l'indirizzo email del tuo account."), "error")
        elif UserProfileService.request_password_reset(email):
            # Lo stesso messaggio sia che l'email appartenga a qualcuno sia
            # che non appartenga a nessuno: distinguere i due casi direbbe a
            # chiunque quali indirizzi sono registrati sul sito.
            flash(
                _("Se l'email esiste, riceverai un link per resettare la password."),
                "info",
            )
            return redirect(url_for("auth.login"))
        else:
            # Questo ramo esisteva gia' ma non lo raggiungeva nessuno: l'esito
            # dell'invio veniva scartato e l'utente leggeva comunque «riceverai
            # un link», restando ad aspettare un'email mai partita.
            flash(
                _(
                    "Non siamo riusciti a inviare l'email. "
                    "Riprova fra qualche minuto."
                ),
                "error",
            )

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Pagina di reset password"""
    # Validate token on GET to avoid showing form for expired/used tokens
    if request.method == "GET":
        from models.user.tokens import UserToken

        token_obj = UserToken.query.filter_by(
            token=token, token_type="password_reset"
        ).first()
        if not token_obj or not token_obj.is_valid():
            flash(_("Token non valido o scaduto."), "error")
            return redirect(url_for("auth.login"))

    if request.method == "POST":
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            flash(_("Le password non coincidono."), "error")
            return render_template("auth/reset_password.html", token=token)

        try:
            if UserProfileService.reset_password_with_token(token, password):
                flash(
                    _(
                        "Password aggiornata con successo! "
                        "Ora puoi effettuare il login."
                    ),
                    "success",
                )
                return redirect(url_for("auth.login"))
            else:
                flash(_("Token non valido o scaduto."), "error")
                return redirect(url_for("auth.login"))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("auth/reset_password.html", token=token)

    return render_template("auth/reset_password.html", token=token)


@auth_bp.route("/timezone", methods=["POST"])
@login_required
def sync_timezone():
    """Il browser dice in che fuso sta l'utente, quando è cambiato.

    Il campo nascosto del login copre l'accesso; questo copre tutto il resto:
    la sessione ripresa da «ricordami» (che un login non lo fa), e chi si
    sposta di fuso a sessione aperta. La pagina chiama solo quando il fuso del
    browser è **diverso** da quello salvato, quindi in condizioni normali non
    parte nessuna richiesta.

    Risponde sempre 204: al chiamante non serve sapere niente, e un fuso
    rifiutato perché inventato non è un errore da mostrare a nessuno.
    """
    from flask import Response
    from flask_login import current_user

    payload = request.get_json(silent=True) or {}
    try:
        UserService.remember_timezone(current_user.id, payload.get("timezone"))
    except Exception:
        import logging

        logging.getLogger(__name__).warning("Fuso orario non aggiornato", exc_info=True)

    return Response(status=204)
