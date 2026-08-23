"""La stagione nasce come il direttore l'ha pensata — controllo capo per capo.

Questi test non giocano nemmeno una partita: creano il campionato e le quattro
gare dal wizard e dai form veri, e poi rileggono ogni singola impostazione. È
il livello più economico della suite e il più utile prima di martedì, perché
risponde alla domanda «quello che ho compilato è quello che è stato salvato?»
— che è dove i guasti passano inosservati più a lungo: una gara configurata
male non dà errore, dà una gara diversa.

La specifica sta in `stagione.py` e non qui: se il calendario cambia si cambia
là, e questi test seguono senza essere riscritti.
"""

from __future__ import annotations

import pytest

from campionato_driver import CampionatoDriver
from stagione import (
    CALENDARIO,
    CLASSIFICA,
    DISPARI_CON_X,
    MASSIMO_ISCRITTI,
    MINIMO_ISCRITTI,
    QUALIFICATI_AL_PLAYOFF,
    SPAREGGIO_FINO_A,
    TURNI,
    TURNI_MISTI,
    crea_stagione,
)
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import GaraStatus
from models.user.role_enum import UserRole


@pytest.fixture
def stagione(campionato: CampionatoDriver):
    """Campionato e quattro gare create, nessun iscritto, nessuna partita."""
    direttore = campionato.crea_utente(UserRole.DIRECTOR.value)
    campionato_id, gare = crea_stagione(campionato, direttore)
    return campionato_id, gare, direttore


@pytest.mark.e2e
class TestIlCampionato:
    def test_nasce_amalfi_a_vittorie_con_i_playoff(
        self, campionato: CampionatoDriver, stagione
    ):
        campionato_id, _gare, _direttore = stagione

        record = campionato.campionato(campionato_id)
        assert record.campionato_type == MatchmakingStrategy.AMALFI.value
        assert record.default_classification_system == CLASSIFICA
        assert record.default_rounds_count == TURNI
        assert record.default_odd_policy == DISPARI_CON_X
        assert record.default_anti_rematch is True
        assert record.planned_gare_count == len(CALENDARIO)

    def test_il_playoff_e_configurato_per_i_primi_otto(
        self, campionato: CampionatoDriver, stagione
    ):
        campionato_id, _gare, _direttore = stagione

        (configurazione,) = campionato.configurazioni_playoff(campionato_id)
        assert configurazione.is_active is True
        assert configurazione.max_participants == QUALIFICATI_AL_PLAYOFF
        assert configurazione.positions_from == 1
        assert configurazione.positions_to == QUALIFICATI_AL_PLAYOFF


@pytest.mark.e2e
class TestLeQuattroGare:
    """Quello che è uguale in tutte e quattro, e quello che cambia."""

    def test_il_calendario_e_completo_e_in_ordine(
        self, campionato: CampionatoDriver, stagione
    ):
        campionato_id, _gare, _direttore = stagione

        gare = campionato.gare_del_campionato(campionato_id)
        assert [gara.number for gara in gare] == [g.numero for g in CALENDARIO]
        assert [gara.name for gara in gare] == [g.nome for g in CALENDARIO]
        assert all(gara.status == GaraStatus.SETUP.value for gara in gare)
        # ADR-016: le date devono crescere col numero.
        date_gare = [gara.date for gara in gare]
        assert date_gare == sorted(date_gare)

    def test_le_impostazioni_comuni_valgono_per_tutte(
        self, campionato: CampionatoDriver, stagione
    ):
        _campionato_id, gare, _direttore = stagione

        for programmata in CALENDARIO:
            gara = campionato.gara(gare[programmata.numero])
            quale = f"gara {programmata.numero}"
            assert gara.matchmaking_strategy == MatchmakingStrategy.AMALFI.value, quale
            assert gara.rounds_count == TURNI, quale
            assert gara.min_participants == MINIMO_ISCRITTI, quale
            assert gara.max_participants == MASSIMO_ISCRITTI, quale
            assert gara.odd_number_policy == DISPARI_CON_X, quale
            assert gara.classification_system == CLASSIFICA, quale
            assert gara.anti_rematch_enabled is True, quale
            assert gara.tiebreaker_enabled is True, quale
            assert gara.tiebreaker_until_position == SPAREGGIO_FINO_A, quale
            # Il numero di rack è **esatto**, non un traguardo.
            assert gara.is_race_to is False, quale
            assert gara.is_multi_set is False, quale

    def test_ogni_gara_ha_la_sua_disciplina_e_la_sua_distanza(
        self, campionato: CampionatoDriver, stagione
    ):
        _campionato_id, gare, _direttore = stagione

        for programmata in CALENDARIO:
            gara = campionato.gara(gare[programmata.numero])
            assert gara.discipline == programmata.disciplina
            assert gara.distance == programmata.distanza

    def test_i_tavoli_sono_otto(self, campionato: CampionatoDriver, stagione):
        """Sette partite per turno con quindici iscritti: otto tavoli bastano.

        Senza tavoli le partite restano `pending` e non si possono segnare, ed
        è un modo silenzioso di rendere la serata ingiocabile.
        """
        _campionato_id, gare, _direttore = stagione

        for numero in gare.values():
            assert len(campionato.gara(numero).get_available_tables()) == 8


@pytest.mark.e2e
class TestLaQuartaGaraCambiaTurnoPerTurno:
    """Gli override per turno di ADR-027, che è la parte più facile da sbagliare."""

    def test_i_tre_turni_hanno_disciplina_e_distanza_proprie(
        self, campionato: CampionatoDriver, stagione
    ):
        _campionato_id, gare, _direttore = stagione
        quarta = gare[4]

        override = campionato.override_dei_turni(quarta)

        assert set(override) == {turno.numero for turno in TURNI_MISTI}
        for turno in TURNI_MISTI:
            salvato = override[turno.numero]
            assert salvato["discipline"] == turno.disciplina
            assert salvato["distance"] == turno.distanza
            assert salvato["is_race_to"] is False

    def test_le_prime_tre_gare_non_hanno_override(
        self, campionato: CampionatoDriver, stagione
    ):
        """Uniformi per scelta: un override di troppo qui sarebbe invisibile."""
        _campionato_id, gare, _direttore = stagione

        for numero in (1, 2, 3):
            assert campionato.override_dei_turni(gare[numero]) == {}

    def test_gli_override_valgono_sulle_partite_del_turno(
        self, campionato: CampionatoDriver, stagione
    ):
        """La prova che conta: il turno usa davvero la sua configurazione.

        Non basta che l'override sia salvato — deve arrivare fino al match, che
        è quello che ADR-027 chiede leggendo `match.distance_config` invece di
        `match.gara.distance`. Qui si avvia la gara e si guardano le partite
        del primo turno, che è l'unico che Amalfi crea subito.
        """
        _campionato_id, gare, direttore = stagione
        quarta = gare[4]
        giocatori = campionato.crea_giocatori(MINIMO_ISCRITTI)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(quarta)
        campionato.iscrivi_tutti(quarta, giocatori)
        campionato.entra(direttore)
        campionato.avvia_primo_turno(quarta)

        primo_turno = campionato.partite(quarta, turno=1)
        assert primo_turno
        for partita in primo_turno:
            assert partita.get_effective_discipline() == TURNI_MISTI[0].disciplina
            distanza = partita.distance_config
            assert distanza.racks == TURNI_MISTI[0].distanza
            assert distanza.is_race_to_racks is False

    def test_a_gara_avviata_gli_override_non_si_toccano_piu(
        self, campionato: CampionatoDriver, stagione
    ):
        """Cambiare il formato a metà gara falserebbe i turni già giocati."""
        _campionato_id, gare, direttore = stagione
        quarta = gare[4]
        giocatori = campionato.crea_giocatori(MINIMO_ISCRITTI)

        campionato.entra(direttore)
        campionato.apri_iscrizioni(quarta)
        campionato.iscrivi_tutti(quarta, giocatori)
        campionato.entra(direttore)
        campionato.avvia_primo_turno(quarta)

        esito = campionato.configura_turno(quarta, 2, distance=9)

        assert esito["status"] == 409
        assert campionato.override_dei_turni(quarta)[2]["distance"] == 6

    def test_un_turno_fuori_dai_tre_viene_rifiutato(
        self, campionato: CampionatoDriver, stagione
    ):
        _campionato_id, gare, _direttore = stagione

        esito = campionato.configura_turno(gare[4], TURNI + 1, distance=5)

        assert esito["status"] == 400
        assert esito["success"] is False
