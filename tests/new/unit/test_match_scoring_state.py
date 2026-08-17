"""Stato del segnapunti, condiviso fra le due viste (utils/status_ui.py).

Il tabellone orizzontale e la vista verticale rispondono alle stesse domande —
si può ancora segnare? chi deve confermare? — e finché se le calcolavano per
conto proprio le due divergevano: la verticale spegneva i `+1` a distanza
raggiunta, il tabellone no. Qui si fissa la risposta una volta sola.

Nessun DB: la funzione è pura, gli oggetti sono finti apposta.
"""

from __future__ import annotations

import pytest

from models.match.distance import Distance
from models.status_enum import MatchStatus
from utils.status_ui import match_scoring_state


class _User:
    def __init__(self, user_id, authenticated=True):
        self.id = user_id
        self.is_authenticated = authenticated


class _Match:
    """Il minimo che `match_scoring_state` legge di una partita."""

    def __init__(
        self,
        *,
        status=MatchStatus.PLAYING.value,
        p1_score=0,
        p2_score=0,
        distance=None,
        p1_confirmed=False,
        p2_confirmed=False,
        table_assignment=1,
        is_multi_set=False,
        match_distance=None,
        is_race_to_sets=True,
    ):
        self.status = status
        self.player1_id = 1
        self.player2_id = 2
        self.player1_score = p1_score
        self.player2_score = p2_score
        self.distance_config = distance or Distance(racks=5, is_race_to_racks=True)
        self.player1_confirmed = p1_confirmed
        self.player2_confirmed = p2_confirmed
        self.table_assignment = table_assignment
        self.is_multi_set = is_multi_set
        self.match_distance = match_distance
        self.is_race_to_sets = is_race_to_sets


P1 = _User(1)
P2 = _User(2)
ESTRANEO = _User(99)


class TestSiPuoAncoraSegnare:
    def test_partita_in_corso_lontana_dal_traguardo(self):
        stato = match_scoring_state(_Match(p1_score=2, p2_score=1), P1)
        assert stato["can_add"]
        assert stato["in_progress"]
        assert not stato["at_distance"]

    def test_distanza_raggiunta_chiude_i_piu_uno(self):
        """Il difetto del tabellone: a 5-3 su un «al 5» i `+1` restavano
        premibili e si segnavano rack oltre il traguardo."""
        stato = match_scoring_state(_Match(p1_score=5, p2_score=3), P1)
        assert stato["at_distance"]
        assert not stato["can_add"]

    def test_senza_tavolo_non_si_segna(self):
        stato = match_scoring_state(_Match(table_assignment=None), P1)
        assert not stato["can_add"]

    def test_esattamente_n_guarda_la_somma_non_il_massimo(self):
        """Con «esattamente 4» nessuno dei due arriva a 4: finisce quando i
        rack giocati sono 4. Guardare il punteggio più alto non basta."""
        esatta = Distance(racks=4, is_race_to_racks=False)
        stato = match_scoring_state(_Match(p1_score=2, p2_score=2, distance=esatta), P1)
        assert stato["at_distance"]
        assert not stato["can_add"]


class TestChiDeveConfermare:
    def test_chi_non_ha_ancora_risposto_vede_accetta_e_rifiuta(self):
        m = _Match(p1_score=5, p2_score=3, p1_confirmed=True)
        assert match_scoring_state(m, P2)["awaiting_you"]

    def test_chi_ha_gia_confermato_non_se_lo_vede_richiedere(self):
        m = _Match(p1_score=5, p2_score=3, p1_confirmed=True)
        stato = match_scoring_state(m, P1)
        assert not stato["awaiting_you"]
        assert stato["you_confirmed"]

    def test_il_confermato_dell_altro_e_letto_dal_lato_giusto(self):
        m = _Match(p1_score=5, p2_score=3, p1_confirmed=True)
        assert match_scoring_state(m, P2)["opponent_confirmed"]
        assert not match_scoring_state(m, P1)["opponent_confirmed"]

    def test_chi_guarda_senza_giocare_non_deve_confermare_niente(self):
        """Il direttore che apre il match di altri due: nessuna conferma da
        chiedergli, e i pulsanti non devono comparirgli."""
        m = _Match(p1_score=5, p2_score=3)
        stato = match_scoring_state(m, ESTRANEO)
        assert not stato["is_player"]
        assert not stato["awaiting_you"]

    def test_anonimo_non_e_un_giocatore(self):
        stato = match_scoring_state(_Match(), _User(None, authenticated=False))
        assert not stato["is_player"]


class TestPartitaFinita:
    def test_chiusa_dai_giocatori(self):
        m = _Match(status=MatchStatus.CONFIRMED_BY_BOTH.value, p1_score=5, p2_score=3)
        stato = match_scoring_state(m, P1)
        assert stato["finished"]
        assert stato["closed_by_players"]
        assert not stato["in_progress"]

    def test_chiusa_d_ufficio_non_e_chiusa_dai_giocatori(self):
        """I due stati finali hanno poteri diversi: da quella d'ufficio non si
        torna indietro annullando un rack."""
        m = _Match(status=MatchStatus.CLOSED_UNILATERALLY.value, p1_score=5, p2_score=3)
        stato = match_scoring_state(m, P1)
        assert stato["finished"]
        assert not stato["closed_by_players"]

    @pytest.mark.parametrize("p1,p2,atteso", [(5, 3, 1), (3, 5, 2), (0, 0, None)])
    def test_il_vincitore_esce_dal_punteggio(self, p1, p2, atteso):
        m = _Match(status=MatchStatus.CONFIRMED_BY_BOTH.value, p1_score=p1, p2_score=p2)
        assert match_scoring_state(m, P1)["winner_id"] == atteso


class TestMultiSet:
    def test_il_traguardo_sono_i_set_non_i_rack_del_set(self):
        """I punteggi di un multi-set sono set vinti. Leggere il traguardo in
        `distance_config` — che descrive il singolo set — direbbe «finita» a
        metà partita."""
        m = _Match(
            p1_score=2,
            p2_score=1,
            is_multi_set=True,
            match_distance=3,
            distance=Distance(racks=2, is_race_to_racks=True),
        )
        stato = match_scoring_state(m, P1)
        assert not stato["at_distance"], "2 set su 3 non chiudono la partita"
        assert stato["can_add"]

    def test_raggiunti_i_set_la_partita_e_a_distanza(self):
        m = _Match(p1_score=3, p2_score=1, is_multi_set=True, match_distance=3)
        assert match_scoring_state(m, P1)["at_distance"]
