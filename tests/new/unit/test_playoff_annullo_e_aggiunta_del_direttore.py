"""Due regole del playoff decise il 2026-09-13, insieme alla #390.

1. **Annullato l'avvio** della finale, gli inviti chiusi proprio da quell'avvio
   tornano in attesa, purché la loro scadenza non sia passata: chi non aveva
   risposto può accettare ed entrare come prima. Gli inviti scaduti per la loro
   scadenza o già sostituiti restano come sono. Vale per **ogni** strada che
   riporta la gara in iscrizione: l'annullo del sorteggio, l'annullo del turno
   corrente e la cancellazione del primo turno.
2. **Il giocatore aggiunto a mano dal direttore entra sempre**, prima e dopo la
   creazione della gara, anche oltre i posti. Il limite dei posti vale per la
   cascata degli inviti: chi accetta tardi a posti pieni va in lista d'attesa.

`SPECIFICHE.md`, sezione «Playoff».
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.competition.models import Inscription
from models.competition.round_cancellation import RoundCancellationService
from models.competition.round_manager import AdvancedRoundManager
from models.playoff.models import QualificationStatus
from models.playoff.services import PlayoffService
from tests.new.unit.test_playoff_con_meno_accettazioni import (
    _accetta,
    _avvia,
    _invito,
    _iscritti,
    _playoff,
)


def _annulla_il_sorteggio(gara_id: int) -> None:
    RoundCancellationService.cancel_first_round_startup(gara_id)


def _annulla_il_turno_corrente(gara_id: int) -> None:
    RoundCancellationService.cancel_current_round_startup(gara_id)


def _cancella_il_primo_turno(gara_id: int) -> None:
    riuscito, messaggio = AdvancedRoundManager.cancel_round(gara_id, 1)
    assert riuscito, messaggio


ANNULLI = pytest.mark.parametrize(
    "annulla",
    [_annulla_il_sorteggio, _annulla_il_turno_corrente, _cancella_il_primo_turno],
    ids=["sorteggio", "turno_corrente", "cancella_turno"],
)


def _finale_avviata(db_session):
    """Cinque posti, quattro sì, un invito ancora aperto quando la finale parte."""
    _c, cfg, giocatori = _playoff(db_session, posti=5, classificati=8)
    _accetta(cfg, *giocatori[:4])
    gara = PlayoffService.create_playoff_gara(cfg.id)
    _avvia(gara.id)
    assert _invito(cfg, giocatori[4]).status == QualificationStatus.EXPIRED
    return cfg, gara, giocatori


class TestAnnullatoLAvvioGliInvitiSiRiaprono:
    @ANNULLI
    def test_l_invito_torna_in_attesa_e_chi_accetta_entra(self, db_session, annulla):
        cfg, gara, giocatori = _finale_avviata(db_session)

        annulla(gara.id)

        assert _invito(cfg, giocatori[4]).status == QualificationStatus.PENDING
        _accetta(cfg, giocatori[4])
        assert giocatori[4].id in _iscritti(gara.id)

    def test_l_invito_scaduto_per_la_sua_scadenza_resta_scaduto(self, db_session):
        cfg, gara, giocatori = _finale_avviata(db_session)
        invito = _invito(cfg, giocatori[4])
        invito.expires_at = utc_now() - timedelta(hours=1)
        db.session.commit()

        _annulla_il_sorteggio(gara.id)

        assert _invito(cfg, giocatori[4]).status == QualificationStatus.EXPIRED

    def test_l_invito_gia_sostituito_resta_scaduto(self, db_session):
        cfg, gara, giocatori = _finale_avviata(db_session)
        invito = _invito(cfg, giocatori[4])
        invito.replaced_by_id = giocatori[6].id
        db.session.commit()

        _annulla_il_sorteggio(gara.id)

        assert _invito(cfg, giocatori[4]).status == QualificationStatus.EXPIRED


class TestIlDirettoreAggiungeOltreIPosti:
    def test_prima_della_creazione_entra_e_la_finale_parte(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4, classificati=6)
        _accetta(cfg, *giocatori[:4])
        PlayoffService.admin_add_player(cfg.id, giocatori[5].id, "direttore")

        gara = PlayoffService.create_playoff_gara(cfg.id)

        assert _iscritti(gara.id) == {g.id for g in giocatori[:4]} | {giocatori[5].id}
        assert _avvia(gara.id).current_round == 1

    def test_dopo_la_creazione_entra_oltre_i_posti(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4, classificati=6)
        _accetta(cfg, *giocatori[:4])
        gara = PlayoffService.create_playoff_gara(cfg.id)

        PlayoffService.admin_add_player(cfg.id, giocatori[5].id, "direttore")

        assert len(_iscritti(gara.id)) == 5
        assert _avvia(gara.id).current_round == 1

    def test_chi_accetta_tardi_a_posti_pieni_va_in_lista_d_attesa(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4, classificati=6)
        _accetta(cfg, *giocatori[:3])
        gara = PlayoffService.create_playoff_gara(cfg.id)
        PlayoffService.admin_add_player(cfg.id, giocatori[5].id, "direttore")

        _accetta(cfg, giocatori[3])

        riga = Inscription.query.filter_by(
            gara_id=gara.id, user_id=giocatori[3].id
        ).first()
        assert riga is not None and riga.is_waitlist
        assert giocatori[3].id not in _iscritti(gara.id)

    def test_un_uscita_oltre_i_posti_non_promuove_la_lista_d_attesa(self, db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4, classificati=7)
        _accetta(cfg, *giocatori[:3])
        gara = PlayoffService.create_playoff_gara(cfg.id)
        for aggiunto in giocatori[5:7]:
            PlayoffService.admin_add_player(cfg.id, aggiunto.id, "direttore")
        _accetta(cfg, giocatori[3])
        assert giocatori[3].id not in _iscritti(gara.id)

        # Cinque attivi su quattro posti: un'uscita lascia la gara piena.
        PlayoffService.admin_remove_player(_invito(cfg, giocatori[0]).id, "direttore")
        assert giocatori[3].id not in _iscritti(gara.id)

        # Una seconda uscita libera un posto vero, e chi aspettava entra.
        PlayoffService.admin_remove_player(_invito(cfg, giocatori[1]).id, "direttore")
        assert giocatori[3].id in _iscritti(gara.id)


class TestLAggiuntaDelDirettoreRispettaLaParita:
    """L'aggiunta del direttore supera i posti, ma non la lista d'attesa per parità.

    Decisione del 2026-09-13: se la gara di playoff non ammette dispari —
    niente X e niente trio — chi resterebbe in più aspetta come gli altri
    finché non arriva un secondo giocatore, così la gara resta avviabile.
    """

    @staticmethod
    def _finale_senza_dispari(db_session):
        _c, cfg, giocatori = _playoff(db_session, posti=4, classificati=7)
        cfg.odd_number_policy = "no"
        db.session.commit()
        _accetta(cfg, *giocatori[:4])
        gara = PlayoffService.create_playoff_gara(cfg.id)
        assert gara.odd_number_policy == "no"
        return cfg, gara, giocatori

    def test_due_aggiunte_oltre_i_posti_con_numero_pari_entrano(self, db_session):
        cfg, gara, giocatori = self._finale_senza_dispari(db_session)

        for aggiunto in giocatori[5:7]:
            PlayoffService.admin_add_player(cfg.id, aggiunto.id, "direttore")

        assert _iscritti(gara.id) == {g.id for g in giocatori[:4]} | {
            giocatori[5].id,
            giocatori[6].id,
        }
        assert _avvia(gara.id).current_round == 1

    def test_l_aggiunta_che_renderebbe_dispari_aspetta_e_entra_col_secondo(
        self, db_session
    ):
        cfg, gara, giocatori = self._finale_senza_dispari(db_session)

        PlayoffService.admin_add_player(cfg.id, giocatori[5].id, "direttore")

        riga = Inscription.query.filter_by(
            gara_id=gara.id, user_id=giocatori[5].id
        ).first()
        assert riga is not None and riga.is_waitlist
        assert len(_iscritti(gara.id)) == 4

        PlayoffService.admin_add_player(cfg.id, giocatori[6].id, "direttore")

        assert {giocatori[5].id, giocatori[6].id} <= _iscritti(gara.id)

    def test_con_uno_in_attesa_per_parita_la_gara_resta_avviabile(self, db_session):
        cfg, gara, giocatori = self._finale_senza_dispari(db_session)
        PlayoffService.admin_add_player(cfg.id, giocatori[5].id, "direttore")

        assert _avvia(gara.id).current_round == 1
        assert giocatori[5].id not in _iscritti(gara.id)
