"""Le tre regole con cui lo Spot Shot Rally scioglie il pari merito.

Confermate dall'utente il 2026-08-19, e tutte e tre facili da tradire scrivendo
un `sorted()` in fretta:

1. lo spareggio vale **solo** entro il suo posto («spareggio SSR fino al N°
   posto»); oltre, il pari merito e' un risultato legittimo;
2. dentro un gruppo ordina **solo** l'SSR;
3. a SSR uguale il pari merito **rimane** — nessun ripiego, in particolare non
   l'id del giocatore, che e' l'ordine di iscrizione.

Dal 2026-10-07 lo SSR e' un anello della catena di gara e lo applica il motore
unico (`models/classification/ordinamento.py`, ADR-078). Fino al 2026-08-19 il
risolutore era duplicato alla lettera nelle due strategie di gara, ed e' cosi'
che una correzione applicata a una copia non ha mai raggiunto l'altra: oggi
c'e' un motore solo, e il presidio in fondo lo verifica.
"""

from typing import Dict, List

from models.classification.ordinamento import (
    SSR_FINO_AL_DEFAULT,
    Concorrente,
    Criterio,
    Voce,
    ordina,
)


def _risolvi(gruppi: List[List[int]], ssr: Dict[int, int], soglia=None):
    """Gruppi gia' pari sul principale, poi lo SSR fino a ``soglia``.

    Ogni sotto-lista e' un gruppo a pari vittorie, in ordine decrescente.
    """
    concorrenti = [
        Concorrente(player_id=pid, vittorie=100 - indice, ssr=ssr.get(pid))
        for indice, gruppo in enumerate(gruppi)
        for pid in gruppo
    ]
    voce = Voce(
        Criterio.SPAREGGIO_SSR,
        soglia if soglia is not None else SSR_FINO_AL_DEFAULT,
    )
    fasce = ordina(concorrenti, Criterio.VITTORIE, (voce,))
    return [
        _Esito(g.player_id, f.posizione, tuple(x.player_id for x in f.giocatori))
        for f in fasce
        for g in f.giocatori
    ]


class _Esito:
    def __init__(self, player_id, position, fascia):
        self.player_id = player_id
        self.position = position
        self.tied_with = tuple(p for p in fascia if p != player_id)
        self.tiebreaker_resolved = len(fascia) == 1


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


def test_le_strategie_di_gara_condividono_un_solo_motore():
    """Presidio strutturale: nessuna strategia ordina da se'.

    Il difetto del ripiego su `player_id` e' sopravvissuto per anni perche' il
    risolutore era copiato alla lettera in due classi: correggerne una lasciava
    l'altra indietro, senza che niente lo segnalasse. Il posto giusto e' uno
    solo: il motore della catena, chiamato dalla classe base.
    """
    from models.classification.strategies.base import ClassificationStrategy
    from models.classification.strategies import gara_strategies, round_strategies

    base = ClassificationStrategy._ordina_con_la_catena
    for modulo in (gara_strategies, round_strategies):
        for nome, oggetto in vars(modulo).items():
            if isinstance(oggetto, type) and issubclass(
                oggetto, ClassificationStrategy
            ):
                assert oggetto._ordina_con_la_catena is base, nome
    assert not hasattr(ClassificationStrategy, "_resolve_ties_with_spot_shot")
