"""Separazione dei compagni nel sorteggio del tabellone (Step 6, US-6).

L'aritmetica è già coperta da `test_team_separation.py`: qui si verifica
l'**aggancio** alla strategia, cioè le tre cose che possono andare storte nel
passaggio dal dominio al modulo puro:

1. con l'opzione spenta — il default — non cambia assolutamente nulla;
2. la squadra si legge da `Inscription.squadra_id`, mai dal testo libero del
   profilo, che serve solo a precompilare l'iscrizione;
3. il seeding e i bye restano quelli canonici: la separazione sceglie *quale
   membro di una banda* va in *quale slot della sua banda*, non li sposta di
   banda.
"""

from __future__ import annotations

import pytest

from models.matchmaking.bracket import standard_bracket_order
from models.matchmaking.strategies.direct_elimination import DirectEliminationStrategy
from models.matchmaking.team_separation import (
    derby_counts_by_round,
    first_derby_round,
    theoretical_first_derby_round,
)

pytestmark = pytest.mark.unit


class _FakeUser:
    def __init__(self, squadra=None):
        # Testo libero del profilo: non deve influenzare il sorteggio.
        self.squadra = squadra
        self.elo_rating = None


class _FakeInscription:
    def __init__(self, user_id, squadra_id=None, profilo=None):
        self.user_id = user_id
        self.squadra_id = squadra_id
        self.user = _FakeUser(profilo)
        self.is_withdrawn = False
        self.is_waitlist = False


class _FakeGara:
    def __init__(self, squadre, *, separate_teammates=True, draw_seed=42):
        """`squadre` è la lista di squadra_id, un elemento per iscritto."""
        self.id = 1
        self.draw_seed = draw_seed
        self.first_round_policy = "random"
        self.campionato_id = None
        self.rounds_count = 99
        self.seeding_rating = "elo"
        self.separate_teammates = separate_teammates
        self.inscriptions = [
            _FakeInscription(index + 1, squadra_id=squadra)
            for index, squadra in enumerate(squadre)
        ]


def _slots(strategy, gara, size):
    """Occupazione degli slot ricostruita dai pairing del turno 1."""
    pairings = strategy._generate_first_round_pairings(gara)
    slots = [None] * size
    for pairing in pairings:
        j = pairing.bracket_slot
        if pairing.is_bye:
            slots[2 * j] = pairing.players[0]
        else:
            slots[2 * j], slots[2 * j + 1] = pairing.players
    return slots


def _team_map(gara):
    return {i.user_id: i.squadra_id for i in gara.inscriptions}


class TestNonRegressione:
    def test_opzione_spenta_tabellone_canonico(self):
        """Il default non deve cambiare nulla per chi non usa le squadre."""
        strategy = DirectEliminationStrategy()
        squadre = [1, 1, 1, 1, 2, 2, 2, 2]
        acceso = _FakeGara(squadre, separate_teammates=True)
        spento = _FakeGara(squadre, separate_teammates=False)

        seeded = strategy._get_seeded_players(spento, spento.inscriptions)
        atteso = [seeded[seed - 1] for seed in standard_bracket_order(8)]

        assert _slots(strategy, spento, 8) == atteso
        # E il tabellone separato è davvero diverso, altrimenti il test
        # passerebbe anche se l'aggancio non ci fosse.
        assert _slots(strategy, acceso, 8) != atteso

    def test_nessuno_con_squadra_tabellone_canonico(self):
        """Opzione attiva ma elenco vuoto: niente da separare."""
        strategy = DirectEliminationStrategy()
        gara = _FakeGara([None] * 8, separate_teammates=True)

        seeded = strategy._get_seeded_players(gara, gara.inscriptions)
        atteso = [seeded[seed - 1] for seed in standard_bracket_order(8)]

        assert _slots(strategy, gara, 8) == atteso


class TestFonteAutorevole:
    def test_conta_l_iscrizione_non_il_profilo(self):
        """`user.squadra` è solo il valore che precompila l'iscrizione."""
        strategy = DirectEliminationStrategy()
        gara = _FakeGara([1, 1, 1, 1, 2, 2, 2, 2])
        atteso = _slots(strategy, gara, 8)

        # Tutti cambiano squadra sul profilo: il tabellone non si muove.
        for inscription in gara.inscriptions:
            inscription.user.squadra = "Circolo Nuovo"

        assert _slots(strategy, gara, 8) == atteso

    def test_senza_squadra_e_uno_stato_legittimo(self):
        """NULL non è "squadra sconosciuta": è "gioca senza squadra qui"."""
        strategy = DirectEliminationStrategy()
        # Quattro compagni e quattro senza squadra: i primi vanno separati,
        # i secondi non devono formare una squadra fantasma fra loro.
        gara = _FakeGara([1, 1, 1, 1, None, None, None, None])

        slots = _slots(strategy, gara, 8)
        counts = derby_counts_by_round(slots, _team_map(gara), 8)

        assert counts[0] == 0, "nessun derby al primo turno"
        # Le coppie di compagni sono C(4,2) = 6. Se i quattro senza squadra
        # facessero squadra fra loro sarebbero 12: il conteggio è la prova che
        # NULL non è un valore che aggrega.
        assert sum(counts) == 6


class TestSeedingPreservato:
    def test_ogni_banda_resta_nei_suoi_slot(self):
        """La separazione permuta dentro la banda, non fra bande."""
        strategy = DirectEliminationStrategy()
        gara = _FakeGara([1, 1, 1, 1, 2, 2, 2, 2])
        seeded = strategy._get_seeded_players(gara, gara.inscriptions)

        slots = _slots(strategy, gara, 8)
        posizione = {player: slot for slot, player in enumerate(slots)}
        canonico = {seed: slot for slot, seed in enumerate(standard_bracket_order(8))}

        # Banda 2 = seed 3,4; banda 3 = seed 5..8.
        for banda in ([3, 4], [5, 6, 7, 8]):
            attesi = {canonico[seed] for seed in banda}
            ottenuti = {posizione[seeded[seed - 1]] for seed in banda}
            assert ottenuti == attesi
        # I due favoriti restano ai loro slot: la banda 0 e la 1 hanno un solo
        # membro ciascuna, quindi non c'è nulla da permutare.
        assert posizione[seeded[0]] == canonico[1]
        assert posizione[seeded[1]] == canonico[2]

    def test_i_bye_restano_ai_primi_seed(self):
        strategy = DirectEliminationStrategy()
        gara = _FakeGara([1, 1, 1, 2, 2])  # 5 iscritti, tabellone da 8
        seeded = strategy._get_seeded_players(gara, gara.inscriptions)

        pairings = strategy._generate_first_round_pairings(gara)
        con_bye = {p.players[0] for p in pairings if p.is_bye}

        assert con_bye == set(seeded[:3])


class TestDerbyRinviati:
    def test_tre_squadre_da_quattro_su_sedici(self):
        """Lo scenario dello user journey, con 12 iscritti su tabellone da 16."""
        strategy = DirectEliminationStrategy()
        gara = _FakeGara([1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3])

        slots = _slots(strategy, gara, 16)
        counts = derby_counts_by_round(slots, _team_map(gara), 16)

        # R* = floor(log2(16/4)) + 1 = 3: il primo derby non può cadere prima
        # delle semifinali. Con 4 bye R* resta un maggiorante, quindi si
        # verifica il risultato ottenuto invece di assumerlo.
        assert theoretical_first_derby_round(16, 4) == 3
        assert first_derby_round(counts) >= 3

    def test_squadra_troppo_numerosa_non_blocca_il_sorteggio(self):
        """`R* = 1`: qualche derby al primo turno è inevitabile, non un guasto."""
        strategy = DirectEliminationStrategy()
        gara = _FakeGara([1] * 9 + [2] * 7)  # 16 iscritti, tabellone pieno

        slots = _slots(strategy, gara, 16)
        counts = derby_counts_by_round(slots, _team_map(gara), 16)

        assert theoretical_first_derby_round(16, 9) == 1
        assert len([p for p in slots if p is not None]) == 16
        # Minimizzati, non evitati: con 9 compagni su 8 nodi almeno uno cade.
        assert counts[0] == 1


class TestDeterminismo:
    def test_stesso_seme_stesso_tabellone(self):
        strategy = DirectEliminationStrategy()
        squadre = [1, 1, 1, 2, 2, 2, 3, 3, 3, None, None, None]

        primo = _slots(strategy, _FakeGara(squadre, draw_seed=11), 16)
        secondo = _slots(strategy, _FakeGara(squadre, draw_seed=11), 16)

        assert primo == secondo

    def test_semi_diversi_tabelloni_diversi(self):
        """Annullare e rilanciare il sorteggio deve dare un tabellone nuovo."""
        strategy = DirectEliminationStrategy()
        squadre = [1, 1, 1, 2, 2, 2, 3, 3, 3, None, None, None]

        primo = _slots(strategy, _FakeGara(squadre, draw_seed=11), 16)
        secondo = _slots(strategy, _FakeGara(squadre, draw_seed=12), 16)

        assert primo != secondo


class TestDoppioKO:
    def test_il_doppio_ko_eredita_la_separazione(self):
        """Il turno 1 del doppio KO è quello dell'eliminazione diretta."""
        from models.matchmaking.strategies.double_knockout import (
            DoubleKnockoutStrategy,
        )

        gara = _FakeGara([1, 1, 1, 1, 2, 2, 2, 2])
        de = DirectEliminationStrategy()
        dk = DoubleKnockoutStrategy()

        assert [p.players for p in dk._generate_first_round_pairings(gara)] == [
            p.players for p in de._generate_first_round_pairings(gara)
        ]
        counts = derby_counts_by_round(
            _slots(dk, gara, 8), _team_map(gara), 8  # type: ignore[arg-type]
        )
        assert counts[0] == 0
