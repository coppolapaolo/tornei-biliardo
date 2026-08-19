"""Sposta la partecipazione a UNA gara da un giocatore a un altro.

**Il caso d'uso.** Il direttore iscrive la persona sbagliata — due account con
nomi che si somigliano — e se ne accorge a gara finita, quando in classifica
generale compaiono due omonimi. La gara è già stata giocata: iscrizione,
partite, rack, tentativi di esercizio, XP e posizione in classifica sono tutti
attribuiti a chi non ha mai toccato una stecca.

**Perché non è un'unione di account.** ``UserMergeService`` esiste già e fa una
cosa vicina, ma diversa: fonde *tutto* un account in un altro e anonimizza il
sorgente. Qui i due account sono due persone vere, e quella iscritta per errore
deve restare in piedi con la sua storia altrove. Lo spostamento è quindi
**circoscritto a una gara**.

Cosa fa, in ordine:

1. **valida** — sorgente iscritto alla gara, destinatario che nella gara non
   compare da nessuna parte (né iscritto né in una partita). Un destinatario che
   ha già giocato quella gara renderebbe le due persone avversarie di sé stesse;
2. **sposta i fatti** — ogni colonna che punta a ``user.id`` in una tabella
   raggiungibile dalla gara. L'elenco non è scritto a memoria: è la mappa
   ``_GARA_SCOPES``, e ``tests/new/unit/test_gara_participant_reassign_map.py``
   cammina il grafo delle chiavi esterne e pretende che ogni tabella
   raggiungibile sia classificata (spostata, cancellata o esclusa con motivo);
3. **sposta gli XP della gara** — il registro XP è la fonte esatta del livello,
   quindi i movimenti legati alla gara e alle sue partite cambiano proprietario.
   Si riconoscono da ``related_entities`` (``gara_id`` / ``match_id``);
4. **ricostruisce i derivati** — classifiche di turno, di gara e di campionato,
   ELO (competitivo e globale), livello, serie e traguardi. Nessun dato derivato
   viene *spostato*: sarebbe il modo comodo di sbagliare. Vengono ricalcolati
   dalla fonte di verità, che a quel punto è già corretta.

Due cose non si spostano di proposito:

- ``player_encounter`` (memoria anti-rivincita) porta l'ordinamento
  ``player1_id < player2_id`` dentro la riga, sotto un ``UNIQUE``. Riassegnare
  un id lo romperebbe in silenzio: gli incontri della gara si **cancellano e si
  rigenerano** dalle partite;
- ``hidden_match`` / ``hidden_inscription`` sono preferenze di visibilità di chi
  le ha messe, non fatti della gara. Le righe del sorgente si cancellano.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

from sqlalchemy import Table, and_, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import UniqueConstraint

from models.base import db
from models.exceptions import ConflictError, NotFoundError, ValidationError
from models.user.models import User
from models.user.role_enum import UserRole
from models.transaction.manager import transactional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Mappa delle tabelle raggiungibili dalla gara
# --------------------------------------------------------------------------
#
# Ogni voce dice COME si restringe una tabella a una singola gara. Le tabelle
# raggiungibili dalla gara ma assenti da qui devono comparire in
# `_SKIPPED_TABLES` con un motivo: il test di presidio non accetta silenzi.


def _ids(table_name: str, where) -> Any:
    """Sotto-select degli id di ``table_name`` che soddisfano ``where``."""
    table = db.metadata.tables[table_name]
    return select(table.c.id).where(where)


def _by_gara(column: str) -> Callable[[Table, int], Any]:
    return lambda table, gara_id: table.c[column] == gara_id


def _by_parent(
    column: str, parent: str, parent_scope: str
) -> Callable[[Table, int], Any]:
    """Riga figlia di un padre già ristretto alla gara."""

    def scope(table: Table, gara_id: int):
        parent_table = db.metadata.tables[parent]
        return table.c[column].in_(
            select(parent_table.c.id).where(
                _GARA_SCOPES[parent_scope](parent_table, gara_id)
            )
        )

    return scope


_GARA_SCOPES: Dict[str, Callable[[Table, int], Any]] = {
    # --- ancorate direttamente alla gara ---
    "inscription": _by_gara("gara_id"),
    "match": _by_gara("gara_id"),
    "tiebreaker": _by_gara("gara_id"),
    "gara_classification": _by_gara("gara_id"),
    "round_classification": _by_gara("gara_id"),
    "gara_challenge_classification": _by_gara("gara_id"),
    "gara_bye_challenge": _by_gara("gara_id"),
    "challenge_attempt": _by_gara("gara_id"),
    "playoff_campionato": _by_gara("gara_id"),
    # --- figlie della partita ---
    "match_result": _by_parent("match_id", "match", "match"),
    "rack": _by_parent("match_id", "match", "match"),
    "set": _by_parent("match_id", "match", "match"),
    "trio_match": _by_parent("match_id", "match", "match"),
    "match_rating_history": _by_parent("match_id", "match", "match"),
    # --- nipoti ---
    "set_rack": _by_parent("set_id", "set", "set"),
    "trio_rack": _by_parent("trio_match_id", "trio_match", "trio_match"),
    # --- figlie dello spareggio ---
    "playoff_match": _by_parent("tiebreaker_id", "tiebreaker", "tiebreaker"),
    "spot_shot": _by_parent("tiebreaker_id", "tiebreaker", "tiebreaker"),
    "rally_attempt": _by_parent("tiebreaker_id", "tiebreaker", "tiebreaker"),
    # --- esercizi della gara ---
    "gara_challenge_attempt": _by_parent(
        "gara_challenge_id", "gara_challenge", "gara_challenge"
    ),
    # `gara_challenge` compare qui solo come *padre* per la riga sopra: la sua
    # colonna utente (`added_by_id`) è configurazione del direttore ed è esclusa
    # dallo spostamento (vedi `_SKIPPED_TABLES`).
    "gara_challenge": _by_gara("gara_id"),
}

#: Righe del sorgente da **cancellare** invece che spostare, con lo stesso
#: criterio di restrizione alla gara.
_DELETE_SOURCE_SCOPES: Dict[str, Callable[[Table, int], Any]] = {
    "hidden_match": _by_parent("match_id", "match", "match"),
    "hidden_inscription": _by_parent("inscription_id", "inscription", "inscription"),
}

#: Tabelle raggiungibili dalla gara che NON vanno toccate, e perché.
_SKIPPED_TABLES: Dict[str, str] = {
    "gara": "director_id: il direttore non è un partecipante",
    "gara_challenge": "added_by_id: configurazione della gara, non partecipazione",
    "player_encounter": "ordinamento p1<p2 dentro un UNIQUE: si rigenera dalle partite",
    "hidden_match": "preferenza di visibilità di chi l'ha messa: si cancella",
    "hidden_inscription": "preferenza di visibilità di chi l'ha messa: si cancella",
    "demand_signal": "segnale di disponibilità dell'utente, non un fatto della gara",
}

#: Colonne che, pur stando in una tabella spostata, restano dove sono.
_SKIPPED_COLUMNS: Set[str] = {
    "gara.director_id",
    "gara_challenge.added_by_id",
}

#: Metriche degli achievement che possono **scendere** dopo lo spostamento.
#: Solo queste si rivalutano al ribasso: su un requisito booleano o legato a un
#: evento irripetibile «non idoneo adesso» non vuol dire «non è mai successo».
_AFFECTED_METRICS: Sequence[str] = (
    "match_wins",
    "tournament_participation",
    "tournament_wins",
    "tournament_podium",
    "unique_opponents",
    "win_streak",
    "strategies_tried",
    "challenges_completed",
    "perfect_challenges",
)


class GaraParticipantReassignService:
    """Sposta da un giocatore a un altro tutto ciò che è successo in una gara."""

    # ------------------------------------------------------------ ingresso

    @staticmethod
    def plan(
        gara_id: int, source_id: int, target_id: int, performed_by_id: int
    ) -> Dict[str, Any]:
        """Inventario di **sola lettura**: cosa verrebbe spostato, e da dove.

        Esegue le stesse validazioni di ``reassign`` — quindi solleva sugli
        stessi conflitti — e poi conta le righe senza toccarne nessuna.

        **Perché non è una simulazione completa.** Far girare lo spostamento e
        poi annullare non funziona in questa applicazione: un ``@transactional``
        annidato chiama ``db.session.commit()``, e da SQLAlchemy 1.4 quel commit
        chiude la transazione **esterna** invece di rilasciare il savepoint. Il
        ricalcolo della gamification committerebbe per davvero, e l'annullamento
        finale non troverebbe più niente da annullare. La prova completa si fa
        su una **copia del file .db** (vedi lo script), non con un rollback.

        Raises:
            NotFoundError: gara o utente inesistente.
            ValidationError: stessi id, un amministratore coinvolto, esecutore
                non amministratore, sorgente non iscritto.
            ConflictError: il destinatario compare già nella gara.
        """
        gara, source, target = GaraParticipantReassignService._validate(
            gara_id, source_id, target_id, performed_by_id
        )
        return {
            "gara_id": gara_id,
            "gara_name": gara.name,
            "campionato_id": gara.campionato_id,
            "source": {"id": source.id, "username": source.username},
            "target": {"id": target.id, "username": target.username},
            "read_only": True,
            "moved_rows": GaraParticipantReassignService._count_facts(
                gara_id, source_id
            ),
            "deleted_rows": GaraParticipantReassignService._count_deletions(
                gara_id, source_id
            ),
            "moved_xp": GaraParticipantReassignService._select_xp(gara_id, source_id),
            "before": GaraParticipantReassignService._snapshot(
                gara_id, gara.campionato_id, source_id, target_id
            ),
            "manual_review": GaraParticipantReassignService._manual_review(
                gara, source_id
            ),
        }

    @staticmethod
    @transactional(domain="competition")
    def reassign(
        gara_id: int, source_id: int, target_id: int, performed_by_id: int
    ) -> Dict[str, Any]:
        """Sposta la partecipazione a ``gara_id`` da ``source_id`` a ``target_id``.

        **Scrive.** Non esiste una modalità di prova: usa ``plan`` per l'elenco
        di ciò che si muove, e una copia del database per la prova generale.

        Va eseguita con un backup fresco: i ricalcoli attraversano più
        ``@transactional``, e per il difetto descritto in ``plan`` un guasto a
        metà strada non si annulla da solo.

        Raises:
            NotFoundError: gara o utente inesistente.
            ValidationError: stessi id, un amministratore coinvolto, esecutore
                non amministratore, sorgente non iscritto.
            ConflictError: il destinatario compare già nella gara.
        """
        gara, source, target = GaraParticipantReassignService._validate(
            gara_id, source_id, target_id, performed_by_id
        )

        report: Dict[str, Any] = {
            "gara_id": gara_id,
            "gara_name": gara.name,
            "campionato_id": gara.campionato_id,
            "source": {"id": source.id, "username": source.username},
            "target": {"id": target.id, "username": target.username},
            "read_only": False,
        }

        report["before"] = GaraParticipantReassignService._snapshot(
            gara_id, gara.campionato_id, source_id, target_id
        )

        report["moved_rows"] = GaraParticipantReassignService._reassign_facts(
            gara_id, source_id, target_id
        )
        report["deleted_rows"] = GaraParticipantReassignService._delete_source_rows(
            gara_id, source_id
        )
        report["moved_xp"] = GaraParticipantReassignService._move_xp(
            gara_id, source_id, target_id
        )

        # I bulk UPDATE non sincronizzano l'identity map: senza questo i
        # ricalcoli rileggerebbero le righe vecchie dalla sessione.
        db.session.flush()
        db.session.expire_all()

        GaraParticipantReassignService._rebuild_encounters(gara_id)
        GaraParticipantReassignService._recalculate_classifications(
            gara_id, gara.campionato_id
        )
        GaraParticipantReassignService._recalculate_elo()
        report["gamification"] = GaraParticipantReassignService._rebuild_gamification(
            source_id, target_id
        )
        GaraParticipantReassignService._mark_leaderboards_stale(source_id, target_id)

        db.session.flush()
        db.session.expire_all()
        report["after"] = GaraParticipantReassignService._snapshot(
            gara_id, gara.campionato_id, source_id, target_id
        )
        report["manual_review"] = GaraParticipantReassignService._manual_review(
            gara, source_id
        )

        logger.info(
            "Partecipazione spostata: gara %s, %s → %s (eseguito da %s). Righe: %s",
            gara_id,
            source_id,
            target_id,
            performed_by_id,
            report["moved_rows"],
        )
        return report

    # --------------------------------------------------------- validazioni

    @staticmethod
    def _validate(gara_id: int, source_id: int, target_id: int, performed_by_id: int):
        from models.competition.models import Gara, Inscription
        from models.match.models import Match
        from models.tiebreaker.models import Tiebreaker

        gara = db.session.get(Gara, gara_id)
        if gara is None:
            raise NotFoundError(f"Gara {gara_id} non trovata")

        # get by PK scavalca il filtro soft-delete: serve anche su un account
        # disattivato.
        source = db.session.get(User, source_id)
        target = db.session.get(User, target_id)
        if source is None:
            raise NotFoundError(f"Utente sorgente {source_id} non trovato")
        if target is None:
            raise NotFoundError(f"Utente destinazione {target_id} non trovato")
        if source_id == target_id:
            raise ValidationError("Sorgente e destinazione coincidono")
        if UserRole.ADMIN.value in (source.role, target.role):
            raise ValidationError(
                "Impossibile spostare la partecipazione di un amministratore"
            )

        performer = db.session.get(User, performed_by_id)
        if performer is None or performer.role != UserRole.ADMIN.value:
            raise ValidationError(
                "Solo un amministratore può spostare una partecipazione"
            )

        if not Inscription.query.filter_by(gara_id=gara_id, user_id=source_id).first():
            raise ValidationError(
                f"L'utente {source_id} non risulta iscritto alla gara {gara_id}"
            )

        # Il destinatario non deve comparire da nessuna parte nella gara: se ha
        # già giocato, dopo lo spostamento si troverebbe avversario di sé stesso
        # e ELO e classifica ne uscirebbero corrotti.
        conflicts: List[str] = []
        if Inscription.query.filter_by(gara_id=gara_id, user_id=target_id).first():
            conflicts.append("iscrizione")
        if Match.query.filter(
            Match.gara_id == gara_id,
            db.or_(Match.player1_id == target_id, Match.player2_id == target_id),
        ).first():
            conflicts.append("partita")
        if Tiebreaker.query.filter(
            Tiebreaker.gara_id == gara_id,
            db.or_(
                Tiebreaker.player1_id == target_id,
                Tiebreaker.player2_id == target_id,
            ),
        ).first():
            conflicts.append("spareggio")
        if conflicts:
            raise ConflictError(
                f"L'utente {target_id} compare già nella gara {gara_id} "
                f"({', '.join(conflicts)}): spostamento annullato. Vanno unite "
                "le due partecipazioni a mano."
            )

        return gara, source, target

    # ------------------------------------------------------ spostamento fatti

    @staticmethod
    def _user_fk_columns():
        """(Table, Column) per ogni colonna che punta a ``user.id``."""
        user_table = User.__table__
        for table in db.metadata.sorted_tables:
            for col in table.columns:
                for fk in col.foreign_keys:
                    if fk.column.table is user_table:
                        yield table, col

    @staticmethod
    def _is_constrained(table: Table, col) -> bool:
        """True se ``col`` fa parte della PK o di un UNIQUE."""
        if col.primary_key or col.unique:
            return True
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint) and col.name in (
                c.name for c in constraint.columns
            ):
                return True
        for index in table.indexes:
            if index.unique and col.name in (c.name for c in index.columns):
                return True
        return False

    @staticmethod
    def _fact_targets(gara_id: int, source_id: int):
        """(tabella, colonna, where, quante) per ogni colonna da spostare."""
        for table, col in GaraParticipantReassignService._user_fk_columns():
            scope = _GARA_SCOPES.get(table.name)
            if scope is None:
                continue
            if f"{table.name}.{col.name}" in _SKIPPED_COLUMNS:
                continue

            where = and_(col == source_id, scope(table, gara_id))
            count = (
                db.session.execute(
                    select(db.func.count()).select_from(table).where(where)
                ).scalar()
                or 0
            )
            if count:
                yield table, col, where, count

    @staticmethod
    def _count_facts(gara_id: int, source_id: int) -> Dict[str, int]:
        """Quante righe si sposterebbero, per tabella e colonna. Non scrive."""
        return {
            f"{table.name}.{col.name}": count
            for table, col, _, count in GaraParticipantReassignService._fact_targets(
                gara_id, source_id
            )
        }

    @staticmethod
    def _reassign_facts(gara_id: int, source_id: int, target_id: int) -> Dict[str, int]:
        """Sposta ogni colonna utente delle tabelle ristrette alla gara."""
        moved: Dict[str, int] = {}
        for table, col, where, count in GaraParticipantReassignService._fact_targets(
            gara_id, source_id
        ):
            if GaraParticipantReassignService._is_constrained(table, col):
                GaraParticipantReassignService._move_constrained(
                    table, col, where, target_id
                )
            else:
                db.session.execute(
                    update(table).where(where).values({col.name: target_id})
                )
            moved[f"{table.name}.{col.name}"] = count
        return moved

    @staticmethod
    def _move_constrained(table: Table, col, where, target_id: int) -> None:
        """Sposta riga per riga una colonna sotto PK/UNIQUE.

        Un conflitto qui vorrebbe dire che il destinatario ha già una riga
        equivalente nella gara — la validazione lo esclude, quindi non lo
        assorbiamo in silenzio come fa l'unione di account: si solleva, perché
        cancellare la riga del sorgente perderebbe un fatto vero.
        """
        pk_cols = list(table.primary_key.columns)
        rows = db.session.execute(select(table).where(where)).mappings().all()
        for row in rows:
            row_where = and_(*[pk == row[pk.name] for pk in pk_cols])
            try:
                with db.session.begin_nested():
                    db.session.execute(
                        update(table).where(row_where).values({col.name: target_id})
                    )
            except IntegrityError as exc:
                raise ConflictError(
                    f"Conflitto su {table.name}.{col.name}: il destinatario ha "
                    f"già una riga equivalente. Spostamento annullato ({exc})."
                ) from exc

    @staticmethod
    def _deletion_targets(gara_id: int, source_id: int):
        for name, scope in _DELETE_SOURCE_SCOPES.items():
            table = db.metadata.tables[name]
            where = and_(table.c.user_id == source_id, scope(table, gara_id))
            count = (
                db.session.execute(
                    select(db.func.count()).select_from(table).where(where)
                ).scalar()
                or 0
            )
            if count:
                yield table, where, count

    @staticmethod
    def _count_deletions(gara_id: int, source_id: int) -> Dict[str, int]:
        """Quante righe verrebbero cancellate. Non scrive."""
        return {
            table.name: count
            for table, _, count in GaraParticipantReassignService._deletion_targets(
                gara_id, source_id
            )
        }

    @staticmethod
    def _delete_source_rows(gara_id: int, source_id: int) -> Dict[str, int]:
        """Cancella le righe del sorgente che non ha senso spostare."""
        deleted: Dict[str, int] = {}
        for table, where, count in GaraParticipantReassignService._deletion_targets(
            gara_id, source_id
        ):
            db.session.execute(delete(table).where(where))
            deleted[table.name] = count
        return deleted

    # ---------------------------------------------------------- registro XP

    @staticmethod
    def _move_xp(gara_id: int, source_id: int, target_id: int) -> Dict[str, Any]:
        """Sposta i movimenti XP legati alla gara e alle sue partite.

        Il registro XP è **la** fonte del livello (``_rebuild_level`` lo somma),
        quindi non basta ricalcolare: i movimenti vanno riattribuiti. Si
        riconoscono da ``related_entities``, il JSON che ogni handler scrive
        insieme all'XP (``{"gara_id": …}`` per iscrizione/completamento/podio,
        ``{"match_id": …}`` per vittoria e partecipazione).

        Gli sblocchi di traguardo (``achievement_id``) restano dove sono: sono
        derivati, e li rimette in riga la revoca/riconciliazione.
        """
        from models.gamification.models import XPTransaction

        selezione = GaraParticipantReassignService._select_xp(gara_id, source_id)
        for txn_id in selezione["ids"]:
            txn = db.session.get(XPTransaction, txn_id)
            if txn is not None:
                txn.user_id = target_id

        db.session.flush()
        return selezione

    @staticmethod
    def _select_xp(gara_id: int, source_id: int) -> Dict[str, Any]:
        """Quali movimenti XP del sorgente appartengono alla gara. Non scrive."""
        from models.gamification.models import XPTransaction
        from models.match.models import Match

        match_ids = {
            row[0]
            for row in db.session.query(Match.id).filter(Match.gara_id == gara_id)
        }

        ids: List[int] = []
        amount = 0
        for txn in XPTransaction.query.filter_by(user_id=source_id).all():
            related = GaraParticipantReassignService._parse_related(
                txn.related_entities
            )
            if not related:
                continue
            if (
                related.get("gara_id") == gara_id
                or related.get("match_id") in match_ids
            ):
                ids.append(txn.id)
                amount += txn.xp_amount or 0

        return {"count": len(ids), "xp_amount": amount, "ids": ids}

    @staticmethod
    def _parse_related(raw: Optional[str]) -> Dict[str, Any]:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    # ------------------------------------------------------------ ricalcoli

    @staticmethod
    def _rebuild_encounters(gara_id: int) -> None:
        """Rigenera la memoria anti-rivincita della gara dalle partite."""
        from models.classification.models import PlayerEncounter
        from models.classification.encounter_service import PlayerEncounterService
        from models.match.models import Match

        db.session.query(PlayerEncounter).filter(
            PlayerEncounter.gara_id == gara_id
        ).delete(synchronize_session=False)
        db.session.flush()

        for match in Match.query.filter(Match.gara_id == gara_id).all():
            PlayerEncounterService.record_match_encounters(match)
        db.session.flush()

    @staticmethod
    def _recalculate_classifications(
        gara_id: int, campionato_id: Optional[int]
    ) -> None:
        """Ricostruisce classifiche di turno, di gara e di campionato.

        Gli ID si raccolgono con query a colonne e mai come oggetti ORM: subito
        dopo le classifiche vengono rifatte con DELETE+INSERT e SQLite riusa i
        rowid appena liberati, così un oggetto rimasto in identity-map
        collderebbe con l'INSERT nuovo (stesso inciampo dell'unione account).
        """
        from models.match.models import Match
        from models.classification.gara_classification import (
            StrategyBasedClassificationService,
        )
        from models.classification.campionato_classification import (
            ClassificationService,
        )

        rounds = sorted(
            {
                row[0]
                for row in db.session.query(Match.round_number)
                .filter(Match.gara_id == gara_id, Match.round_number.isnot(None))
                .distinct()
            }
        )

        db.session.expire_all()
        service = StrategyBasedClassificationService()
        for round_number in rounds:
            service.calculate_round_classification(gara_id, round_number)
        if rounds:
            service.calculate_gara_classification(gara_id)

        # La classifica di campionato **persistita** si rinfresca solo se
        # esiste già. Non è pigrizia: l'applicazione la scrive in momenti
        # precisi — chiusura del campionato, avvio dei playoff, correzione
        # manuale di un risultato — e finché quei momenti non arrivano la
        # tabella è vuota di proposito. La schermata che l'utente guarda non la
        # legge nemmeno: `calculate_general_classification` aggrega al volo le
        # `GaraClassification`, che qui sono già corrette.
        #
        # Popolarla adesso cambierebbe il comportamento di un campionato vivo:
        # `AmalfiStrategy._seeding_order` accoppia a caso proprio *perché* non
        # trova righe («fallback a random»), e con le righe passerebbe a
        # seminare per classifica. Una riparazione dati non deve decidere come
        # si sorteggia la prossima gara.
        #
        # Una riga che c'è, invece, va rinfrescata: lasciarla stantia dopo lo
        # spostamento sarebbe peggio che non averla.
        if campionato_id and GaraParticipantReassignService._has_persisted_standings(
            campionato_id
        ):
            ClassificationService.update_campionato_classification(campionato_id)

    @staticmethod
    def _has_persisted_standings(campionato_id: int) -> bool:
        """Il campionato ha già una classifica generale persistita?"""
        from models.classification.models import Classification

        return (
            db.session.query(Classification.id)
            .filter(Classification.campionato_id == campionato_id)
            .first()
            is not None
        )

    @staticmethod
    def _recalculate_elo() -> None:
        """Azzera e rigioca l'ELO: è path-dependent, non si può correggere a mano."""
        from models.rating.calculation_service import RatingCalculationService

        RatingCalculationService.recalculate_all_elo()
        RatingCalculationService.recalculate_all_elo_global()

    @staticmethod
    def _rebuild_gamification(source_id: int, target_id: int) -> Dict[str, Any]:
        """Rimette in riga livello, serie e traguardi dei due account.

        Sul **sorgente** si passa prima dalla revoca: la ricostruzione da sola
        sa solo sbloccare (lo sblocco è monotòno per scelta di dominio), e senza
        revoca resterebbe acceso un traguardo su una gara che non ha giocato.
        La revoca è comunque un *ricalcolo*: se altre gare reggono il requisito,
        il traguardo resta. L'XP del traguardo tolto torna indietro con un
        movimento compensativo, quindi va fatta **prima** del ricalcolo del
        livello, che somma il registro.
        """
        from models.gamification.achievement_service import AchievementService
        from models.gamification.recalc_service import GamificationRecalcService

        revoked = AchievementService.revoke_no_longer_earned(
            source_id, _AFFECTED_METRICS
        )
        db.session.flush()

        return {
            "source_revoked_achievements": revoked,
            "source": GamificationRecalcService.rebuild_for_user(source_id),
            "target": GamificationRecalcService.rebuild_for_user(target_id),
        }

    @staticmethod
    def _mark_leaderboards_stale(source_id: int, target_id: int) -> None:
        from models.gamification.models import LeaderboardEntry

        db.session.query(LeaderboardEntry).filter(
            LeaderboardEntry.user_id.in_([source_id, target_id])
        ).update({"is_stale": True}, synchronize_session=False)

    # -------------------------------------------------------------- report

    @staticmethod
    def _snapshot(
        gara_id: int,
        campionato_id: Optional[int],
        source_id: int,
        target_id: int,
    ) -> Dict[str, Any]:
        """Fotografia leggibile di ciò che l'utente vede: le due classifiche."""
        from models.classification.models import Classification, GaraClassification

        def _gara_rows():
            rows = (
                GaraClassification.query.filter_by(gara_id=gara_id)
                .order_by(GaraClassification.position)
                .all()
            )
            return [
                {
                    "position": r.position,
                    "user_id": r.user_id,
                    "username": GaraParticipantReassignService._username(r.user_id),
                    "matches_won": r.matches_won,
                    "racks_won": r.racks_won,
                    "campionato_points": r.campionato_points,
                }
                for r in rows
            ]

        def _campionato_rows():
            if not campionato_id:
                return []
            rows = (
                Classification.query.filter_by(campionato_id=campionato_id)
                .order_by(Classification.position)
                .all()
            )
            return [
                {
                    "position": r.position,
                    "user_id": r.user_id,
                    "username": GaraParticipantReassignService._username(r.user_id),
                    "gare_played": r.gare_played,
                    "total_matches_won": r.total_matches_won,
                    "total_racks_won": r.total_racks_won,
                }
                for r in rows
            ]

        from models.gamification.models import UserLevel

        def _level(uid: int):
            lvl = db.session.get(UserLevel, uid)
            return {
                "total_xp": lvl.total_xp if lvl else 0,
                "current_level": lvl.current_level if lvl else 1,
            }

        return {
            "gara_classification": _gara_rows(),
            "campionato_classification": _campionato_rows(),
            "elo": {
                source_id: GaraParticipantReassignService._elo(source_id),
                target_id: GaraParticipantReassignService._elo(target_id),
            },
            "level": {source_id: _level(source_id), target_id: _level(target_id)},
        }

    @staticmethod
    def _username(user_id: int) -> str:
        user = db.session.get(User, user_id)
        return user.username if user else f"?{user_id}"

    @staticmethod
    def _elo(user_id: int):
        user = db.session.get(User, user_id)
        return user.elo_rating if user else None

    @staticmethod
    def _manual_review(gara, source_id: int) -> List[str]:
        """Cose che lo spostamento NON risolve e vanno guardate a occhio."""
        from models.notification.models import Notification
        from models.playoff.models import PlayoffQualification, PlayoffConfiguration

        notes: List[str] = []

        stale = [
            n
            for n in Notification.query.filter_by(user_id=source_id).all()
            if GaraParticipantReassignService._parse_related(n.related_entities).get(
                "gara_id"
            )
            == gara.id
        ]
        if stale:
            notes.append(
                f"{len(stale)} notifiche di {source_id} parlano ancora della gara "
                f"{gara.id}: sono messaggi già letti, restano come traccia storica."
            )

        if gara.campionato_id:
            quals = (
                PlayoffQualification.query.join(
                    PlayoffConfiguration,
                    PlayoffQualification.configuration_id == PlayoffConfiguration.id,
                )
                .filter(
                    PlayoffConfiguration.campionato_id == gara.campionato_id,
                    PlayoffQualification.user_id == source_id,
                )
                .count()
            )
            if quals:
                notes.append(
                    f"{source_id} ha {quals} qualificazione/i playoff nel campionato "
                    f"{gara.campionato_id}: sono legate alla posizione in classifica, "
                    "che è appena cambiata. Vanno rigenerate a mano."
                )

        return notes
