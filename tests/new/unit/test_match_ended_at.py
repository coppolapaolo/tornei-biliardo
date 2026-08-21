"""La partita chiusa dai due giocatori ha una data di fine.

Regressione di un difetto silenzioso: `_complete_match_after_confirmation`
scriveva la data dentro un `if hasattr(self, "completed_at")`, ma la colonna
era stata rinominata `ended_at`. Da quel rinomino il guard è stato sempre
falso, quindi la riga non si è più eseguita — senza errori e senza test rossi.

In produzione erano 40 partite su 367 senza data di fine (censimento del
2026-08-21), e non un campione casuale: **esattamente** quelle chiuse dalla
doppia conferma. Quelle chiuse dal direttore passano da
`MatchStateService.to_completed`, che la data la scrive.

Il danno non era estetico: SQLite ordina i NULL **per primi**, e
`recalculate_all_elo` rigioca la storia con `ORDER BY ended_at ASC`.

Vedi `scripts/repair_match_ended_at.py` per la riparazione dei dati storici.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from models.base import utc_now
from models.status_enum import MatchStatus

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _carica_riparazione() -> Any:
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_match_ended_at", _SCRIPTS / "repair_match_ended_at.py"
    )
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


riparazione = _carica_riparazione()


@pytest.fixture
def partita(db_session, isolated_players):
    """Una partita di gara in corso, fra due giocatori."""
    from models.competition.models import Gara
    from models.match.models import Match
    from models.status_enum import GaraStatus

    gara = Gara(
        number=1,
        name="Gara di prova",
        date=utc_now().date(),
        time=utc_now().time(),
        discipline="8_ball",
        distance=5,
        is_race_to=True,
        status=GaraStatus.INSCRIPTION.value,
    )
    db_session.add(gara)
    db_session.flush()

    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=isolated_players[0].id,
        player2_id=isolated_players[1].id,
        player1_score=0,
        player2_score=0,
        status=MatchStatus.PLAYING.value,
    )
    db_session.add(match)
    db_session.commit()
    return match


class TestDoppiaConfermaScriveLaData:
    def test_la_seconda_conferma_chiude_e_data_la_partita(self, db_session, partita):
        """È il difetto originale: qui `ended_at` restava None."""
        partita.player1_score = 5
        partita.player2_score = 3
        partita.status = MatchStatus.PLAYING.value
        partita.ended_at = None

        partita.confirm_result(partita.player1_id)
        assert partita.ended_at is None, "una sola conferma non chiude nulla"

        partita.confirm_result(partita.player2_id)

        assert partita.status == MatchStatus.CONFIRMED_BY_BOTH.value
        assert partita.ended_at is not None

    def test_una_data_fissata_a_mano_non_viene_sovrascritta(self, db_session, partita):
        """Il direttore può fissare data e ora di fine: hanno la precedenza.

        Stessa regola di `MatchStateService.to_completed`, che scrive solo se
        il campo è vuoto.
        """
        scelta = datetime(2026, 3, 14, 21, 30)
        partita.player1_score = 5
        partita.player2_score = 3
        partita.status = MatchStatus.PLAYING.value
        partita.ended_at = scelta

        partita.confirm_result(partita.player1_id)
        partita.confirm_result(partita.player2_id)

        assert partita.ended_at == scelta


class TestOgniStatoFinaleTimbraLaData:
    """L'invariante non dipende da quale percorso ha chiuso la partita.

    I percorsi che chiudevano senza scrivere la data erano quattro, e
    correggerli uno a uno avrebbe lasciato scoperto il quinto. Qui si verifica
    la garanzia a valle: qualunque scrittura che porti la partita in uno stato
    finale le lascia una data.
    """

    def test_il_pareggio_a_rack_esatti_riceve_la_data(self, db_session, partita):
        """`ScoringService` chiude cosi' i pari, senza passare da to_completed."""
        partita.player1_score = 2
        partita.player2_score = 2
        partita.winner_id = None
        partita.status = MatchStatus.CLOSED_UNILATERALLY.value
        db_session.flush()

        assert partita.ended_at is not None

    def test_il_walkover_da_ritiro_riceve_la_data(self, db_session, partita):
        """`WithdrawPolicyService` assegna il punteggio e chiude d'ufficio."""
        partita.player1_score = 5
        partita.player2_score = 0
        partita.winner_id = partita.player1_id
        partita.status = MatchStatus.CLOSED_UNILATERALLY.value
        db_session.flush()

        assert partita.ended_at is not None

    def test_una_partita_creata_gia_chiusa_riceve_la_data(
        self, db_session, isolated_players, partita
    ):
        """Il bye Amalfi nasce direttamente in stato finale: vale l'insert."""
        from models.match.models import Match

        bye = Match(
            gara_id=partita.gara_id,
            round_number=1,
            player1_id=isolated_players[2].id,
            player2_id=None,
            player1_score=1,
            player2_score=0,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
        )
        db_session.add(bye)
        db_session.flush()

        assert bye.ended_at is not None

    def test_uno_stato_non_finale_non_timbra_niente(self, db_session, partita):
        partita.status = MatchStatus.PLAYING.value
        db_session.flush()

        assert partita.ended_at is None

    def test_una_data_gia_scritta_non_viene_sovrascritta(self, db_session, partita):
        scelta = datetime(2026, 3, 14, 21, 30)
        partita.ended_at = scelta
        partita.status = MatchStatus.CLOSED_UNILATERALLY.value
        db_session.flush()

        assert partita.ended_at == scelta

    def test_toccare_una_partita_gia_chiusa_non_le_inventa_una_data(
        self, db_session, partita
    ):
        """Il punto piu' delicato dell'intero hook.

        Le 63 righe storiche vanno riparate ricostruendo la data **vera** con
        `repair_match_ended_at.py`. Se l'hook timbrasse a ogni aggiornamento,
        basterebbe un ricalcolo che sfiora quelle partite per scrivergli sopra
        la data di oggi — e la ricostruzione diventerebbe impossibile.
        Si timbra solo la **transizione**.
        """
        partita.status = MatchStatus.CLOSED_UNILATERALLY.value
        db_session.flush()
        partita.ended_at = None  # come le righe storiche in produzione
        db_session.flush()

        partita.player1_score = 4  # un aggiornamento qualunque
        db_session.flush()

        assert partita.ended_at is None


def _rack(quando, cancellato=False):
    return SimpleNamespace(created_at=quando, added_at=None, is_deleted=cancellato)


class TestRicostruzioneDellaData:
    """Da dove lo script ricava la data, e con quale precedenza."""

    def test_vince_la_seconda_conferma(self):
        """È l'istante esatto della chiusura: la conferma *è* la chiusura."""
        prima = datetime(2026, 3, 14, 21, 0)
        dopo = datetime(2026, 3, 14, 21, 12)
        match = SimpleNamespace(
            player1_confirmed_at=prima,
            player2_confirmed_at=dopo,
            racks=[_rack(datetime(2026, 3, 14, 20, 55))],
            gara=None,
        )
        quando, fonte = riparazione.ricostruisci(match)
        assert quando == dopo
        assert fonte == "seconda conferma"

    def test_senza_conferme_si_usa_l_ultimo_rack(self):
        ultimo = datetime(2026, 3, 14, 20, 55)
        match = SimpleNamespace(
            player1_confirmed_at=None,
            player2_confirmed_at=None,
            racks=[_rack(ultimo - timedelta(minutes=10)), _rack(ultimo)],
            gara=None,
        )
        quando, fonte = riparazione.ricostruisci(match)
        assert quando == ultimo
        assert fonte == "ultimo rack"

    def test_i_rack_cancellati_valgono_solo_se_non_ne_restano_altri(self):
        """Un rack cancellato dice comunque quando si stava giocando.

        Ma se ne esiste uno vivo, è quello a raccontare la fine della partita:
        il cancellato potrebbe essere stato tolto molto dopo.
        """
        vivo = datetime(2026, 3, 14, 20, 55)
        cancellato = datetime(2026, 3, 14, 23, 0)
        match = SimpleNamespace(
            player1_confirmed_at=None,
            player2_confirmed_at=None,
            racks=[_rack(vivo), _rack(cancellato, cancellato=True)],
            gara=None,
        )
        assert riparazione.ricostruisci(match) == (vivo, "ultimo rack")

        solo_cancellati = SimpleNamespace(
            player1_confirmed_at=None,
            player2_confirmed_at=None,
            racks=[_rack(cancellato, cancellato=True)],
            gara=None,
        )
        quando, fonte = riparazione.ricostruisci(solo_cancellati)
        assert quando == cancellato
        assert fonte == "ultimo rack (anche cancellato)"

    def test_ultimo_appiglio_la_data_della_gara(self):
        from datetime import date, time

        match = SimpleNamespace(
            player1_confirmed_at=None,
            player2_confirmed_at=None,
            racks=[],
            gara=SimpleNamespace(date=date(2026, 3, 14), time=time(18, 0)),
        )
        quando, fonte = riparazione.ricostruisci(match)
        assert quando == datetime(2026, 3, 14, 18, 0)
        assert fonte == "data della gara"

    def test_senza_alcun_appiglio_non_si_inventa_niente(self):
        """Un buco dichiarato è meglio di una data plausibile e falsa."""
        match = SimpleNamespace(
            player1_confirmed_at=None,
            player2_confirmed_at=None,
            racks=[],
            gara=None,
        )
        assert riparazione.ricostruisci(match) == (None, None)
