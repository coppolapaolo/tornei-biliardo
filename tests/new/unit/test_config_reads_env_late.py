"""La configurazione deve leggere l'ambiente quando l'app si crea.

Non quando il modulo si importa. È la differenza fra un task che gira e uno
che muore ogni notte:

    Env di produzione lette da /var/www/..._wsgi.py: ... SECRET_KEY ...
    RuntimeError: SECRET_KEY env var must be set in production

Le due righe sembrano contraddirsi e invece raccontano momenti diversi.
`ProductionConfig.SECRET_KEY = os.environ.get("SECRET_KEY") or ""` era
un'assegnazione nel corpo della classe, eseguita una volta sola all'import di
`config`; e gli scheduled task importavano `app` (quindi `config`) in cima al
file, **prima** di caricare le env dal file WSGI. Il valore congelato era la
stringa vuota, per sempre.

Questi test scrivono nell'ambiente *dopo* che `config` è stato importato — la
sequenza esatta del guasto — e pretendono che il valore nuovo arrivi
comunque.
"""

from __future__ import annotations

import pytest

from config import Config, DevelopmentConfig, ProductionConfig, TestingConfig

# ══ Il guasto in sé ══════════════════════════════════════════════════════════


@pytest.mark.unit
def test_secret_key_impostata_dopo_l_import_viene_vista(monkeypatch):
    """Il modulo `config` è già importato da un pezzo: il valore deve arrivare
    lo stesso."""
    monkeypatch.setenv("SECRET_KEY", "arrivata-dal-file-wsgi")

    assert (
        ProductionConfig.environment_settings()["SECRET_KEY"]
        == "arrivata-dal-file-wsgi"
    )


@pytest.mark.unit
def test_senza_secret_key_la_produzione_resta_a_vuoto(monkeypatch):
    """Il fail-fast di `create_app` non va indebolito: in produzione non c'è
    fallback, e la stringa vuota è ciò che lo fa scattare."""
    monkeypatch.delenv("SECRET_KEY", raising=False)

    assert ProductionConfig.environment_settings()["SECRET_KEY"] == ""


@pytest.mark.unit
def test_fuori_produzione_il_default_c_e_ancora(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)

    chiave = DevelopmentConfig.environment_settings()["SECRET_KEY"]
    assert chiave and chiave != ""


@pytest.mark.unit
def test_credenziali_di_posta_impostate_dopo_l_import(monkeypatch):
    """Stessa trappola, conseguenza diversa e più silenziosa.

    Il task orario dei promemoria manda email: con MAIL_USERNAME/MAIL_PASSWORD
    congelate a None all'import, l'invio fallisce senza che nessuno lo veda.
    Il guasto su SECRET_KEY almeno gridava.
    """
    monkeypatch.setenv("MAIL_USERNAME", "tornei@example.test")
    monkeypatch.setenv("MAIL_PASSWORD", "segreta")
    # Un mittente esplicito vincerebbe su quello composto (ed è giusto così):
    # qui si sta verificando proprio la composizione.
    monkeypatch.delenv("MAIL_DEFAULT_SENDER", raising=False)

    valori = ProductionConfig.environment_settings()
    assert valori["MAIL_USERNAME"] == "tornei@example.test"
    assert valori["MAIL_PASSWORD"] == "segreta"
    # Il mittente di default si compone dal nome utente: va ricomposto anche lui.
    assert valori["MAIL_DEFAULT_SENDER"].endswith("<tornei@example.test>")


# ══ create_app applica davvero la rilettura ══════════════════════════════════


@pytest.mark.unit
def test_create_app_applica_le_impostazioni_ambientali(monkeypatch):
    """Il pezzo che chiude il cerchio: non basta che il classmethod sia giusto,
    `create_app` deve chiamarlo dopo `from_object`."""
    from app import create_app

    monkeypatch.setenv("MAIL_SERVER", "smtp.impostato-tardi.test")
    app = create_app("testing")

    assert app.config["MAIL_SERVER"] == "smtp.impostato-tardi.test"


# ══ Le sottoclassi che l'ambiente lo ignorano di proposito ══════════════════


@pytest.mark.unit
def test_i_test_non_si_fanno_dirottare_dal_database_url(monkeypatch):
    """Il rischio introdotto dalla rilettura, presidiato.

    Prima, `TestingConfig.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"` era
    un attributo di classe che vinceva su tutto. Rileggendo l'ambiente senza
    attenzione, un `DATABASE_URL` esportato nella shell dirotterebbe l'intera
    suite sul DB di sviluppo — cancellandolo a colpi di `db.drop_all()`.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite:///instance/billiard_campionato.db")

    valori = TestingConfig.environment_settings()
    assert valori["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"


@pytest.mark.unit
def test_i_test_non_spediscono_a_glitchtip(monkeypatch):
    """Stessa logica del punto precedente, su un'altra variabile che fa danni
    fuori dal processo (quota GlitchTip, incidente 2026-06-10)."""
    monkeypatch.setenv("GLITCHTIP_DSN", "https://chiave@glitchtip.example/42")

    assert TestingConfig.environment_settings()["GLITCHTIP_DSN"] is None
    assert TestingConfig.environment_settings()["GA_MEASUREMENT_ID"] is None


@pytest.mark.unit
def test_in_produzione_il_debug_mode_resta_spento(monkeypatch):
    """`DEBUG_MODE=true` nell'ambiente non deve poter riaprire le route di
    debug in produzione."""
    monkeypatch.setenv("DEBUG_MODE", "true")

    assert ProductionConfig.environment_settings()["DEBUG_MODE"] is False
    assert DevelopmentConfig.environment_settings()["DEBUG_MODE"] is True


# ══ Chi legge gli attributi di classe direttamente ══════════════════════════


@pytest.mark.unit
def test_gli_attributi_di_classe_esistono_ancora():
    """`models/shared/email_service.py` fa `APP_NAME = Config.APP_NAME`, e
    alcuni test leggono `Config.ASSET_VERSION` / `Config.GLITCHTIP_DSN`.

    Spostare i valori dentro un classmethod non deve trasformarli in
    AttributeError: il ciclo di allineamento in fondo a `config.py` li
    riporta sulle classi.
    """
    for classe in (Config, DevelopmentConfig, ProductionConfig, TestingConfig):
        for nome in ("SECRET_KEY", "SQLALCHEMY_DATABASE_URI", "MAIL_SERVER"):
            assert hasattr(classe, nome), f"{classe.__name__}.{nome} sparito"

    assert Config.APP_NAME == "Tornei Biliardo"
    assert TestingConfig.SQLALCHEMY_DATABASE_URI == "sqlite:///:memory:"
    assert TestingConfig.GLITCHTIP_DSN is None
