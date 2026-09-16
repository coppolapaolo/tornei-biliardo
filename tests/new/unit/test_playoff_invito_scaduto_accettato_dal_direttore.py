"""Un invito scaduto lo riapre il direttore, solo per accettarlo, fino all'avvio.

`SPECIFICHE.md`, sezione «Playoff», nota del 2026-09-16. La scadenza scatta
quando il direttore apre la pagina del campionato: se coincide con l'orario di
gioco, chi arriva in sala senza aver risposto risulta scaduto proprio quando il
direttore va ad avviare la finale, e fino a oggi la lista non gli offriva più
niente — né la risposta per conto, che voleva un invito in attesa, né
l'aggiunta a mano, che lo trovava «già in lista». Il campionato 4 ha chiuso la
stagione in una gara a parte per questo.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.exceptions import ConflictError
from models.playoff.models import PlayoffQualification, QualificationStatus
from models.playoff.services import PlayoffService
from tests.new.unit.test_avvio_playoff import _make_user
from tests.new.unit.test_playoff_con_meno_accettazioni import (
    _accetta,
    _avvia,
    _invito,
    _iscritti,
    _playoff,
)


def _fai_scadere(cfg):
    """La scadenza passa e la pagina del direttore chiude gli inviti aperti."""
    scaduta = utc_now() - timedelta(hours=1)
    cfg.response_deadline = scaduta
    for q in PlayoffQualification.query.filter_by(configuration_id=cfg.id):
        if q.status == QualificationStatus.PENDING:
            q.expires_at = scaduta
    db.session.commit()
    PlayoffService.expire_old_qualifications()


def _scenario(db_session, *, posti=6, classificati=None):
    """Sei posti, quattro sì, due scaduti; il direttore è a parte."""
    _c, cfg, giocatori = _playoff(db_session, posti=posti, classificati=classificati)
    _accetta(cfg, *giocatori[:4])
    _fai_scadere(cfg)
    direttore = _make_user(db_session, role="director")
    db_session.commit()
    return cfg, giocatori, direttore


class TestIlDirettoreAccettaUnInvitoScaduto:
    def test_prima_della_gara_l_invito_torna_confermato_e_firmato(self, db_session):
        cfg, giocatori, direttore = _scenario(db_session)
        invito = _invito(cfg, giocatori[4])
        assert invito.status == QualificationStatus.EXPIRED

        PlayoffService.respond_on_behalf(
            invito.id, accept=True, responded_by_id=direttore.id
        )

        invito = db.session.get(PlayoffQualification, invito.id)
        assert invito.status == QualificationStatus.CONFIRMED
        assert invito.responded_by_id == direttore.id
        assert invito.answered_on_behalf
        gara = PlayoffService.create_playoff_gara(cfg.id)
        assert giocatori[4].id in _iscritti(gara.id)

    def test_a_gara_creata_entra_subito_fra_gli_iscritti(self, db_session):
        cfg, giocatori, direttore = _scenario(db_session)
        gara = PlayoffService.create_playoff_gara(cfg.id)
        assert giocatori[4].id not in _iscritti(gara.id)

        PlayoffService.respond_on_behalf(
            _invito(cfg, giocatori[4]).id, accept=True, responded_by_id=direttore.id
        )

        assert giocatori[4].id in _iscritti(gara.id)

    def test_entra_anche_oltre_i_posti(self, db_session):
        """È una decisione del direttore: il limite vale per la cascata.

        Cinque posti, sei in classifica: il quinto scade e la cascata chiama
        il sesto, che accetta. La gara è piena. Il quinto si presenta in sala
        e il direttore lo accetta: entra come sesto iscritto, non in lista
        d'attesa.
        """
        cfg, giocatori, direttore = _scenario(db_session, posti=5, classificati=6)
        sostituto = _invito(cfg, giocatori[5])
        assert sostituto.status == QualificationStatus.PENDING
        _accetta(cfg, giocatori[5])
        gara = PlayoffService.create_playoff_gara(cfg.id)
        assert len(_iscritti(gara.id)) == 5

        PlayoffService.respond_on_behalf(
            _invito(cfg, giocatori[4]).id, accept=True, responded_by_id=direttore.id
        )

        assert giocatori[4].id in _iscritti(gara.id)
        assert len(_iscritti(gara.id)) == 6

    def test_a_gara_avviata_no(self, db_session):
        cfg, giocatori, direttore = _scenario(db_session)
        gara = PlayoffService.create_playoff_gara(cfg.id)
        _avvia(gara.id)

        with pytest.raises(ConflictError):
            PlayoffService.respond_on_behalf(
                _invito(cfg, giocatori[4]).id,
                accept=True,
                responded_by_id=direttore.id,
            )
        assert _invito(cfg, giocatori[4]).status == QualificationStatus.EXPIRED


class TestLaPaginaDelCampionato:
    """La riga scaduta ha «Accetta» finché la gara non è avviata."""

    def _pagina(self, client, campionato_id, direttore):
        from flask import g

        with client.session_transaction() as sessione:
            sessione["_user_id"] = direttore.get_id()
        g.pop("_login_user", None)
        risposta = client.get(f"/admin/campionato/{campionato_id}")
        assert risposta.status_code == 200
        return risposta.get_data(as_text=True)

    def test_la_riga_scaduta_offre_accetta(self, client, db_session):
        cfg, _giocatori, _d = _scenario(db_session)
        admin = _make_user(db_session, role="admin")
        db_session.commit()

        html = self._pagina(client, cfg.campionato_id, admin)

        assert 'data-help="playoff-invito-scaduto"' in html
        assert "data-avviso-scadenza" in html

    def test_a_gara_avviata_la_riga_scaduta_resta_muta(self, client, db_session):
        cfg, _giocatori, _d = _scenario(db_session)
        admin = _make_user(db_session, role="admin")
        db_session.commit()
        gara = PlayoffService.create_playoff_gara(cfg.id)
        _avvia(gara.id)

        html = self._pagina(client, cfg.campionato_id, admin)

        assert 'data-help="playoff-invito-scaduto"' not in html


class TestCosaNonCambia:
    def test_uno_scaduto_non_si_rifiuta(self, db_session):
        """Il posto è già libero e il sostituto già chiamato: niente da fare."""
        cfg, giocatori, direttore = _scenario(db_session)
        with pytest.raises(ValueError, match="solo accettare"):
            PlayoffService.respond_on_behalf(
                _invito(cfg, giocatori[4]).id,
                accept=False,
                responded_by_id=direttore.id,
            )
        assert _invito(cfg, giocatori[4]).status == QualificationStatus.EXPIRED

    def test_il_giocatore_da_solo_non_riapre_il_suo_invito(self, db_session):
        cfg, giocatori, _direttore = _scenario(db_session)
        with pytest.raises(ValueError):
            PlayoffService.confirm_qualification(
                _invito(cfg, giocatori[4]).id, giocatori[4].id
            )
        assert _invito(cfg, giocatori[4]).status == QualificationStatus.EXPIRED

    def test_chi_ha_rifiutato_resta_rifiutato(self, db_session):
        cfg, giocatori, direttore = _scenario(db_session)
        rifiutato = _invito(cfg, giocatori[5])
        rifiutato.status = QualificationStatus.DECLINED
        db_session.commit()
        with pytest.raises(ValueError, match="già una risposta"):
            PlayoffService.respond_on_behalf(
                rifiutato.id, accept=True, responded_by_id=direttore.id
            )

    def test_un_sostituto_gia_chiamato_resta_in_lista(self, db_session):
        """La cascata ha già chiamato il primo degli esclusi alla scadenza: il
        rientro dello scaduto non gli toglie l'invito."""
        cfg, giocatori, direttore = _scenario(db_session, posti=5, classificati=6)
        scaduto = _invito(cfg, giocatori[4])
        assert scaduto.replaced_by_id == giocatori[5].id
        assert _invito(cfg, giocatori[5]).status == QualificationStatus.PENDING

        PlayoffService.respond_on_behalf(
            scaduto.id, accept=True, responded_by_id=direttore.id
        )

        assert _invito(cfg, giocatori[4]).status == QualificationStatus.CONFIRMED
        assert _invito(cfg, giocatori[5]).status == QualificationStatus.PENDING
