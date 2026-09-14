"""Regression: l'error log del server web di produzione resta a WARNING.

Il 2026-09-14 l'error log di PythonAnywhere conteneva i `logger.info` dei
moduli del progetto. Nel repo nessuno li alza nel percorso della web app: solo
`development` fa `basicConfig(level=INFO)`, il file WSGI non tocca `logging`, e
`create_app("production")` in locale lascia il root a WARNING.

La prima correzione (#427) valeva solo se il processo risultava dentro uWSGI,
e controllava solo all'avvio. In produzione non ha fatto nulla: nessuna riga
diagnostica, e `Triggered nudge …` — un `logger.info` — ancora nell'error log
tre minuti dopo il reload. O il rilevamento di uWSGI era falso, o il livello
scende dopo `create_app`. Da qui le due regole di adesso:

* vale per ogni app `production` **tranne** quelle create dagli script via
  `scripts/prod_env.bootstrap_and_create_app`, che fanno `basicConfig(INFO)`
  apposta per il loro resoconto;
* il controllo si ripete **alla prima richiesta** di ogni processo, e la riga
  diagnostica dice anche cosa avrebbe risposto il vecchio rilevamento di
  uWSGI, così l'error log dice quale delle due spiegazioni era vera.
"""

import logging
from unittest.mock import patch

import pytest
from flask import Flask

from app import (
    configure_production_logging,
    create_app,
    registra_controllo_logging_alla_prima_richiesta,
)


class _Raccoglitore(logging.Handler):
    def __init__(self):
        super().__init__(logging.NOTSET)
        self.record = []

    def emit(self, record):
        self.record.append(record)

    def avvisi(self):
        return [r.getMessage() for r in self.record if r.levelno == logging.WARNING]


@pytest.fixture
def root_isolato():
    """Root a INFO con un handler che raccoglie; stato ripristinato alla fine.

    Si salvano i livelli di **tutti** i logger, non solo del root: altri test
    dello stesso worker creano l'app in `development`, che alza a INFO
    `routes.admin.match`, e la funzione sotto test li riporta a NOTSET.
    """
    root = logging.getLogger()
    livello_prima = root.level
    livelli_prima = {
        name: logger.level
        for name, logger in logging.root.manager.loggerDict.items()
        if isinstance(logger, logging.Logger)
    }
    for name, livello in livelli_prima.items():
        if logging.NOTSET < livello < logging.WARNING:
            logging.getLogger(name).setLevel(logging.NOTSET)
    raccoglitore = _Raccoglitore()
    root.addHandler(raccoglitore)
    root.setLevel(logging.INFO)
    try:
        yield raccoglitore
    finally:
        root.removeHandler(raccoglitore)
        root.setLevel(livello_prima)
        for name, livello in livelli_prima.items():
            logging.getLogger(name).setLevel(livello)
        logging.getLogger("prova.logger_alzato").setLevel(logging.NOTSET)


def test_server_web_di_produzione_torna_a_warning(root_isolato):
    configure_production_logging("production")
    logging.getLogger("routes.sse").info("non deve uscire")

    assert logging.getLogger().level == logging.WARNING
    messaggi = [r.getMessage() for r in root_isolato.record]
    assert "non deve uscire" not in messaggi


def test_non_dipende_dal_rilevamento_di_uwsgi(root_isolato):
    """In produzione il rilevamento di uWSGI è stato la prima sospettata."""
    with patch("app._inside_uwsgi", return_value=False):
        configure_production_logging("production")

    assert logging.getLogger().level == logging.WARNING


def test_la_riga_diagnostica_dice_cosa_ha_trovato(root_isolato):
    with patch("app._inside_uwsgi", return_value=False):
        configure_production_logging("production")

    avvisi = root_isolato.avvisi()
    assert len(avvisi) == 1
    testo = avvisi[0]
    assert "avvio" in testo
    assert "INFO" in testo
    assert "_Raccoglitore" in testo
    assert "uWSGI rilevato: False" in testo


def test_un_logger_con_livello_proprio_torna_a_ereditare(root_isolato):
    """Se in produzione l'INFO arriva da un logger alzato a mano, non dal root."""
    logging.getLogger().setLevel(logging.WARNING)
    alzato = logging.getLogger("prova.logger_alzato")
    alzato.setLevel(logging.INFO)

    configure_production_logging("production")
    alzato.info("non deve uscire")

    assert alzato.level == logging.NOTSET
    messaggi = [r.getMessage() for r in root_isolato.record]
    assert "non deve uscire" not in messaggi
    assert any("prova.logger_alzato" in m for m in messaggi)


def test_nessuna_riga_se_il_root_e_gia_a_warning(root_isolato):
    logging.getLogger().setLevel(logging.WARNING)

    configure_production_logging("production")

    assert root_isolato.record == []
    assert logging.getLogger().level == logging.WARNING


def test_gli_script_da_console_restano_a_info(root_isolato):
    """`recalc_elo.py` & C.: basicConfig a INFO, poi app via bootstrap."""
    configure_production_logging("production", da_script=True)
    logging.getLogger("scripts.recalc_elo").info("resoconto del dry-run")

    assert logging.getLogger().level == logging.INFO
    assert "resoconto del dry-run" in [r.getMessage() for r in root_isolato.record]


@pytest.mark.parametrize("config_name", ["development", "testing"])
def test_sviluppo_e_test_non_sono_toccati(root_isolato, config_name):
    configure_production_logging(config_name)

    assert logging.getLogger().level == logging.INFO
    assert root_isolato.record == []


def _app_con_controllo():
    app = Flask(__name__)

    @app.route("/")
    def home():
        return "ok"

    registra_controllo_logging_alla_prima_richiesta(app)
    return app


def test_livello_abbassato_dopo_l_avvio_torna_a_warning_alla_prima_richiesta(
    root_isolato,
):
    """Il caso che l'avvio non può vedere: qualcuno abbassa il livello dopo."""
    app = _app_con_controllo()
    logging.getLogger().setLevel(logging.INFO)

    app.test_client().get("/")

    assert logging.getLogger().level == logging.WARNING
    avvisi = root_isolato.avvisi()
    assert len(avvisi) == 1
    assert "prima richiesta" in avvisi[0]


def test_la_seconda_richiesta_non_ripete_il_controllo(root_isolato):
    app = _app_con_controllo()
    client = app.test_client()
    client.get("/")
    logging.getLogger().setLevel(logging.INFO)

    client.get("/")

    assert len(root_isolato.avvisi()) == 1
    assert logging.getLogger().level == logging.INFO


def test_create_app_passa_la_propria_configurazione_e_la_provenienza():
    with patch(
        "app.configure_production_logging", return_value=False
    ) as configura, patch(
        "app.registra_controllo_logging_alla_prima_richiesta"
    ) as registra:
        create_app("testing")

    configura.assert_called_once_with("testing", da_script=False)
    registra.assert_not_called()


def test_create_app_registra_il_controllo_quando_si_applica():
    with patch("app.configure_production_logging", return_value=True), patch(
        "app.registra_controllo_logging_alla_prima_richiesta"
    ) as registra:
        app = create_app("testing")

    registra.assert_called_once_with(app)
