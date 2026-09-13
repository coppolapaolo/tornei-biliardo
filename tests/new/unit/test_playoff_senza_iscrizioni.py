"""La gara di playoff si avvia senza aprire le iscrizioni.

Rilievo del 2026-09-13: per far partire un playoff il direttore doveva aprire
le iscrizioni, con inizio e fine, su una gara a cui non si iscrive nessuno. Al
playoff si entra accettando l'invito, e inviti, accettazioni e rifiuti sono
già avvenuti prima che la gara esista. La gara di playoff resta quindi in
preparazione fino all'avvio: niente fase delle iscrizioni, né nella macchina a
stati né nella pagina del direttore (SPECIFICHE.md, «Playoff», nota del
2026-09-13).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.competition.direttore_view import FaseGara, fase_della_gara, striscia
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara
from models.competition.round_service import RoundService
from models.dashboard.comandi import ComandoDirezione, comando_per
from models.exceptions import ConflictError
from models.playoff.services import PlayoffService
from models.status_enum import GaraStatus
from tests.new.unit.test_avvio_playoff import (
    _make_campionato,
    _make_gara,
    _make_inscription,
    _make_user,
)
from tests.new.unit.test_playoff_con_meno_accettazioni import _accetta, _playoff

pytestmark = pytest.mark.unit


def _gara_di_playoff(db_session, posti: int = 4) -> Gara:
    _campionato, cfg, giocatori = _playoff(db_session, posti=posti)
    _accetta(cfg, *giocatori)
    return PlayoffService.create_playoff_gara(cfg.id)


class TestMacchinaAStati:
    def test_la_gara_di_playoff_nasce_in_preparazione_e_si_avvia_da_li(
        self, db_session
    ):
        gara = _gara_di_playoff(db_session)
        assert gara.status == GaraStatus.SETUP.value

        avviata = RoundService.start_first_round(gara.id)

        assert avviata.current_round == 1
        assert avviata.status == GaraStatus.PLAYING.value

    def test_aprire_le_iscrizioni_di_un_playoff_si_rifiuta(self, db_session):
        gara = _gara_di_playoff(db_session)
        adesso = utc_now()

        with pytest.raises(ConflictError):
            InscriptionService.open_inscriptions(
                gara.id, adesso, adesso + timedelta(hours=1)
            )

        ripresa = db.session.get(Gara, gara.id)
        assert ripresa is not None and ripresa.status == GaraStatus.SETUP.value

    def test_annullare_l_avvio_riporta_il_playoff_in_preparazione(self, db_session):
        gara = _gara_di_playoff(db_session)
        RoundService.start_first_round(gara.id)

        RoundService.cancel_first_round_startup(gara.id)

        ripresa = db.session.get(Gara, gara.id)
        assert ripresa is not None and ripresa.status == GaraStatus.SETUP.value
        assert RoundService.start_first_round(gara.id).current_round == 1

    def test_un_playoff_gia_aperto_alle_iscrizioni_si_avvia_ancora(self, db_session):
        """Le gare di playoff nate prima del 2026-09-13 possono essere lì."""
        gara = _gara_di_playoff(db_session)
        gara.status = GaraStatus.INSCRIPTION.value
        db_session.commit()

        assert RoundService.start_first_round(gara.id).current_round == 1

    def test_una_gara_normale_non_salta_le_iscrizioni(self, db_session):
        campionato = _make_campionato(db_session)
        gara = _make_gara(db_session, campionato, status=GaraStatus.SETUP.value)
        gara.min_participants = 2
        gara.current_round = 0  # `_make_gara` la crea come già avviata
        for _ in range(4):
            _make_inscription(db_session, _make_user(db_session), gara)
        db_session.commit()

        with pytest.raises(ValueError, match="Transizione non ammessa"):
            RoundService.start_first_round(gara.id)


class TestComandoEFasi:
    def test_il_comando_del_playoff_in_preparazione_e_avvia_la_gara(self, db_session):
        comando = comando_per(_gara_di_playoff(db_session))

        assert comando is not None
        assert comando.tipo == ComandoDirezione.AVVIA_GARA
        assert not comando.bloccato

    def test_senza_abbastanza_accettazioni_l_avvio_si_annuncia_bloccato(
        self, db_session
    ):
        gara = _gara_di_playoff(db_session)
        gara.min_participants = 10

        comando = comando_per(gara)

        assert comando is not None
        assert comando.tipo == ComandoDirezione.AVVIA_GARA
        assert comando.bloccato and comando.minimo == 10

    def test_un_playoff_con_la_finestra_scaduta_non_chiede_di_estenderla(
        self, db_session
    ):
        gara = _gara_di_playoff(db_session)
        adesso = utc_now()
        gara.status = GaraStatus.INSCRIPTION.value
        gara.inscription_start = adesso - timedelta(hours=2)
        gara.inscription_end = adesso - timedelta(hours=1)
        gara.min_participants = 10

        comando = comando_per(gara)

        assert comando is not None
        assert comando.tipo == ComandoDirezione.AVVIA_GARA

    def test_la_fase_del_playoff_prima_dell_avvio_e_la_preparazione(self):
        assert (
            fase_della_gara(GaraStatus.SETUP.value, playoff=True)
            == FaseGara.PREPARAZIONE
        )
        assert (
            fase_della_gara(GaraStatus.INSCRIPTION.value, playoff=True)
            == FaseGara.PREPARAZIONE
        )
        assert fase_della_gara(GaraStatus.INSCRIPTION.value) == FaseGara.ISCRIZIONI

    def test_la_striscia_del_playoff_non_ha_le_iscrizioni(self):
        tacche = striscia(FaseGara.GIOCO, con_spareggio=False, con_iscrizioni=False)
        assert [t.fase for t in tacche] == [
            FaseGara.PREPARAZIONE,
            FaseGara.GIOCO,
            FaseGara.CONCLUSA,
        ]
