# config.py - Configurazioni dell'applicazione
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _compute_asset_version() -> str:
    """Cache-buster derivato dal file statico modificato più di recente.

    I CSS/JS sono referenziati come `?v=<questo valore>` e in produzione sono
    serviti con cache lunga: serve quindi un valore che cambi da sé a ogni
    modifica di un asset, altrimenti i browser resterebbero con file vecchi
    in cache per un anno. `VERSION` non va bene perché è scritta a mano e
    nessuno si ricorderebbe di incrementarla dopo un ritocco al CSS.

    Si guardano solo `static/css` e `static/js`: `static/uploads` contiene le
    immagini caricate dagli utenti, non è codice e cresce senza limiti.
    Ritorna "0" se le cartelle non esistono (il caching resta corretto: il
    valore è comunque stabile).

    Si usa `st_mtime_ns` e non `getmtime()`: quest'ultimo andrebbe troncato ai
    secondi, e due modifiche allo stesso asset nello stesso secondo
    produrrebbero lo stesso cache-buster — con cache di un anno gli utenti
    resterebbero sul file vecchio senza modo di accorgersene.
    """
    latest = 0
    for folder in ("css", "js"):
        base = os.path.join(_BASE_DIR, "static", folder)
        for root, _dirs, files in os.walk(base):
            for name in files:
                try:
                    latest = max(latest, os.stat(os.path.join(root, name)).st_mtime_ns)
                except OSError:
                    continue
    return str(latest)


def _flag(name: str, default: str = "true") -> bool:
    """Legge una variabile d'ambiente booleana con la convenzione del progetto."""
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


class Config:
    """Configurazione base.

    **Le impostazioni che vengono dall'ambiente stanno in
    ``environment_settings()``, non nel corpo della classe.**

    Il corpo di una classe viene eseguito una volta sola, all'``import``. Un
    ``SECRET_KEY = os.environ.get("SECRET_KEY")`` scritto qui fotografa
    l'ambiente di quel preciso istante e non lo rilegge mai più. Per la web
    app va bene — le variabili sono già nel processo prima di ogni import —
    ma per gli script da console e gli scheduled task no: quelli le env di
    produzione se le devono andare a prendere dal file WSGI
    (``scripts/prod_env.py``), e se ciò accade dopo l'import di ``config`` il
    valore congelato è quello sbagliato **per sempre**.

    È il guasto che ha fermato ``daily_jobs.py`` e ``send_match_reminders.py``
    ogni notte: entrambi facevano ``from app import create_app`` in cima al
    file, quindi ``config`` era già importato quando ``bootstrap_or_exit()``
    popolava ``os.environ``. Il log risultava contraddittorio — "Env di
    produzione lette da ...: SECRET_KEY" seguito da "SECRET_KEY env var must
    be set in production" — perché le due righe raccontano momenti diversi.

    Mettendo quei valori in un classmethod, ``create_app`` può rileggerli al
    momento giusto (``app.py``), e l'ordine degli import smette di essere una
    trappola. Gli attributi di classe restano comunque valorizzati — c'è chi
    legge ``Config.APP_NAME`` direttamente — ma li scrive il ciclo in fondo al
    modulo, sempre da ``environment_settings()``: una fonte sola, nessuna
    possibilità che le due divergano.
    """

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ADMIN_PASSWORD_REQUIRED = False

    # App Info
    APP_NAME = "Tornei Biliardo"

    # **Non si scrive a mano.** La riscrive release-please quando si unisce la
    # PR di rilascio, calcolandola dai titoli delle PR unite da allora
    # (`fix:` alza la patch, `feat:` la minor, `feat!:` la major). L'annotazione
    # in fondo alla riga e' esattamente cio' che il bot cerca per sapere dove
    # scrivere: toglierla non rompe niente di visibile, il numero semplicemente
    # smette di muoversi — per questo c'e' un test che la pretende
    # (`tests/new/unit/test_version_single_source.py`).
    #
    # Il valore compare nel footer di ogni pagina (`templates/base.html`) e
    # nella risposta di `/health`.
    VERSION = "1.12.0"  # x-release-please-version

    # Cache-buster per CSS/JS (vedi _compute_asset_version). Non dipende
    # dall'ambiente ma dal filesystem, quindi resta qui.
    ASSET_VERSION = _compute_asset_version()

    # Upload configurations
    UPLOAD_BASE_PATH = "static/uploads"
    CHALLENGE_UPLOAD_FOLDER = "challenges"
    VENUE_UPLOAD_FOLDER = "venues"
    # Locandine della vetrina social di gare e campionati (issue #235)
    BANNER_UPLOAD_FOLDER = "banners"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

    # I18n settings
    BABEL_DEFAULT_LOCALE = "it"
    BABEL_TRANSLATION_DIRECTORIES = "translations"

    # Onboarding obbligatorio (ADR-035): quando True, gli utenti non-admin con
    # onboarding non completato vengono reindirizzati alla pagina dedicata.
    # Attivo in dev e prod; disattivato nei test (vedi TestingConfig).
    ONBOARDING_ENFORCED = True

    # CSRF: il token resta obbligatorio, il *referrer* no.
    #
    # Flask-WTF, oltre a validare il token, su HTTPS pretende anche un header
    # `Referer` che combaci con l'host (`WTF_CSRF_SSL_STRICT`, default True) e
    # risponde 400 quando manca. È una difesa nata prima di SameSite, e oggi
    # scarica il costo su chi il referrer non lo manda: browser con la
    # privacy stretta, webview dentro altre app, estensioni e proxy che lo
    # tolgono. Per quelle persone *ogni* POST era 400 — login compreso, quindi
    # senza nemmeno un modo per entrare — mentre per tutti gli altri il sito
    # funzionava: un guasto che si vede solo addosso a qualcuno.
    #
    # Quel che resta a proteggere i form non è poco: il token firmato e legato
    # alla sessione (che un sito terzo non può leggere), il cookie di sessione
    # `SameSite=Lax` (che su un POST cross-site non viene proprio inviato) e
    # il controllo di `Origin` in `app.py`, che rifiuta l'unica cosa che il
    # referrer rifiutava davvero — una richiesta partita da un altro sito —
    # senza pretendere un header facoltativo.
    WTF_CSRF_SSL_STRICT = False

    # ...e il token non scade dopo un'ora.
    #
    # Il default di Flask-WTF è 3600 secondi, contati dalla **generazione della
    # pagina**. Su un telefono il browser non si chiude mai: una scheda con il
    # modulo di accesso aperta ieri sera ha il cookie di sessione ancora buono
    # e il token già scaduto, quindi al primo invio arriva 400 — la pagina «Il
    # tavolo si è raffreddato», che di suo dice il vero ma descrive un guasto
    # che non doveva esistere. Chi ricarica non se ne accorge più; chi riprende
    # la scheda da dove l'aveva lasciata ci sbatte ogni volta.
    #
    # `None` lega la validità del token a quella della **sessione**, che è la
    # cosa che il token protegge: finché il cookie vale, il modulo che ne
    # deriva vale. Un token rubato non diventa più pericoloso — per usarlo
    # servirebbe comunque il cookie di sessione della vittima, che è il vero
    # segreto, e quello scade per conto suo.
    WTF_CSRF_TIME_LIMIT = None

    @classmethod
    def environment_settings(cls) -> dict:
        """Le impostazioni che leggono ``os.environ``, risolte **adesso**.

        Ogni sottoclasse che vuole ignorare o forzare una di queste variabili
        lo fa sovrascrivendo questo metodo, non riscrivendo l'attributo nel
        corpo: un attributo di classe verrebbe rimpiazzato dal ciclo di
        allineamento in fondo al modulo, e la sovrascrittura sparirebbe.
        """
        app_name = cls.APP_NAME
        mail_username = os.environ.get("MAIL_USERNAME")
        return {
            "SECRET_KEY": (
                os.environ.get("SECRET_KEY")
                or "your-secret-key-change-this-in-production"
            ),
            "SQLALCHEMY_DATABASE_URI": (
                os.environ.get("DATABASE_URL") or "sqlite:///billiard_campionato.db"
            ),
            "DEBUG_MODE": _flag("DEBUG_MODE"),
            # Admin bootstrap (ENV-first)
            "ADMIN_USERNAME": os.environ.get("ADMIN_USERNAME") or "admin",
            "ADMIN_EMAIL": os.environ.get("ADMIN_EMAIL") or "admin@nowhere.it",
            "ADMIN_PASSWORD": os.environ.get("ADMIN_PASSWORD") or "admin123",
            # Email Service (SMTP)
            "MAIL_SERVER": os.environ.get("MAIL_SERVER") or "smtp.gmail.com",
            "MAIL_PORT": int(os.environ.get("MAIL_PORT") or 587),
            "MAIL_USE_TLS": _flag("MAIL_USE_TLS"),
            "MAIL_USERNAME": mail_username,
            "MAIL_PASSWORD": os.environ.get("MAIL_PASSWORD"),
            "MAIL_DEFAULT_SENDER": (
                os.environ.get("MAIL_DEFAULT_SENDER") or f"{app_name} <{mail_username}>"
            ),
            # Error tracking (GlitchTip/Sentry)
            "GLITCHTIP_DSN": os.environ.get("GLITCHTIP_DSN"),
            # Google Analytics 4 (ID misurazione, formato "G-XXXXXXXXXX").
            # Non impostato = nessuno snippet renderizzato: in sviluppo e nei
            # test il traffico locale non finisce nelle statistiche di
            # produzione.
            "GA_MEASUREMENT_ID": os.environ.get("GA_MEASUREMENT_ID"),
            # Segnalazioni degli utenti (issue #255): un token fine-grained
            # con `Issues: read and write` sul solo repo del progetto. Assente
            # = le segnalazioni si salvano lo stesso e restano in attesa; è il
            # job giornaliero a rispedirle quando il token c'è.
            "GITHUB_FEEDBACK_TOKEN": os.environ.get("GITHUB_FEEDBACK_TOKEN"),
            "GITHUB_FEEDBACK_REPO": (
                os.environ.get("GITHUB_FEEDBACK_REPO") or "coppolapaolo/tornei-biliardo"
            ),
        }


class DevelopmentConfig(Config):
    """Configurazione per sviluppo"""

    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Configurazione per produzione"""

    DEBUG = False
    TESTING = False
    ADMIN_PASSWORD_REQUIRED = True

    # Secure session cookies
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # NB: la cache lunga sugli asset NON si imposta qui con
    # SEND_FILE_MAX_AGE_DEFAULT, perché quello varrebbe per tutto /static/,
    # incluse le cartelle i cui file sono referenziati senza cache-buster
    # (img/, uploads/): resterebbero bloccati nei browser per un anno.
    # La policy è in app.py, applicata solo ai prefissi versionati.

    @classmethod
    def environment_settings(cls) -> dict:
        values = super().environment_settings()
        values.update(
            {
                # In produzione SECRET_KEY DEVE venire da env var: nessun
                # fallback, e `create_app` si ferma se manca (app.py).
                "SECRET_KEY": os.environ.get("SECRET_KEY") or "",
                # Idem per la password admin, che serve a
                # create_admin_if_not_exists().
                "ADMIN_PASSWORD": os.environ.get("ADMIN_PASSWORD") or None,
                # Sempre False in produzione, qualunque cosa dica l'ambiente.
                "DEBUG_MODE": False,
            }
        )
        return values


class TestingConfig(Config):
    """Configurazione per test"""

    TESTING = True
    WTF_CSRF_ENABLED = False
    # L'enforcement onboarding è opt-in nei test: la maggior parte usa utenti
    # con onboarding_completed=False e finirebbe reindirizzata. I test dedicati
    # (ADR-035) lo riattivano localmente con app.config["ONBOARDING_ENFORCED"].
    ONBOARDING_ENFORCED = False
    SQLALCHEMY_SESSION_OPTIONS = {"expire_on_commit": False}
    ADMIN_PASSWORD_REQUIRED = False

    @classmethod
    def environment_settings(cls) -> dict:
        """I test ignorano l'ambiente, di proposito.

        Un `DATABASE_URL` esportato nella shell (o un DSN GlitchTip che
        arriva da `.envrc`) non deve poter dirottare la suite sul DB di
        sviluppo né spedire eventi veri: qui le variabili che potrebbero
        farlo vengono forzate **dopo** la lettura dell'ambiente.
        """
        values = super().environment_settings()
        values.update(
            {
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "GLITCHTIP_DSN": None,
                "GA_MEASUREMENT_ID": None,
                "ADMIN_USERNAME": "admin",
                "ADMIN_EMAIL": "admin@campionato.local",
                "ADMIN_PASSWORD": "admin123",
            }
        )
        return values


# Mappatura configurazioni
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def _align_class_attributes() -> None:
    """Riporta sugli attributi di classe ciò che dice `environment_settings()`.

    Serve a chi legge `Config.APP_NAME` o `Config.ASSET_VERSION` direttamente
    (c'è: `models/shared/email_service.py`, e alcuni test). Senza questo
    passaggio quelle classi avrebbero solo i valori non ambientali, e un
    `Config.SECRET_KEY` sarebbe un AttributeError invece di un valore vecchio
    — un guasto diverso ma non migliore.

    Resta vero che l'unica lettura *affidabile* è `app.config`, popolata da
    `create_app` al momento giusto: questi attributi sono la fotografia
    dell'ambiente all'import, esattamente come prima.
    """
    for config_class in (
        Config,
        DevelopmentConfig,
        ProductionConfig,
        TestingConfig,
    ):
        for key, value in config_class.environment_settings().items():
            setattr(config_class, key, value)


_align_class_attributes()
