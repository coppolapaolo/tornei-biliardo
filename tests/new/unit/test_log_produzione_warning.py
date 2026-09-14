"""Regression: l'error log del server web di produzione resta a WARNING.

Il 2026-09-14 l'error log di PythonAnywhere conteneva i `logger.info` dei
moduli del progetto. Nel repo nessuno li alza nel percorso della web app: solo
`development` fa `basicConfig(level=INFO)`, il file WSGI non tocca `logging`, e
`create_app("production")` in locale — con e senza DSN di GlitchTip — lascia il
root a WARNING. Chi lo abbassa sta quindi fuori dal codice, con ogni
probabilità nel caricamento WSGI di PythonAnywhere.

`configure_production_logging` riporta il root a WARNING e, prima di farlo,
scrive una riga con livello e handler che ha trovato: è quella riga a dire, in
produzione, chi li aveva impostati.

Vale **solo dentro uWSGI**. Gli script da console — `recalc_elo.py`,
`repair_match_ended_at.py` e gli altri — fanno `basicConfig(level=INFO)` e poi
creano l'app in configurazione production: un override senza condizioni
renderebbe muto il loro resoconto, dry-run compresi.
"""

import logging
import sys
import types
from unittest.mock import patch

import pytest

from app import configure_production_logging, create_app


class _Raccoglitore(logging.Handler):
    def __init__(self):
        super().__init__(logging.NOTSET)
        self.record = []

    def emit(self, record):
        self.record.append(record)


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
    uwsgi_prima = sys.modules.get("uwsgi")
    try:
        yield raccoglitore
    finally:
        root.removeHandler(raccoglitore)
        root.setLevel(livello_prima)
        for name, livello in livelli_prima.items():
            logging.getLogger(name).setLevel(livello)
        logging.getLogger("prova.logger_alzato").setLevel(logging.NOTSET)
        if uwsgi_prima is None:
            sys.modules.pop("uwsgi", None)
        else:
            sys.modules["uwsgi"] = uwsgi_prima


def _dentro_uwsgi():
    sys.modules["uwsgi"] = types.ModuleType("uwsgi")


def _fuori_da_uwsgi():
    sys.modules.pop("uwsgi", None)


def test_server_web_di_produzione_torna_a_warning(root_isolato):
    _dentro_uwsgi()

    configure_production_logging("production")
    logging.getLogger("routes.sse").info("non deve uscire")

    assert logging.getLogger().level == logging.WARNING
    messaggi = [r.getMessage() for r in root_isolato.record]
    assert "non deve uscire" not in messaggi


def test_la_riga_diagnostica_dice_cosa_ha_trovato(root_isolato):
    _dentro_uwsgi()

    configure_production_logging("production")

    avvisi = [r for r in root_isolato.record if r.levelno == logging.WARNING]
    assert len(avvisi) == 1
    testo = avvisi[0].getMessage()
    assert "INFO" in testo
    assert "_Raccoglitore" in testo


def test_un_logger_con_livello_proprio_torna_a_ereditare(root_isolato):
    """Se in produzione l'INFO arriva da un logger alzato a mano, non dal root."""
    _dentro_uwsgi()
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
    _dentro_uwsgi()
    logging.getLogger().setLevel(logging.WARNING)

    configure_production_logging("production")

    assert root_isolato.record == []
    assert logging.getLogger().level == logging.WARNING


def test_gli_script_da_console_restano_a_info(root_isolato):
    """`recalc_elo.py` & C.: basicConfig a INFO, poi app in production."""
    _fuori_da_uwsgi()

    configure_production_logging("production")
    logging.getLogger("scripts.recalc_elo").info("resoconto del dry-run")

    assert logging.getLogger().level == logging.INFO
    assert "resoconto del dry-run" in [r.getMessage() for r in root_isolato.record]


@pytest.mark.parametrize("config_name", ["development", "testing"])
def test_sviluppo_e_test_non_sono_toccati(root_isolato, config_name):
    _dentro_uwsgi()

    configure_production_logging(config_name)

    assert logging.getLogger().level == logging.INFO
    assert root_isolato.record == []


def test_create_app_la_chiama_con_la_propria_configurazione():
    with patch("app.configure_production_logging") as configura:
        create_app("testing")

    configura.assert_called_once_with("testing")
