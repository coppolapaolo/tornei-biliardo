# models/campionato/statistics_service.py
"""Statistics and classification logic for Campionato.

Extracted from services.py for maintainability (Round 4 P4).
Contains: TournamentStatisticsService, compute_campionato_status.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.base import db
from models.match.models import Match
from models.status_enum import (
    TournamentStatus,
    GaraStatus,
    MatchStatus,
    ClassificationSystem,
)
from .models import Campionato
from ..transaction.manager import read_only
from models.exceptions import NotFoundError


def sistema_della_classifica_generale(campionato: Campionato) -> ClassificationSystem:
    """Su cosa si ordina la classifica generale di questo campionato.

    Il sistema scelto per il campionato, non il suo tipo (ADR-047) — tranne
    per i campionati a tabellone, che sommano punti per piazzamento anche se
    sono nati prima che il sistema POSITION fosse selezionabile
    (`ClassificationService.uses_position_points`).
    """
    from models.classification.campionato_classification import (
        ClassificationService,
    )

    if ClassificationService.uses_position_points(campionato):
        return ClassificationSystem.POSITION
    return campionato.classification_system


def _racks_won_of(classification, gara_is_rack: bool) -> int:
    """I triangoli vinti da una riga di classifica di turno.

    `racks_won` è NULL sulle righe scritte prima della separazione delle due
    colonne (migration 20260728). Per le gare a triangoli totali il valore
    stava in `rack_difference` e il backfill l'ha già ricopiato; per le altre
    non è ricostruibile dalle colonne, e resta 0 finché
    `scripts/repair_round_classification_racks.py` non lo ricalcola dai match.

    Restituire 0 anziché la differenza è deliberato: in una gara a vittorie
    quel numero non è un totale, e sommarcelo dentro rifarebbe esattamente il
    guasto della issue #89.
    """
    if classification.racks_won is not None:
        return classification.racks_won
    if gara_is_rack:
        return classification.rack_difference or 0
    return 0


class TournamentStatisticsService:
    """Statistics and classification operations for Campionati."""

    @read_only(domain="campionato")
    def get_campionato_statistics(self, campionato_id: int) -> Dict[str, Any]:
        """
        Get campionato-level statistics.

        Args:
            campionato_id: ID of the campionato

        Returns:
            Dictionary containing campionato statistics
        """
        from models.competition.models import Gara, Inscription

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise NotFoundError("Campionato not found")

        # Get all gare for this campionato
        gare = Gara.query.filter_by(campionato_id=campionato_id).all()
        gara_ids = [p.id for p in gare]

        # Calculate statistics
        total_garas = len(gare)
        total_inscriptions = (
            Inscription.query.filter(Inscription.gara_id.in_(gara_ids)).count()
            if gara_ids
            else 0
        )
        total_matches = (
            Match.query.filter(Match.gara_id.in_(gara_ids)).count() if gara_ids else 0
        )

        # Status distribution
        status_counts: Dict[str, int] = {}
        for gara in gare:
            status = getattr(gara, "status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_garas": total_garas,
            "total_inscriptions": total_inscriptions,
            "total_matches": total_matches,
            "status_distribution": status_counts,
        }

    @read_only(domain="campionato")
    def calculate_campionato_statistics(self, campionato_id: int) -> Dict[str, Any]:
        """Calcola statistiche avanzate del campionato."""
        from models.competition.models import Gara, Inscription
        from sqlalchemy import func, distinct

        # Giocatori unici che hanno mai partecipato al campionato
        unique_players_query = (
            db.session.query(distinct(Inscription.user_id))
            .join(Gara, Inscription.gara_id == Gara.id)
            .filter(Gara.campionato_id == campionato_id)
        )
        total_unique_players = unique_players_query.count()

        # Giocatori attualmente iscritti a gare con iscrizioni aperte
        active_inscriptions_query = (
            db.session.query(distinct(Inscription.user_id))
            .join(Gara, Inscription.gara_id == Gara.id)
            .filter(
                Gara.campionato_id == campionato_id,
                # Solo gare con iscrizioni aperte
                Gara.status == GaraStatus.INSCRIPTION.value,
            )
        )
        currently_inscribed_players = active_inscriptions_query.count()

        # Match totali completati in tutte le gare
        completed_matches_query = (
            db.session.query(func.count(Match.id))
            .join(Gara, Match.gara_id == Gara.id)
            .filter(
                Gara.campionato_id == campionato_id,
                Match.status == MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
        total_completed_matches = completed_matches_query.scalar() or 0

        # Rack totali giocati (somma dei punteggi di tutti i match completati)
        rack_sum_query = (
            db.session.query(func.sum(Match.player1_score + Match.player2_score))
            .join(Gara, Match.gara_id == Gara.id)
            .filter(
                Gara.campionato_id == campionato_id,
                Match.status == MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
        total_racks_played = rack_sum_query.scalar() or 0

        return {
            "total_unique_players": total_unique_players,
            "currently_inscribed_players": currently_inscribed_players,
            "total_completed_matches": total_completed_matches,
            "total_racks_played": total_racks_played,
        }

    def _aggregate_player_totals(
        self,
        garas: List,
        classification_system: ClassificationSystem,
        campionato: Optional[Campionato] = None,
    ) -> Dict[int, Dict[str, Any]]:
        """Aggrega i totali dei giocatori per un insieme di gare.

        Somma le classifiche **finali delle gare** (`SPECIFICHE.md` riga 292):
        vittorie, triangoli e differenza dall'ultimo turno, lo spareggio e il
        piazzamento dalla classifica della gara. La X c'è perché c'è nella
        classifica della gara, con la sua vittoria.

        Args:
            garas: Lista di gare da aggregare
            classification_system: Sistema di classifica del campionato
            campionato: serve alla tabella dei punti per piazzamento, che il
                campionato può sovrascrivere; senza, vale quella di default

        Returns:
            Dizionario user_id -> dati aggregati del giocatore
        """
        from models.classification.models import RoundClassification, GaraClassification
        from sqlalchemy import tuple_
        from sqlalchemy.orm import joinedload

        player_totals: Dict[int, Dict[str, Any]] = {}
        if not garas:
            return player_totals

        # N+1 fix (hot path homepage anonima): invece di una query
        # RoundClassification + un lazy-load user PER OGNI gara, batcha tutto in
        # un'unica query sulle coppie (gara_id, round-finale) con user eager.
        # L'ultimo turno è quello **giocato**, come lo legge la chiusura della
        # gara (`SpareggioService._get_effective_final_round`), che scrive lì le
        # posizioni finali: una gara chiusa con meno turni del previsto non ha
        # classifica al turno `rounds_count`, e sparirebbe dalla somma.
        ultimo_giocato = dict(
            db.session.query(Match.gara_id, db.func.max(Match.round_number))
            .filter(Match.gara_id.in_([g.id for g in garas]))
            .group_by(Match.gara_id)
            .all()
        )
        final_round_by_gara = {
            g.id: ultimo_giocato.get(g.id) or g.current_round or g.rounds_count
            for g in garas
        }
        rc_rows = (
            db.session.query(RoundClassification)
            .filter(
                tuple_(
                    RoundClassification.gara_id, RoundClassification.round_number
                ).in_(list(final_round_by_gara.items()))
            )
            .options(joinedload(RoundClassification.user))
            .order_by(RoundClassification.position)
            .all()
        )
        rc_by_gara: Dict[int, List[Any]] = {}
        for rc in rc_rows:
            rc_by_gara.setdefault(rc.gara_id, []).append(rc)

        # SSR: un'unica query GaraClassification per tutte le gare. Serve a
        # ogni sistema, non solo a RACK — anche la classifica a vittorie usa lo
        # spareggio come terzo criterio (`Campionato.get_scoring_system`).
        ssr_by_gara: Dict[int, Dict[int, int]] = {}
        piazzamento_by_gara: Dict[int, Dict[int, int]] = {}
        gc_rows = (
            db.session.query(GaraClassification)
            .filter(GaraClassification.gara_id.in_(final_round_by_gara.keys()))
            .all()
        )
        for gc in gc_rows:
            ssr_by_gara.setdefault(gc.gara_id, {})[gc.user_id] = gc.spot_shot_wins or 0
            piazzamento_by_gara.setdefault(gc.gara_id, {})[gc.user_id] = gc.position

        # Quali gare classificano a triangoli totali. Si legge dalle gare già in
        # mano invece che da `rc.gara`, che sarebbe un lazy-load per riga.
        rack_gara_ids = {
            g.id
            for g in garas
            if ClassificationSystem.resolve(getattr(g, "classification_system", None))
            == ClassificationSystem.RACK
        }

        for gara in garas:
            classifications = rc_by_gara.get(gara.id, [])
            gara_ssr_scores = ssr_by_gara.get(gara.id, {})

            gara_is_rack = gara.id in rack_gara_ids
            # Il peso moltiplica ogni contributo della gara prima della somma
            # (ADR-053).
            # Vale 0 per la gara di un playoff che decide la classifica: chi
            # l'ha giocata compare comunque, con contributo nullo.
            peso = gara.classification_weight

            for classification in classifications:
                user_id = classification.user_id
                if user_id not in player_totals:
                    player_totals[user_id] = {
                        "username": classification.user.username,
                        # L'id accanto al nome: chi legge la classifica per
                        # trovare la propria riga confronta l'id, non il nome.
                        "user_id": user_id,
                        "total_matches_won": 0,
                        "total_racks_won": 0,
                        "total_rack_difference": 0,
                        "total_spot_shot_wins": 0,
                        "participations": 0,
                        "total_points": 0,
                    }

                player_totals[user_id]["total_matches_won"] += peso * (
                    classification.matches_won or 0
                )
                # Due colonne, due significati fissi (migration 20260728). Prima
                # qui si sommava `rack_difference` e lo si mostrava come
                # "triangoli totali": funzionava solo finché quella colonna
                # conteneva il totale, cioè fino alla separazione — poi la stessa
                # classifica ha iniziato a sommare differenze, con valori
                # negativi e totali dimezzati (issue #89).
                player_totals[user_id]["total_racks_won"] += peso * _racks_won_of(
                    classification, gara_is_rack
                )
                player_totals[user_id]["total_rack_difference"] += peso * (
                    classification.rack_difference or 0
                )
                player_totals[user_id][
                    "total_spot_shot_wins"
                ] += peso * gara_ssr_scores.get(user_id, 0)
                player_totals[user_id]["participations"] += 1

        # Il sistema a piazzamenti somma i punti del piazzamento **finale** di
        # ogni gara — la banda del tabellone, dove i pari merito condividono la
        # posizione — con la tabella della specifica o quella del campionato
        # (`position_points.py`). Fino al 2026-09-24 qui c'era una seconda
        # tabella, 10/7/5/4, letta dalla posizione nell'ultimo turno: la pagina
        # e le righe davano punti diversi agli stessi piazzamenti.
        if classification_system == ClassificationSystem.POSITION:
            from models.classification.position_points import (
                points_for_position,
                points_table_for_campionato,
            )

            tabella = points_table_for_campionato(campionato)
            for gara in garas:
                for user_id, posizione in piazzamento_by_gara.get(gara.id, {}).items():
                    if user_id in player_totals:
                        # Anche i punti seguono il peso della gara (ADR-053).
                        player_totals[user_id][
                            "total_points"
                        ] += gara.classification_weight * points_for_position(
                            posizione, tabella
                        )

        return player_totals

    @staticmethod
    def _ordine_deciso_dal_playoff(
        campionato: Campionato, ranking: List[tuple]
    ) -> List[tuple]:
        """Riordina `(posizione, user_id)` quando la classifica la decide il playoff.

        Chi ha giocato il playoff occupa le prime posizioni nell'ordine deciso
        lì; sotto vengono tutti gli altri nell'ordine che avevano. I blocchi
        li dà `ClassificationService.playoff_final_blocks`, la stessa fonte
        delle righe persistite: finché la finale non è chiusa sono vuoti e
        la classifica resta quella del campionato.
        """
        from models.classification.campionato_classification import (
            ClassificationService,
        )

        blocks = ClassificationService.playoff_final_blocks(campionato)
        if not blocks:
            return ranking

        presenti = {user_id for _, user_id in ranking}
        promossi: List[int] = []
        for block in blocks:
            for user_id in block:
                if user_id in presenti and user_id not in promossi:
                    promossi.append(user_id)
        resto = [user_id for _, user_id in ranking if user_id not in promossi]
        return [(pos, user_id) for pos, user_id in enumerate(promossi + resto, 1)]

    def _sort_and_rank_players(
        self,
        player_totals: Dict[int, Dict[str, Any]],
        classification_system: ClassificationSystem,
    ) -> List[tuple]:
        """Ordina i giocatori e assegna le posizioni.

        I criteri sono quelli dichiarati da `Campionato.get_scoring_system()` e
        discendono dal sistema di classifica scelto dal direttore, non dalla
        strategia di accoppiamento (ADR-047).

        Args:
            player_totals: Dizionario user_id -> dati aggregati
            classification_system: Sistema di classifica del campionato

        Returns:
            Lista di tuple (posizione, user_id) ordinate
        """
        if classification_system == ClassificationSystem.RACK:

            def chiave(dati: Dict[str, Any]) -> tuple:
                return (-dati["total_racks_won"], -dati["total_spot_shot_wins"])

        elif classification_system == ClassificationSystem.POSITION:

            def chiave(dati: Dict[str, Any]) -> tuple:
                return (
                    -dati.get("total_points", 0),
                    -dati["total_matches_won"],
                    -dati["total_rack_difference"],
                )

        else:

            def chiave(dati: Dict[str, Any]) -> tuple:
                return (
                    -dati["total_matches_won"],
                    -dati["total_rack_difference"],
                    -dati["total_spot_shot_wins"],
                )

        sorted_players = sorted(player_totals.items(), key=lambda x: chiave(x[1]))

        if classification_system != ClassificationSystem.POSITION:
            return [
                (pos, user_id) for pos, (user_id, _) in enumerate(sorted_players, 1)
            ]

        # A piazzamenti il pari merito è l'esito, non un'ambiguità (ADR-040):
        # chi ha la stessa chiave condivide la posizione, e il successivo salta
        # quelle occupate (1, 2, 2, 4).
        ranking: List[tuple] = []
        precedente = None
        for indice, (user_id, dati) in enumerate(sorted_players, 1):
            if chiave(dati) != precedente:
                posizione = indice
                precedente = chiave(dati)
            ranking.append((posizione, user_id))
        return ranking

    @read_only(domain="campionato")
    def calculate_general_classification(self, campionato_id: int) -> List[tuple]:
        """Classifica generale del campionato su tutte le gare completate.

        Include il calcolo del trend (previous_position) confrontando la classifica
        attuale con quella calcolata escludendo l'ultima gara completata.
        Il calcolo sta in `classifica_generale`; qui c'è solo la sessione in
        sola lettura.
        """
        return self.classifica_generale(campionato_id)

    def classifica_generale(self, campionato_id: int) -> List[tuple]:
        """La classifica generale: l'**unico** posto in cui si calcola.

        La leggono la pagina del campionato (attraverso
        `calculate_general_classification`) e le righe `Classification`, che
        ne sono la copia (`ClassificationService.update_campionato_classification`):
        profilo, export e inviti ai playoff. Fino al 2026-09-24 le righe
        rifacevano i conti dalle partite con regole loro, e ogni regola nuova
        andava scritta due volte (ADR-073).

        Non ha decoratori di sessione perché la chiama anche chi scrive, dentro
        la propria transazione.
        """
        from models.competition.models import Gara
        from models.campionato.models import Campionato

        # Trova il campionato per verificare il tipo
        campionato = db.session.query(Campionato).filter_by(id=campionato_id).first()
        if not campionato:
            return []

        from sqlalchemy.orm import joinedload

        # Tutte le gare completate del campionato (incl. "playing" ma finite).
        # `playoff_config` serve a `classification_weight`: caricarla qui evita
        # un lazy-load per gara sulla homepage.
        all_garas = (
            db.session.query(Gara)
            .filter_by(campionato_id=campionato_id)
            .filter(
                Gara.status.in_([GaraStatus.COMPLETED.value, GaraStatus.PLAYING.value])
            )
            .options(joinedload(Gara.playoff_config))
            .order_by(Gara.number)
            .all()
        )

        # Filtra le gare che sono realmente completate
        completed_garas = []
        for gara in all_garas:
            if gara.status == GaraStatus.COMPLETED.value:
                completed_garas.append(gara)
            elif (
                gara.status == GaraStatus.PLAYING.value
                and gara.current_round > gara.rounds_count
            ):
                # Gara con tutti i round completati
                completed_garas.append(gara)

        if not completed_garas:
            return []

        system = sistema_della_classifica_generale(campionato)

        # Calcola posizioni precedenti (tutte le gare tranne l'ultima)
        previous_positions: Dict[int, int] = {}
        if len(completed_garas) > 1:
            previous_garas = completed_garas[:-1]
            previous_totals = self._aggregate_player_totals(
                previous_garas, system, campionato
            )
            previous_ranking = self._sort_and_rank_players(previous_totals, system)
            previous_positions = {user_id: pos for pos, user_id in previous_ranking}

        # Calcola classifica attuale (tutte le gare)
        player_totals = self._aggregate_player_totals(
            completed_garas, system, campionato
        )
        current_ranking = self._sort_and_rank_players(player_totals, system)
        # Quando la classifica finale la decide il playoff, l'ordine dei
        # partecipanti lo detta la gara di playoff (ADR-053).
        current_ranking = self._ordine_deciso_dal_playoff(campionato, current_ranking)

        # Costruisci risultato con posizione precedente
        result = []
        for position, user_id in current_ranking:
            data = player_totals[user_id]
            # previous_position solo se il giocatore era in classifica prima
            data["previous_position"] = previous_positions.get(user_id)
            result.append((position, data))

        return result


# -----------------------------
# Funzione *pura* per lo stato derivato del Campionato
# -----------------------------


def _raccoglie_iscrizioni(gara: Any) -> bool:
    """Se su questa gara ci si può iscrivere **adesso**.

    `status == INSCRIPTION` dice che la gara è nella fase delle iscrizioni, non
    che la finestra sia aperta: una con l'apertura programmata per la settimana
    prossima ha quello stato e non accetta nessuno. La distinzione la fa già
    `get_real_status()`, che in quel caso risponde `inscription_not_yet_open`
    (ed è la stessa che il badge della gara mostra come «Iscrizioni
    programmate»): la si chiede a lui invece di riscrivere qui un terzo
    confronto sulle date.

    Il controllo sullo status viene prima della chiamata per due ragioni: sulle
    gare PLAYING il resolver scorre `gara.matches` — lazy, quindi una query per
    gara sulla homepage anonima — e per tutte le altre la risposta è comunque
    no.
    """
    if getattr(gara, "status", None) != GaraStatus.INSCRIPTION.value:
        return False
    reale = getattr(gara, "get_real_status", None)
    if not callable(reale):
        return True
    return reale() == GaraStatus.INSCRIPTION.value


def compute_campionato_status(campionato: Campionato) -> str:
    """Calcola lo stato derivato del campionato in base agli stati delle Gare.

    Le due domande sono distinte, ed è il punto di tutta la funzione:
    «si può ancora giocare?» e «il direttore ha chiuso?». Prima della #242 una
    risposta sola le copriva entrambe, e COMPLETED significava tanto
    "consolidato" quanto "esaurito ma in attesa di qualcuno che prema Termina".

    Regole:
    - terminated_at valorizzato → AWAITING_PLAYOFF se restano playoff da
      giocare, altrimenti COMPLETED
    - Se non ci sono Gare → SETUP
    - Se almeno una Gara è in PLAYING → IN_PROGRESS
    - Altrimenti, se almeno una Gara raccoglie iscrizioni **adesso** →
      REGISTRATION_OPEN (`status == INSCRIPTION` non basta: la finestra può
      aprirsi la settimana prossima — vedi `_raccoglie_iscrizioni`)
    - Altrimenti, se tutte le gare previste esistono e sono COMPLETED →
      AWAITING_CLOSURE (finite le gare, non chiuso il campionato)
    - Altrimenti, se almeno una Gara è COMPLETED → IN_PROGRESS: il campionato è
      cominciato, la prossima gara non ha ancora aperto
    - In tutti gli altri casi → SETUP

    Ritorna la stringa dello stato (compat con UI/template esistenti).
    """
    if getattr(campionato, "terminated_at", None):
        if (
            hasattr(campionato, "has_playoff_configurations")
            and campionato.has_playoff_configurations()
        ):
            # AWAITING_PLAYOFF finché le gare di playoff non sono tutte chiuse.
            # La fonte è `PlayoffConfiguration.gara`, cioè la gara che il
            # direttore chiude davvero. Fino all'11/09/2026 si guardava il
            # `PlayoffTournament` legacy, che chiudeva solo
            # `complete_playoff_campionato` — mai chiamato da una route — e
            # il campionato restava «In attesa dei playoff» per sempre.
            # Relationship, non query per-config: i chiamanti su lista
            # (homepage, elenco pubblico) le caricano in eager → no N+1.
            active_configs = [
                cfg
                for cfg in getattr(campionato, "playoff_configurations", [])
                if cfg.is_active
            ]
            if active_configs:
                all_completed = all(
                    (g := cfg.gara) is not None
                    and not g.is_deleted
                    and g.status == GaraStatus.COMPLETED.value
                    for cfg in active_configs
                )
                if all_completed:
                    return TournamentStatus.COMPLETED.value
            return TournamentStatus.AWAITING_PLAYOFF.value
        return TournamentStatus.COMPLETED.value

    gare = getattr(campionato, "gare", []) or []
    if not gare:
        return TournamentStatus.SETUP.value

    # Normalizza valori (stringhe) e valuta
    values = [getattr(p, "status", GaraStatus.SETUP.value) for p in gare]

    if any(v == GaraStatus.PLAYING.value for v in values):
        return TournamentStatus.IN_PROGRESS.value
    if any(_raccoglie_iscrizioni(g) for g in gare):
        return TournamentStatus.REGISTRATION_OPEN.value
    if all(v == GaraStatus.COMPLETED.value for v in values):
        # "Tutte le gare esistenti sono completate" non basta: nel mezzo di un
        # campionato, fra la fine di una prova e la creazione della successiva
        # la condizione è vera e il campionato risultava "Completato" — dato
        # fuorviante, e per giunta transitorio (issue #60). Finché restano
        # prove da creare rispetto a quelle pianificate il campionato è
        # ancora in corso; il completamento "vero" passa da
        # `terminate_campionato` (ramo `terminated_at` sopra).
        # La finale dei playoff non è una delle gare pianificate.
        from models.campionato.conteggio_gare import gare_regolari

        planned = getattr(campionato, "planned_gare_count", 0) or 0
        if len(gare_regolari(gare)) < planned:
            return TournamentStatus.IN_PROGRESS.value
        # Le gare previste sono finite tutte, ma `terminated_at` è NULL: la
        # classifica generale non è consolidata e il pulsante "Termina" aspetta
        # ancora qualcuno. Non è COMPLETED, e soprattutto non è terminale — così
        # il campionato resta fra gli attivi della dashboard, che è dove il
        # direttore lo ritrova.
        return TournamentStatus.AWAITING_CLOSURE.value

    if any(v == GaraStatus.COMPLETED.value for v in values):
        # Qualche gara è stata giocata e altre restano, ma nessuna raccoglie
        # iscrizioni adesso — tipicamente la prossima ha l'apertura programmata
        # fra qualche giorno. Non è REGISTRATION_OPEN (non si iscrive nessuno) e
        # non è SETUP: metà campionato è già alle spalle. È IN_PROGRESS, che è
        # anche ciò che lo tiene fra i «Campionati in corso» della homepage
        # invece di spedirlo fra quelli «in preparazione».
        return TournamentStatus.IN_PROGRESS.value

    return TournamentStatus.SETUP.value


# -----------------------------
# Partizione per presentazione: attivi vs completati/terminati
# -----------------------------


_TERMINAL_TOURNAMENT_STATUSES = frozenset(
    {
        TournamentStatus.COMPLETED.value,
        TournamentStatus.AWAITING_PLAYOFF.value,
    }
)


def partition_campionati_by_status(
    campionati: list[Campionato],
    completed_limit: int,
) -> dict:
    """Partiziona campionati in attivi vs completati/terminati per la UI.

    Le viste pubbliche (homepage guest, dashboard player/director) mostrano
    tutti gli attivi e una "coda recente" di completati limitata a
    `completed_limit`. Il resto resta accessibile via pagina archivio
    (`/campionati` con filtri).

    Args:
        campionati: lista pre-filtrata (es. is_active=True, oppure scopata
            al singolo utente). L'ordinamento viene preservato.
        completed_limit: numero massimo di completati da includere in `to_show`.

    Returns:
        Dict con:
        - `active`: lista di campionati con status non-terminale
        - `completed`: lista completa dei campionati COMPLETED/AWAITING_PLAYOFF
        - `completed_shown`: prefisso di `completed` con al più
          `completed_limit` elementi (preserva l'ordine in input)
        - `to_show`: `active + completed_shown` (lista renderizzabile)
        - `completed_total`: `len(completed)`, utile al template per
          decidere se mostrare "Vedi tutti".
    """
    active: list[Campionato] = []
    completed: list[Campionato] = []
    for c in campionati:
        if c.get_status() in _TERMINAL_TOURNAMENT_STATUSES:
            completed.append(c)
        else:
            active.append(c)

    completed_shown = completed[:completed_limit]
    return {
        "active": active,
        "completed": completed,
        "completed_shown": completed_shown,
        "to_show": active + completed_shown,
        "completed_total": len(completed),
    }
