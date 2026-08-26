"""A chi tocca la X nel primo turno: sorteggio, o l'ultimo iscritto.

Il caso dispari gestito con la X assegna il turno di riposo a chi capita: è il
sorteggio a deciderlo, e finché gli iscritti sono tutti sullo stesso piano va
benissimo. Nella pratica non lo sono sempre — l'ultimo arrivato è spesso quello
che ha completato il tabellone all'ultimo momento, e il direttore vuole poter
dire «la X è sua» invece di rischiare che tocchi a chi era iscritto da una
settimana.

Da qui la scelta esplicita all'avvio (`Gara.bye_to_last_inscribed`): il resto
degli abbinamenti resta casuale, cambia solo *chi* riceve la X del primo turno.

Come viene applicata: **rietichettando**, mai riabbinando
------------------------------------------------------
La tentazione è generare gli abbinamenti e poi spostare la X. È sbagliato per
la strategia casuale, che pre-genera **tutti** i turni in un colpo solo: lì chi
riceve la X al turno 1 non la riceve più per il resto della gara, e toccare il
solo turno 1 gli regalerebbe una seconda X più avanti, oltre a introdurre un
reincontro che il circle method aveva escluso.

Quel che si fa invece è scambiare **le identità** dei due giocatori — il
destinatario voluto e quello sorteggiato — ovunque compaiano. È una
permutazione dei nomi su una struttura che dipende solo dalle posizioni:
zero reincontri, una X a testa e tutto il resto restano veri per costruzione.

Per Amalfi lo scambio avviene sul primo turno **e sulla classifica di
partenza**, che è l'input da cui il turno 1 discende: al turno 1 la matrice
degli incontri è vuota e nessuno ha ancora avuto la X, quindi l'algoritmo
dipende solo dalle posizioni e scambiare due nomi nel seeding equivale
esattamente a scambiarli negli abbinamenti. Tenerli allineati serve a chi
volesse ricontrollare il sorteggio a posteriori.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import List, Optional, Sequence

from .configuration import FirstRoundPolicy, MatchmakingStrategy, OddNumberPolicy
from .strategies.base import Pairing

#: Le strategie in cui il primo turno nasce da un sorteggio e la X è una sola.
#: Fuori da queste la domanda non si pone: il tabellone assegna i suoi bye per
#: dimensionamento, il round robin li fa ruotare su tutti.
X_STRATEGIES = (
    MatchmakingStrategy.AMALFI.value,
    "advanced_amalfi",  # alias storico, mappato su amalfi dal registry
    MatchmakingStrategy.RANDOM.value,
)

#: Le politiche del dispari che producono davvero una X. `TRIO` fa giocare tre
#: giocatori insieme (nessuno riposa) e `NO` manda l'eccedenza in lista
#: d'attesa (il numero resta pari).
X_POLICIES = (
    OddNumberPolicy.BYE.value,
    OddNumberPolicy.BYE_WITH_CHALLENGE.value,
)


def choice_applies(gara) -> bool:
    """La scelta ha senso per questa gara, qui e ora?

    Serve sia a decidere se mostrare la domanda al direttore, sia a non
    applicare una preferenza rimasta appesa a una gara che nel frattempo è
    diventata pari (un'iscrizione in più fra la scelta e l'avvio).
    """
    if getattr(gara, "matchmaking_strategy", None) not in X_STRATEGIES:
        return False
    policy = getattr(gara, "first_round_policy", FirstRoundPolicy.RANDOM.value)
    if policy != FirstRoundPolicy.RANDOM.value:
        return False
    if getattr(gara, "odd_number_policy", None) not in X_POLICIES:
        return False
    return _active_inscriptions_count(gara) % 2 == 1


def last_inscribed_user_id(gara) -> Optional[int]:
    """L'ultimo iscritto attivo, o `None` se non ce ne sono.

    "Ultimo" è l'ordine di arrivo: `created_at`, e a parità l'id — due
    iscrizioni possono condividere il timestamp (iscrizione multipla da parte
    del direttore) e senza il secondo criterio la scelta sarebbe arbitraria.
    Le righe storiche senza `created_at` valgono come le più vecchie.
    """
    inscriptions = _active_inscriptions(gara)
    if not inscriptions:
        return None
    last = max(
        inscriptions,
        key=lambda i: (getattr(i, "created_at", None) or datetime.min, i.id),
    )
    return last.user_id


def preferred_bye_player(gara) -> Optional[int]:
    """Chi deve ricevere la X del primo turno, se il direttore l'ha chiesto.

    `None` significa «lascia decidere al sorteggio», che è anche la risposta
    per ogni gara in cui la domanda non si pone.
    """
    if not getattr(gara, "bye_to_last_inscribed", False):
        return None
    if not choice_applies(gara):
        return None
    return last_inscribed_user_id(gara)


def bye_player_in(pairings: Sequence[Pairing]) -> Optional[int]:
    """Chi riceve la X in questo turno, o `None` se non c'è una X."""
    for pairing in pairings:
        if pairing.is_bye and pairing.players:
            return pairing.players[0]
    return None


def swap_players(pairings: Sequence[Pairing], first: int, second: int) -> List[Pairing]:
    """Gli stessi abbinamenti con due giocatori scambiati di posto."""
    if first == second:
        return list(pairings)

    def relabel(player_id: int) -> int:
        if player_id == first:
            return second
        if player_id == second:
            return first
        return player_id

    return [
        replace(pairing, players=tuple(relabel(p) for p in pairing.players))
        for pairing in pairings
    ]


def apply_to_round(
    pairings: Sequence[Pairing], target_player_id: Optional[int]
) -> List[Pairing]:
    """Porta la X a `target_player_id` scambiandolo con chi l'ha sorteggiata.

    No-op quando non c'è una preferenza, quando il turno non ha una X, o
    quando il sorteggio ha già fatto da sé.
    """
    result = list(pairings)
    if target_player_id is None:
        return result
    drawn = bye_player_in(result)
    if drawn is None or drawn == target_player_id:
        return result
    return swap_players(result, drawn, target_player_id)


def _active_inscriptions(gara) -> list:
    """Gli iscritti che giocano davvero: né ritirati né in lista d'attesa."""
    inscriptions = getattr(gara, "inscriptions", None) or []
    return [
        i
        for i in inscriptions
        if not getattr(i, "is_withdrawn", False)
        and not getattr(i, "is_waitlist", False)
    ]


def _active_inscriptions_count(gara) -> int:
    return len(_active_inscriptions(gara))


__all__ = [
    "X_STRATEGIES",
    "X_POLICIES",
    "apply_to_round",
    "bye_player_in",
    "choice_applies",
    "last_inscribed_user_id",
    "preferred_bye_player",
    "swap_players",
]
