"""Le tre regole con cui lo Spot Shot Rally scioglie il pari merito.

Confermate dall'utente il 2026-08-19, e tutte e tre facili da tradire scrivendo
un `sorted()` in fretta:

1. lo spareggio vale **solo** entro `tiebreaker_until_position`; oltre, il pari
   merito e' un risultato legittimo;
2. dentro un gruppo ordina **solo** l'SSR;
3. a SSR uguale il pari merito **rimane** — nessun ripiego, in particolare non
   l'id del giocatore, che e' l'ordine di iscrizione.

Il risolutore vive nella classe base: fino al 2026-08-19 era duplicato alla
lettera nelle due strategie di gara, ed e' cosi' che una correzione applicata a
una copia non ha mai raggiunto l'altra.
"""

from typing import Dict, List

from models.classification.strategies.base import (
    ClassificationEntry,
    PlayerScore,
)
from models.classification.strategies.gara_strategies import (
    RandomGaraClassificationStrategy,
)


def _entries(gruppi: List[List[int]]) -> tuple:
    """Entries gia' raggruppate: ogni sotto-lista condivide una posizione."""
    out = []
    posizione = 1
    for gruppo in gruppi:
        for player_id in gruppo:
            out.append(
                ClassificationEntry(
                    player_id=player_id,
                    position=posizione,
                    score=PlayerScore(player_id=player_id),
                    tied_with=tuple(p for p in gruppo if p != player_id),
                    tiebreaker_resolved=len(gruppo) == 1,
                )
            )
        posizione += len(gruppo)
    return tuple(out)


def _risolvi(gruppi, ssr: Dict[int, int], soglia=None):
    strategia = RandomGaraClassificationStrategy()
    return strategia._resolve_ties_with_spot_shot(_entries(gruppi), ssr, soglia)


def _posizioni(risolte) -> Dict[int, int]:
    return {e.player_id: e.position for e in risolte}


def test_quattro_pari_al_terzo_uno_vince_lo_spareggio():
    """L'esempio di dominio: 4 al 3°, uno fa 1 → 3° lui, 4° gli altri tre."""
    risolte = _risolvi([[1], [2], [3, 4, 5, 6]], {3: 1}, soglia=3)
    assert _posizioni(risolte) == {1: 1, 2: 2, 3: 3, 4: 4, 5: 4, 6: 4}

    per_id = {e.player_id: e for e in risolte}
    assert per_id[3].tied_with == ()
    assert per_id[3].tiebreaker_resolved is True
    assert set(per_id[4].tied_with) == {5, 6}
    assert per_id[4].tiebreaker_resolved is False


def test_a_ssr_uguale_il_pari_merito_rimane():
    """Zero contro zero non e' un ordine: e' un pareggio."""
    risolte = _risolvi([[1], [2, 3]], {}, soglia=3)
    assert _posizioni(risolte) == {1: 1, 2: 2, 3: 2}
    assert all(e.tiebreaker_resolved is False for e in risolte if e.player_id in (2, 3))


def test_non_separa_mai_per_id_del_giocatore():
    """L'id e' l'ordine di iscrizione: separare due pari merito con quello
    inventerebbe un risultato, per giunta marcandolo «risolto»."""
    risolte = _risolvi([[7, 900]], {}, soglia=3)
    assert _posizioni(risolte) == {
        7: 1,
        900: 1,
    }, "il giocatore iscritto prima non deve passare davanti"


def test_oltre_la_soglia_il_pari_merito_non_si_tocca():
    """Con soglia 3, un pari merito al 6° resta anche se un SSR e' registrato."""
    risolte = _risolvi([[1], [2], [3], [4], [5], [6, 7]], {6: 5}, soglia=3)
    assert _posizioni(risolte)[6] == 6
    assert _posizioni(risolte)[7] == 6


def test_dentro_la_soglia_ordina_solo_lo_ssr():
    risolte = _risolvi([[1, 2, 3]], {1: 0, 2: 9, 3: 4}, soglia=3)
    assert _posizioni(risolte) == {2: 1, 3: 2, 1: 3}


def test_soglia_assente_usa_il_default_del_dominio():
    """`tiebreaker_until_position` NULL vale 3, come `Gara.podio`."""
    risolte = _risolvi([[1], [2], [3], [4, 5]], {4: 1}, soglia=None)
    assert _posizioni(risolte)[4] == 4, "il 4° posto e' gia' oltre la soglia"
    assert _posizioni(risolte)[5] == 4


def test_banco_di_prova_gara_35():
    """L'esito corretto della gara reale che ha fatto emergere le tre regole.

    LEONARDO (#52) e FLAVIO (#51) sono pari al 3° e lo spareggio li separa 1-0;
    MARIA (#57) e LUIGI R (#58) sono pari al 6° e restano pari, perche' oltre la
    soglia e perche' nessuno dei due ha tirato.
    """
    risolte = _risolvi([[53], [50], [52, 51], [59], [57, 58]], {52: 1}, soglia=3)
    assert _posizioni(risolte) == {53: 1, 50: 2, 52: 3, 51: 4, 59: 5, 57: 6, 58: 6}

    per_id = {e.player_id: e for e in risolte}
    assert per_id[51].tied_with == (), "FLAVIO non e' piu' a pari merito"
    assert set(per_id[57].tied_with) == {58}
    assert per_id[58].tiebreaker_resolved is False


def test_le_strategie_di_gara_condividono_un_solo_risolutore():
    """Presidio strutturale: nessuna classe puo' ridefinire il risolutore.

    Il difetto del ripiego su `player_id` e' sopravvissuto per anni perche' il
    metodo era copiato alla lettera in due classi: correggerne una lasciava
    l'altra indietro, senza che niente lo segnalasse. Il posto giusto e' uno
    solo, ed e' la classe base.
    """
    from models.classification.strategies.base import ClassificationStrategy
    from models.classification.strategies import gara_strategies

    base = ClassificationStrategy._resolve_ties_with_spot_shot
    ridefinizioni = [
        nome
        for nome, oggetto in vars(gara_strategies).items()
        if isinstance(oggetto, type)
        and issubclass(oggetto, ClassificationStrategy)
        and oggetto is not ClassificationStrategy  # la base *deve* definirlo
        and vars(oggetto).get("_resolve_ties_with_spot_shot") is not None
    ]
    assert not ridefinizioni, (
        "queste strategie ridefiniscono il risolutore invece di usare quello "
        f"della classe base: {ridefinizioni}"
    )
    assert (
        gara_strategies.RandomGaraClassificationStrategy._resolve_ties_with_spot_shot
        is base
    )
