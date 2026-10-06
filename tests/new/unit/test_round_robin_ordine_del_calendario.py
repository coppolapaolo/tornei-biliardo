"""Il calendario del girone all'italiana si ricostruisce dalla classifica di partenza.

La classifica di partenza (`SeedingService`) elenca i giocatori nell'ordine in
cui compaiono negli abbinamenti del turno 1, che non è l'ordine su cui il
metodo del poligono costruisce il calendario. `order_from_seeding` fa il
percorso inverso: rigenerare il calendario da quell'ordine deve ridare il turno
1 già giocato, e quindi tutti i turni successivi come previsti all'avvio.

Il percorso completo, con il ritiro EXCLUDE che cancella l'iscrizione, è in
`tests/new/integration/test_round_robin_calendario_stabile.py`.
"""

from __future__ import annotations

import pytest

from models.classification.seeding_service import SeedingService
from models.matchmaking.configuration import (
    MatchmakingStrategy,
    calculate_rounds_for_strategy,
)
from models.matchmaking.strategies.base import Pairing
from models.matchmaking.strategies.round_robin import RoundRobinStrategy

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6, 7, 11, 12])
def test_order_from_seeding_rigenera_lo_stesso_calendario(n):
    strategy = RoundRobinStrategy()
    ordine = [100 + 7 * i for i in range(n)]
    calendario = strategy._generate_round_robin_schedule(ordine)

    turno_1 = [Pairing(players=p, round_number=1) for p in calendario[0]]
    seeding = SeedingService.order_from_pairings(turno_1)

    assert strategy.order_from_seeding(seeding) == ordine
    assert (
        strategy._generate_round_robin_schedule(strategy.order_from_seeding(seeding))
        == calendario
    )


@pytest.mark.parametrize(
    "n,turni", [(2, 1), (3, 3), (4, 3), (5, 5), (6, 5), (11, 11), (12, 11)]
)
def test_turni_del_girone_all_italiana(n, turni):
    """N-1 turni con N pari, N con N dispari: ognuno riposa una volta."""
    assert calculate_rounds_for_strategy(MatchmakingStrategy.ROUND_ROBIN, n) == turni
    assert RoundRobinStrategy().get_total_rounds_needed(n) == turni
