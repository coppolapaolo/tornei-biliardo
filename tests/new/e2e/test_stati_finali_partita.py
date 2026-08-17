"""Quale percorso porta a quale stato finale, e cosa concede ciascuno dei due.

È la cosa che dai vecchi nomi non si riusciva a leggere. Si chiamavano
``COMPLETED`` e ``VALIDATED`` e significavano il contrario di come suonavano:
``VALIDATED`` non era la validazione del direttore ma la chiusura decisa dai
**giocatori**, e ``COMPLETED`` era proprio quella del direttore — cioè lo stato
dai poteri più forti portava il nome più debole.

I nomi sono ora ``CLOSED_UNILATERALLY`` (chiusa senza la doppia firma:
direttore, forfait, bye) e ``CONFIRMED_BY_BOTH`` (chiusa dall'accordo dei due
giocatori). Un rinomino però si può sempre rifare al contrario, e nessun test
se ne accorgerebbe: quello che questi test bloccano non sono i nomi, è la
**corrispondenza fra il gesto e lo stato che ne esce**, verificata dalle route
vere. Se un giorno qualcuno invertisse di nuovo i due, qui si spacca.

L'asimmetria dei poteri è nell'ultima classe, ed è la ragione per cui la
distinzione conta davvero.
"""

from __future__ import annotations

import pytest

from gara_driver import GaraDriver
from models.status_enum import MatchStatus
from models.user.role_enum import UserRole


@pytest.fixture
def gara_in_corso(driver: GaraDriver):
    """Gara Amalfi con 8 iscritti e il primo turno sorteggiato."""
    direttore = driver.crea_utente(UserRole.DIRECTOR.value)
    giocatori = driver.crea_giocatori(8)

    driver.entra(direttore)
    gara_id = driver.crea_gara(matchmaking_strategy="amalfi", min_participants=4)
    driver.apri_iscrizioni(gara_id)
    driver.iscrivi_tutti(gara_id, giocatori)

    driver.entra(direttore)
    driver.avvia_primo_turno(gara_id)
    return gara_id, direttore, {g.id: g for g in giocatori}


def _stato(driver: GaraDriver, gara_id: int, match_id: int) -> str:
    partita = [p for p in driver.partite(gara_id, turno=1) if p.id == match_id][0]
    return partita.status


# ══ I valori persistiti non si toccano per sbaglio ══════════════════════════


@pytest.mark.e2e
def test_i_valori_su_disco_restano_quelli_storici():
    """Il rinomino è **solo** lessicale: sul database e nei payload JSON i due
    stati sono ancora `completed` e `validated`.

    Cambiarli è un secondo passo — migration più allineamento di JS e API — e
    deve essere una decisione, non l'effetto collaterale di un ritocco a
    questo enum. Se questo test cade senza che quel lavoro sia stato fatto,
    ogni riga già scritta è diventata illeggibile.
    """
    assert MatchStatus.CLOSED_UNILATERALLY.value == "completed"
    assert MatchStatus.CONFIRMED_BY_BOTH.value == "validated"
    assert set(MatchStatus.finished_values()) == {"completed", "validated"}


# ══ Il gesto e lo stato che ne esce ═════════════════════════════════════════


@pytest.mark.e2e
class TestQualePercorsoPortaAQualeStato:

    def test_la_doppia_conferma_dei_giocatori_da_confirmed_by_both(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Due firme, e nessun direttore di mezzo."""
        gara_id, _direttore, per_id = gara_in_corso
        partita = driver.partite(gara_id, turno=1)[0]
        uno, due = per_id[partita.player1_id], per_id[partita.player2_id]
        traguardo = partita.distance_config.get_winning_racks()

        driver.entra(uno)
        for _ in range(traguardo):
            driver.aggiungi_rack_da_giocatore(partita.id, uno.id)
        driver.conferma(partita.id)

        driver.entra(due)
        driver.conferma(partita.id)

        assert (
            _stato(driver, gara_id, partita.id) == MatchStatus.CONFIRMED_BY_BOTH.value
        )

    def test_la_validazione_del_direttore_da_closed_unilaterally(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Una firma sola, quella che ha titolo per bastare."""
        gara_id, direttore, per_id = gara_in_corso
        partita = driver.partite(gara_id, turno=1)[0]
        uno = per_id[partita.player1_id]
        traguardo = partita.distance_config.get_winning_racks()

        driver.entra(uno)
        for _ in range(traguardo):
            driver.aggiungi_rack_da_giocatore(partita.id, uno.id)

        driver.entra(direttore)
        risposta = driver.valida(partita.id)
        assert risposta.status_code == 200, risposta.get_data(as_text=True)

        assert (
            _stato(driver, gara_id, partita.id) == MatchStatus.CLOSED_UNILATERALLY.value
        )

    def test_il_risultato_secco_del_direttore_da_closed_unilaterally(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Nessun rack, nessuna conferma: il direttore scrive il risultato."""
        gara_id, direttore, _per_id = gara_in_corso
        partita = driver.partite(gara_id, turno=1)[0]
        traguardo = partita.distance_config.get_winning_racks()

        driver.entra(direttore)
        driver.imposta_risultato(partita.id, traguardo, 1)

        assert (
            _stato(driver, gara_id, partita.id) == MatchStatus.CLOSED_UNILATERALLY.value
        )

    def test_il_forfait_da_closed_unilaterally(self, driver: GaraDriver, gara_in_corso):
        """Il ritiro è un gesto di uno solo, quindi non è un accordo: chiude
        d'ufficio anche se a farlo è un giocatore."""
        gara_id, _direttore, per_id = gara_in_corso
        partita = driver.partite(gara_id, turno=1)[0]
        uno = per_id[partita.player1_id]

        driver.entra(uno)
        driver.ritirati(partita.id)

        assert (
            _stato(driver, gara_id, partita.id) == MatchStatus.CLOSED_UNILATERALLY.value
        )


# ══ L'asimmetria dei poteri, che è il motivo per cui la distinzione conta ═══


@pytest.mark.e2e
class TestCosaConcedeCiascunoDeiDueStati:

    def test_dopo_la_doppia_conferma_un_giocatore_puo_ancora_disfare(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Quel che i due hanno concordato, uno dei due può riaprirlo.

        Un rack segnato per sbaglio non smette di essere un errore perché era
        l'ultimo — anzi, è proprio quello che chiude la partita.
        """
        gara_id, _direttore, per_id = gara_in_corso
        partita = driver.partite(gara_id, turno=1)[0]
        uno, due = per_id[partita.player1_id], per_id[partita.player2_id]
        traguardo = partita.distance_config.get_winning_racks()

        driver.entra(uno)
        for _ in range(traguardo):
            driver.aggiungi_rack_da_giocatore(partita.id, uno.id)
        driver.conferma(partita.id)
        driver.entra(due)
        driver.conferma(partita.id)

        assert (
            _stato(driver, gara_id, partita.id) == MatchStatus.CONFIRMED_BY_BOTH.value
        )

        driver.entra(uno)
        risposta = driver.annulla_ultimo_rack(partita.id, uno.id)

        assert risposta.status_code == 200, risposta.get_data(as_text=True)
        dopo = [p for p in driver.partite(gara_id, turno=1) if p.id == partita.id][0]
        assert dopo.player1_score == traguardo - 1

    def test_dopo_la_chiusura_del_direttore_i_giocatori_non_possono_piu(
        self, driver: GaraDriver, gara_in_corso
    ):
        """Il risultato è agli atti: per correggerlo serve il direttore.

        Prima del rinomino questo era il punto più difficile da leggere: il
        codice vietava il ripensamento allo stato che si chiamava «completed»
        e lo concedeva a quello che si chiamava «validated», cioè esattamente
        il contrario di quello che i due nomi suggerivano.
        """
        gara_id, direttore, per_id = gara_in_corso
        partita = driver.partite(gara_id, turno=1)[0]
        uno = per_id[partita.player1_id]
        traguardo = partita.distance_config.get_winning_racks()

        driver.entra(uno)
        for _ in range(traguardo):
            driver.aggiungi_rack_da_giocatore(partita.id, uno.id)

        driver.entra(direttore)
        driver.valida(partita.id)

        driver.entra(uno)
        risposta = driver.annulla_ultimo_rack(partita.id, uno.id)

        assert risposta.status_code != 200
        dopo = [p for p in driver.partite(gara_id, turno=1) if p.id == partita.id][0]
        assert dopo.player1_score == traguardo
        assert dopo.status == MatchStatus.CLOSED_UNILATERALLY.value
