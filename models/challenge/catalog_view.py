"""«Oggi» e il catalogo che si filtra: le due viste di sola lettura degli esercizi.

Stessa forma di ``models/exam/overview.py``: la route chiede, qui si interroga e
si compone, il template stampa. Niente query nel markup e niente conti nel
template — la card di prima chiamava ``get_statistics()`` a ogni giro, cioè
caricava **tutte** le prove di ogni esercizio per stampare due numeri.

Quante query, qualunque sia la lunghezza del catalogo: gli esercizi (con
categorie e varianti in ``selectin``), i preferiti, le prove di chi guarda (due,
catalogo e gara, da ``TrainingHistoryService``), e le tre di ``popularity_for``.

**«Oggi» è una porta, non una pagina di statistiche** (D3). Oggi propone ciò che
c'è già — riprendere l'ultimo esercizio, i preferiti, i più provati — e ha
dietro il catalogo. Si riempie da sola con le fasi dopo: la scheda da riprendere
(fase 6), obiettivi e consigli (fase 7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..base import db
from ..status_enum import _StrEnum
from .models import Challenge, ChallengeAttempt, ChallengeFavorite
from .popularity import ChallengePopularity, popularity_for
from .training_service import TrainingHistoryService
from .vocabulary import MAX_LEVEL, MIN_LEVEL, Abilita, Gesto

# Quanti esercizi mostra ciascuna striscia di «Oggi»: abbastanza da scegliere,
# non tanti da diventare un secondo catalogo.
TODAY_STRIP = 4
# Sotto questa soglia «voto alto» non vuol dire niente.
RATING_FLOORS = (4, 3)
RECENT = 3


class CatalogSort(_StrEnum):
    MOST_TRIED = "provati"
    TOP_RATED = "voto"
    NEWEST = "nuovi"

    @classmethod
    def parse(cls, value: object) -> "CatalogSort":
        try:
            return cls(str(value or "").strip().lower())
        except ValueError:
            return cls.MOST_TRIED


class CatalogScope(_StrEnum):
    ALL = "tutti"
    MINE = "miei"
    FAVORITES = "preferiti"

    @classmethod
    def parse(cls, value: object) -> "CatalogScope":
        try:
            return cls(str(value or "").strip().lower())
        except ValueError:
            return cls.ALL


@dataclass(frozen=True)
class CatalogFilter:
    """I filtri del catalogo, già ripuliti. Un valore ignoto vale «nessun filtro»."""

    abilita: Optional[Abilita] = None
    gesto: Optional[Gesto] = None
    level: Optional[int] = None
    min_rating: Optional[int] = None
    sort: CatalogSort = CatalogSort.MOST_TRIED
    scope: CatalogScope = CatalogScope.ALL

    @classmethod
    def from_args(cls, args: Any) -> "CatalogFilter":
        def _int(key: str, allowed: Iterable[int]) -> Optional[int]:
            try:
                valore = int(args.get(key) or "")
            except (TypeError, ValueError):
                return None
            return valore if valore in allowed else None

        return cls(
            abilita=Abilita.normalize(args.get("abilita")),
            gesto=Gesto.normalize(args.get("gesto")),
            level=_int("livello", range(MIN_LEVEL, MAX_LEVEL + 1)),
            min_rating=_int("voto", RATING_FLOORS),
            sort=CatalogSort.parse(args.get("ordine")),
            scope=CatalogScope.parse(args.get("vista")),
        )

    def to_args(self, **changes: Any) -> Dict[str, Any]:
        """La query string di questo filtro, con qualche voce cambiata.

        ``None`` toglie la voce: è così che una pillola accesa, ritoccata, si
        spegne. I default non si scrivono, per non sporcare gli indirizzi.
        """
        valori: Dict[str, Any] = {
            "abilita": self.abilita.value if self.abilita else None,
            "gesto": self.gesto.value if self.gesto else None,
            "livello": self.level,
            "voto": self.min_rating,
            "ordine": None if self.sort == CatalogSort.MOST_TRIED else self.sort.value,
            "vista": None if self.scope == CatalogScope.ALL else self.scope.value,
        }
        valori.update(changes)
        return {k: v for k, v in valori.items() if v not in (None, "")}

    @property
    def is_filtering(self) -> bool:
        return any(
            v is not None
            for v in (self.abilita, self.gesto, self.level, self.min_rating)
        )


@dataclass(frozen=True)
class PlayerLine:
    """Com'è andato chi guarda su un esercizio: la riga in fondo alla card."""

    attempts: int = 0
    best: Optional[int] = None
    passed_count: int = 0
    average_pct: Optional[int] = None
    recent_pct: Optional[int] = None
    last_attempted_at: Any = None

    @property
    def tried(self) -> bool:
        return self.attempts > 0


@dataclass(frozen=True)
class ExerciseCard:
    challenge: Challenge
    popularity: ChallengePopularity
    mine: PlayerLine
    is_favorite: bool = False


@dataclass(frozen=True)
class CatalogView:
    cards: Sequence[ExerciseCard]
    filter: CatalogFilter
    total: int
    abilita_in_use: int
    counts: Dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class TodayView:
    resume: Optional[ExerciseCard]
    favorites: Sequence[ExerciseCard]
    most_tried: Sequence[ExerciseCard]
    total: int

    @property
    def is_empty(self) -> bool:
        return self.total == 0


# ────────────────────────────────────────────────────────────────────────
# Comporre
# ────────────────────────────────────────────────────────────────────────
def _pct(valori: List[int], massimo: Optional[int]) -> Optional[int]:
    if not valori or not massimo:
        return None
    return round(sum(valori) / (len(valori) * massimo) * 100)


def _player_lines(user_id: Optional[int]) -> Dict[int, PlayerLine]:
    """Una riga per esercizio provato, dalle stesse fonti dello storico."""
    if not user_id:
        return {}
    per_esercizio: Dict[int, List[Dict[str, Any]]] = {}
    # Le voci arrivano dalla più recente: l'ordine serve a «ultime tre».
    for entry in TrainingHistoryService.get_drill_attempts(user_id):
        per_esercizio.setdefault(entry["challenge_id"], []).append(entry)

    righe: Dict[int, PlayerLine] = {}
    for challenge_id, entries in per_esercizio.items():
        prima = entries[0]
        punteggi = [e["score"] for e in entries if e["score"] is not None]
        if prima["is_pass_fail"]:
            righe[challenge_id] = PlayerLine(
                attempts=len(entries),
                passed_count=sum(1 for e in entries if e["passed"]),
                last_attempted_at=prima["attempted_at"],
            )
            continue
        righe[challenge_id] = PlayerLine(
            attempts=len(entries),
            best=max(punteggi) if punteggi else None,
            average_pct=_pct(punteggi, prima["max_score"]),
            recent_pct=(
                _pct(punteggi[:RECENT], prima["max_score"])
                if len(punteggi) > RECENT
                else None
            ),
            last_attempted_at=prima["attempted_at"],
        )
    return righe


def _favorite_ids(user_id: Optional[int]) -> set[int]:
    if not user_id:
        return set()
    return {
        riga[0]
        for riga in db.session.query(ChallengeFavorite.challenge_id)
        .filter_by(user_id=user_id)
        .all()
    }


def _cards(
    challenges: Sequence[Challenge], user_id: Optional[int]
) -> List[ExerciseCard]:
    numeri = popularity_for(c.id for c in challenges)
    righe = _player_lines(user_id)
    preferiti = _favorite_ids(user_id)
    return [
        ExerciseCard(
            challenge=c,
            popularity=numeri.get(c.id, ChallengePopularity()),
            mine=righe.get(c.id, PlayerLine()),
            is_favorite=c.id in preferiti,
        )
        for c in challenges
    ]


def _sorted(cards: List[ExerciseCard], sort: CatalogSort) -> List[ExerciseCard]:
    if sort == CatalogSort.TOP_RATED:
        # Chi non ha voti va in fondo, non in cima con uno zero travestito.
        return sorted(
            cards,
            key=lambda c: (
                c.popularity.rating_average is None,
                -(c.popularity.rating_average or 0),
                -c.popularity.rating_count,
                -c.challenge.id,
            ),
        )
    if sort == CatalogSort.NEWEST:
        return sorted(cards, key=lambda c: -c.challenge.id)
    return sorted(cards, key=lambda c: (-c.popularity.players, -c.challenge.id))


def _active() -> List[Challenge]:
    return db.session.query(Challenge).filter_by(is_active=True).all()


def build_catalog(user_id: Optional[int], filtro: CatalogFilter) -> CatalogView:
    """Il catalogo attivo, filtrato e ordinato."""
    tutte = _cards(_active(), user_id)
    counts = {
        CatalogScope.ALL.value: len(tutte),
        CatalogScope.MINE.value: sum(
            1 for c in tutte if user_id and c.challenge.created_by_id == user_id
        ),
        CatalogScope.FAVORITES.value: sum(1 for c in tutte if c.is_favorite),
    }

    def _passa(card: ExerciseCard) -> bool:
        c = card.challenge
        if filtro.scope == CatalogScope.MINE and c.created_by_id != user_id:
            return False
        if filtro.scope == CatalogScope.FAVORITES and not card.is_favorite:
            return False
        if filtro.abilita and filtro.abilita not in c.abilita:
            return False
        if filtro.gesto and filtro.gesto not in c.gesti:
            return False
        if filtro.level and c.declared_level != filtro.level:
            return False
        if (
            filtro.min_rating
            and (card.popularity.rating_average or 0) < filtro.min_rating
        ):
            return False
        return True

    return CatalogView(
        cards=_sorted([c for c in tutte if _passa(c)], filtro.sort),
        filter=filtro,
        total=len(tutte),
        abilita_in_use=len({a for c in tutte for a in c.challenge.abilita}),
        counts=counts,
    )


def build_today(user_id: Optional[int]) -> TodayView:
    """La porta d'ingresso: riprendi l'ultimo, i preferiti, i più provati."""
    tutte = _cards(_active(), user_id)

    provate = [c for c in tutte if c.mine.tried and c.mine.last_attempted_at]
    resume = max(provate, key=lambda c: c.mine.last_attempted_at, default=None)

    preferiti = [c for c in tutte if c.is_favorite and c is not resume]
    gia_mostrati = {id(resume), *(id(c) for c in preferiti[:TODAY_STRIP])}
    piu_provati = [
        c
        for c in _sorted(tutte, CatalogSort.MOST_TRIED)
        if id(c) not in gia_mostrati and c.popularity.players > 0
    ]
    return TodayView(
        resume=resume,
        favorites=preferiti[:TODAY_STRIP],
        most_tried=piu_provati[:TODAY_STRIP],
        total=len(tutte),
    )


# ────────────────────────────────────────────────────────────────────────
# La scheda di un esercizio
# ────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class VariantLine:
    """Com'è andato chi guarda su **una** variante: destra e sinistra separate."""

    label: str
    attempts: int = 0
    best: Optional[int] = None
    passed_count: int = 0
    average_pct: Optional[int] = None


def build_card(challenge: Challenge, user_id: Optional[int]) -> ExerciseCard:
    """La stessa card del catalogo, per un esercizio solo: la usa la scheda."""
    return _cards([challenge], user_id)[0]


def variant_lines(challenge: Challenge, user_id: Optional[int]) -> List[VariantLine]:
    """Una riga per variante, nell'ordine dell'autore. Vuoto senza varianti.

    Il 9 su 10 di destra e il 4 su 10 di sinistra sono la notizia, non la loro
    media: è il motivo per cui le varianti esistono.
    """
    if not user_id or not challenge.has_variants:
        return []
    prove = (
        db.session.query(ChallengeAttempt)
        .filter(
            ChallengeAttempt.challenge_id == challenge.id,
            ChallengeAttempt.user_id == user_id,
            ChallengeAttempt.completed.is_(True),
            ChallengeAttempt.variant_id.isnot(None),
        )
        .all()
    )
    righe: List[VariantLine] = []
    for variante in challenge.variants:
        sue = [p for p in prove if p.variant_id == variante.id]
        punteggi = [p.score for p in sue if p.score is not None]
        if challenge.pass_fail_only:
            righe.append(
                VariantLine(
                    label=variante.label,
                    attempts=len(sue),
                    passed_count=sum(1 for p in sue if p.passed),
                )
            )
        else:
            righe.append(
                VariantLine(
                    label=variante.label,
                    attempts=len(sue),
                    best=max(punteggi) if punteggi else None,
                    average_pct=_pct(punteggi, challenge.max_score),
                )
            )
    return righe
