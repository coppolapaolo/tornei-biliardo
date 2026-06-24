"""
User merge service.

Merge two user accounts into one. Use case: a user forgot their password and
re-registered, splitting their history across two accounts. The admin merges the
**source** (the duplicate, anonymized at the end) into the **target** (the kept
account), so the target inherits all of the source's matches, inscriptions, XP,
etc.

Why a plain "UPDATE user_id everywhere" is not enough (see
``docs`` / the merge plan): three classes of problems are handled here:

1. **UNIQUE/PK constraints that include user_id** (e.g. ``user_level`` PK,
   ``user_achievement`` UNIQUE(user_id, achievement_id), one-to-one
   ``user_privacy_setting``): a blind bulk UPDATE would raise IntegrityError
   when the target already has its own row. These columns are reassigned
   **per-row with a savepoint**, deleting the source row on conflict (the target
   keeps its own).

2. **Head-to-head**: if source and target played each other, after the merge a
   match would have ``player1_id == player2_id`` (a self-match), corrupting ELO
   and classifications. We detect this up front and **abort** with a
   ``ConflictError`` — for a "forgot password" duplicate this must never happen;
   if it does, it is a data-integrity signal for the admin to resolve manually.

3. **Derived/aggregate data** (ELO, classifications, gamification) is **not
   transferred** but **recomputed from scratch** after the factual records have
   been reassigned.

The FK reassignment is **metadata-driven**: every column that references
``user.id`` is discovered from the SQLAlchemy metadata, so the merge keeps
working when new models are added. Only a small set of tables needs special
handling.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Set

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import UniqueConstraint

from models.base import db
from models.exceptions import ConflictError, NotFoundError, ValidationError
from models.user.models import User
from models.user.role_enum import UserRole
from models.transaction.manager import transactional

logger = logging.getLogger(__name__)

# Tables whose source rows are deleted (not reassigned) before recompute.
# PlayerEncounter is anti-rematch matchmaking data with an ordered
# CHECK(player1_id < player2_id) + UNIQUE(gara_id, player1, player2): reassigning
# user ids would break ordering/uniqueness. It only matters for active gare, so
# dropping the source's encounters is safe.
_DELETE_SOURCE_TABLES: Set[str] = {"player_encounter"}


class UserMergeService:
    """Merge a source user account into a target account."""

    @staticmethod
    @transactional(domain="user")
    def merge_users(
        source_id: int, target_id: int, performed_by_id: int
    ) -> Dict[str, object]:
        """Merge ``source_id`` into ``target_id``.

        Steps: validate → detect head-to-head → reassign FK (metadata-driven,
        with per-row dedup on constrained columns) → drop source-only derived
        rows → recompute ELO + classifications + gamification → anonymize source.

        Returns a report dict.

        Raises:
            NotFoundError: a user does not exist.
            ValidationError: same user, an admin involved, or performer not admin.
            ConflictError: source and target played head-to-head.
        """
        # ---- FASE 0: validazioni (get by PK bypassa il filtro soft-delete) ----
        source = db.session.get(User, source_id)
        target = db.session.get(User, target_id)
        if source is None:
            raise NotFoundError("Utente sorgente non trovato")
        if target is None:
            raise NotFoundError("Utente destinazione non trovato")
        if source_id == target_id:
            raise ValidationError("Sorgente e destinazione coincidono")
        if source.role == UserRole.ADMIN.value or target.role == UserRole.ADMIN.value:
            raise ValidationError("Impossibile unire un account amministratore")

        performer = db.session.get(User, performed_by_id)
        if performer is None or performer.role != UserRole.ADMIN.value:
            raise ValidationError("Solo un amministratore può unire gli account")

        # ---- FASE 1: rilevamento head-to-head ----
        head_to_head = UserMergeService._detect_head_to_head(source_id, target_id)
        if head_to_head:
            raise ConflictError(
                "I due account hanno giocato l'uno contro l'altro "
                f"({', '.join(head_to_head)}): unione annullata. Risolvi "
                "manualmente quelle partite prima di riprovare."
            )

        # ---- FASE 2/3: reassign FK + cleanup tabelle a sola eliminazione ----
        reassigned = UserMergeService._reassign_foreign_keys(source_id, target_id)
        UserMergeService._delete_source_only_rows(source_id)

        # I bulk UPDATE core non sincronizzano l'identity map ORM: forziamo il
        # reload così i ricalcoli successivi vedono i record riassegnati.
        db.session.flush()
        db.session.expire_all()

        # ---- FASE 4/5: ricalcoli da zero ----
        UserMergeService._recalculate_elo()
        UserMergeService._recalculate_classifications(target_id)
        UserMergeService._rebuild_gamification(target_id)

        # ---- FASE 6: anonimizza la sorgente (libera username/email unique) ----
        source = db.session.get(User, source_id)
        if source is not None:
            source.anonymize()

        logger.info(
            "Merge utenti: %s → %s (eseguito da %s). Colonne riassegnate: %s",
            source_id,
            target_id,
            performed_by_id,
            reassigned,
        )
        return {
            "source_id": source_id,
            "target_id": target_id,
            "reassigned_columns": reassigned,
        }

    # ----------------------------------------------------------- head-to-head

    @staticmethod
    def _detect_head_to_head(source_id: int, target_id: int) -> List[str]:
        """Return labels of factual tables where source and target faced off."""
        found: List[str] = []

        def _pair(col_a, col_b):
            return or_(
                and_(col_a == source_id, col_b == target_id),
                and_(col_a == target_id, col_b == source_id),
            )

        # Standard tournament match
        from models.match.models import Match, TrioMatch

        if db.session.query(
            Match.query.filter(_pair(Match.player1_id, Match.player2_id)).exists()
        ).scalar():
            found.append("match")

        # Trio match: any two of the three slots being source & target
        trio_pairs = or_(
            _pair(TrioMatch.player1_id, TrioMatch.player2_id),
            _pair(TrioMatch.player1_id, TrioMatch.player3_id),
            _pair(TrioMatch.player2_id, TrioMatch.player3_id),
        )
        if db.session.query(TrioMatch.query.filter(trio_pairs).exists()).scalar():
            found.append("trio_match")

        # Individual (casual) match
        try:
            from models.individual_match.match_models import IndividualMatch

            if db.session.query(
                IndividualMatch.query.filter(
                    _pair(IndividualMatch.player1_id, IndividualMatch.player2_id)
                ).exists()
            ).scalar():
                found.append("individual_match")
        except ImportError:  # pragma: no cover
            pass

        # Tiebreaker match
        try:
            from models.tiebreaker.models import TiebreakerMatch

            if db.session.query(
                TiebreakerMatch.query.filter(
                    _pair(TiebreakerMatch.player1_id, TiebreakerMatch.player2_id)
                ).exists()
            ).scalar():
                found.append("tiebreaker")
        except ImportError:  # pragma: no cover
            pass

        return found

    # -------------------------------------------------------------- reassign

    @staticmethod
    def _user_fk_columns():
        """Yield (Table, Column) for every column referencing ``user.id``."""
        user_table = User.__table__
        for table in db.metadata.sorted_tables:
            for col in table.columns:
                for fk in col.foreign_keys:
                    if fk.column.table is user_table:
                        yield table, col

    @staticmethod
    def _is_constrained(table, col) -> bool:
        """True if ``col`` is part of the PK or any UNIQUE constraint/index."""
        if col.primary_key:
            return True
        if col.unique:
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
    def _reassign_foreign_keys(source_id: int, target_id: int) -> int:
        """Reassign every user FK from source to target.

        Constrained columns (PK/unique) are moved per-row with a savepoint and
        deleted on conflict (the target keeps its own row). Plain columns are
        moved with a single bulk UPDATE.
        """
        reassigned = 0
        for table, col in UserMergeService._user_fk_columns():
            if table.name == "user" or table.name in _DELETE_SOURCE_TABLES:
                continue
            if UserMergeService._is_constrained(table, col):
                UserMergeService._reassign_with_dedup(table, col, source_id, target_id)
            else:
                db.session.execute(
                    update(table).where(col == source_id).values({col.name: target_id})
                )
            reassigned += 1
        return reassigned

    @staticmethod
    def _reassign_with_dedup(table, col, source_id: int, target_id: int) -> None:
        """Move ``col`` from source to target one row at a time.

        On IntegrityError (the target already has an equivalent row, given a
        UNIQUE/PK that includes this column) the savepoint is rolled back and the
        source row is deleted instead.
        """
        pk_cols = list(table.primary_key.columns)
        rows = (
            db.session.execute(select(table).where(col == source_id)).mappings().all()
        )
        for row in rows:
            where = and_(*[pk == row[pk.name] for pk in pk_cols])
            try:
                with db.session.begin_nested():
                    db.session.execute(
                        update(table).where(where).values({col.name: target_id})
                    )
            except IntegrityError:
                db.session.execute(delete(table).where(where))

    @staticmethod
    def _delete_source_only_rows(source_id: int) -> None:
        """Delete the source's rows in tables we don't reassign (PlayerEncounter)."""
        from models.classification.models import PlayerEncounter

        db.session.query(PlayerEncounter).filter(
            or_(
                PlayerEncounter.player1_id == source_id,
                PlayerEncounter.player2_id == source_id,
            )
        ).delete(synchronize_session=False)

    # ------------------------------------------------------------- recompute

    @staticmethod
    def _recalculate_elo() -> None:
        from models.rating.calculation_service import RatingCalculationService

        RatingCalculationService.recalculate_all_elo()

    @staticmethod
    def _recalculate_classifications(target_id: int) -> None:
        """Recompute round/gara/campionato classifications for affected events.

        The aggregators read directly from match data (now attributed to the
        target), so recomputing rebuilds correct standings. Affected gare and
        campionati are derived from the target's matches, inscriptions and
        existing classification rows.
        """
        from models.match.models import Match
        from models.competition.models import Inscription, Gara
        from models.classification.models import (
            Classification,
            RoundClassification,
            GaraClassification,
        )
        from models.classification.gara_classification import (
            StrategyBasedClassificationService,
        )
        from models.classification.campionato_classification import (
            ClassificationService,
        )

        gara_ids: Set[int] = set()
        for m in Match.query.filter(
            or_(Match.player1_id == target_id, Match.player2_id == target_id)
        ).all():
            if m.gara_id:
                gara_ids.add(m.gara_id)
        for ins in Inscription.query.filter(Inscription.user_id == target_id).all():
            gara_ids.add(ins.gara_id)
        for rc in RoundClassification.query.filter(
            RoundClassification.user_id == target_id
        ).all():
            gara_ids.add(rc.gara_id)
        for gc in GaraClassification.query.filter(
            GaraClassification.user_id == target_id
        ).all():
            gara_ids.add(gc.gara_id)

        service = StrategyBasedClassificationService()
        campionato_ids: Set[int] = set()
        for gara_id in gara_ids:
            gara = db.session.get(Gara, gara_id)
            if gara is None:
                continue
            if gara.campionato_id:
                campionato_ids.add(gara.campionato_id)

            rounds = sorted(
                {
                    m.round_number
                    for m in Match.query.filter(Match.gara_id == gara_id).all()
                    if m.round_number is not None
                }
            )
            for round_number in rounds:
                service.calculate_round_classification(gara_id, round_number)
            if rounds:
                service.calculate_gara_classification(gara_id)

        for cid in {
            c.campionato_id
            for c in Classification.query.filter(
                Classification.user_id == target_id
            ).all()
        } | campionato_ids:
            ClassificationService.update_campionato_classification(cid)

    @staticmethod
    def _rebuild_gamification(target_id: int) -> None:
        from models.gamification.recalc_service import GamificationRecalcService

        GamificationRecalcService.rebuild_for_user(target_id)
