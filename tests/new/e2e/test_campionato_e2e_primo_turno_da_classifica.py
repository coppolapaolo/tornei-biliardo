"""Il primo turno di ogni gara abbinato sulla classifica del campionato.

Un campionato Amalfi in cui il direttore vuole che, dalla seconda gara in poi,
il turno 1 non sia sorteggiato ma parta dalla classifica generale. Si sceglie
**una volta**, sul campionato («Primo abbinamento proposto»), e lo ricevono
tutte le gare che nascono dopo — come i dispari e i turni (ADR-075).

Alla prima gara la classifica non c'è ancora, e il turno 1 si sorteggia: è il
ripiego di `AmalfiStrategy._campionato_seeding_order`, ed è ciò che rende la
scelta valida per tutto il campionato invece che «dalla seconda in poi».

L'ordine di partenza si legge dalla classifica generale **calcolata**
(`classifica_generale`, ADR-073), non dalla sua copia nelle righe
`Classification`: la copia si riscrive alla chiusura di ogni gara, ma un
errore lì è solo un avviso nel log, e la gara dopo partirebbe da una
classifica vecchia senza che nessuno se ne accorga.
"""

from __future__ import annotations

import pytest

from campionato_driver import CampionatoDriver
from models.base import db
from models.campionato.statistics_service import TournamentStatisticsService
from models.classification.models import Classification
from models.classification.seeding_service import SeedingService
from models.matchmaking.configuration import FirstRoundPolicy
from models.status_enum import GaraStatus
from models.user.role_enum import UserRole

GIOCATORI = 8
TURNI = 3


def _gioca_gara(campionato: CampionatoDriver, gara_id: int, direttore, giocatori):
    campionato.entra(direttore)
    campionato.apri_iscrizioni(gara_id)
    campionato.iscrivi_tutti(gara_id, giocatori)
    campionato.entra(direttore)
    campionato.avvia_primo_turno(gara_id)
    for turno in range(1, TURNI + 1):
        if turno > 1:
            esito = campionato.avvia_turno(gara_id, turno)
            assert esito["success"] is True, esito.get("error")
        campionato.gioca_turno(gara_id, turno)
        campionato.pagina_gara(gara_id)
    return campionato.chiudi_gara(gara_id)


def _ordine_della_classifica_generale(campionato_id: int) -> list[int]:
    classifica = TournamentStatisticsService().classifica_generale(campionato_id)
    return [dati["user_id"] for _pos, dati in classifica]


@pytest.fixture
def campionato_a_classifica(campionato: CampionatoDriver):
    """Campionato Amalfi che propone «Basato su classifica», due gare create."""
    direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
    giocatori = campionato.crea_giocatori(GIOCATORI)
    campionato.entra(direttore)
    campionato_id = campionato.crea_campionato(
        default_first_round_policy=FirstRoundPolicy.CLASSIFICATION.value,
        default_rounds_count=TURNI,
    )
    # Il modulo della nuova gara mostra già la scelta del campionato: il
    # browser la rimanda così com'è.
    pagina = campionato.pagina_campionato(campionato_id)
    assert (
        f'value="{FirstRoundPolicy.CLASSIFICATION.value}" selected' in pagina
    ), "il modulo della nuova gara non propone il primo abbinamento del campionato"

    gare = {
        numero: campionato.crea_gara_di_campionato(
            campionato_id,
            numero,
            rounds_count=TURNI,
            first_round_policy=FirstRoundPolicy.CLASSIFICATION.value,
        )
        for numero in (1, 2)
    }
    return campionato_id, gare, direttore, giocatori


@pytest.mark.e2e
class TestPrimoTurnoDallaClassificaDelCampionato:
    def test_il_campionato_lo_propone_e_la_gara_lo_riceve(
        self, campionato: CampionatoDriver
    ):
        """Una gara creata senza dire niente prende la scelta del campionato."""
        direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
        campionato.entra(direttore)
        campionato_id = campionato.crea_campionato(
            default_first_round_policy=FirstRoundPolicy.CLASSIFICATION.value
        )
        gara_id = campionato.crea_gara_di_campionato(
            campionato_id, 1, first_round_policy=None
        )

        assert (
            campionato.gara(gara_id).first_round_policy
            == FirstRoundPolicy.CLASSIFICATION.value
        )

    def test_la_seconda_gara_parte_dalla_classifica_generale(
        self, campionato: CampionatoDriver, campionato_a_classifica
    ):
        campionato_id, gare, direttore, giocatori = campionato_a_classifica

        # Gara 1: niente classifica ancora, il turno 1 si sorteggia.
        assert (
            _gioca_gara(campionato, gare[1], direttore, giocatori)
            == GaraStatus.COMPLETED.value
        )
        attesa = _ordine_della_classifica_generale(campionato_id)
        assert len(attesa) == GIOCATORI

        # Gara 2: il turno 1 parte dalla classifica dopo la gara 1.
        campionato.entra(direttore)
        campionato.apri_iscrizioni(gare[2])
        campionato.iscrivi_tutti(gare[2], giocatori)
        campionato.entra(direttore)
        campionato.avvia_primo_turno(gare[2])

        partenza = [riga.user_id for riga in SeedingService.get_seeding(gare[2])]
        assert partenza == attesa

    def test_una_copia_ferma_delle_righe_non_sposta_la_partenza(
        self, campionato: CampionatoDriver, campionato_a_classifica
    ):
        """Le righe `Classification` sono una copia: la partenza non le legge.

        Si capovolgono le righe dopo la gara 1, come se la copia fosse rimasta
        a un'altra classifica: il turno 1 della gara 2 deve seguire comunque la
        classifica calcolata.
        """
        campionato_id, gare, direttore, giocatori = campionato_a_classifica
        _gioca_gara(campionato, gare[1], direttore, giocatori)
        attesa = _ordine_della_classifica_generale(campionato_id)

        righe = (
            Classification.query.filter_by(campionato_id=campionato_id)
            .order_by(Classification.position)
            .all()
        )
        posizioni = [r.position for r in righe]
        for riga, posizione in zip(righe, reversed(posizioni)):
            riga.position = posizione
        db.session.commit()

        campionato.entra(direttore)
        campionato.apri_iscrizioni(gare[2])
        campionato.iscrivi_tutti(gare[2], giocatori)
        campionato.entra(direttore)
        campionato.avvia_primo_turno(gare[2])

        partenza = [riga.user_id for riga in SeedingService.get_seeding(gare[2])]
        assert partenza == attesa
