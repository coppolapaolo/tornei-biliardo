"""Regressione issue #89 — la classifica generale segue il sistema di classifica.

Due difetti distinti, sovrapposti nella segnalazione:

1. `_aggregate_player_totals` sommava `rack_difference` e il template lo
   mostrava sotto l'etichetta "Triangoli Totali". Ha funzionato finché quella
   colonna *era* il totale nelle gare a triangoli; dopo la separazione delle due
   colonne (migration 20260728) la stessa classifica ha iniziato a sommare
   differenze — con valori negativi e totali sbagliati, senza che nulla
   cambiasse nel codice della classifica.

2. Il criterio veniva scelto guardando `campionato_type` (la strategia di
   accoppiamento) invece di `default_classification_system` (il sistema di
   classifica). I due coincidono nella configurazione più comune e divergono in
   silenzio in tutte le altre — è lo stesso equivoco che il fix B14 aveva già
   corretto a livello di gara, mai propagato al campionato (ADR-047).

Lo scenario numerico del primo test è quello reale della segnalazione.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models import Gara, User
from models.campionato.models import Campionato
from models.campionato.statistics_service import TournamentStatisticsService
from models.classification.models import RoundClassification
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import ClassificationSystem, GaraStatus
from models.user.role_enum import UserRole


def _make_campionato(db_session, campionato_type: str, system: str) -> Campionato:
    suffix = str(uuid.uuid4())[:8]
    director = User(
        username=f"dir_{suffix}",
        email=f"dir_{suffix}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("x")
    db_session.add(director)
    db_session.flush()

    campionato = Campionato(
        name=f"Campionato {suffix}",
        campionato_type=campionato_type,
        default_classification_system=system,
        planned_gare_count=2,
    )
    db_session.add(campionato)
    db_session.flush()
    campionato._test_director_id = director.id  # type: ignore[attr-defined]
    return campionato


def _make_gara(db_session, campionato: Campionato, number: int, system: str) -> Gara:
    gara = Gara(
        number=number,
        name=f"Gara {number}",
        date=date(2026, 1, number),
        time=time(18, 0),
        discipline="9_ball",
        distance=3,
        is_race_to=True,
        director_id=campionato._test_director_id,  # type: ignore[attr-defined]
        campionato_id=campionato.id,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        matchmaking_strategy=MatchmakingStrategy.RANDOM.value,
        classification_system=system,
        status=GaraStatus.COMPLETED.value,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _make_player(db_session, name: str) -> User:
    suffix = str(uuid.uuid4())[:8]
    player = User(
        username=f"{name}_{suffix}",
        email=f"{name}_{suffix}@test.com",
        role=UserRole.PLAYER.value,
    )
    player.set_password("x")
    db_session.add(player)
    db_session.flush()
    return player


def _add_row(
    db_session,
    gara: Gara,
    user: User,
    position: int,
    matches_won: int,
    rack_difference: int,
    racks_won,
) -> None:
    db_session.add(
        RoundClassification(
            gara_id=gara.id,
            round_number=gara.rounds_count,
            user_id=user.id,
            position=position,
            matches_won=matches_won,
            rack_difference=rack_difference,
            racks_won=racks_won,
        )
    )


@pytest.mark.unit
class TestIssue89TotaliNonDifferenze:
    """Lo scenario reale della segnalazione, con i suoi numeri."""

    def test_totale_somma_i_triangoli_delle_due_gare(self, db_session):
        """NICOLA: 6 triangoli in Gara 1 + 3 in Gara 3 = 9, non 3.

        Gara 1 è chiusa prima della separazione delle colonne: `rack_difference`
        contiene ancora il totale (6) e il backfill ha ricopiato quel valore in
        `racks_won`. Gara 3 è stata ricalcolata dopo: `rack_difference` è la
        differenza vera (3 vinti - 6 persi = -3).

        Sommando `rack_difference` si otteneva 6 + (-3) = 3, il numero della
        segnalazione. Il totale vero è 6 + 3 = 9.
        """
        campionato = _make_campionato(
            db_session,
            campionato_type=MatchmakingStrategy.RANDOM.value,
            system=ClassificationSystem.RACK.value,
        )
        gara1 = _make_gara(db_session, campionato, 1, ClassificationSystem.RACK.value)
        gara3 = _make_gara(db_session, campionato, 2, ClassificationSystem.RACK.value)
        nicola = _make_player(db_session, "nicola")

        # Riga storica: rack_difference è ancora il totale, racks_won ricopiato.
        _add_row(
            db_session,
            gara1,
            nicola,
            position=1,
            matches_won=3,
            rack_difference=6,
            racks_won=6,
        )
        # Riga ricalcolata dopo la separazione: differenza vera, negativa.
        _add_row(
            db_session,
            gara3,
            nicola,
            position=4,
            matches_won=1,
            rack_difference=-3,
            racks_won=3,
        )
        db_session.flush()

        service = TournamentStatisticsService()
        totals = service._aggregate_player_totals(
            [gara1, gara3], ClassificationSystem.RACK
        )

        assert totals[nicola.id]["total_racks_won"] == 9, (
            "I triangoli totali devono sommare i totali di ogni gara (6 + 3), "
            "non le differenze (6 + -3 = 3, il numero della issue #89)."
        )

    def test_i_triangoli_totali_non_sono_mai_negativi(self, db_session):
        """Un totale negativo è la firma della differenza travestita da totale."""
        campionato = _make_campionato(
            db_session,
            campionato_type=MatchmakingStrategy.RANDOM.value,
            system=ClassificationSystem.RACK.value,
        )
        gara = _make_gara(db_session, campionato, 1, ClassificationSystem.RACK.value)
        anil = _make_player(db_session, "anil")

        # Chi perde più di quanto vince ha differenza negativa ma totale positivo.
        _add_row(
            db_session,
            gara,
            anil,
            position=5,
            matches_won=0,
            rack_difference=-4,
            racks_won=2,
        )
        db_session.flush()

        service = TournamentStatisticsService()
        totals = service._aggregate_player_totals([gara], ClassificationSystem.RACK)

        assert totals[anil.id]["total_racks_won"] == 2
        assert totals[anil.id]["total_racks_won"] >= 0
        # La differenza resta disponibile, col suo segno e senza confusione.
        assert totals[anil.id]["total_rack_difference"] == -4

    def test_riga_storica_di_gara_a_vittorie_non_inventa_un_totale(self, db_session):
        """`racks_won` NULL in una gara a vittorie vale 0, non la differenza.

        Il totale non è ricostruibile dalle colonne per quelle righe: lo
        ricalcola `scripts/repair_round_classification_racks.py` dai match.
        Prenderci in mezzo la differenza rifarebbe il guasto della issue.
        """
        campionato = _make_campionato(
            db_session,
            campionato_type=MatchmakingStrategy.AMALFI.value,
            system=ClassificationSystem.WINS.value,
        )
        gara = _make_gara(db_session, campionato, 1, ClassificationSystem.WINS.value)
        player = _make_player(db_session, "storico")

        _add_row(
            db_session,
            gara,
            player,
            position=1,
            matches_won=2,
            rack_difference=5,
            racks_won=None,
        )
        db_session.flush()

        service = TournamentStatisticsService()
        totals = service._aggregate_player_totals([gara], ClassificationSystem.WINS)

        assert totals[player.id]["total_racks_won"] == 0
        assert totals[player.id]["total_rack_difference"] == 5


@pytest.mark.unit
class TestCriterioSegueIlSistemaNonIlTipo:
    """Tipo di campionato e sistema di classifica sono indipendenti."""

    def _due_giocatori(self, db_session, campionato_type: str, system: str):
        campionato = _make_campionato(db_session, campionato_type, system)
        gara = _make_gara(db_session, campionato, 1, system)
        vincente = _make_player(db_session, "vincente")
        prolifico = _make_player(db_session, "prolifico")

        # `vincente` ha più partite vinte; `prolifico` più triangoli totali.
        _add_row(
            db_session,
            gara,
            vincente,
            position=1,
            matches_won=3,
            rack_difference=2,
            racks_won=8,
        )
        _add_row(
            db_session,
            gara,
            prolifico,
            position=2,
            matches_won=1,
            rack_difference=1,
            racks_won=12,
        )
        db_session.flush()
        return gara, vincente, prolifico

    def test_amalfi_con_sistema_a_triangoli_ordina_per_triangoli(self, db_session):
        """Un campionato Amalfi può classificare a triangoli totali.

        Prima il criterio veniva dedotto dal tipo, quindi qui vinceva sempre chi
        aveva più partite — ignorando la scelta del direttore.
        """
        gara, vincente, prolifico = self._due_giocatori(
            db_session,
            campionato_type=MatchmakingStrategy.AMALFI.value,
            system=ClassificationSystem.RACK.value,
        )

        service = TournamentStatisticsService()
        totals = service._aggregate_player_totals([gara], ClassificationSystem.RACK)
        ranking = service._sort_and_rank_players(totals, ClassificationSystem.RACK)

        assert ranking[0][1] == prolifico.id, (
            "Con sistema RACK vince chi ha più triangoli totali, "
            "anche se il campionato è di tipo Amalfi."
        )

    def test_random_con_sistema_a_vittorie_ordina_per_vittorie(self, db_session):
        """Simmetrico: un campionato Random può classificare a vittorie."""
        gara, vincente, prolifico = self._due_giocatori(
            db_session,
            campionato_type=MatchmakingStrategy.RANDOM.value,
            system=ClassificationSystem.WINS.value,
        )

        service = TournamentStatisticsService()
        totals = service._aggregate_player_totals([gara], ClassificationSystem.WINS)
        ranking = service._sort_and_rank_players(totals, ClassificationSystem.WINS)

        assert ranking[0][1] == vincente.id, (
            "Con sistema WINS vince chi ha più partite vinte, "
            "anche se il campionato è di tipo Random."
        )

    def test_la_classifica_generale_segue_il_sistema(self, db_session):
        """Pagina e righe persistite leggono lo stesso sistema.

        Fino al 2026-09-24 la classifica persistita sceglieva una strategia
        sua (`_get_campionato_strategy`), mappata a mano sul sistema: due
        percorsi, due mappe da tenere allineate. Ora il calcolo è uno (ADR-073)
        e il sistema lo dice `sistema_della_classifica_generale`.
        """
        from models.campionato.statistics_service import (
            sistema_della_classifica_generale,
        )

        amalfi_a_triangoli = _make_campionato(
            db_session,
            campionato_type=MatchmakingStrategy.AMALFI.value,
            system=ClassificationSystem.RACK.value,
        )
        assert (
            sistema_della_classifica_generale(amalfi_a_triangoli)
            == ClassificationSystem.RACK
        )

        random_a_vittorie = _make_campionato(
            db_session,
            campionato_type=MatchmakingStrategy.RANDOM.value,
            system=ClassificationSystem.WINS.value,
        )
        assert (
            sistema_della_classifica_generale(random_a_vittorie)
            == ClassificationSystem.WINS
        )

        a_tabellone = _make_campionato(
            db_session,
            campionato_type=MatchmakingStrategy.DIRECT_ELIMINATION.value,
            system=ClassificationSystem.WINS.value,
        )
        assert (
            sistema_della_classifica_generale(a_tabellone)
            == ClassificationSystem.POSITION
        ), "un campionato a tabellone somma punti per piazzamento"


@pytest.mark.unit
class TestVocabolarioSistemaDiClassifica:
    """`ClassificationSystem` è l'unico vocabolario, e conosce lo storico."""

    def test_normalize_riconosce_il_plurale_storico(self):
        assert ClassificationSystem.normalize("RACKS") == ClassificationSystem.RACK

    def test_normalize_e_insensibile_al_caso(self):
        assert ClassificationSystem.normalize("rack") == ClassificationSystem.RACK
        assert ClassificationSystem.normalize(" wins ") == ClassificationSystem.WINS

    def test_normalize_e_idempotente(self):
        assert (
            ClassificationSystem.normalize(ClassificationSystem.POSITION)
            == ClassificationSystem.POSITION
        )

    def test_normalize_non_inventa_un_ripiego(self):
        """Su valore ignoto torna None: il ripiego lo sceglie chi chiama."""
        assert ClassificationSystem.normalize("QUALCOSALTRO") is None
        assert ClassificationSystem.normalize(None) is None
        assert ClassificationSystem.normalize("") is None

    def test_resolve_ripiega_su_wins(self):
        assert ClassificationSystem.resolve(None) == ClassificationSystem.WINS
        assert ClassificationSystem.resolve("QUALCOSALTRO") == ClassificationSystem.WINS
        assert ClassificationSystem.resolve("RACKS") == ClassificationSystem.RACK

    def test_campionato_espone_il_sistema_normalizzato(self, db_session):
        campionato = _make_campionato(
            db_session,
            campionato_type=MatchmakingStrategy.AMALFI.value,
            system="RACKS",
        )
        assert campionato.classification_system == ClassificationSystem.RACK

    def test_una_gara_col_plurale_storico_classifica_a_triangoli(self, db_session):
        """`is_rack_ranking` deve riconoscere anche "RACKS".

        Con un confronto secco `== "RACK"` quelle gare venivano classificate a
        vittorie senza che nessuno lo dicesse.
        """
        campionato = _make_campionato(
            db_session,
            campionato_type=MatchmakingStrategy.RANDOM.value,
            system="RACKS",
        )
        gara = _make_gara(db_session, campionato, 1, "RACKS")
        player = _make_player(db_session, "plurale")
        _add_row(
            db_session,
            gara,
            player,
            position=1,
            matches_won=1,
            rack_difference=7,
            racks_won=None,
        )
        db_session.flush()

        row = (
            db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, user_id=player.id)
            .one()
        )
        assert row.is_rack_ranking is True
        assert row.ranking_rack_value == 7
