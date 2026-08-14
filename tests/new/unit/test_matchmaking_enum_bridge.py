"""Il ponte fra i due enum `MatchmakingStrategy` omonimi (Step 11).

Nel codice ce ne sono **due** con lo stesso nome di classe e valori diversi:

- `models/matchmaking/configuration.py` — quello canonico, i cui valori sono
  anche quelli persistiti su `gara.matchmaking_strategy`
  (`direct_elimination`, `double_knockout`);
- `models/competition/validators.py` — quello della validazione della
  configurazione di classifica (`elimination`, `double_ko`).

A tenerli insieme è `_MATCHMAKING_MAP`. Se una strategia nuova non ci finisce
dentro, `.get(..., AMALFI)` la fa cadere **in silenzio** sul default: la gara
verrebbe validata con le regole di Amalfi, e la combinazione sbagliata
passerebbe senza che nessuno se ne accorga. Da qui il test.

Unificare i due enum sarebbe il lavoro giusto, ma tocca la validazione di
tutte le gare esistenti: finché non lo si fa, questo test è la rete.
"""

import pytest

from models.competition.validators import _MATCHMAKING_MAP
from models.matchmaking.configuration import MatchmakingStrategy

pytestmark = pytest.mark.unit


def test_ogni_strategia_canonica_ha_il_suo_ponte():
    mancanti = [s.value for s in MatchmakingStrategy if s.value not in _MATCHMAKING_MAP]
    assert not mancanti, (
        "strategie senza voce in _MATCHMAKING_MAP: "
        f"{mancanti}. Cadrebbero sul default Amalfi e verrebbero validate "
        "con le regole di un altro formato."
    )


def test_nessuna_voce_di_troppo():
    """Una chiave che non è un valore canonico non la userebbe mai nessuno."""
    canoniche = {s.value for s in MatchmakingStrategy}
    assert set(_MATCHMAKING_MAP) <= canoniche


def test_i_due_formati_a_tabellone_non_si_scambiano():
    """L'errore che il ponte deve escludere è proprio lo scambio fra i due."""
    from models.competition.validators import MatchmakingStrategy as ValidatorStrategy

    assert _MATCHMAKING_MAP["direct_elimination"] is ValidatorStrategy.ELIMINATION
    assert _MATCHMAKING_MAP["double_knockout"] is ValidatorStrategy.DOUBLE_KO


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
