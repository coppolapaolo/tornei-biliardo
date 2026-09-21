"""Una migration pendente tiene sveglio il deploy anche senza codice nuovo.

`auto_deploy.py` usciva subito quando il `git pull` non portava niente e le
dipendenze erano in pari — ragionevole, se «niente da fare» e «niente di nuovo»
coincidessero. Non coincidono: una migration può essere pendente **perché è
fallita**, e il codice che la pretende è già in produzione da ieri.

È successo il 2026-09-20. Due migration su dieci sono fallite per l'ordine
alfabetico (vedi `test_runner_riprova_le_fallite.py`), quindi non sono state
marcate applicate; il giorno dopo il pull non aveva nulla da portare e lo
script si fermava a «No changes to deploy» senza mai guardarle. Il retry non
sarebbe arrivato col giro successivo ma col **prossimo merge** che porta
codice, e fino ad allora l'app girava su uno schema privo delle colonne che i
modelli dichiarano: 500 su ogni pagina delle schede di allenamento.

Le due direzioni si difendono insieme, perché è il secondo test a dare un
significato al primo: senza, «non esce mai» lo si otterrebbe togliendo
l'uscita anticipata, e ogni notte tranquilla finirebbe con un reload inutile
della web app sotto gli utenti collegati.
"""

from __future__ import annotations

import pytest

import scripts.auto_deploy as auto_deploy


@pytest.fixture
def deploy_senza_codice_nuovo(monkeypatch):
    """`main()` con ogni passo finto, e il pull che non porta niente.

    Restituisce la lista dove finiscono i passi realmente eseguiti.
    """
    eseguiti: list[str] = []

    monkeypatch.setenv("ENCRYPTION_KEY", "chiave-di-prova")
    monkeypatch.setattr(auto_deploy, "load_wsgi_env", lambda: {"ENCRYPTION_KEY": "x"})
    monkeypatch.setattr(auto_deploy, "git_pull", lambda: (True, "Already up to date"))
    monkeypatch.setattr(auto_deploy, "deps_in_sync", lambda: True)

    def _passo(nome, esito=(True, "ok")):
        def finto(*_args, **_kwargs):
            eseguiti.append(nome)
            return esito

        return finto

    monkeypatch.setattr(auto_deploy, "install_dependencies", _passo("dipendenze"))
    monkeypatch.setattr(auto_deploy, "run_migrations_safely", _passo("migrations"))
    monkeypatch.setattr(auto_deploy, "reload_webapp", _passo("reload"))
    return eseguiti


def test_le_migration_pendenti_non_si_saltano(deploy_senza_codice_nuovo, monkeypatch):
    """Due migration pendenti e nessun commit nuovo: si deve comunque migrare."""
    monkeypatch.setattr(auto_deploy, "count_pending_migrations", lambda: 2)

    auto_deploy.main()

    assert "migrations" in deploy_senza_codice_nuovo


def test_stato_non_determinabile_si_prosegue(deploy_senza_codice_nuovo, monkeypatch):
    """`None` è «non lo so»: si prosegue, come già fa lo step 3.

    Un deploy in più non ha mai fatto danni; una migration saltata sì.
    """
    monkeypatch.setattr(auto_deploy, "count_pending_migrations", lambda: None)

    auto_deploy.main()

    assert "migrations" in deploy_senza_codice_nuovo


def test_la_notte_tranquilla_resta_tranquilla(
    deploy_senza_codice_nuovo, monkeypatch, capsys
):
    """Niente codice nuovo, niente pendenti: si esce senza ricaricare la web app.

    Il reload è la cosa da non fare: ogni riavvio ha una finestra di 5xx per
    chi è collegato, ed è il motivo per cui nel 2026-09-14 il reload è stato
    tolto dalla CI.
    """
    monkeypatch.setattr(auto_deploy, "count_pending_migrations", lambda: 0)

    auto_deploy.main()

    assert deploy_senza_codice_nuovo == []
    assert "No changes to deploy." in capsys.readouterr().out
