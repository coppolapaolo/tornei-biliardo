"""Due domande che la partita sa rispondere da sé.

Erano sparse: «prendi parte a questa partita?» riscritta in ogni servizio come
un confronto con i due id, e «com'è finita per me?» dedotta per differenza
(`perse = giocate - vinte`) in cinque conteggi diversi. Sparse vuol dire due
cose: che si ripetono, e che si può rispondere in modo diverso in punti
diversi — ed è successo.

Nessun DB: sono metodi del modello, si provano su un'istanza in memoria.
"""

from __future__ import annotations

from models.individual_match.models import IndividualMatch


def _partita(player1_id: int = 1, player2_id: int = 2, winner_id=None):
    """Il minimo che serve alle due domande."""
    partita = IndividualMatch()
    partita.player1_id = player1_id
    partita.player2_id = player2_id
    partita.winner_id = winner_id
    return partita


class TestChiPrendeParte:
    def test_i_due_giocatori_si_riconoscono(self):
        partita = _partita()

        assert partita.is_player(1)
        assert partita.is_player(2)

    def test_un_estraneo_no(self):
        assert not _partita().is_player(99)

    def test_nessuno_non_e_un_giocatore(self):
        """Un utente non autenticato arriva qui come `None`."""
        assert not _partita().is_player(None)

    def test_non_dipende_da_come_la_partita_e_nata(self):
        """È il punto della faccenda.

        Una partita da avvio rapido non ha proposta (`proposal_id` è `None`
        per costruzione, ADR-051). Finché la domanda passava dalla proposta,
        su quelle partite non era un giocatore nessuno dei due.
        """
        veloce = _partita()
        veloce.proposal_id = None
        da_proposta = _partita()
        da_proposta.proposal_id = 7

        assert veloce.is_player(1) == da_proposta.is_player(1)
        assert veloce.is_player(2) == da_proposta.is_player(2)


class TestComEFinita:
    def test_chi_ha_vinto(self):
        assert _partita(winner_id=1).outcome_for(1) == "won"

    def test_chi_ha_perso(self):
        assert _partita(winner_id=1).outcome_for(2) == "lost"

    def test_il_pareggio_non_e_una_sconfitta(self):
        """Su «esattamente N» triangoli si finisce pari: è un esito suo."""
        pari = _partita(winner_id=None)

        assert pari.outcome_for(1) == "tie"
        assert pari.outcome_for(2) == "tie"

    def test_lo_stesso_vocabolario_dello_storico(self):
        """`PlayerHistoryService` usa già questi tre nomi.

        Due vocabolari per la stessa cosa sono il modo in cui, un domani, il
        profilo e le statistiche tornano a contare in modo diverso.
        """
        from models.player.history_service import PlayerHistoryService

        for winner_id, atteso in ((1, "won"), (2, "lost"), (None, "tie")):
            partita = _partita(winner_id=winner_id)
            assert (
                partita.outcome_for(1)
                == PlayerHistoryService._outcome_of(winner_id, 1)
                == atteso
            )
