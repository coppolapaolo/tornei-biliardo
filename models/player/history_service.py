"""
Module: models/player/history_service.py
Purpose: Service for querying player match/gara/campionato history with filters
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, List, Tuple, Any, Dict

from flask_sqlalchemy.pagination import Pagination
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import joinedload, selectinload

from models.base import db
from models.match.models import Match, TrioMatch
from models.competition.models import Gara, Inscription
from models.campionato.models import Campionato
from models.user.models import User
from models.status_enum import MatchStatus, GaraStatus, Discipline


@dataclass
class HistoryFilters:
    """Filter parameters for history queries."""

    discipline: Optional[str] = None  # Discipline enum value (e.g., '8_ball')
    venue: Optional[str] = None  # Location string (partial match)
    opponent_id: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    result: Optional[str] = None  # 'won', 'lost', or None for all
    campionato_id: Optional[int] = None
    gara_id: Optional[int] = None
    completed_only: bool = True  # For gare: show only completed
    campionato_status: Optional[str] = None  # 'active' | 'completed' | None=all
    #: Da dove nasce la partita: 'campionato' | 'gara' | 'individuale'.
    #: `None` = tutte. Non è deducibile da `campionato_id`/`gara_id`, che
    #: selezionano UNA competizione: qui si sceglie il *tipo* di provenienza.
    context: Optional[str] = None

    @classmethod
    def from_request(cls, request_args: Any) -> "HistoryFilters":
        """Create filters from Flask request args."""
        return cls(
            discipline=request_args.get("discipline") or None,
            venue=request_args.get("venue") or None,
            opponent_id=request_args.get("opponent_id", type=int),
            date_from=cls._parse_date(request_args.get("date_from")),
            date_to=cls._parse_date(request_args.get("date_to")),
            result=request_args.get("result") or None,
            campionato_id=request_args.get("campionato_id", type=int),
            gara_id=request_args.get("gara_id", type=int),
            completed_only=request_args.get("completed_only", "true").lower() == "true",
            campionato_status=request_args.get("campionato_status") or None,
            context=request_args.get("context") or None,
        )

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[date]:
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None


@dataclass
class MatchStats:
    """Aggregated statistics for filtered match history."""

    total_matches: int
    won_matches: int
    lost_matches: int
    win_percentage: float
    total_racks_won: int
    total_racks_lost: int
    #: Quante partite per provenienza — {'campionato': n, 'gara': n,
    #: 'individuale': n}. È la torta, e si conta qui: un template che conta può
    #: contare diversamente dalla riga sopra.
    by_context: Dict[str, int] = field(default_factory=dict)


@dataclass
class MatchEntry:
    """Una partita giocata, comunque sia nata.

    Le partite di torneo e le sfide individuali stanno su due tabelle con
    colonne diverse. Restano due tabelle — non è questo il posto per unificarle
    — ma escono dal servizio con **questa** forma, così chi le mostra non deve
    più sapere da dove vengono.

    ``source`` e ``match_id`` bastano al template per costruire il link giusto:
    l'URL non si compone qui, perché un servizio che chiama ``url_for`` smette
    di funzionare fuori da una richiesta (script, migration, test unitari).
    """

    source: str  # 'tournament' | 'individual'
    match_id: int
    context: str  # 'campionato' | 'gara' | 'individuale'
    played_on: Optional[date]
    opponents: List[str]
    my_score: Optional[int]
    opponent_score: Optional[int]
    outcome: str  # 'won' | 'lost' | 'tie'
    discipline: Optional[str]
    venue: Optional[str]
    competition: Optional[str]
    is_trio: bool = False
    #: Gara e campionato di provenienza, quando ci sono. Non servono a
    #: mostrare la riga — `competition` è già il testo — ma a chi deve
    #: decidere se **nasconderla**: il proprietario di un profilo può nascondere
    #: una partita o un campionato intero, e senza questi due la voce non si
    #: riconosce più una volta uscita dall'ORM.
    gara_id: Optional[int] = None
    campionato_id: Optional[int] = None


class ListPagination:
    """La paginazione di una lista già in memoria.

    Espone gli stessi attributi della ``Pagination`` di Flask-SQLAlchemy —
    ``items``, ``page``, ``pages``, ``total``, ``has_prev``/``has_next``,
    ``prev_num``/``next_num``, ``iter_pages()`` — così il componente di
    paginazione dello storico funziona senza sapere che sotto non c'è una
    query. Reimplementarne uno apposta avrebbe voluto dire due paginazioni da
    tenere allineate.
    """

    def __init__(self, items: List[Any], page: int = 1, per_page: int = 20):
        self.total = len(items)
        self.per_page = max(1, per_page)
        self.pages = max(1, (self.total + self.per_page - 1) // self.per_page)
        self.page = min(max(1, page), self.pages)
        inizio = (self.page - 1) * self.per_page
        self.items = items[inizio : inizio + self.per_page]

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def prev_num(self) -> int:
        return self.page - 1

    @property
    def next_num(self) -> int:
        return self.page + 1

    def iter_pages(
        self,
        left_edge: int = 1,
        left_current: int = 2,
        right_current: int = 2,
        right_edge: int = 1,
    ):
        """Stessa semantica di Flask-SQLAlchemy: ``None`` dove va il «…»."""
        ultimo = 0
        for numero in range(1, self.pages + 1):
            vicino = (
                numero <= left_edge
                or (
                    numero > self.page - left_current - 1
                    and numero < self.page + right_current
                )
                or numero > self.pages - right_edge
            )
            if not vicino:
                continue
            if ultimo + 1 != numero:
                yield None
            yield numero
            ultimo = numero


@dataclass
class GaraStats:
    """Aggregated statistics for filtered gara history."""

    total_gare: int
    first_places: int  # Times finished 1st
    podiums: int  # Times finished 1st, 2nd, or 3rd
    total_matches_played: int


class PlayerHistoryService:
    """Service for querying player match/gara/campionato history with filters."""

    # =========================================================================
    # PARTITE (Matches)
    # =========================================================================

    @staticmethod
    def get_match_history(
        user_id: int,
        filters: HistoryFilters,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[Pagination, MatchStats]:
        """Get paginated match history with filters.

        Returns:
            Tuple of (pagination object, aggregated stats for filtered matches)
        """
        # Calculate stats BEFORE pagination (on filtered results)
        query = PlayerHistoryService._build_match_history_query(user_id, filters)
        stats = PlayerHistoryService._calculate_match_stats(query.all(), user_id)

        # Re-run query for pagination (SQLAlchemy pagination needs fresh query)
        query = PlayerHistoryService._build_match_history_query(user_id, filters)
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination, stats

    @staticmethod
    def _build_match_history_query(user_id: int, filters: HistoryFilters) -> Any:
        """Build the filtered+ordered query for completed matches of a user.

        Use outerjoin for Gara to include standalone matches (gara_id = NULL);
        outerjoin TrioMatch too: trio matches have user as one of the 3 players.
        """
        query = (
            db.session.query(Match)
            .outerjoin(Gara, Gara.id == Match.gara_id)
            .outerjoin(Campionato, Campionato.id == Gara.campionato_id)
            .outerjoin(TrioMatch, Match.id == TrioMatch.match_id)
            .filter(
                # Entrambi gli stati finali, non solo la chiusura del
                # direttore: `CONFIRMED_BY_BOTH` è la partita chiusa **dai due
                # giocatori** con doppia conferma, ed è a tutti gli effetti
                # giocata. Filtrando il solo `CLOSED_UNILATERALLY` lo storico
                # era monco proprio per chi gioca dove i risultati se li
                # confermano fra loro — e mancavano righe, non c'era un errore.
                Match.status.in_(MatchStatus.finished_values()),
                Match.is_bye == False,  # noqa: E712
                or_(
                    # Regular matches (not trio)
                    and_(
                        Match.is_trio == False,  # noqa: E712
                        or_(
                            Match.player1_id == user_id,
                            Match.player2_id == user_id,
                        ),
                    ),
                    # Trio matches - check all 3 player positions
                    and_(
                        Match.is_trio == True,  # noqa: E712
                        or_(
                            TrioMatch.player1_id == user_id,
                            TrioMatch.player2_id == user_id,
                            TrioMatch.player3_id == user_id,
                        ),
                    ),
                ),
            )
            .options(
                joinedload(Match.player1),
                joinedload(Match.player2),
                joinedload(Match.gara).joinedload(Gara.campionato),
                joinedload(Match.trio_match),
                # I match multi-set leggono i rack reali dai Set (vedi
                # _calculate_match_stats): pre-carica la collection per
                # evitare un lazy-load N+1 per ogni match.
                selectinload(Match.sets),
            )
        )
        query = PlayerHistoryService._apply_match_filters(query, user_id, filters)
        return query.order_by(Gara.date.desc().nullslast(), Match.created_at.desc())

    @staticmethod
    def _apply_match_filters(query: Any, user_id: int, filters: HistoryFilters) -> Any:
        """Apply filter conditions to match query."""

        # Discipline filter (check both match override and gara discipline)
        if filters.discipline:
            query = query.filter(
                or_(
                    Match.discipline == filters.discipline,
                    and_(
                        Match.discipline.is_(None),
                        Gara.discipline == filters.discipline,
                    ),
                )
            )

        # Venue filter (partial match on location)
        if filters.venue:
            query = query.filter(Gara.location.ilike(f"%{filters.venue}%"))

        # Opponent filter. Nei trio l'avversario puo' comparire solo su
        # TrioMatch.player1/2/3_id (Match.player1/2_id tengono 2 dei 3
        # giocatori): la query base garantisce gia' che user_id partecipi,
        # qui basta verificare la presenza dell'avversario nel trio.
        if filters.opponent_id:
            query = query.filter(
                or_(
                    and_(
                        Match.is_trio == False,  # noqa: E712
                        or_(
                            and_(
                                Match.player1_id == user_id,
                                Match.player2_id == filters.opponent_id,
                            ),
                            and_(
                                Match.player2_id == user_id,
                                Match.player1_id == filters.opponent_id,
                            ),
                        ),
                    ),
                    and_(
                        Match.is_trio == True,  # noqa: E712
                        or_(
                            TrioMatch.player1_id == filters.opponent_id,
                            TrioMatch.player2_id == filters.opponent_id,
                            TrioMatch.player3_id == filters.opponent_id,
                        ),
                    ),
                )
            )

        # Date range filter. I match standalone hanno gara_id NULL → Gara.date
        # NULL (outerjoin): `NULL >= date` e' NULL/falsy e li escluderebbe da
        # qualsiasi filtro data. Fallback su Match.created_at per quelli.
        if filters.date_from:
            query = query.filter(
                or_(
                    Gara.date >= filters.date_from,
                    and_(
                        Gara.date.is_(None),
                        func.date(Match.created_at) >= filters.date_from,
                    ),
                )
            )
        if filters.date_to:
            query = query.filter(
                or_(
                    Gara.date <= filters.date_to,
                    and_(
                        Gara.date.is_(None),
                        func.date(Match.created_at) <= filters.date_to,
                    ),
                )
            )

        # Result filter
        if filters.result == "won":
            query = query.filter(Match.winner_id == user_id)
        elif filters.result == "lost":
            query = query.filter(
                Match.winner_id.isnot(None), Match.winner_id != user_id
            )

        # Campionato filter
        if filters.campionato_id:
            query = query.filter(Gara.campionato_id == filters.campionato_id)

        # Gara filter
        if filters.gara_id:
            query = query.filter(Match.gara_id == filters.gara_id)

        return query

    @staticmethod
    def _calculate_match_stats(matches: List[Match], user_id: int) -> MatchStats:
        """Calculate aggregated stats for filtered matches.

        Handles both regular 2-player matches and trio matches.
        For trio matches, 'lost' only counts if someone else won (not ties).
        """
        total = len(matches)
        won = sum(1 for m in matches if m.winner_id == user_id)
        # For losses: count matches where someone else won (not ties, not wins)
        lost = sum(
            1 for m in matches if m.winner_id is not None and m.winner_id != user_id
        )

        racks_won = 0
        racks_lost = 0
        for m in matches:
            if m.is_trio and m.trio_match:
                from models.match.trio_config import trio_racks_lost

                trio = m.trio_match
                # ADR-027: rispetta gli override per turno via effective_distance.
                distance = m.effective_distance
                if trio.player1_id == user_id:
                    player_r = trio.player1_racks or 0
                elif trio.player2_id == user_id:
                    player_r = trio.player2_racks or 0
                elif trio.player3_id == user_id:
                    player_r = trio.player3_racks or 0
                else:
                    player_r = 0
                racks_won += player_r
                racks_lost += trio_racks_lost(player_r, distance)
            elif m.is_multi_set:
                # Multi-set: player*_score sono i SET vinti, non i rack. I rack
                # reali vivono nei record Set: sommali per non inquinare i
                # totali rack con conteggi di set.
                for s in m.sets:
                    if m.player1_id == user_id:
                        racks_won += s.player1_racks or 0
                        racks_lost += s.player2_racks or 0
                    else:
                        racks_won += s.player2_racks or 0
                        racks_lost += s.player1_racks or 0
            else:
                # Regular single-set match: player*_score sono i rack.
                if m.player1_id == user_id:
                    racks_won += m.player1_score or 0
                    racks_lost += m.player2_score or 0
                else:
                    racks_won += m.player2_score or 0
                    racks_lost += m.player1_score or 0

        return MatchStats(
            total_matches=total,
            won_matches=won,
            lost_matches=lost,
            win_percentage=round((won / total * 100) if total else 0, 1),
            total_racks_won=racks_won,
            total_racks_lost=racks_lost,
        )

    # =========================================================================
    # PARTITE, tutte insieme (torneo + sfide individuali)
    # =========================================================================

    @staticmethod
    def get_unified_match_history(
        user_id: int,
        filters: HistoryFilters,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple["ListPagination", MatchStats]:
        """Lo storico delle partite, da qualunque parte siano nate.

        **Perché non una query sola.** Le partite di torneo stanno su ``match``,
        le sfide individuali su ``individual_match``: due tabelle con colonne
        diverse, e non è questo il posto per unificarle. Escono di qui con la
        **stessa forma** — come fa ``TrainingHistoryService`` per i due tipi di
        prova — e chi le mostra non deve più sapere da dove vengono.

        Prima la scheda «Partite» interrogava solo ``match``: le sfide
        individuali non comparivano in nessuno storico, e nessuno lo segnalava
        perché la pagina funzionava — mostrava semplicemente meno partite di
        quelle giocate.

        **La paginazione è in memoria**, ed è una scelta: unire due sorgenti
        ordinate per data in SQL vorrebbe dire una UNION fra schemi diversi,
        con i filtri scritti due volte. Lo storico di un giocatore è nell'ordine
        delle centinaia di righe, non dei milioni.
        """
        voci = PlayerHistoryService._tournament_entries(user_id, filters)
        voci += PlayerHistoryService._individual_entries(user_id, filters)

        if filters.context:
            voci = [v for v in voci if v.context == filters.context]

        # `played_on` può mancare (una gara senza data): le righe senza data
        # vanno in fondo invece che in cima, dove un `None` ordinato come minimo
        # le manderebbe.
        voci.sort(key=lambda v: (v.played_on is not None, v.played_on), reverse=True)

        stats = PlayerHistoryService._stats_from_entries(voci)
        return ListPagination(voci, page=page, per_page=per_page), stats

    @staticmethod
    def _tournament_entries(
        user_id: int, filters: HistoryFilters
    ) -> List["MatchEntry"]:
        """Le partite di gara, nella forma comune."""
        query = PlayerHistoryService._build_match_history_query(user_id, filters)
        voci: List[MatchEntry] = []
        for match in query.all():
            gara = match.gara
            campionato = gara.campionato if gara else None
            if campionato is not None:
                context = "campionato"
                competition = f"{campionato.name} · {gara.display_name}"
            elif gara is not None:
                context = "gara"
                competition = gara.display_name
            else:
                # Un match senza gara è una partita sciolta: nasce da una gara
                # cancellata (i suoi match «diventano sfide individuali») o da
                # un vecchio dato. Non è una sfida individuale vera — quelle
                # stanno nell'altra tabella — ma per chi legge è la stessa cosa.
                context = "individuale"
                competition = None

            voci.append(
                MatchEntry(
                    source="tournament",
                    match_id=match.id,
                    context=context,
                    played_on=(gara.date if gara and gara.date else None)
                    or (match.created_at.date() if match.created_at else None),
                    opponents=PlayerHistoryService._opponents_of(match, user_id),
                    my_score=PlayerHistoryService._score_of(match, user_id),
                    opponent_score=PlayerHistoryService._score_of(
                        match, user_id, opponent=True
                    ),
                    outcome=PlayerHistoryService._outcome_of(match.winner_id, user_id),
                    discipline=match.discipline or (gara.discipline if gara else None),
                    venue=(gara.location if gara else None),
                    competition=competition,
                    is_trio=bool(match.is_trio),
                    gara_id=gara.id if gara else None,
                    campionato_id=campionato.id if campionato else None,
                )
            )
        return voci

    @staticmethod
    def _individual_entries(
        user_id: int, filters: HistoryFilters
    ) -> List["MatchEntry"]:
        """Le sfide individuali, nella stessa forma.

        I filtri si riapplicano qui a mano invece di riusare
        ``_apply_match_filters``: quello parla di ``Match`` e di ``Gara``, che
        una sfida individuale non ha. Riusarlo avrebbe voluto dire piegare la
        query a colonne inesistenti.
        """
        from models.individual_match.match_models import IndividualMatch

        query = (
            db.session.query(IndividualMatch)
            .options(
                joinedload(IndividualMatch.player1),
                joinedload(IndividualMatch.player2),
            )
            .filter(
                IndividualMatch.status.in_(MatchStatus.finished_values()),
                or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                ),
            )
        )

        if filters.discipline:
            query = query.filter(IndividualMatch.discipline == filters.discipline)
        if filters.venue:
            query = query.filter(IndividualMatch.location.ilike(f"%{filters.venue}%"))
        if filters.opponent_id:
            query = query.filter(
                or_(
                    and_(
                        IndividualMatch.player1_id == user_id,
                        IndividualMatch.player2_id == filters.opponent_id,
                    ),
                    and_(
                        IndividualMatch.player2_id == user_id,
                        IndividualMatch.player1_id == filters.opponent_id,
                    ),
                )
            )
        if filters.result == "won":
            query = query.filter(IndividualMatch.winner_id == user_id)
        elif filters.result == "lost":
            query = query.filter(
                IndividualMatch.winner_id.isnot(None),
                IndividualMatch.winner_id != user_id,
            )
        # Una sfida individuale non appartiene mai a una gara o a un campionato:
        # se il filtro ne chiede uno, qui non c'è niente da restituire.
        if filters.campionato_id or filters.gara_id:
            return []

        voci: List[MatchEntry] = []
        for im in query.all():
            quando = im.ended_at or im.scheduled_at
            giorno = quando.date() if quando else None
            if filters.date_from and (giorno is None or giorno < filters.date_from):
                continue
            if filters.date_to and (giorno is None or giorno > filters.date_to):
                continue

            sono_p1 = im.player1_id == user_id
            avversario = im.player2 if sono_p1 else im.player1
            voci.append(
                MatchEntry(
                    source="individual",
                    match_id=im.id,
                    context="individuale",
                    played_on=giorno,
                    opponents=[avversario.username] if avversario else [],
                    my_score=(im.player1_score if sono_p1 else im.player2_score),
                    opponent_score=(im.player2_score if sono_p1 else im.player1_score),
                    outcome=PlayerHistoryService._outcome_of(im.winner_id, user_id),
                    discipline=im.discipline,
                    venue=im.location,
                    competition=None,
                    is_trio=False,
                )
            )
        return voci

    # ------------------------------------------------------------- helper

    @staticmethod
    def _outcome_of(winner_id: Optional[int], user_id: int) -> str:
        """Vinta, persa o pari. Il pari esiste: nei trio nessuno vince."""
        if winner_id is None:
            return "tie"
        return "won" if winner_id == user_id else "lost"

    @staticmethod
    def _opponents_of(match: Match, user_id: int) -> List[str]:
        """Chi c'era dall'altra parte: uno, o due in un trio."""
        if match.is_trio and match.trio_match:
            trio = match.trio_match
            altri = []
            for giocatore in (trio.player1, trio.player2, trio.player3):
                if giocatore is not None and giocatore.id != user_id:
                    altri.append(giocatore.username)
            return altri
        avversario = match.player2 if match.player1_id == user_id else match.player1
        return [avversario.username] if avversario else []

    @staticmethod
    def _score_of(match: Match, user_id: int, opponent: bool = False) -> Optional[int]:
        """Il punteggio come lo legge chi guarda, non come sta a DB.

        Nei trio il punteggio è sul ``TrioMatch``; nei multi-set
        ``player*_score`` sono i **set** vinti, non i triangoli — e sono quelli
        che vanno mostrati accanto al nome, perché è il risultato della partita.
        """
        if match.is_trio and match.trio_match:
            trio = match.trio_match
            if opponent:
                return None  # in un trio non c'è "il punteggio dell'altro"
            for pid, racks in (
                (trio.player1_id, trio.player1_racks),
                (trio.player2_id, trio.player2_racks),
                (trio.player3_id, trio.player3_racks),
            ):
                if pid == user_id:
                    return racks or 0
            return 0
        sono_p1 = match.player1_id == user_id
        if opponent:
            sono_p1 = not sono_p1
        return match.player1_score if sono_p1 else match.player2_score

    @staticmethod
    def stats_of(voci: List["MatchEntry"]) -> MatchStats:
        """Gli aggregati di un elenco di voci già in mano al chiamante.

        Serve a chi le voci le ha dovute filtrare per conto suo — il profilo
        pubblico, che toglie le partite nascoste — e non può quindi riusare le
        statistiche calcolate su tutto. Conta lo stesso codice, così le due
        schermate non possono divergere.
        """
        return PlayerHistoryService._stats_from_entries(voci)

    @staticmethod
    def filter_visible_entries(
        user_id: int,
        viewer_id: Optional[int],
        entries: List["MatchEntry"],
        is_admin: bool = False,
    ) -> List["MatchEntry"]:
        """Le voci che il visitatore può vedere sul profilo di qualcun altro.

        Calco di ``PrivacyService.filter_visible_matches``, ma sulle voci
        unificate. **Gli id nascosti riguardano le partite di gara**: una sfida
        individuale non si può ancora nascondere, e gli id delle due tabelle si
        sovrappongono — filtrare senza guardare la provenienza nasconderebbe una
        sfida a caso, quella con lo stesso numero di una partita nascosta.
        """
        if is_admin or (viewer_id is not None and viewer_id == user_id):
            return list(entries)

        from models.user.privacy_service import PrivacyService

        nascosti = PrivacyService.get_hidden_ids(user_id)
        partite_nascoste = nascosti["matches"]
        campionati_nascosti = nascosti["campionati"]

        visibili: List[MatchEntry] = []
        for voce in entries:
            if voce.source == "tournament":
                if voce.match_id in partite_nascoste:
                    continue
                if (
                    voce.campionato_id is not None
                    and voce.campionato_id in campionati_nascosti
                ):
                    continue
            visibili.append(voce)
        return visibili

    @staticmethod
    def _stats_from_entries(voci: List["MatchEntry"]) -> MatchStats:
        """Gli aggregati sulle partite **filtrate**, comprese le fette.

        Le fette servono alla torta, e si contano qui e non nel template: un
        template che conta è un template che può contare diversamente dalla
        riga sopra.
        """
        totale = len(voci)
        vinte = sum(1 for v in voci if v.outcome == "won")
        perse = sum(1 for v in voci if v.outcome == "lost")
        vinti = sum(v.my_score or 0 for v in voci)
        persi = sum(v.opponent_score or 0 for v in voci)

        per_contesto = {"campionato": 0, "gara": 0, "individuale": 0}
        for v in voci:
            per_contesto[v.context] = per_contesto.get(v.context, 0) + 1

        return MatchStats(
            total_matches=totale,
            won_matches=vinte,
            lost_matches=perse,
            win_percentage=round((vinte / totale * 100) if totale else 0, 1),
            total_racks_won=vinti,
            total_racks_lost=persi,
            by_context=per_contesto,
        )

    # =========================================================================
    # DISEGNI (torta e andamento)
    # =========================================================================

    #: Colore e nome di ogni provenienza. Uno solo: se la legenda e la
    #: pastiglia si scrivessero in due posti, divergerebbero al primo ritocco.
    CONTEXT_STYLE = {
        "campionato": ("accent", "Campionato"),
        "gara": ("ok", "Gara"),
        "individuale": ("muted", "Individuali"),
    }

    @staticmethod
    def context_donut(stats: MatchStats) -> Optional[Dict[str, Any]]:
        """La torta delle partite filtrate, per provenienza.

        ``None`` quando non c'è niente da disegnare: una torta vuota è un
        cerchio grigio che sembra un errore di caricamento.
        """
        fette = [
            {
                "label": etichetta,
                "count": stats.by_context.get(chiave, 0),
                "color_role": colore,
            }
            for chiave, (colore, etichetta) in (
                PlayerHistoryService.CONTEXT_STYLE.items()
            )
            if stats.by_context.get(chiave, 0) > 0
        ]
        if not fette:
            return None
        return PlayerHistoryService._donut(fette, str(stats.total_matches))

    @staticmethod
    def _donut(slices: List[Dict[str, Any]], center: str) -> Dict[str, Any]:
        """Gli stop cumulati del `conic-gradient`.

        Stessa forma e stessa palette del riquadro di feedback della dashboard
        (``models/dashboard/activity_feedback.py``): due torte nella stessa app
        non devono sembrare di due app diverse.
        """
        totale = sum(s["count"] for s in slices) or 1
        palette = {
            "ok": "var(--c7-ok)",
            "muted": "#C9CFCE",
            "err": "var(--c7-err)",
            "accent": "var(--c7-accent)",
        }
        stop = []
        corrente = 0.0
        for fetta in slices:
            inizio = corrente
            corrente += fetta["count"] / totale * 100
            stop.append(f"{palette[fetta['color_role']]} {inizio:.4g}% {corrente:.4g}%")
        return {
            "slices": slices,
            "center": center,
            "gradient": "conic-gradient(" + ", ".join(stop) + ")",
        }

    @staticmethod
    def trend_chart(punti: List[Dict[str, Any]], max_score: Optional[int] = None):
        """L'andamento come spezzata, in coordinate già pronte per l'SVG.

        Il viewBox è 0..100 in larghezza e 0..40 in altezza, e la Y è
        rovesciata perché nell'SVG cresce verso il basso: un punteggio alto
        deve stare in alto.

        Il fondoscala è il massimo dell'esercizio quando c'è, altrimenti il
        miglior punteggio del periodo. Non è un dettaglio: senza tetto
        dichiarato, una serie 3-4-5 e una 30-40-50 disegnerebbero la stessa
        identica linea, e il grafico direbbe che sono andate uguale.

        ``None`` sotto i due punti: una spezzata di un punto solo non è un
        andamento, è un punto.
        """
        if len(punti) < 2:
            return None

        valori = [p["score"] for p in punti]
        fondo = max_score or max(valori) or 1
        passo = 100 / (len(valori) - 1)

        def _y(valore: int) -> float:
            quota = min(max(valore / fondo, 0), 1)
            return round(40 - quota * 36 - 2, 2)

        coordinate = [
            (round(indice * passo, 2), _y(valore))
            for indice, valore in enumerate(valori)
        ]
        # I punti si disegnano in **HTML**, non nell'SVG: il viewBox è stirato
        # (`preserveAspectRatio="none"`) perché la spezzata deve riempire la
        # larghezza, e lo stiramento deforma anche la geometria — un
        # `<circle>` diventa un'ellisse schiacciata. `vector-effect` salva lo
        # spessore del tratto, non la forma. Le percentuali qui sotto servono a
        # posizionarli sopra il disegno, dove restano tondi.
        return {
            "polyline": " ".join(f"{x},{y}" for x, y in coordinate),
            "points": [
                {
                    "x": x,
                    "y": y,
                    "x_pct": x,
                    "y_pct": round(y / 40 * 100, 2),
                    "score": valore,
                }
                for (x, y), valore in zip(coordinate, valori)
            ],
            "max": fondo,
            "best": max(valori),
            "first": valori[0],
            "last": valori[-1],
            "delta": valori[-1] - valori[0],
        }

    # =========================================================================
    # ESERCIZI
    # =========================================================================

    @staticmethod
    def get_drill_history(
        user_id: int,
        filters: HistoryFilters,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple["ListPagination", Dict[str, Any]]:
        """Le prove di esercizio, dal catalogo e dalle gare.

        La fonte è ``TrainingHistoryService``, che già unisce le due tabelle
        nella stessa forma: qui si aggiungono solo il filtro per data e gli
        aggregati. Duplicare la lettura avrebbe rimesso in piedi la divergenza
        che quel servizio esiste per impedire.
        """
        from models.challenge.training_service import TrainingHistoryService

        voci = TrainingHistoryService.get_drill_attempts(user_id)

        if filters.date_from or filters.date_to:
            filtrate = []
            for voce in voci:
                quando = voce.get("attempted_at")
                giorno = quando.date() if quando else None
                if filters.date_from and (giorno is None or giorno < filters.date_from):
                    continue
                if filters.date_to and (giorno is None or giorno > filters.date_to):
                    continue
                filtrate.append(voce)
            voci = filtrate

        totali = len(voci)
        a_punteggio = [v for v in voci if not v["is_pass_fail"]]
        riuscita_o_no = [v for v in voci if v["is_pass_fail"]]
        superate = sum(1 for v in riuscita_o_no if v["passed"])

        stats = {
            "total": totali,
            "scored": len(a_punteggio),
            "pass_fail": len(riuscita_o_no),
            "passed": superate,
            "failed": len(riuscita_o_no) - superate,
            "distinct": len({v["challenge_id"] for v in voci}),
            "best_score": (
                max((v["score"] or 0) for v in a_punteggio) if a_punteggio else None
            ),
        }
        return ListPagination(voci, page=page, per_page=per_page), stats

    @staticmethod
    def get_drill_trend(
        user_id: int, challenge_id: int, filters: HistoryFilters
    ) -> List[Dict[str, Any]]:
        """L'andamento su UN esercizio a punteggio, nel periodo filtrato.

        In ordine cronologico — dalla più vecchia alla più recente — perché un
        andamento si legge da sinistra a destra. L'elenco dello storico va nel
        verso opposto, e questa è l'unica ragione per cui i due ordini
        divergono.

        Lista vuota se l'esercizio è superato/non superato: lì non c'è un
        andamento da disegnare, c'è una percentuale — e mostrarla come una
        linea che salta fra 0 e 1 direbbe una cosa che non significa niente.
        """
        from models.challenge.training_service import TrainingHistoryService

        punti = []
        for voce in TrainingHistoryService.get_drill_attempts(user_id):
            if voce["challenge_id"] != challenge_id or voce["is_pass_fail"]:
                continue
            quando = voce.get("attempted_at")
            giorno = quando.date() if quando else None
            if filters.date_from and (giorno is None or giorno < filters.date_from):
                continue
            if filters.date_to and (giorno is None or giorno > filters.date_to):
                continue
            punti.append(
                {
                    "score": voce["score"] or 0,
                    "attempted_at": quando,
                    "day": giorno,
                }
            )
        punti.sort(key=lambda p: (p["attempted_at"] is not None, p["attempted_at"]))
        return punti

    # =========================================================================
    # ESAMI
    # =========================================================================

    @staticmethod
    def get_exam_history(
        user_id: int,
        filters: HistoryFilters,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple["ListPagination", Dict[str, Any]]:
        """Gli esami sostenuti e conclusi.

        Sola lettura, e non è una dimenticanza: un esame certificato lo chiude
        un esaminatore davanti al candidato (ADR-042). Lasciarlo cancellare a
        chi l'ha sostenuto significherebbe lasciargli cancellare il giudizio di
        un altro.
        """
        from models.exam.models import ExamAttempt
        from models.status_enum import ExamAttemptMode, ExamAttemptStatus

        query = (
            db.session.query(ExamAttempt)
            .options(
                joinedload(ExamAttempt.exam),
                joinedload(ExamAttempt.examiner),
            )
            .filter(
                ExamAttempt.user_id == user_id,
                ExamAttempt.status == ExamAttemptStatus.COMPLETED.value,
            )
        )
        if filters.date_from:
            query = query.filter(
                func.date(ExamAttempt.completed_at) >= filters.date_from
            )
        if filters.date_to:
            query = query.filter(func.date(ExamAttempt.completed_at) <= filters.date_to)

        tentativi = query.order_by(ExamAttempt.completed_at.desc()).all()

        certificati = [
            a for a in tentativi if a.mode == ExamAttemptMode.CERTIFIED.value
        ]
        stats = {
            "total": len(tentativi),
            "certified": len(certificati),
            "passed": sum(1 for a in tentativi if a.passed),
            "certified_passed": sum(1 for a in certificati if a.passed),
        }
        return ListPagination(tentativi, page=page, per_page=per_page), stats

    # =========================================================================
    # GARE (Competitions)
    # =========================================================================

    @staticmethod
    def get_gara_history(
        user_id: int,
        filters: HistoryFilters,
        page: int = 1,
        per_page: int = 20,
    ) -> Tuple[Pagination, GaraStats]:
        """Get paginated gara history with filters.

        Returns gare where user had an inscription (active or completed).
        """

        # Subquery for user's inscriptions
        inscribed_gara_ids = (
            db.session.query(Inscription.gara_id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,  # noqa: E712
            )
            .scalar_subquery()
        )

        # Base query
        query = (
            db.session.query(Gara)
            .outerjoin(Campionato, Campionato.id == Gara.campionato_id)
            .filter(Gara.id.in_(inscribed_gara_ids))
            .options(
                joinedload(Gara.campionato),
                joinedload(Gara.round_classifications),
            )
        )

        # Filter by status
        if filters.completed_only:
            query = query.filter(Gara.status == GaraStatus.COMPLETED.value)

        # Apply other filters
        query = PlayerHistoryService._apply_gara_filters(query, filters)

        # Order by date descending
        query = query.order_by(Gara.date.desc().nullslast(), Gara.id.desc())

        # Calculate stats
        all_gare = query.all()
        stats = PlayerHistoryService._calculate_gara_stats(all_gare, user_id)

        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination, stats

    @staticmethod
    def _apply_gara_filters(query: Any, filters: HistoryFilters) -> Any:
        """Apply filter conditions to gara query."""

        # Discipline filter
        if filters.discipline:
            query = query.filter(Gara.discipline == filters.discipline)

        # Venue filter
        if filters.venue:
            query = query.filter(Gara.location.ilike(f"%{filters.venue}%"))

        # Date range filter
        if filters.date_from:
            query = query.filter(Gara.date >= filters.date_from)
        if filters.date_to:
            query = query.filter(Gara.date <= filters.date_to)

        # Campionato filter
        if filters.campionato_id:
            query = query.filter(Gara.campionato_id == filters.campionato_id)

        return query

    @staticmethod
    def _calculate_gara_stats(gare: List[Gara], user_id: int) -> GaraStats:
        """Calculate aggregated stats for gare history."""
        total = len(gare)
        first_places = 0
        podiums = 0
        total_matches = 0

        for gara in gare:
            # Usa la relationship gia' eager-loaded in get_gara_history
            # (joinedload(Gara.round_classifications)) invece di una query
            # RoundClassification per gara (N+1): la classifica finale del
            # giocatore e' la sua riga al round corrente.
            final_classification = next(
                (
                    rc
                    for rc in gara.round_classifications
                    if rc.user_id == user_id and rc.round_number == gara.current_round
                ),
                None,
            )

            if final_classification:
                if final_classification.position == 1:
                    first_places += 1
                if final_classification.position <= 3:
                    podiums += 1
                total_matches += final_classification.matches_won

        return GaraStats(
            total_gare=total,
            first_places=first_places,
            podiums=podiums,
            total_matches_played=total_matches,
        )

    # =========================================================================
    # CAMPIONATI
    # =========================================================================

    @staticmethod
    def get_campionato_history(
        user_id: int,
        page: int = 1,
        per_page: int = 20,
        filters: Optional["HistoryFilters"] = None,
    ) -> Pagination:
        """Get paginated campionato history.

        Returns campionati where user participated in at least one gara.
        Supports optional status filter ('active' | 'completed' | None=all).
        """
        # Subquery for gare where user inscribed
        inscribed_gara_ids = (
            db.session.query(Inscription.gara_id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,  # noqa: E712
            )
            .subquery()
        )

        # Campionati that have gare where user inscribed
        campionato_ids_with_participation = (
            db.session.query(Gara.campionato_id)
            .filter(
                Gara.id.in_(inscribed_gara_ids),
                Gara.campionato_id.isnot(None),
            )
            .distinct()
            .subquery()
        )

        # Query campionati
        query = db.session.query(Campionato).filter(
            Campionato.id.in_(campionato_ids_with_participation),
            Campionato.is_deleted == False,  # noqa: E712
        )

        if filters and filters.campionato_status == "active":
            query = query.filter(Campionato.is_active == True)  # noqa: E712
        elif filters and filters.campionato_status == "completed":
            query = query.filter(Campionato.is_active == False)  # noqa: E712

        query = query.order_by(Campionato.created_at.desc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return pagination

    # =========================================================================
    # FILTER OPTIONS (for dropdowns)
    # =========================================================================

    @staticmethod
    def get_filter_options(user_id: int) -> Dict[str, Any]:
        """Get available filter options for UI dropdowns.

        Returns dict with:
        - venues: List of unique venue names
        - opponents: List of User objects
        - campionati: List of Campionato objects
        - disciplines: List of (value, display_name) tuples
        """
        # Unique venues from user's match history
        venues_query = (
            db.session.query(Gara.location)
            .join(Match, Match.gara_id == Gara.id)
            .filter(
                Gara.location.isnot(None),
                Gara.location != "",
                or_(
                    Match.player1_id == user_id,
                    Match.player2_id == user_id,
                ),
            )
            .distinct()
            .order_by(Gara.location)
        )
        venues = [v[0] for v in venues_query.all()]

        # Unique opponents from user's match history
        # Get all player IDs that user has faced
        opponent_ids_as_p1 = (
            db.session.query(Match.player2_id)  # type: ignore[call-overload]
            .filter(
                Match.player1_id == user_id,
                Match.player2_id.isnot(None),
                Match.is_bye == False,  # noqa: E712
            )
            .distinct()
        )

        opponent_ids_as_p2 = (
            db.session.query(Match.player1_id)  # type: ignore[call-overload]
            .filter(
                Match.player2_id == user_id,
                Match.player1_id.isnot(None),
            )
            .distinct()
        )

        # Use scalar_subquery() for IN() to avoid SQLAlchemy warnings
        opponent_ids_subq = opponent_ids_as_p1.union(
            opponent_ids_as_p2
        ).scalar_subquery()

        opponents = (
            db.session.query(User)
            .filter(User.id.in_(opponent_ids_subq))
            .order_by(User.username)
            .all()
        )

        # Campionati where user participated
        inscribed_gara_ids_subq = (
            db.session.query(Inscription.gara_id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,  # noqa: E712
            )
            .scalar_subquery()
        )

        campionato_ids_subq = (
            db.session.query(Gara.campionato_id)
            .filter(
                Gara.id.in_(inscribed_gara_ids_subq),
                Gara.campionato_id.isnot(None),
            )
            .distinct()
            .scalar_subquery()
        )

        campionati = (
            db.session.query(Campionato)
            .filter(
                Campionato.id.in_(campionato_ids_subq),
                Campionato.is_deleted == False,  # noqa: E712
            )
            .order_by(Campionato.created_at.desc())
            .all()
        )

        # Disciplines - use enum
        disciplines = [(d.value, d.display_name) for d in Discipline]

        return {
            "venues": venues,
            "opponents": opponents,
            "campionati": campionati,
            "disciplines": disciplines,
        }
