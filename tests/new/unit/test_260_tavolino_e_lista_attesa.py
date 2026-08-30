"""Regressioni per la prima metà della issue #260.

Due difetti indipendenti dal cambio di modello descritto nella issue, e
correggibili prima di esso:

1. **Quanto vale un tavolino** era scritto in tre posti che non concordavano.
   In una gara multi-set `player1_score`/`player2_score` contengono i **set**,
   non i rack: `create_matches_from_pairings` ci segnava i rack del turno, cioè
   un punteggio che in quella gara nessuno può ottenere giocando. La risposta
   sta ora in `Distance.walkover_score()`, e i tre punti la chiedono a lui.

2. **La lista d'attesa non si tocca più a gara avviata.** Dopo il primo turno
   la composizione degli iscritti è la base degli abbinamenti già sorteggiati:
   promuovere qualcuno lo faceva entrare senza i turni giocati e con zero
   punti, retrocedere un attivo lo toglieva da partite che aveva davanti.
"""

from __future__ import annotations

from datetime import date

import pytest

from models.base import db
from models.competition.inscription_service import InscriptionService
from models.competition.models import (
    Gara,
    Inscription,
    WaitlistReason,
    WithdrawPolicy,
)
from models.competition.round_creation import create_matches_from_pairings
from models.competition.withdraw_policy_service import WithdrawPolicyService
from models.match.distance import Distance
from models.match.models import Match
from models.matchmaking.strategies.base import Pairing
from models.status_enum import GaraStatus


def _make_gara(db_session, **overrides) -> Gara:
    existing = db_session.query(Gara).count()
    defaults = {
        "name": f"Gara #260 n.{existing + 1}",
        "number": existing + 1,
        "date": date.today(),
        "distance": 5,
        "discipline": "9_ball",
        "matchmaking_strategy": "amalfi",
        "status": GaraStatus.PLAYING.value,
        "is_race_to": True,
    }
    defaults.update(overrides)
    gara = Gara(**defaults)
    db_session.add(gara)
    db_session.flush()
    return gara


def _inscribe(db_session, gara_id: int, user_id: int, **kwargs) -> Inscription:
    ins = Inscription(gara_id=gara_id, user_id=user_id, **kwargs)
    db_session.add(ins)
    db_session.flush()
    return ins


@pytest.mark.unit
class TestQuantoValeUnTavolino:
    """`Distance.walkover_score()` è l'unica sede della regola."""

    def test_a_set_unico_il_tavolino_si_conta_in_rack(self):
        assert Distance(racks=5, is_race_to_racks=True).walkover_score() == 5

    def test_a_set_unico_vale_anche_per_esattamente_n_rack(self):
        """Con «esattamente N rack» il tavolino resta N-0: il ritirato non
        gioca, quindi non c'è il pareggio possibile a partita giocata."""
        assert Distance(racks=4, is_race_to_racks=False).walkover_score() == 4

    def test_in_multi_set_il_tavolino_si_conta_in_set(self):
        """«Al 3 set da 4 rack» → 3, non 4: la colonna conta i set."""
        distanza = Distance(racks=4, is_race_to_racks=True, is_multi_set=True, sets=3)
        assert distanza.walkover_score() == 3

    def test_creazione_turno_multi_set_segna_i_set_non_i_rack(
        self, db_session, isolated_players
    ):
        """Il difetto originale: 4-0 **set** in una gara al 3 set da 4 rack."""
        gara = _make_gara(db_session, distance=4, is_multi_set=True, match_distance=3)
        p0, p1 = (p.id for p in isolated_players[:2])
        _inscribe(db_session, gara.id, p0, is_forfeit=True)
        _inscribe(db_session, gara.id, p1)

        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(p0, p1), is_bye=False)],
            round_number=1,
            round_distance=4,
            forfeit_user_ids={p0},
        )
        db_session.flush()

        match = db_session.query(Match).filter_by(gara_id=gara.id).one()
        assert match.winner_id == p1
        assert (match.player1_score, match.player2_score) == (
            0,
            3,
        ), "Il tavolino multi-set deve valere i set-per-vincere, non i rack"

    def test_creazione_turno_a_set_unico_resta_in_rack(
        self, db_session, isolated_players
    ):
        """Il caso di gran lunga più comune non deve cambiare."""
        gara = _make_gara(db_session, distance=5)
        p0, p1 = (p.id for p in isolated_players[:2])
        _inscribe(db_session, gara.id, p0, is_forfeit=True)
        _inscribe(db_session, gara.id, p1)

        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(p0, p1), is_bye=False)],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0},
        )
        db_session.flush()

        match = db_session.query(Match).filter_by(gara_id=gara.id).one()
        assert (match.player1_score, match.player2_score) == (0, 5)

    def test_trio_walkover_resta_in_rack_anche_in_gara_multi_set(
        self, db_session, isolated_players
    ):
        """I trio nascono `is_multi_set=False`: il loro tavolino è in rack.

        Prendevano `winning_score` calcolato per i match a set, cioè 3 in una
        gara «al 3 set da 4 rack» — un punteggio in set scritto in una colonna
        che per quel match significa triangoli.
        """
        gara = _make_gara(
            db_session,
            distance=4,
            is_multi_set=True,
            match_distance=3,
            odd_number_policy="trio",
        )
        p0, p1, p2 = (p.id for p in isolated_players[:3])
        _inscribe(db_session, gara.id, p0, is_forfeit=True)
        _inscribe(db_session, gara.id, p1, is_forfeit=True)
        _inscribe(db_session, gara.id, p2)

        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(p0, p1, p2), is_bye=False)],
            round_number=1,
            round_distance=4,
            forfeit_user_ids={p0, p1},
        )
        db_session.flush()

        match = db_session.query(Match).filter_by(gara_id=gara.id).one()
        assert match.is_trio is True
        assert match.is_multi_set is False
        assert match.player1_score == 4, "Il trio si conta in rack, non in set"

    def test_forfait_su_partita_mai_configurata_usa_la_distanza_della_gara(
        self, db_session, isolated_players
    ):
        """`match_distance == 1` è il sentinella di «non popolato».

        `WithdrawPolicyService` faceva `match.match_distance or gara.distance`:
        un `or` non scatta su 1, quindi la partita veniva chiusa 1-0 invece che
        alla distanza vera. `distance_config` conosce il sentinella.
        """
        gara = _make_gara(
            db_session,
            distance=5,
            withdraw_policy=WithdrawPolicy.FORFEIT.value,
        )
        p0, p1 = (p.id for p in isolated_players[:2])
        _inscribe(db_session, gara.id, p0)
        _inscribe(db_session, gara.id, p1)
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p0,
            player2_id=p1,
            match_distance=1,
            status="pending",
        )
        db_session.add(match)
        db_session.commit()

        WithdrawPolicyService.handle_forfeit(gara.id, p0)

        aggiornato = db.session.get(Match, match.id)
        assert aggiornato is not None
        assert (aggiornato.player1_score, aggiornato.player2_score) == (0, 5)


@pytest.mark.unit
class TestListaAttesaChiudeConLAvvioDellaGara:
    """A gara avviata gli iscritti non si spostano più da soli."""

    def _gara_parita(self, db_session, status: str) -> Gara:
        return _make_gara(
            db_session,
            status=status,
            odd_number_policy="no",
            min_participants=2,
        )

    def test_a_gara_avviata_non_si_promuove_dalla_lista(
        self, db_session, isolated_players
    ):
        """Chi era in attesa resta in attesa: entrare a turni sorteggiati
        significherebbe comparire in classifica con zero punti e nessuna
        partita da giocare."""
        gara = self._gara_parita(db_session, GaraStatus.PLAYING.value)
        p0, p1, p2 = (p.id for p in isolated_players[:3])
        _inscribe(db_session, gara.id, p0)
        _inscribe(db_session, gara.id, p1)
        in_attesa = _inscribe(
            db_session,
            gara.id,
            p2,
            is_waitlist=True,
            waitlist_reason=WaitlistReason.PARITY.value,
            waitlist_position=1,
        )
        db_session.commit()

        InscriptionService.uninscribe_user(p0, gara.id)

        db_session.refresh(in_attesa)
        assert in_attesa.is_waitlist is True
        assert in_attesa.waitlist_reason == WaitlistReason.PARITY.value

    def test_a_gara_avviata_non_si_retrocede_l_ultimo_iscritto(
        self, db_session, isolated_players
    ):
        """Nessuno in lista: prima l'ultimo attivo veniva messo in attesa —
        cioè tolto dagli abbinamenti che aveva davanti.

        Si parte da quattro attivi perché la disiscrizione ne lasci tre: con
        due il conto resta pari e la retrocessione non scatterebbe comunque,
        e il test passerebbe anche col guard rimosso.
        """
        gara = self._gara_parita(db_session, GaraStatus.PLAYING.value)
        p0, p1, p2, p3 = (p.id for p in isolated_players[:4])
        _inscribe(db_session, gara.id, p0)
        _inscribe(db_session, gara.id, p1)
        _inscribe(db_session, gara.id, p2)
        ultimo = _inscribe(db_session, gara.id, p3)
        db_session.commit()

        InscriptionService.uninscribe_user(p0, gara.id)

        db_session.refresh(ultimo)
        assert ultimo.is_waitlist is False

    def test_a_iscrizioni_aperte_la_promozione_funziona_ancora(
        self, db_session, isolated_players
    ):
        """Il guard non deve spegnere la lista d'attesa dove serve."""
        gara = self._gara_parita(db_session, GaraStatus.INSCRIPTION.value)
        p0, p1, p2 = (p.id for p in isolated_players[:3])
        _inscribe(db_session, gara.id, p0)
        _inscribe(db_session, gara.id, p1)
        in_attesa = _inscribe(
            db_session,
            gara.id,
            p2,
            is_waitlist=True,
            waitlist_reason=WaitlistReason.PARITY.value,
            waitlist_position=1,
        )
        db_session.commit()

        InscriptionService.uninscribe_user(p0, gara.id)

        db_session.refresh(in_attesa)
        assert in_attesa.is_waitlist is False

    def test_a_iscrizioni_aperte_l_ultimo_iscritto_si_retrocede_ancora(
        self, db_session, isolated_players
    ):
        gara = self._gara_parita(db_session, GaraStatus.INSCRIPTION.value)
        p0, p1, p2, p3 = (p.id for p in isolated_players[:4])
        _inscribe(db_session, gara.id, p0)
        _inscribe(db_session, gara.id, p1)
        _inscribe(db_session, gara.id, p2)
        ultimo = _inscribe(db_session, gara.id, p3)
        db_session.commit()

        InscriptionService.uninscribe_user(p0, gara.id)

        db_session.refresh(ultimo)
        assert ultimo.is_waitlist is True
        assert ultimo.waitlist_reason == WaitlistReason.PARITY.value
