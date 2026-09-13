# models/dashboard/comandi.py
"""Qual è il comando che una gara sta aspettando dal suo direttore.

Una gara diretta, in dashboard, non dice mai *cosa* aspetta: dice «In corso» o
«Turno completato» e offre un «Gestisci» uguale per tutti gli stati. Con cinque
gare in mano, sapere quale delle cinque aspetta te e per fare cosa richiede di
aprirle una a una.

Qui la domanda si risolve una volta sola, in Python. La pagina della gara del
direttore (`templates/direttore/_fase_*.html`, una per fase) resta l'unico
posto in cui i comandi si **eseguono**: dipende da variabili che calcola la
route della gara e da funzioni JavaScript che vivono su quella pagina. Dal
2026-09-12 e' lei a leggere da qui il comando che aspetta, per la fascia
scura in cima (canvas «Pagina gara del direttore»): la dashboard lo annuncia,
la pagina lo esegue, la macchina a stati e' una sola.

Quello che si può portare in dashboard senza duplicare niente è **l'annuncio**:
il nome del comando che tocca adesso. Il tocco porta alla gara, dove il
pulsante vero sta già.

Il comando è un valore simbolico e non una frase: le stringhe da tradurre
stanno nei template, dov'è puntata la pipeline di Babel, e un enum in colonna
non ci finisce mai — questo vive solo per la durata di una richiesta.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from models.competition.models import Gara
from models.competition.pendenze_turno import (
    pendenze_del_turno,
    pendenze_della_chiusura,
)
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import GaraStatus, MatchStatus, ProvaDerivedStatus


class ComandoDirezione(str, Enum):
    """I comandi che esistono davvero, quelli della pagina della gara.

    Non ce ne sono altri, e in particolare **non** esistono «chiudi il turno»
    né «assegna i tavoli»: un turno finisce quando finiscono le sue partite, e
    i tavoli li assegna la gara da sé secondo `available_tables`.
    """

    APRI_ISCRIZIONI = "apri_iscrizioni"
    AVVIA_GARA = "avvia_gara"
    ESTENDI_ISCRIZIONI = "estendi_iscrizioni"
    AVVIA_TURNO = "avvia_turno"
    AVVIA_SPAREGGIO = "avvia_spareggio"
    TERMINA_GARA = "termina_gara"


@dataclass(frozen=True)
class ComandoVM:
    """Il comando che aspetta, più quel poco che serve a raccontarlo."""

    tipo: ComandoDirezione
    #: Il turno da avviare, per `AVVIA_TURNO`.
    turno: Optional[int] = None
    #: Vero quando il comando c'è ma non si può ancora dare: la gara non ha
    #: abbastanza iscritti. Si annuncia lo stesso, perché il direttore deve
    #: sapere che quella gara aspetta **lui** e cosa le manca.
    bloccato: bool = False
    iscritti: Optional[int] = None
    minimo: Optional[int] = None
    #: Per `AVVIA_TURNO` bloccato: prove della X da convalidare ed esercizi
    #: da registrare del turno appena concluso (`pendenze_turno`).
    prove_x: Optional[int] = None
    esercizi: Optional[int] = None


def _partite_tutte_chiuse(gara: Gara) -> bool:
    """Tutte le partite della gara sono concluse.

    Serve solo alla formula casuale, dove i turni nascono tutti insieme e la
    gara è finita quando non resta niente da giocare — `get_real_status()` da
    solo non basta, ed è la stessa condizione che il pannello valuta come
    `completed_matches == total_matches`.
    """
    partite = list(gara.matches or [])
    if not partite:
        return False
    return all(MatchStatus.is_finished(m.status) for m in partite)


def comando_per(gara: Gara) -> Optional[ComandoVM]:
    """Il comando che questa gara aspetta, o `None` se non aspetta niente.

    «Niente» è una risposta frequente e giusta: mentre un turno si gioca il
    direttore non ha nulla da fare, e annunciargli un comando qualsiasi
    varrebbe meno di zero.

    Rispecchia le fasi della pagina del direttore. Dove una fase offre più
    di un pulsante si sceglie **quello che fa andare avanti la gara**: è la
    domanda a cui questa funzione risponde.
    """
    stato = gara.status
    reale = gara.get_real_status()

    # La gara di playoff non ha iscrizioni da aprire: ci si entra accettando
    # l'invito, e prima dell'avvio l'unico comando è avviarla (SPECIFICHE.md,
    # «Playoff», nota del 2026-09-13). Vale anche per quelle nate prima e
    # rimaste in iscrizione, con una finestra magari scaduta: estenderla non
    # porterebbe nessuno.
    if (
        gara.is_playoff
        and not gara.current_round
        and stato in (GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value)
    ):
        iscritti = gara.get_active_inscriptions_count()
        minimo = gara.min_participants or 0
        return ComandoVM(
            tipo=ComandoDirezione.AVVIA_GARA,
            bloccato=iscritti < minimo,
            iscritti=iscritti,
            minimo=minimo,
        )

    if stato == GaraStatus.SETUP.value:
        return ComandoVM(tipo=ComandoDirezione.APRI_ISCRIZIONI)

    if reale == GaraStatus.INSCRIPTION.value:
        iscritti = gara.get_active_inscriptions_count()
        minimo = gara.min_participants or 0
        return ComandoVM(
            tipo=ComandoDirezione.AVVIA_GARA,
            bloccato=iscritti < minimo,
            iscritti=iscritti,
            minimo=minimo,
        )

    if reale == ProvaDerivedStatus.INSCRIPTION_CLOSED.value:
        iscritti = gara.get_active_inscriptions_count()
        minimo = gara.min_participants or 0
        if iscritti >= minimo:
            return ComandoVM(tipo=ComandoDirezione.AVVIA_GARA)
        # Le iscrizioni sono scadute e i giocatori non bastano: l'unica mossa
        # che sblocca la gara è riaprire la finestra.
        return ComandoVM(
            tipo=ComandoDirezione.ESTENDI_ISCRIZIONI,
            bloccato=True,
            iscritti=iscritti,
            minimo=minimo,
        )

    if reale == ProvaDerivedStatus.INSCRIPTION_NOT_YET_OPEN.value:
        # Le iscrizioni si aprono da sole, all'ora fissata: qui si aspetta.
        return None

    if stato == GaraStatus.PLAYING.value:
        casuale = gara.matchmaking_strategy == MatchmakingStrategy.RANDOM.value

        # L'ordine dei due controlli conta, e conta solo nella formula
        # casuale. Li' i turni nascono **tutti insieme**, quindi finito un
        # turno non c'e' un turno da avviare: `get_real_status()` risponde
        # comunque `round_completed`, ma la gara e' finita quando finiscono
        # le partite. Chiedere prima «e' finita?» e poi «c'e' un turno dopo?»
        # e' lo stesso ordine della pagina della gara, che nella formula
        # casuale guarda prima se resta qualcosa da giocare.
        # Invertendoli — come faceva la prima stesura — una gara casuale
        # conclusa annunciava «Avvia il turno 2», che non esiste.
        finita = reale == ProvaDerivedStatus.TOURNAMENT_COMPLETED.value or (
            casuale and _partite_tutte_chiuse(gara)
        )
        if finita:
            return _chiusura(gara)

        if reale == ProvaDerivedStatus.ROUND_COMPLETED.value and not casuale:
            # Le partite sono chiuse, ma il turno puo' aspettare ancora la
            # prova della X e gli esercizi: il comando c'e', bloccato.
            pendenze = pendenze_del_turno(gara, gara.current_round or 0)
            return ComandoVM(
                tipo=ComandoDirezione.AVVIA_TURNO,
                turno=(gara.current_round or 0) + 1,
                bloccato=pendenze.bloccano,
                prove_x=pendenze.prove_x,
                esercizi=pendenze.esercizi,
            )

        # Turno in corso: non tocca a lui.
        return None

    if stato == GaraStatus.AWAITING_SSR.value:
        return _chiusura(gara)

    return None


def _chiusura(gara: Gara) -> ComandoVM:
    """Spareggio o terminazione: la differenza la fa il pari merito.

    `SpareggioService` è l'**unica** implementazione viva del rilevamento dei
    parimerito: nel repo ne esistono altre due, morte, e chiamare quelle
    darebbe una risposta plausibile e sbagliata.
    """
    from models.competition.spareggio_service import SpareggioService

    tipo = (
        ComandoDirezione.AVVIA_SPAREGGIO
        if SpareggioService.has_unresolved_tiebreakers(gara.id)
        else ComandoDirezione.TERMINA_GARA
    )
    # Come il turno dopo, la chiusura aspetta la prova della X e gli esercizi
    # dell'ultimo turno: il comando c'e', bloccato.
    pendenze = pendenze_della_chiusura(gara)
    return ComandoVM(
        tipo=tipo,
        bloccato=pendenze.bloccano,
        prove_x=pendenze.prove_x,
        esercizi=pendenze.esercizi,
    )


__all__ = ["ComandoDirezione", "ComandoVM", "comando_per"]
