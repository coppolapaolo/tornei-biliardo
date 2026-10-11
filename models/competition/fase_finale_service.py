"""La fase finale dopo i gironi, sul database (piano gironi, PR 5).

Le regole stanno in `models/matchmaking/fase_finale.py` e
`models/classification/fase_finale.py`, pure. Qui:

* **dove finiscono i gironi** (`turni_dei_gironi`): i turni del girone più
  numeroso, o del girone unico. Dopo, si gioca il tabellone;
* **chi va al tabellone, e con che ordine** (`semina`): la classifica a
  gironi alla fine dei gironi, con la catena di gara;
* **come ne è uscito ognuno** (`bande`): le bande del tabellone, dalle sole
  partite della fase finale;
* **la classifica finale** (`classifica_finale`): il tabellone, poi gli altri
  nell'ordine dei gironi;
* **le finali per piazzamento** (`incroci`, PR 6): il p-esimo del girone A
  contro il p-esimo del girone B, con le posizioni nel girone decise come per
  il taglio; ogni finale assegna due posti (`bande`).

Nessun metodo scrive: si chiamano dentro la generazione dei turni e dentro i
calcoli di classifica, che hanno già la loro transazione.

**Pari merito al taglio.** Chi passa fra il `K`-esimo e il `K+1`-esimo di un
girone si decide come in una classifica di turno: con la catena di turno
della gara (ADR-078), che finisce sempre col sorteggio; niente spareggio SSR
a metà gara (decisione dell'utente, 2026-10-11). Lo stesso ordine decide chi
è migliore fra i primi dei gironi, cioè chi prende i bye.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from models.base import db
from models.matchmaking.fase_finale import (
    incroci_per_piazzamento,
    qualificati_dei_gironi,
    semina_del_tabellone,
    verifica_qualificati,
)
from models.matchmaking.gironi import turni_dei_gironi as turni_per_taglie
from models.matchmaking.gironi import turni_del_girone


def ha_tabellone_finale(gara: Any) -> bool:
    """La gara prevede il tabellone dopo i gironi? Solo un ``True`` vero conta."""
    return getattr(gara, "ha_tabellone_finale", False) is True


def ha_finali_per_piazzamento(gara: Any) -> bool:
    """La gara prevede le finali per piazzamento? Solo un ``True`` vero conta."""
    return getattr(gara, "ha_finali_per_piazzamento", False) is True


def ha_fase_finale(gara: Any) -> bool:
    """La gara prevede una fase finale dopo i gironi: tabellone o finali."""
    return ha_tabellone_finale(gara) or ha_finali_per_piazzamento(gara)


def si_giocano_le_finali_per_piazzamento(gara: Any) -> bool:
    """Le finali per piazzamento si giocano davvero: previste, e con due gironi.

    Come il tabellone: se la gara parte con un girone solo la gara finisce
    col girone. Con tre o più gironi non si arriva qui: l'avvio li rifiuta.
    """
    if not ha_finali_per_piazzamento(gara) or not getattr(gara, "id", None):
        return False
    from models.competition.gironi_service import GironiService

    return bool(GironiService.girone_dei_giocatori(gara))


def si_gioca_la_fase_finale(gara: Any) -> bool:
    """Dopo i gironi si gioca qualcosa: il tabellone o le finali per piazzamento."""
    return si_gioca_il_tabellone(gara) or si_giocano_le_finali_per_piazzamento(gara)


def si_gioca_il_tabellone(gara: Any) -> bool:
    """Il tabellone dopo i gironi si gioca davvero: previsto, e con più gironi.

    Se la gara parte con un girone solo, perché gli iscritti erano pochi, il
    tabellone non si gioca: la gara finisce col girone, e la classifica del
    girone è quella finale. Prima dell'avvio i gironi non ci sono ancora, e la
    risposta è no.
    """
    if not ha_tabellone_finale(gara) or not getattr(gara, "id", None):
        return False
    from models.competition.gironi_service import GironiService

    return bool(GironiService.girone_dei_giocatori(gara))


def turni_dei_gironi(gara: Any) -> int:
    """I turni della fase a gironi della gara: quelli del girone più numeroso.

    Chi sta in quale girone lo dice `GironiService.girone_dei_giocatori`;
    nel girone unico contano gli iscritti del calendario, cioè la classifica
    di partenza del primo turno (che resta anche per chi si è ritirato) o,
    prima dell'avvio, gli iscritti attivi.
    """
    from models.classification.seeding_service import SeedingService
    from models.competition.gironi_service import GironiService

    gironi = GironiService.gironi(gara)
    if gironi:
        return turni_per_taglie([len(g) for g in gironi])
    n = len(SeedingService.get_seeding(gara.id)) if gara.id else 0
    if not n:
        n = gara.get_active_inscriptions_count()
    return turni_del_girone(n)


def e_della_fase_finale(gara: Any, round_number: Optional[int]) -> bool:
    """Questo turno è della fase finale: del tabellone o delle finali?"""
    if round_number is None or not si_gioca_la_fase_finale(gara):
        return False
    return round_number > turni_dei_gironi(gara)


def distanza_della_fase(gara: Any, round_number: Optional[int]) -> int:
    """La distanza di un turno senza override del turno (ADR-027, ADR-081).

    Nei turni della fase finale dopo i gironi — tabellone o finali per
    piazzamento — quella della fase finale
    (`Gara.effective_final_phase_distance`: come i gironi o «al N»),
    altrimenti quella della gara. La sola finale può averne un'altra:
    `distanza_della_finale`.
    """
    if ha_fase_finale(gara) and e_della_fase_finale(gara, round_number):
        return gara.effective_final_phase_distance
    return gara.distance


def distanza_della_finale(gara: Any) -> int:
    """La distanza della sola finale: la sua, o come la fase finale."""
    return gara.effective_final_distance


def motivo_tabellone_impossibile(taglie: Sequence[int], k: int) -> Optional[str]:
    """Perché coi gironi composti il tabellone non si fa: una chiave, o None."""
    return verifica_qualificati(taglie, k)


def _in_gara(gara: Any) -> set:
    from models.competition.models import Inscription

    return {
        uid
        for (uid,) in db.session.query(Inscription.user_id)
        .filter(
            Inscription.gara_id == gara.id,
            Inscription.is_waitlist.is_(False),
            Inscription.is_withdrawn.is_(False),
        )
        .all()
    }


def _concorrenti(gara: Any, fino_al_turno: int) -> List[Any]:
    """I giocatori con i numeri dei gironi, e la posizione al turno prima."""
    from models.classification.gironi_della_gara import concorrente
    from models.classification.models import RoundClassification
    from models.classification.score_aggregator import ScoreAggregator

    prima = {
        rc.user_id: rc.position
        for rc in db.session.query(RoundClassification)
        .filter_by(gara_id=gara.id, round_number=fino_al_turno - 1)
        .all()
    }
    return [
        concorrente(
            gara,
            s.player_id,
            vittorie=s.matches_won,
            rack_vinti=s.racks_won,
            differenza_rack=s.rack_difference,
            punti=s.points,
            posizione_precedente=prima.get(s.player_id),
        )
        for s in ScoreAggregator().aggregate_round_scores(gara.id, fino_al_turno)
    ]


def ordine_dei_gironi(
    gara: Any, *, per_il_taglio: bool
) -> Tuple[List[Tuple[int, List[int]]], Dict[int, Tuple[int, int]]]:
    """La classifica a gironi alla fine dei gironi.

    Returns:
        Le fasce ``(posizione, giocatori)`` della gara, e per ognuno
        ``(girone, posizione nel girone)``.

    Con ``per_il_taglio`` — chi passa al tabellone, e con che testa di serie —
    è una **classifica di turno**, fatta con la catena di turno della gara
    all'ultimo turno dei gironi (di norma principale → differenza → posizione
    al turno precedente → sorteggio, ADR-078): l'ordine è sempre completo, e
    lo spareggio SSR non c'è (decisione dell'utente, 2026-10-11). Senza, è la
    classifica di gara, con la catena di gara senza lo SSR, e chi resta pari
    condivide la posizione: serve a ordinare la classifica finale.
    """
    from models.classification.catene import catena_di_gara, catena_di_turno
    from models.classification.gironi_della_gara import classifica_a_gironi
    from models.classification.ordinamento import prima_dello_ssr
    from models.competition.gironi_service import GironiService

    g = turni_dei_gironi(gara)
    catena = (
        tuple(catena_di_turno(gara, g))
        if per_il_taglio
        else tuple(prima_dello_ssr(catena_di_gara(gara)))
    )
    esito = classifica_a_gironi(
        gara,
        _concorrenti(gara, g),
        GironiService.girone_dei_giocatori(gara),
        catena,
        g,
        completa=per_il_taglio,
    )
    fasce = [(f.posizione, [c.player_id for c in f.giocatori]) for f in esito.fasce]
    return fasce, {
        pid: (esito.girone[pid], esito.posizione_nel_girone[pid])
        for pid in esito.girone
    }


def semina(gara: Any) -> Tuple[List[int], Dict[int, int]]:
    """I qualificati in ordine di testa di serie, e il girone di ognuno."""
    fasce, posti = ordine_dei_gironi(gara, per_il_taglio=True)
    ordine_della_gara = [pid for _pos, ids in fasce for pid in ids]
    per_girone: Dict[int, List[int]] = {}
    for pid in sorted(posti, key=lambda p: posti[p][1]):
        per_girone.setdefault(posti[pid][0], []).append(pid)
    qualificati = qualificati_dei_gironi(
        per_girone, gara.effective_qualifiers_per_group, _in_gara(gara)
    )
    seme = semina_del_tabellone(qualificati, ordine_della_gara)
    return seme, {pid: posti[pid][0] for pid in seme}


def incroci(gara: Any) -> Tuple[List[Tuple[int, int]], List[int]]:
    """Le coppie delle finali per piazzamento, e chi si classifica diretto.

    Le posizioni nel girone le decide la classifica di turno all'ultimo turno
    dei gironi, come per il taglio del tabellone (`ordine_dei_gironi(
    per_il_taglio=True)`): l'ordine è sempre completo. Ci sono tutti, anche
    chi si è ritirato: perde la sua finale a tavolino.
    """
    _fasce, posti = ordine_dei_gironi(gara, per_il_taglio=True)
    per_girone: Dict[int, List[int]] = {}
    for pid in sorted(posti, key=lambda p: posti[p][1]):
        per_girone.setdefault(posti[pid][0], []).append(pid)
    return incroci_per_piazzamento(per_girone)


def chi_va_al_tabellone(
    gara: Any, partite: Optional[Sequence[Any]] = None
) -> Optional[FrozenSet[int]]:
    """Chi gioca il tabellone dopo i gironi, o None se non si sa ancora.

    Dal sorteggio lo dicono i nodi del tabellone; prima, a gironi finiti, la
    stessa classifica che userà il sorteggio (`semina`). Mentre si giocano i
    gironi, col girone unico o senza fase finale: None.
    """
    from models.competition.tabellone_della_gara import tabellone_della_gara
    from models.match.models import Match
    from models.status_enum import MatchStatus

    if not getattr(gara, "id", None):
        return None
    if partite is None:
        partite = Match.query.filter_by(gara_id=gara.id).all()
    quale = tabellone_della_gara(gara, partite)
    if not quale.dopo_i_gironi:
        return None
    if quale.da_mostrare:
        return frozenset(
            pid
            for m in partite
            if m.bracket_type and m.bracket_group is None
            for pid in (m.player1_id, m.player2_id)
            if pid
        )
    g = turni_dei_gironi(gara)
    dei_gironi = [m for m in partite if (m.round_number or 0) <= g]
    if (gara.current_round or 0) < g or any(
        not MatchStatus.is_finished(m.status) for m in dei_gironi
    ):
        return None
    return frozenset(semina(gara)[0])


def bande(gara: Any, fino_al_turno: int) -> Tuple[List[List[int]], FrozenSet[int]]:
    """Le bande della fase finale, e chi resta a pari merito.

    Solo le partite della fase finale: quelle dei gironi non eliminano
    nessuno. Senza finalina i due semifinalisti sconfitti sono terzi a pari
    merito (UC6). Con le finali per piazzamento: `_bande_delle_finali`.
    """
    if ha_finali_per_piazzamento(gara):
        return _bande_delle_finali(gara, fino_al_turno)
    from models.classification.bracket_standings import (
        BracketMatch,
        elimination_bands,
    )
    from models.match.models import Match
    from models.matchmaking.bracket import BRACKET_WINNERS
    from models.status_enum import MatchStatus

    g = turni_dei_gironi(gara)
    righe = (
        Match.query.filter(
            Match.gara_id == gara.id,
            Match.round_number > g,
            Match.round_number <= fino_al_turno,
            Match.bracket_type.isnot(None),
        )
        .order_by(Match.round_number, Match.id)
        .all()
    )
    nodi: List[BracketMatch] = []
    for m in righe:
        finita = MatchStatus.is_finished(m.status)
        perdente = None
        if finita and m.winner_id and not m.is_bye:
            perdente = m.player1_id if m.winner_id == m.player2_id else m.player2_id
        nodi.append(
            BracketMatch(
                bracket_type=m.bracket_type,
                round_number=m.round_number,
                players=tuple(p for p in (m.player1_id, m.player2_id) if p),
                winner_id=m.winner_id if finita else None,
                loser_id=perdente,
                order=m.id or 0,
                double_elimination=False,
            )
        )
    pari: FrozenSet[int] = frozenset()
    if not getattr(gara, "third_place_match", False):
        primo = [n for n in righe if n.bracket_type == BRACKET_WINNERS]
        if primo:
            finale = max(n.bracket_round for n in primo)
            # La finale esiste davvero solo se il turno che la contiene ha
            # un nodo solo: prima, i «semifinalisti» non ci sono ancora.
            nodi_finale = [n for n in primo if n.bracket_round == finale]
            if len(nodi_finale) == 1:
                pari = frozenset(
                    n.player1_id if n.winner_id == n.player2_id else n.player2_id
                    for n in primo
                    if n.bracket_round == finale - 1
                    and n.winner_id
                    and not n.is_bye
                    and MatchStatus.is_finished(n.status)
                )
    return elimination_bands(nodi), pari


def _bande_delle_finali(
    gara: Any, fino_al_turno: int
) -> Tuple[List[List[int]], FrozenSet[int]]:
    """Le bande delle finali per piazzamento: due posti per finale.

    Le coppie sono quelle delle partite (`bracket_slot` è la coppia), che
    restano anche se poi si corregge un risultato dei gironi; una coppia senza
    partita — ritirati tutti e due — si legge dagli incroci e resta a pari
    merito sui suoi due posti.
    """
    from models.classification.fase_finale import bande_delle_finali
    from models.match.models import Match
    from models.matchmaking.bracket import BRACKET_PLACEMENT
    from models.status_enum import MatchStatus

    coppie, diretti = incroci(gara)
    partite = {
        m.bracket_slot: m
        for m in Match.query.filter(
            Match.gara_id == gara.id,
            Match.round_number > turni_dei_gironi(gara),
            Match.round_number <= fino_al_turno,
            Match.bracket_type == BRACKET_PLACEMENT,
        ).all()
    }
    vincitori: Dict[int, Optional[int]] = {}
    for indice in range(len(coppie)):
        m = partite.get(indice)
        if m is None:
            continue
        coppie[indice] = (m.player1_id, m.player2_id)
        vincitori[indice] = m.winner_id if MatchStatus.is_finished(m.status) else None
    senza_partita = (
        {i for i in range(len(coppie)) if i not in partite}
        if fino_al_turno > turni_dei_gironi(gara)
        else set()
    )
    return bande_delle_finali(coppie, vincitori, diretti, senza_partita=senza_partita)


def classifica_finale(
    gara: Any,
    fasce_dei_gironi: Sequence[Tuple[int, Sequence[int]]],
    fino_al_turno: int,
) -> List[Tuple[int, List[int]]]:
    """La fase finale, poi gli altri nell'ordine dei gironi (UC6)."""
    from models.classification.fase_finale import classifica_con_tabellone

    bande_tabellone, pari = bande(gara, fino_al_turno)
    return classifica_con_tabellone(bande_tabellone, fasce_dei_gironi, pari_merito=pari)


__all__ = [
    "bande",
    "chi_va_al_tabellone",
    "classifica_finale",
    "distanza_della_fase",
    "distanza_della_finale",
    "e_della_fase_finale",
    "ha_fase_finale",
    "ha_finali_per_piazzamento",
    "ha_tabellone_finale",
    "incroci",
    "si_gioca_il_tabellone",
    "si_gioca_la_fase_finale",
    "si_giocano_le_finali_per_piazzamento",
    "motivo_tabellone_impossibile",
    "ordine_dei_gironi",
    "semina",
    "turni_dei_gironi",
]
