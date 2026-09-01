"""Quali partite contano per l'ELO, e perché quelle escluse non contano.

Decisione: docs/adr/ADR-049-same-category-restores-elo-in-handicap-events.md

Fino al 2026-08 la regola era: *una gara con handicap non aggiorna mai i
rating*. Troppo grossolana. In una gara con handicap due giocatori della
**stessa categoria** si affrontano ad armi pari — fra loro nessun handicap è
in gioco — e quel risultato dice esattamente quello che l'ELO vuole sapere.
La regola nuova è quindi: *con l'handicap, l'ELO si aggiorna se e solo se i
giocatori condividono la categoria*.

Perché un modulo e non un ``if`` in più nei chiamanti: la vecchia condizione
era già duplicata in quattro posti — l'handler degli eventi, i due ricalcoli
e ``scripts/diagnose_elo.py``, che nella docstring **dichiarava** di essere
una replica. Aggiungere una seconda condizione a quattro copie è il modo
sicuro per farle divergere, e qui la divergenza non dà errore: dà un ELO che
non torna, mesi dopo.

``exclusion_reason`` restituisce **il motivo** e non un booleano perché i
chiamanti ne fanno usi diversi: l'handler ci scrive il log, la diagnostica ci
spiega un rating fermo, i ricalcoli ci contano gli scarti. Con un ``bool`` il
perché andrebbe ricostruito a valle, cioè riscritto.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from models.base import db

#: Chiave dell'indice: la categoria è per (gara, giocatore), non per giocatore.
CategoriaKey = Tuple[int, int]
CategoriaIndex = Dict[CategoriaKey, Optional[int]]


class RatingExclusion(Enum):
    """Perché una partita conclusa non muove i rating. ``None`` = li muove."""

    WALKOVER = "walkover"
    HANDICAP_CATEGORY_MISSING = "handicap_category_missing"
    HANDICAP_DIFFERENT_CATEGORY = "handicap_different_category"

    @property
    def description(self) -> str:
        """Testo per log e diagnostica — non è rivolto agli utenti finali."""
        return {
            RatingExclusion.WALKOVER: "walkover: nessun rack giocato",
            RatingExclusion.HANDICAP_CATEGORY_MISSING: (
                "handicap: categoria non assegnata a uno dei giocatori"
            ),
            RatingExclusion.HANDICAP_DIFFERENT_CATEGORY: (
                "handicap: i giocatori sono di categorie diverse"
            ),
        }[self]


class RatingEligibility:
    """L'unica fonte di verità su quali partite entrano nell'ELO."""

    @staticmethod
    def player_ids(match) -> List[Optional[int]]:
        """I giocatori della partita: due, o tre se è un trio.

        Per i trii la categoria va confrontata su **tutti e tre**: due su tre
        uguali non bastano, perché il girone interno li fa incontrare tutti.
        """
        if getattr(match, "is_trio", False) and getattr(match, "trio_match", None):
            trio = match.trio_match
            return [trio.player1_id, trio.player2_id, trio.player3_id]
        return [match.player1_id, match.player2_id]

    @staticmethod
    def build_index(matches: Sequence) -> CategoriaIndex:
        """Le categorie di tutte le gare toccate, in **una** query.

        I ricalcoli ciclano su ogni partita mai giocata: leggere le due
        iscrizioni per partita trasformerebbe il replay in migliaia di query.
        Qui si carica tutto in un colpo e si consulta in memoria.
        """
        from models.competition.models import Inscription

        gara_ids = {m.gara_id for m in matches if getattr(m, "gara_id", None)}
        if not gara_ids:
            return {}

        rows = (
            db.session.query(
                Inscription.gara_id,
                Inscription.user_id,
                Inscription.categoria_id,
            )
            .filter(Inscription.gara_id.in_(gara_ids))
            # Dal vincolo `uq_inscription_gara_user` (settembre 2026) la riga
            # è una sola e l'ordinamento non decide più niente. Resta perché su
            # un database non ancora migrato le doppie ci sono ancora, e in quel
            # caso fa vincere l'iscrizione attiva su quella ritirata.
            .order_by(Inscription.is_withdrawn.desc(), Inscription.id.asc())
            .all()
        )
        return {(gara_id, user_id): cat_id for gara_id, user_id, cat_id in rows}

    @staticmethod
    def _categoria_id(
        gara_id: int, user_id: int, index: Optional[CategoriaIndex]
    ) -> Optional[int]:
        if index is not None:
            return index.get((gara_id, user_id))

        from models.competition.models import Inscription

        row = (
            db.session.query(Inscription.categoria_id)
            .filter(
                Inscription.gara_id == gara_id,
                Inscription.user_id == user_id,
            )
            .order_by(Inscription.is_withdrawn.asc(), Inscription.id.desc())
            .first()
        )
        return row[0] if row else None

    @staticmethod
    def exclusion_reason(
        match,
        index: Optional[CategoriaIndex] = None,
        *,
        is_walkover: Optional[bool] = None,
    ) -> Optional[RatingExclusion]:
        """Il motivo per cui questa partita non conta, o ``None`` se conta.

        ``index`` è l'indice di ``build_index`` per i lotti; omesso, le
        categorie si leggono dal DB (due query, irrilevanti sul match singolo).
        ``is_walkover`` permette a chi ha già calcolato i rack di non rifarlo.
        """
        walkover = match.is_walkover if is_walkover is None else is_walkover
        if walkover:
            return RatingExclusion.WALKOVER

        # Fuori dall'handicap la policy non cambia: la partita conta, come
        # prima e come sempre.
        if not match.effective_has_handicap:
            return None

        gara_id = getattr(match, "gara_id", None)
        if gara_id is None:
            # Handicap forzato su una partita senza gara: non esistono
            # iscrizioni, quindi non esiste una categoria da confrontare.
            return RatingExclusion.HANDICAP_CATEGORY_MISSING

        player_ids = RatingEligibility.player_ids(match)
        if len(player_ids) < 2 or any(pid is None for pid in player_ids):
            # Slot vuoto o bye: non c'è un confronto fra due giocatori.
            return RatingExclusion.HANDICAP_CATEGORY_MISSING

        categorie = [
            RatingEligibility._categoria_id(gara_id, pid, index) for pid in player_ids
        ]
        if any(cat is None for cat in categorie):
            # «Non lo so» non è «sono uguali»: senza categoria si conserva il
            # comportamento storico, cioè nessun aggiornamento.
            return RatingExclusion.HANDICAP_CATEGORY_MISSING
        if len(set(categorie)) > 1:
            return RatingExclusion.HANDICAP_DIFFERENT_CATEGORY
        return None

    @staticmethod
    def counts_for_rating(
        match,
        index: Optional[CategoriaIndex] = None,
        *,
        is_walkover: Optional[bool] = None,
    ) -> bool:
        """Questa partita contribuisce ai rating?"""
        return (
            RatingEligibility.exclusion_reason(match, index, is_walkover=is_walkover)
            is None
        )
