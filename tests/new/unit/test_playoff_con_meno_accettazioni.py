"""Il playoff si gioca con chi ha accettato, anche se sono meno dei posti.

`SPECIFICHE.md`, sezione «Playoff»: l'invito scorre fino a quando i posti sono
coperti **oppure sono finiti i giocatori**. Fino al 2026-09-13 l'app non ci
arrivava per due strade:

* la gara di playoff nasceva col minimo di default delle gare di serata, sei
  iscritti, che nessuno le cambiava: sei posti con quattro «sì» non partiva, e
  un playoff da quattro posti non partiva nemmeno con quattro «sì»;
* «Crea la gara playoff» iscriveva i confermati **di quel momento**: chi
  accettava dopo, compreso il sostituto chiamato da un rifiuto, restava
  confermato ma fuori dalla gara, e senza nessun modo di rientrarci.

Regola decisa: l'ordine resta «prima gli inviti, poi la gara», e chi accetta
dopo la creazione **entra** fino all'avvio del primo turno. All'avvio gli
inviti ancora senza risposta scadono, senza chiamare sostituti: la finale è
cominciata e un posto non si riempie più.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.models import Inscription
from models.competition.round_service import RoundService
from models.dashboard.section_builders import DashboardSectionBuilder
from models.exceptions import ConflictError
from models.status_enum import GaraStatus
from models.playoff.models import PlayoffQualification, QualificationStatus
from models.playoff.services import PlayoffService
from tests.new.unit.test_avvio_playoff import (
    _make_campionato,
    _make_classification,
    _make_config,
    _make_gara,
    _make_inscription,
    _make_user,
)


def _invito(cfg, giocatore) -> PlayoffQualification:
    return PlayoffQualification.query.filter_by(
        configuration_id=cfg.id, user_id=giocatore.id
    ).first()


def _playoff(db_session, *, posti: int, classificati: int | None = None):
    """Campionato terminato, playoff avviato: gli inviti sono partiti."""
    campionato = _make_campionato(db_session, terminated=True)
    cfg = _make_config(db_session, campionato, pos_to=posti, max_p=posti)
    gara = _make_gara(db_session, campionato)
    giocatori = []
    for posizione in range(1, (classificati or posti) + 1):
        giocatore = _make_user(db_session)
        _make_classification(db_session, campionato, giocatore, posizione)
        _make_inscription(db_session, giocatore, gara)
        giocatori.append(giocatore)
    db_session.commit()
    PlayoffService.start_playoff(campionato.id)
    return campionato, cfg, giocatori


def _accetta(cfg, *giocatori):
    for giocatore in giocatori:
        PlayoffService.confirm_qualification(_invito(cfg, giocatore).id, giocatore.id)


def _rifiuta(cfg, giocatore):
    return PlayoffService.decline_qualification(
        _invito(cfg, giocatore).id, giocatore.id
    )


def _iscritti(gara_id: int) -> set[int]:
    return {
        riga.user_id
        for riga in Inscription.query.filter_by(
            gara_id=gara_id, is_withdrawn=False, is_waitlist=False
        )
    }


def _avvia(gara_id: int):
    """Dalla preparazione: il playoff non ha iscrizioni da aprire."""
    return RoundService.start_first_round(gara_id)


class TestSiGiocaConChiHaAccettato:
    def test_la_gara_di_playoff_nasce_col_minimo_di_due(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=6)
        _accetta(cfg, *giocatori[:4])
        for giocatore in giocatori[4:]:
            assert _rifiuta(cfg, giocatore) is None

        gara = PlayoffService.create_playoff_gara(cfg.id)

        assert gara.min_participants == 2
        assert _iscritti(gara.id) == {g.id for g in giocatori[:4]}
        avviata = _avvia(gara.id)
        assert avviata.current_round == 1

    def test_un_playoff_da_quattro_parte_con_tutti_e_quattro(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4)
        _accetta(cfg, *giocatori)

        gara = PlayoffService.create_playoff_gara(cfg.id)

        assert _avvia(gara.id).current_round == 1


class TestChiAccettaDopoLaCreazioneEntra:
    def test_il_giocatore_che_accetta_dopo_entra_fra_gli_iscritti(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=6)
        _accetta(cfg, *giocatori[:4])
        gara = PlayoffService.create_playoff_gara(cfg.id)

        _accetta(cfg, giocatori[4])

        assert giocatori[4].id in _iscritti(gara.id)

    def test_il_sostituto_chiamato_dopo_la_creazione_entra(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4, classificati=6)
        _accetta(cfg, *giocatori[:3])
        gara = PlayoffService.create_playoff_gara(cfg.id)

        sostituto = _rifiuta(cfg, giocatori[3])
        assert sostituto is not None and sostituto.user_id == giocatori[4].id
        _accetta(cfg, giocatori[4])

        assert _iscritti(gara.id) == {g.id for g in giocatori[:3]} | {giocatori[4].id}

    def test_la_risposta_registrata_dal_direttore_iscrive(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=6)
        _accetta(cfg, *giocatori[:4])
        gara = PlayoffService.create_playoff_gara(cfg.id)
        direttore = _make_user(db_session, role="director")

        PlayoffService.respond_on_behalf(
            _invito(cfg, giocatori[5]).id, accept=True, responded_by_id=direttore.id
        )

        assert giocatori[5].id in _iscritti(gara.id)

    def test_entra_anche_a_finestra_di_iscrizione_chiusa(self, db_session):
        """La finestra serve alle gare aperte a tutti: qui l'invito è il biglietto."""
        _c, cfg, giocatori = _playoff(db_session, posti=6)
        _accetta(cfg, *giocatori[:4])
        gara = PlayoffService.create_playoff_gara(cfg.id)
        # Oggi la gara di playoff non ha finestra; una nata prima del
        # 2026-09-13 poteva averla, anche scaduta, e l'invito vale lo stesso.
        adesso = utc_now()
        gara.status = GaraStatus.INSCRIPTION.value
        gara.inscription_start = adesso - timedelta(hours=2)
        gara.inscription_end = adesso - timedelta(hours=1)
        db.session.commit()

        _accetta(cfg, giocatori[4])

        assert giocatori[4].id in _iscritti(gara.id)


class TestAllAvvioGliInvitiSiChiudono:
    def test_gli_inviti_in_attesa_scadono_senza_chiamare_sostituti(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4, classificati=8)
        _accetta(cfg, *giocatori[:3])
        gara = PlayoffService.create_playoff_gara(cfg.id)

        _avvia(gara.id)

        assert _invito(cfg, giocatori[3]).status == QualificationStatus.EXPIRED
        assert (
            PlayoffQualification.query.filter_by(configuration_id=cfg.id).count() == 4
        )
        assert DashboardSectionBuilder.build_playoff_invitations(giocatori[3].id) == []
        assert _iscritti(gara.id) == {g.id for g in giocatori[:3]}

    def test_dopo_l_avvio_un_si_viene_rifiutato(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4, classificati=8)
        _accetta(cfg, *giocatori[:3])
        gara = PlayoffService.create_playoff_gara(cfg.id)
        _avvia(gara.id)
        # Un invito rimasto aperto per altre vie, per esempio un invio in
        # ritardo: l'avvio lo avrebbe chiuso, qui lo si riapre a mano.
        ritardatario = _invito(cfg, giocatori[3])
        ritardatario.status = QualificationStatus.PENDING
        db.session.commit()

        with pytest.raises(ConflictError):
            _accetta(cfg, giocatori[3])

        assert giocatori[3].id not in _iscritti(gara.id)

    def test_una_gara_di_serata_non_tocca_gli_inviti(self, db_session):
        """Solo la gara del playoff chiude gli inviti: le altre non ne hanno."""
        campionato, cfg, giocatori = _playoff(db_session, posti=4, classificati=8)
        serata = _make_gara(db_session, campionato, number=2)
        serata.status = "setup"
        serata.current_round = 0
        serata.min_participants = 2
        for giocatore in giocatori[4:8]:
            _make_inscription(db_session, giocatore, serata)
        db_session.commit()
        # Una gara di serata le iscrizioni le apre: il salto vale solo per il
        # playoff.
        adesso = utc_now()
        InscriptionService.open_inscriptions(
            serata.id, adesso, adesso + timedelta(hours=2)
        )

        _avvia(serata.id)

        assert _invito(cfg, giocatori[0]).status == QualificationStatus.PENDING


class TestLaListaDelDirettoreFinoAllAvvio:
    def test_chi_aggiunge_il_direttore_dopo_la_creazione_entra(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4, classificati=6)
        _accetta(cfg, *giocatori[:3])
        gara = PlayoffService.create_playoff_gara(cfg.id)

        PlayoffService.admin_add_player(cfg.id, giocatori[5].id, "direttore")

        assert giocatori[5].id in _iscritti(gara.id)

    def test_chi_toglie_il_direttore_dopo_la_creazione_esce(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4)
        _accetta(cfg, *giocatori)
        gara = PlayoffService.create_playoff_gara(cfg.id)

        PlayoffService.admin_remove_player(_invito(cfg, giocatori[0]).id, "direttore")

        assert giocatori[0].id not in _iscritti(gara.id)

    def test_dopo_l_avvio_la_lista_non_si_tocca_piu(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4, classificati=6)
        _accetta(cfg, *giocatori[:4])
        gara = PlayoffService.create_playoff_gara(cfg.id)
        _avvia(gara.id)

        with pytest.raises(ConflictError):
            PlayoffService.admin_add_player(cfg.id, giocatori[5].id, "direttore")
        with pytest.raises(ConflictError):
            PlayoffService.admin_remove_player(
                _invito(cfg, giocatori[0]).id, "direttore"
            )
