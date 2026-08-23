"""Come si scrive un risultato, come si sbaglia, e come si torna indietro.

La stessa partita si può chiudere da almeno cinque strade diverse — i rack
segnati dal giocatore, i rack segnati dal direttore, il risultato secco, la
validazione d'ufficio, il forfait — e ciascuna lascia la partita in uno stato
che *deve* essere lo stesso. Qui si percorrono tutte, e poi si torna indietro:
rifiuto dell'avversario, annullamento dell'ultimo rack, reset del direttore.

C'è anche la parte fisica della serata: quali tavoli ha la sala, quale partita
va su quale tavolo, e cosa succede quando il direttore ne sposta una su un
tavolo già occupato.

Tutto sulla configurazione vera della stagione — numero **esatto** di rack —
perché è lì che i comportamenti divergono da quelli abituali: alla distanza 5
un 3-2 è una partita chiusa, e alla distanza 6 della seconda gara un 3-3 è un
pareggio, che in un «al N» non potrebbe esistere.
"""

from __future__ import annotations

import pytest

from campionato_driver import CampionatoDriver
from stagione import CALENDARIO, MINIMO_ISCRITTI, crea_stagione
from models.status_enum import MatchStatus
from models.user.role_enum import UserRole

#: Sei iscritti: tre partite per turno, pari, nessuna X di mezzo. Le X hanno i
#: loro test in `test_stagione_e2e_stagione.py`, dove i quindici sono davvero
#: dispari.
GIOCATORI = MINIMO_ISCRITTI


def _avvia(campionato: CampionatoDriver, gara_id: int, direttore, giocatori):
    campionato.entra(direttore)
    campionato.apri_iscrizioni(gara_id)
    campionato.iscrivi_tutti(gara_id, giocatori)
    campionato.entra(direttore)
    campionato.avvia_primo_turno(gara_id)


@pytest.fixture
def prima_gara_in_corso(campionato: CampionatoDriver):
    """Prima gara (palla 8, esattamente 5 rack), primo turno avviato."""
    direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
    _campionato_id, gare = crea_stagione(campionato, direttore)
    giocatori = campionato.crea_giocatori(GIOCATORI)
    _avvia(campionato, gare[1], direttore, giocatori)
    return gare[1], direttore, giocatori


@pytest.fixture
def seconda_gara_in_corso(campionato: CampionatoDriver):
    """Seconda gara (palla 9, esattamente 6 rack), primo turno avviato.

    Sei è pari, quindi qui il pareggio è possibile: è la ragione per cui questa
    gara ha una fixture sua.
    """
    direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
    _campionato_id, gare = crea_stagione(campionato, direttore)
    giocatori = campionato.crea_giocatori(GIOCATORI)
    _avvia(campionato, gare[2], direttore, giocatori)
    return gare[2], direttore, giocatori


def _una_partita(campionato: CampionatoDriver, gara_id: int):
    partita = campionato.partite(gara_id, turno=1)[0]
    assert not partita.is_bye and not partita.is_trio
    return partita


@pytest.mark.e2e
class TestLeStradeCheChiudonoUnaPartita:
    def test_i_giocatori_segnano_e_firmano_in_due(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        """Dal percorso del giocatore i rack non bastano: servono due firme.

        È la differenza col percorso del direttore, che chiude subito. Qui il
        3-2 lascia la partita «pronta da validare», e una firma sola non la
        chiude.
        """
        gara_id, _direttore, giocatori = prima_gara_in_corso
        partita = _una_partita(campionato, gara_id)
        uno, due = partita.player1_id, partita.player2_id

        campionato.entra(next(g for g in giocatori if g.id == uno))
        for vincitore in (due, uno, due, uno, uno):
            campionato.aggiungi_rack_da_giocatore(partita.id, vincitore)

        segnata = campionato.partite(gara_id, turno=1)[0]
        assert (segnata.player1_score, segnata.player2_score) == (3, 2)
        assert not MatchStatus.is_finished(segnata.status)

        campionato.conferma(partita.id)
        campionato.entra(next(g for g in giocatori if g.id == due))
        campionato.conferma(partita.id)

        chiusa = campionato.partite(gara_id, turno=1)[0]
        assert chiusa.status == MatchStatus.CONFIRMED_BY_BOTH.value
        assert chiusa.winner_id == uno

    def test_il_direttore_segna_e_la_partita_e_agli_atti(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        gara_id, direttore, _giocatori = prima_gara_in_corso
        partita = _una_partita(campionato, gara_id)

        campionato.entra(direttore)
        campionato.gioca_match(partita.id)

        aggiornata = campionato.partite(gara_id, turno=1)[0]
        assert aggiornata.status == MatchStatus.CLOSED_UNILATERALLY.value
        assert aggiornata.player1_score + aggiornata.player2_score == 5

    def test_il_risultato_secco_pretende_il_totale_esatto(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        """In «esattamente 5» il risultato secco deve fare 5, non «almeno 5»."""
        gara_id, direttore, _giocatori = prima_gara_in_corso
        partita = _una_partita(campionato, gara_id)

        campionato.entra(direttore)
        rifiutato = campionato.imposta_risultato(partita.id, 5, 3)
        assert "esattamente 5" in rifiutato.get_data(as_text=True)
        assert not MatchStatus.is_finished(
            campionato.partite(gara_id, turno=1)[0].status
        )

        campionato.imposta_risultato(partita.id, 3, 2)

        aggiornata = campionato.partite(gara_id, turno=1)[0]
        assert (aggiornata.player1_score, aggiornata.player2_score) == (3, 2)
        assert MatchStatus.is_finished(aggiornata.status)

    def test_il_direttore_valida_quello_che_hanno_segnato_i_giocatori(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        gara_id, direttore, _giocatori = prima_gara_in_corso
        partita = _una_partita(campionato, gara_id)
        uno, due = partita.player1_id, partita.player2_id

        campionato.entra(next(g for g in _giocatori if g.id == uno))
        for vincitore in (uno, due, uno, due):
            campionato.aggiungi_rack_da_giocatore(partita.id, vincitore)

        campionato.entra(direttore)
        campionato.aggiungi_rack(partita.id, uno)

        aggiornata = campionato.partite(gara_id, turno=1)[0]
        assert aggiornata.status == MatchStatus.CLOSED_UNILATERALLY.value
        assert aggiornata.winner_id == uno

    def test_il_forfait_chiude_senza_giocare(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        """Chi si ritira perde, e in «esattamente N» i rack non giocati vanno
        all'altro: la somma resta N."""
        gara_id, _direttore, giocatori = prima_gara_in_corso
        partita = _una_partita(campionato, gara_id)
        chi_si_ritira = next(g for g in giocatori if g.id == partita.player1_id)

        campionato.entra(chi_si_ritira)
        campionato.ritirati(partita.id)

        aggiornata = campionato.partite(gara_id, turno=1)[0]
        assert MatchStatus.is_finished(aggiornata.status)
        assert aggiornata.winner_id == partita.player2_id
        assert aggiornata.player1_score + aggiornata.player2_score == 5


@pytest.mark.e2e
class TestTornareIndietro:
    def test_l_avversario_rifiuta_e_l_ultimo_rack_sparisce(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        gara_id, _direttore, giocatori = prima_gara_in_corso
        partita = _una_partita(campionato, gara_id)
        uno, due = partita.player1_id, partita.player2_id

        campionato.entra(next(g for g in giocatori if g.id == uno))
        for vincitore in (due, uno, due, uno, uno):
            campionato.aggiungi_rack_da_giocatore(partita.id, vincitore)
        assert campionato.partite(gara_id, turno=1)[0].player1_score == 3

        risposta = campionato.rifiuta_risultato(
            partita.id, next(g for g in giocatori if g.id == due)
        )

        assert risposta.status_code == 200, risposta.get_data(as_text=True)
        aggiornata = campionato.partite(gara_id, turno=1)[0]
        assert (aggiornata.player1_score, aggiornata.player2_score) == (2, 2)
        assert not MatchStatus.is_finished(aggiornata.status)

    def test_il_giocatore_annulla_il_proprio_ultimo_rack(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        gara_id, _direttore, giocatori = prima_gara_in_corso
        partita = _una_partita(campionato, gara_id)
        uno = partita.player1_id

        campionato.entra(next(g for g in giocatori if g.id == uno))
        campionato.aggiungi_rack_da_giocatore(partita.id, uno)
        campionato.annulla_ultimo_rack(partita.id, uno)

        aggiornata = campionato.partite(gara_id, turno=1)[0]
        assert (aggiornata.player1_score, aggiornata.player2_score) == (0, 0)

    def test_il_direttore_resetta_la_partita_sbagliata(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        gara_id, direttore, _giocatori = prima_gara_in_corso
        partita = _una_partita(campionato, gara_id)

        campionato.entra(direttore)
        campionato.gioca_match(partita.id)
        assert MatchStatus.is_finished(campionato.partite(gara_id, turno=1)[0].status)

        campionato.resetta_match(partita.id)

        aggiornata = campionato.partite(gara_id, turno=1)[0]
        assert not MatchStatus.is_finished(aggiornata.status)
        assert (aggiornata.player1_score, aggiornata.player2_score) == (0, 0)
        assert aggiornata.winner_id is None

    def test_col_turno_successivo_gia_avviato_il_reset_e_bloccato(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        """Resettare un turno chiuso falserebbe gli abbinamenti già estratti.

        In Amalfi il turno 2 nasce *dalla classifica* del turno 1: cambiare a
        posteriori un risultato del turno 1 renderebbe il turno 2 il frutto di
        una classifica che non esiste più.
        """
        gara_id, direttore, _giocatori = prima_gara_in_corso

        campionato.entra(direttore)
        campionato.gioca_turno(gara_id, 1)
        campionato.pagina_gara(gara_id)
        assert campionato.avvia_turno(gara_id, 2)["success"] is True

        primo = campionato.partite(gara_id, turno=1)[0]
        campionato.resetta_match(primo.id)

        invariata = campionato.partite(gara_id, turno=1)[0]
        assert MatchStatus.is_finished(invariata.status)
        assert invariata.player1_score + invariata.player2_score == 5


@pytest.mark.e2e
class TestIlPareggioDellaSecondaGara:
    """Distanza 6 **esatti**: tre a tre è un risultato possibile.

    È la conseguenza meno ovvia della configurazione scelta, e vale la pena
    saperla prima di martedì: nelle gare a distanza dispari (5) il pareggio non
    può capitare, nella seconda gara sì.
    """

    def test_tre_a_tre_chiude_la_partita_senza_vincitore(
        self, campionato: CampionatoDriver, seconda_gara_in_corso
    ):
        gara_id, _direttore, giocatori = seconda_gara_in_corso
        partita = _una_partita(campionato, gara_id)
        uno, due = partita.player1_id, partita.player2_id

        campionato.entra(next(g for g in giocatori if g.id == uno))
        for vincitore in (uno, due, uno, due, uno, due):
            campionato.aggiungi_rack_da_giocatore(partita.id, vincitore)
        campionato.conferma(partita.id)
        campionato.entra(next(g for g in giocatori if g.id == due))
        campionato.conferma(partita.id)

        aggiornata = campionato.partite(gara_id, turno=1)[0]
        assert (aggiornata.player1_score, aggiornata.player2_score) == (3, 3)
        assert MatchStatus.is_finished(aggiornata.status)
        assert aggiornata.winner_id is None

    def test_il_settimo_rack_e_rifiutato(
        self, campionato: CampionatoDriver, seconda_gara_in_corso
    ):
        gara_id, direttore, _giocatori = seconda_gara_in_corso
        partita = _una_partita(campionato, gara_id)
        uno, due = partita.player1_id, partita.player2_id

        campionato.entra(direttore)
        for vincitore in (uno, due, uno, due, uno, due):
            campionato.aggiungi_rack(partita.id, vincitore)

        risposta = campionato.aggiungi_rack(partita.id, uno)

        assert risposta.status_code != 200
        aggiornata = campionato.partite(gara_id, turno=1)[0]
        assert aggiornata.player1_score + aggiornata.player2_score == 6

    def test_la_distanza_e_quella_della_gara_non_quella_della_prima(
        self, campionato: CampionatoDriver, seconda_gara_in_corso
    ):
        gara_id, _direttore, _giocatori = seconda_gara_in_corso
        seconda = next(g for g in CALENDARIO if g.numero == 2)

        for partita in campionato.partite(gara_id, turno=1):
            distanza = partita.distance_config
            assert distanza.racks == seconda.distanza
            assert distanza.is_race_to_racks is False


@pytest.mark.e2e
class TestITavoli:
    def test_i_tavoli_si_ridefiniscono_prima_dell_avvio(
        self, campionato: CampionatoDriver
    ):
        """La sala ha meno tavoli del previsto: si cambia fino all'avvio."""
        direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
        _campionato_id, gare = crea_stagione(campionato, direttore)
        gara_id = gare[1]

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gara_id)
        campionato.configura_tavoli(gara_id, "Rosso, Verde, Blu")

        assert campionato.gara(gara_id).get_available_tables() == [
            "Rosso",
            "Verde",
            "Blu",
        ]

    def test_il_sorteggio_assegna_un_tavolo_a_ogni_partita(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        gara_id, _direttore, _giocatori = prima_gara_in_corso

        tavoli = [p.table_assignment for p in campionato.partite(gara_id, turno=1)]

        assert all(tavolo for tavolo in tavoli), tavoli
        assert len(set(tavoli)) == len(tavoli), "due partite sullo stesso tavolo"

    def test_il_direttore_sposta_una_partita_su_un_altro_tavolo(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        gara_id, direttore, _giocatori = prima_gara_in_corso
        partita = _una_partita(campionato, gara_id)

        campionato.entra(direttore)
        esito = campionato.assegna_tavolo(partita.id, "8")

        assert esito.get("success") is True, esito
        assert campionato.partite(gara_id, turno=1)[0].table_assignment == "8"

    def test_spostarla_su_un_tavolo_occupato_scambia_le_due(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        """Non è un errore: è il direttore che scambia due tavoli."""
        gara_id, direttore, _giocatori = prima_gara_in_corso
        prima, seconda = campionato.partite(gara_id, turno=1)[:2]
        tavolo_di_prima = prima.table_assignment
        tavolo_di_seconda = seconda.table_assignment

        campionato.entra(direttore)
        esito = campionato.assegna_tavolo(prima.id, tavolo_di_seconda)

        assert esito.get("success") is True, esito
        aggiornate = {p.id: p.table_assignment for p in campionato.partite(gara_id, 1)}
        assert aggiornate[prima.id] == tavolo_di_seconda
        assert aggiornate[seconda.id] == tavolo_di_prima

    def test_il_tavolo_si_puo_anche_togliere(
        self, campionato: CampionatoDriver, prima_gara_in_corso
    ):
        gara_id, direttore, _giocatori = prima_gara_in_corso
        partita = _una_partita(campionato, gara_id)

        campionato.entra(direttore)
        esito = campionato.assegna_tavolo(partita.id, None)

        assert esito.get("success") is True, esito
        assert campionato.partite(gara_id, turno=1)[0].table_assignment is None
