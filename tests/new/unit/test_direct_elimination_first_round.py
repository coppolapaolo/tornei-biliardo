"""Turno 1 dell'eliminazione diretta: slot canonici, bye, seeding (Step 4).

Quello che deve valere:

1. il tabellone si dimensiona sugli **iscritti effettivi**, non sui posti
   dichiarati: 16 posti con 6 presenti = tabellone da 8, non da 16;
2. le teste di serie stanno negli slot canonici, quindi 1 e 2 in metà opposte;
3. i bye vanno ai primi seed e sono nodi pieni del tabellone, con la loro
   posizione;
4. la `first_round_policy` conta davvero — finora era dichiarata e ignorata;
5. il sorteggio è deterministico dato `draw_seed`.
"""

from datetime import date, timedelta

import pytest

from models import Gara, User
from models.matchmaking.bracket import standard_bracket_order
from models.matchmaking.strategies.direct_elimination import DirectEliminationStrategy
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


class _FakeInscription:
    """Iscrizione minimale: la strategia legge solo questi attributi."""

    def __init__(self, user_id, user=None, is_withdrawn=False, is_waitlist=False):
        self.user_id = user_id
        self.user = user
        self.is_withdrawn = is_withdrawn
        self.is_waitlist = is_waitlist


class _FakeUser:
    def __init__(self, elo_rating=None, fargo_rating=None):
        self.elo_rating = elo_rating
        self.fargo_rating = fargo_rating


class _FakeGara:
    """Gara in memoria: il turno 1 non tocca il DB se non c'è un campionato."""

    def __init__(self, n_players, *, policy="random", draw_seed=42, **kwargs):
        self.id = 1
        self.draw_seed = draw_seed
        self.first_round_policy = policy
        self.campionato_id = None
        self.rounds_count = 99
        self.seeding_rating = kwargs.pop("seeding_rating", "elo")
        users = kwargs.pop("users", {})
        self.inscriptions = [
            _FakeInscription(uid, user=users.get(uid))
            for uid in range(1, n_players + 1)
        ]
        for key, value in kwargs.items():
            setattr(self, key, value)


def _slots_from_pairings(pairings, size):
    """Ricostruisce l'occupazione degli slot dai pairing generati."""
    slots = [None] * size
    for pairing in pairings:
        j = pairing.bracket_slot
        if pairing.is_bye:
            slots[2 * j] = pairing.players[0]
        else:
            slots[2 * j], slots[2 * j + 1] = pairing.players
    return slots


class TestDimensionamento:
    @pytest.mark.parametrize(
        "n_players,expected_size,expected_nodes,expected_byes",
        [
            (8, 8, 4, 0),  # tabellone pieno
            (6, 8, 4, 2),
            (5, 8, 4, 3),
            (4, 4, 2, 0),
            (12, 16, 8, 4),
            (16, 16, 8, 0),
        ],
    )
    def test_tabellone_sugli_iscritti_effettivi(
        self, n_players, expected_size, expected_nodes, expected_byes
    ):
        """La dimensione viene dagli iscritti, non da max_participants."""
        strategy = DirectEliminationStrategy()
        gara = _FakeGara(n_players, max_participants=64)

        pairings = strategy._generate_first_round_pairings(gara)

        assert len(pairings) == expected_nodes == expected_size // 2
        assert sum(1 for p in pairings if p.is_bye) == expected_byes

    def test_slot_contigui_senza_lacune(self):
        """Il turno 1 ha sempre S/2 nodi con slot da 0 a S/2-1."""
        strategy = DirectEliminationStrategy()
        pairings = strategy._generate_first_round_pairings(_FakeGara(11))

        slots = sorted(p.bracket_slot for p in pairings)
        assert slots == list(range(8))

    def test_tutti_marcati_winners_bracket_al_turno_1(self):
        strategy = DirectEliminationStrategy()
        pairings = strategy._generate_first_round_pairings(_FakeGara(8))

        assert all(p.bracket_type == "W" for p in pairings)
        assert all(p.bracket_round == 1 for p in pairings)

    def test_sotto_il_minimo_nessun_accoppiamento(self):
        strategy = DirectEliminationStrategy()
        assert strategy._generate_first_round_pairings(_FakeGara(3)) == []


class TestSlotCanonici:
    def test_seed_1_e_2_in_meta_opposte(self):
        """La garanzia base del seeding: i due favoriti non si incontrano prima
        della finale."""
        strategy = DirectEliminationStrategy()
        gara = _FakeGara(8, policy="classification")
        # Con policy classification ma senza campionato il rank è vuoto,
        # quindi l'ordine resta quello casuale: uso l'ordine prodotto dalla
        # strategia stessa come riferimento di "seed".
        seeded = strategy._get_seeded_players(gara, gara.inscriptions)

        pairings = strategy._generate_first_round_pairings(gara)
        slots = _slots_from_pairings(pairings, 8)

        pos_1 = slots.index(seeded[0])
        pos_2 = slots.index(seeded[1])
        # Metà opposte: i primi 4 slot contro gli ultimi 4.
        assert (pos_1 < 4) != (pos_2 < 4)

    def test_ordine_canonico_rispettato(self):
        """Slot i ospita la testa di serie standard_bracket_order[i]."""
        strategy = DirectEliminationStrategy()
        gara = _FakeGara(8)
        seeded = strategy._get_seeded_players(gara, gara.inscriptions)

        pairings = strategy._generate_first_round_pairings(gara)
        slots = _slots_from_pairings(pairings, 8)

        expected = [seeded[seed - 1] for seed in standard_bracket_order(8)]
        assert slots == expected

    def test_bye_ai_primi_seed(self):
        """Con 5 iscritti su tabellone da 8, i bye vanno ai seed 1, 2 e 3."""
        strategy = DirectEliminationStrategy()
        gara = _FakeGara(5)
        seeded = strategy._get_seeded_players(gara, gara.inscriptions)

        pairings = strategy._generate_first_round_pairings(gara)
        con_bye = {p.players[0] for p in pairings if p.is_bye}

        assert con_bye == set(seeded[:3])


class TestFirstRoundPolicy:
    """La policy era dichiarata in configurazione ma nessuno la leggeva."""

    def test_rating_ordina_per_elo_decrescente(self):
        users = {
            1: _FakeUser(elo_rating=1200),
            2: _FakeUser(elo_rating=1800),
            3: _FakeUser(elo_rating=1500),
            4: _FakeUser(elo_rating=1000),
        }
        strategy = DirectEliminationStrategy()
        gara = _FakeGara(4, policy="rating", users=users)

        seeded = strategy._get_seeded_players(gara, gara.inscriptions)
        assert seeded == [2, 3, 1, 4]

    def test_senza_rating_si_finisce_in_coda(self):
        """Mancanza di dato non è un piazzamento intermedio."""
        users = {
            1: _FakeUser(elo_rating=None),
            2: _FakeUser(elo_rating=1800),
            3: _FakeUser(elo_rating=None),
            4: _FakeUser(elo_rating=1000),
        }
        strategy = DirectEliminationStrategy()
        gara = _FakeGara(4, policy="rating", users=users)

        seeded = strategy._get_seeded_players(gara, gara.inscriptions)
        assert seeded[:2] == [2, 4]
        assert set(seeded[2:]) == {1, 3}

    def test_random_ignora_il_rating(self):
        users = {i: _FakeUser(elo_rating=1000 * i) for i in range(1, 5)}
        strategy = DirectEliminationStrategy()
        gara = _FakeGara(4, policy="random", users=users)

        seeded = strategy._get_seeded_players(gara, gara.inscriptions)
        assert seeded != [4, 3, 2, 1]  # non è l'ordine per rating
        assert sorted(seeded) == [1, 2, 3, 4]

    def test_seeding_rating_seleziona_il_campo(self):
        """`seeding_rating` decide quale rating guida il sorteggio."""
        users = {
            1: _FakeUser(elo_rating=1000, fargo_rating=900),
            2: _FakeUser(elo_rating=900, fargo_rating=1000),
        }
        strategy = DirectEliminationStrategy()

        by_elo = _FakeGara(2, policy="rating", users=users, seeding_rating="elo")
        by_fargo = _FakeGara(2, policy="rating", users=users, seeding_rating="fargo")

        assert strategy._get_seeded_players(by_elo, by_elo.inscriptions) == [1, 2]
        assert strategy._get_seeded_players(by_fargo, by_fargo.inscriptions) == [2, 1]


class TestDeterminismo:
    def test_stesso_seed_stesso_tabellone(self):
        strategy = DirectEliminationStrategy()
        a = strategy._generate_first_round_pairings(_FakeGara(11, draw_seed=7))
        b = strategy._generate_first_round_pairings(_FakeGara(11, draw_seed=7))

        assert [(p.players, p.bracket_slot) for p in a] == [
            (p.players, p.bracket_slot) for p in b
        ]

    def test_seed_diversi_tabelloni_diversi(self):
        """Annullare e rilanciare il sorteggio deve dare un tabellone nuovo."""
        strategy = DirectEliminationStrategy()
        a = strategy._generate_first_round_pairings(_FakeGara(11, draw_seed=7))
        b = strategy._generate_first_round_pairings(_FakeGara(11, draw_seed=8))

        assert [p.players for p in a] != [p.players for p in b]

    def test_senza_seed_ricade_su_un_valore_stabile(self):
        """Gare precedenti al campo: arbitrario ma riproducibile."""
        strategy = DirectEliminationStrategy()
        a = strategy._generate_first_round_pairings(_FakeGara(8, draw_seed=None))
        b = strategy._generate_first_round_pairings(_FakeGara(8, draw_seed=None))

        assert [p.players for p in a] == [p.players for p in b]


class TestRoundsCount:
    def test_fissato_sugli_iscritti_effettivi(self):
        """16 posti, 6 presenti: 3 turni, non 4."""
        strategy = DirectEliminationStrategy()
        gara = _FakeGara(6, max_participants=16)
        gara.rounds_count = 4

        pairings = strategy._generate_first_round_pairings(gara)
        strategy._apply_side_effects(pairings, gara, 1)

        assert gara.rounds_count == 3

    def test_non_tocca_i_turni_successivi(self):
        strategy = DirectEliminationStrategy()
        gara = _FakeGara(8)
        gara.rounds_count = 3
        strategy._apply_side_effects([], gara, 2)
        assert gara.rounds_count == 3


class TestErroriNonIngoiati:
    def test_eccezione_propagata(self):
        """Prima ogni errore diventava "zero accoppiamenti" con un print."""
        strategy = DirectEliminationStrategy()

        class _Rotta(_FakeGara):
            @property
            def inscriptions(self):
                raise RuntimeError("boom")

            @inscriptions.setter
            def inscriptions(self, value):
                pass

        with pytest.raises(RuntimeError, match="boom"):
            strategy._generate_round_pairings(_Rotta(8), 1)


class TestSeedPersistito:
    def test_start_first_round_genera_e_persiste_il_seme(self, db_session):
        """Il seme nasce all'avvio del turno e resta sulla gara."""
        from models.competition.inscription_service import InscriptionService
        from models.competition.round_service import RoundService
        from models.base import utc_now

        director = User(
            username="dir_seed",
            email="dir_seed@example.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("pw")
        db_session.add(director)
        db_session.flush()

        gara = Gara(
            director_id=director.id,
            number=1,
            name="Seed",
            date=date.today() + timedelta(days=7),
            discipline="palla_8",
            distance=5,
            is_race_to=True,
            rounds_count=3,
            min_participants=4,
            max_participants=8,
            matchmaking_strategy="direct_elimination",
        )
        db_session.add(gara)
        db_session.flush()

        InscriptionService.open_inscriptions(
            gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
        )
        for n in range(8):
            player = User(
                username=f"pl_seed_{n}",
                email=f"pl_seed_{n}@example.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("pw")
            db_session.add(player)
            db_session.flush()
            InscriptionService.inscribe_user(player.id, gara.id)

        assert gara.draw_seed is None
        RoundService.start_first_round(gara.id)
        assert gara.draw_seed is not None
