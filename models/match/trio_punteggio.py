# models/match/trio_punteggio.py
"""Il punteggio di un trio segnato a totali, dalla card del direttore.

Il trio si gioca in un ordine fisso (`TrioConfig.get_matchup_for_rack`): il
primo triangolo di ogni girone e' fra il primo e il secondo giocatore, il
secondo fra il primo e il terzo, il terzo fra il secondo e il terzo. Il
segnapunti registra un triangolo alla volta e il vincitore e' per forza uno
dei due al tavolo; la card invece segna **quanti** triangoli ha vinto
ciascuno, con − e + sotto ogni nome.

Un totale non sempre corrisponde a una sequenza possibile: dopo un triangolo
solo, il terzo giocatore non puo' averne vinto nessuno, perche' non ha ancora
giocato. Qui si risponde, senza database, a due domande:

* quale sequenza di vincitori realizza quei totali, cambiando il meno possibile
  i triangoli gia' registrati (`assegna_vincitori`);
* quali «+» hanno senso adesso (`piu_ammessi`), cosi' la card li spegne invece
  di far arrivare un rifiuto.

I triangoli sono al massimo nove (tre gironi): la ricerca e' esaustiva.
"""

from __future__ import annotations

from itertools import product
from typing import Optional, Sequence

from models.match.trio_config import TrioConfig


def massimo_per_giocatore(config: TrioConfig) -> int:
    """Quanti triangoli puo' vincere al tavolo un giocatore del trio.

    Ognuno ne gioca due per girone: e' il limite di `set_result_direct`. Il
    bonus delle distanze dispari non e' un triangolo giocato, e non si segna.
    """
    return config.racks_played_per_player


def assegna_vincitori(
    config: TrioConfig,
    punti: Sequence[int],
    esistenti: Sequence[int] = (),
) -> Optional[list[int]]:
    """La sequenza dei vincitori (indici 0–2) che realizza `punti`, o `None`.

    Fra le sequenze possibili sceglie quella che cambia meno vincitori rispetto
    a `esistenti` (gli indici dei triangoli gia' registrati, in ordine): chi
    corregge un numero non deve riscrivere la storia del tavolo.
    """
    if len(punti) != 3 or any(p < 0 for p in punti):
        return None
    totale = sum(punti)
    if totale > config.total_played_racks:
        return None
    if any(p > massimo_per_giocatore(config) for p in punti):
        return None

    coppie = []
    for numero in range(1, totale + 1):
        incontro = config.get_matchup_for_rack(numero)
        if incontro is None:
            return None
        coppie.append((incontro[0], incontro[1]))

    migliore: Optional[list[int]] = None
    migliore_costo = totale + 1
    obiettivo = list(punti)
    for scelta in product((0, 1), repeat=totale):
        vincitori = [coppie[i][s] for i, s in enumerate(scelta)]
        if [vincitori.count(g) for g in range(3)] != obiettivo:
            continue
        costo = sum(
            1
            for i, v in enumerate(vincitori)
            if i < len(esistenti) and esistenti[i] != v
        )
        if costo < migliore_costo:
            migliore, migliore_costo = vincitori, costo
            if costo == 0:
                break
    return migliore


def piu_ammessi(config: TrioConfig, punti: Sequence[int]) -> list[bool]:
    """Per ogni giocatore, se un triangolo in piu' e' un punteggio possibile."""
    ammessi = []
    for g in range(3):
        dopo = list(punti)
        dopo[g] += 1
        ammessi.append(assegna_vincitori(config, dopo) is not None)
    return ammessi


__all__ = ["assegna_vincitori", "massimo_per_giocatore", "piu_ammessi"]
