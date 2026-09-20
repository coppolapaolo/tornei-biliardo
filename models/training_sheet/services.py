"""Comporre una scheda di allenamento (ADR-067).

Una porta sola, ``save_composition``, come per l'esame: la sequenza arriva
**come deve risultare** e si scrive tutta insieme, o non si scrive. Comporre a
colpi di «aggiungi», «togli», «sposta» lascerebbe una scheda scritta a metà al
primo rifiuto, e una scheda scritta a metà è una seduta sbagliata.

Due regole che qui valgono più che altrove:

* una voce con delle registrazioni **si ritira, non si cancella** — e la
  differenza la vede chi rilegge il registro di tre mesi fa;
* la **versione** cresce quando cambia ciò che i numeri vogliono dire, e non
  quando si corregge un titolo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from flask_babel import gettext as _

from ..base import db
from ..challenge.models import Challenge
from ..exceptions import NotFoundError, PermissionDeniedError, ValidationError
from ..transaction.manager import transactional
from ..user.models import User
from .measure import MAX_AMOUNT, MAX_ITEMS, MIN_AMOUNT, SheetMeasure
from .models import TrainingSheet, TrainingSheetItem, TrainingSheetReader

#: Quanti livelli può avere una scala di schede. Nessuno ne usa cento, e un
#: numero incollato per sbaglio finirebbe stampato accanto al nome.
MAX_LEVEL = 99
#: Quante sedute di fila sopra la soglia si possono chiedere.
MAX_STREAK = 20
#: Quante settimane può durare un programma.
MAX_WEEKS = 52


@dataclass(frozen=True)
class SheetItemSpec:
    """Una voce come la manda la pagina: l'esercizio, e il suo «quanto farne».

    ``item_id`` dice che è una voce **già in questa scheda**, riconosciuta: è
    ciò che distingue lo spostare dal rifare. Senza, la voce è nuova — e due
    voci sullo stesso esercizio sono ammesse: il rastrello del riscaldamento e
    quello di fine seduta sono due righe del foglio.
    """

    challenge_id: int
    measure: SheetMeasure = SheetMeasure.MADE
    amount: Optional[int] = None
    per_variant: bool = False
    section: Optional[str] = None
    day: Optional[str] = None
    item_id: Optional[int] = None


class TrainingSheetService:
    """Le schede: crearle, comporle, leggerle, archiviarle."""

    # ────────────────────────────────────────────────────────────────────
    # Lookup e permessi
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def get_sheet(sheet_id: int) -> TrainingSheet:
        sheet = db.session.get(TrainingSheet, sheet_id)
        if sheet is None:
            raise NotFoundError(_("Scheda non trovata"))
        return sheet

    @staticmethod
    def can_edit(sheet: TrainingSheet, actor: Optional[User]) -> bool:
        """Compone solo chi la possiede.

        Un istruttore che legge la scheda **non** la cambia: guarda le sedute e
        dice la sua a voce. Aprire la composizione a chi legge vorrebbe dire
        che una mattina il tuo allenamento è diverso e non l'hai deciso tu.
        """
        return bool(actor and getattr(actor, "id", None) == sheet.owner_id)

    @staticmethod
    def can_read(sheet: TrainingSheet, actor: Optional[User]) -> bool:
        """La legge chi la possiede e chi ne ha avuto il permesso (D11)."""
        if TrainingSheetService.can_edit(sheet, actor):
            return True
        if actor is None or not getattr(actor, "id", None):
            return False
        return any(
            reader.user_id == actor.id and reader.is_current for reader in sheet.readers
        )

    @staticmethod
    def _require_edit(sheet: TrainingSheet, actor: Optional[User]) -> None:
        if not TrainingSheetService.can_edit(sheet, actor):
            raise PermissionDeniedError(_("Questa scheda non è tua"))

    @staticmethod
    def sheets_of(user_id: int) -> List[TrainingSheet]:
        """Le schede del giocatore, la più usata di recente per prima."""
        return (
            TrainingSheet.query.filter_by(owner_id=user_id, is_active=True)
            .order_by(TrainingSheet.updated_at.desc())
            .all()
        )

    # ────────────────────────────────────────────────────────────────────
    # Creare e archiviare
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="training_sheet")
    def create_sheet(actor: User, name: str) -> TrainingSheet:
        """Una scheda vuota, con un nome. Le voci si aggiungono componendola."""
        sheet = TrainingSheet(
            name=TrainingSheetService._clean_name(name), owner_id=actor.id
        )
        db.session.add(sheet)
        db.session.flush()
        return sheet

    @staticmethod
    @transactional(domain="training_sheet")
    def archive_sheet(sheet_id: int, actor: User) -> TrainingSheet:
        """Toglie la scheda dall'elenco senza cancellarne le sedute.

        Le sedute fatte sono il registro di qualcuno: restano. Stessa scelta di
        `delete_challenge`, e per lo stesso motivo.
        """
        sheet = TrainingSheetService.get_sheet(sheet_id)
        TrainingSheetService._require_edit(sheet, actor)
        sheet.is_active = False
        return sheet

    # ────────────────────────────────────────────────────────────────────
    # La composizione, tutta insieme
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="training_sheet")
    def save_composition(
        sheet_id: int,
        actor: User,
        *,
        name: str,
        items: Sequence[SheetItemSpec],
        level: Optional[int] = None,
        threshold: Optional[int] = None,
        threshold_streak: int = 1,
        weeks: Optional[int] = None,
        uses_days: bool = False,
    ) -> TrainingSheet:
        """Salva nome, opzioni e **l'intera sequenza**, tutto o niente.

        Chi non c'è più esce — ritirato se ha delle registrazioni —, chi è
        nuovo entra, chi resta prende posizione, misura e «quanto farne» che
        porta. Alla fine, se è cambiato ciò che i numeri vogliono dire, la
        versione sale di uno.
        """
        sheet = TrainingSheetService.get_sheet(sheet_id)
        TrainingSheetService._require_edit(sheet, actor)

        if len(items) > MAX_ITEMS:
            raise ValidationError(
                _("Una scheda arriva a %(n)s voci.", n=MAX_ITEMS),
            )

        prima = TrainingSheetService._fingerprint(sheet)

        sheet.name = TrainingSheetService._clean_name(name)
        sheet.level = TrainingSheetService._check_range(
            level, 1, MAX_LEVEL, _("Il livello va da 1 a %(n)s.", n=MAX_LEVEL)
        )
        sheet.threshold_streak = (
            TrainingSheetService._check_range(
                threshold_streak,
                1,
                MAX_STREAK,
                _("Le sedute di fila vanno da 1 a %(n)s.", n=MAX_STREAK),
            )
            or 1
        )
        sheet.weeks = TrainingSheetService._check_range(
            weeks, 1, MAX_WEEKS, _("Le settimane vanno da 1 a %(n)s.", n=MAX_WEEKS)
        )
        sheet.uses_days = bool(uses_days)

        TrainingSheetService._write_items(sheet, items)
        db.session.flush()

        # La soglia si controlla **dopo** le voci: è un numero che vive sul
        # totale, e un totale non c'è finché non c'è la sequenza.
        sheet.threshold = TrainingSheetService._check_threshold(sheet, threshold)

        if TrainingSheetService._fingerprint(sheet) != prima:
            sheet.version = (sheet.version or 1) + 1
        return sheet

    @staticmethod
    def _write_items(sheet: TrainingSheet, items: Sequence[SheetItemSpec]) -> None:
        esistenti = {item.id: item for item in sheet.items}
        tenute: set = set()

        # Prima si parcheggiano le posizioni sui negativi: l'unicità vale fra
        # le voci attive, e scriverle una per una farebbe collidere due voci
        # che si scambiano di posto (stessa passata doppia dell'esame).
        for item in sheet.items:
            if item.is_active:
                item.position = -abs(item.position or 1)
        db.session.flush()

        for posizione, spec in enumerate(items, start=1):
            voce = esistenti.get(spec.item_id) if spec.item_id else None
            if voce is not None and voce.sheet_id != sheet.id:
                raise ValidationError(_("Questa voce non è di questa scheda"))
            challenge = db.session.get(Challenge, spec.challenge_id)
            if challenge is None:
                raise NotFoundError(_("Esercizio non trovato"))

            measure = spec.measure
            amount = TrainingSheetService._check_amount(measure, spec.amount)
            per_variant = bool(spec.per_variant) and bool(challenge.variants)

            if voce is None:
                # Alla collezione, non alla sessione: `sheet.items` deve
                # essere in pari subito, perché il totale della scheda — e
                # quindi la soglia — si calcola da lì un attimo dopo.
                voce = TrainingSheetItem(position=posizione)
                sheet.items.append(voce)
            voce.challenge_id = challenge.id
            voce.position = posizione
            voce.section = (spec.section or "").strip() or None
            voce.day = (spec.day or "").strip() or None if sheet.uses_days else None
            voce.measure = measure.value
            voce.amount = amount
            voce.per_variant = per_variant
            voce.is_active = True
            db.session.flush()
            tenute.add(voce.id)

        for voce in list(sheet.items):
            if voce.id in tenute:
                continue
            if voce.entries:
                # Ritirata: le caselle già compilate restano leggibili, e la
                # voce non ricompare in nessuna seduta nuova.
                voce.is_active = False
                voce.position = abs(voce.position or 1)
            else:
                # `delete-orphan`: toglierla dalla collezione la cancella, e
                # la collezione resta quella vera anche prima del flush.
                sheet.items.remove(voce)
        db.session.flush()

    # ────────────────────────────────────────────────────────────────────
    # Lettori (D11) — l'interfaccia arriva con gli istruttori, fase 8
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="training_sheet")
    def add_reader(sheet_id: int, user_id: int, actor: User) -> TrainingSheetReader:
        """Apre la scheda a un altro: vale subito, senza attese (D18)."""
        sheet = TrainingSheetService.get_sheet(sheet_id)
        TrainingSheetService._require_edit(sheet, actor)
        if user_id == sheet.owner_id:
            raise ValidationError(_("La scheda è già tua"))
        lettore = db.session.get(User, user_id)
        if lettore is None or lettore.is_deleted:
            raise NotFoundError(_("Utente non trovato"))

        corrente = next(
            (r for r in sheet.readers if r.user_id == user_id and r.is_current), None
        )
        if corrente is not None:
            return corrente

        reader = TrainingSheetReader(sheet_id=sheet.id, user_id=user_id)
        db.session.add(reader)
        db.session.flush()
        return reader

    @staticmethod
    @transactional(domain="training_sheet")
    def remove_reader(sheet_id: int, user_id: int, actor: User) -> None:
        """Toglie il permesso. La riga resta: dice da quando a quando."""
        from ..base import utc_now

        sheet = TrainingSheetService.get_sheet(sheet_id)
        TrainingSheetService._require_edit(sheet, actor)
        for reader in sheet.readers:
            if reader.user_id == user_id and reader.is_current:
                reader.revoked_at = utc_now()

    @staticmethod
    def readers_of(sheet: TrainingSheet) -> List[TrainingSheetReader]:
        return [reader for reader in sheet.readers if reader.is_current]

    # ────────────────────────────────────────────────────────────────────
    # Convalide
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _clean_name(name: Optional[str]) -> str:
        pulito = (name or "").strip()
        if not pulito:
            raise ValidationError(_("La scheda vuole un nome"))
        return pulito[:120]

    @staticmethod
    def _check_range(
        value: Optional[int], minimo: int, massimo: int, messaggio: str
    ) -> Optional[int]:
        if value is None:
            return None
        if value < minimo or value > massimo:
            raise ValidationError(messaggio)
        return value

    @staticmethod
    def _check_amount(measure: SheetMeasure, amount: Optional[int]) -> Optional[int]:
        """Il «quanto farne»: obbligatorio, facoltativo o assente.

        Col punteggio è **assente** e non vuoto: quanto vale al massimo quella
        prova lo dice l'esercizio, e un secondo tetto accanto sarebbe il difetto
        dei due `max_score` (ADR-042) rifatto in casa d'altri.
        """
        if measure is SheetMeasure.SCORE:
            return None
        if amount is None:
            if measure.wants_amount:
                raise ValidationError(
                    _("Serve dire quanto farne: %(unita)s.", unita=str(measure.unit))
                )
            return None
        if amount < MIN_AMOUNT or amount > MAX_AMOUNT:
            raise ValidationError(
                _(
                    "Il «quanto farne» va da %(min)s a %(max)s.",
                    min=MIN_AMOUNT,
                    max=MAX_AMOUNT,
                )
            )
        return amount

    @staticmethod
    def _check_threshold(
        sheet: TrainingSheet, threshold: Optional[int]
    ) -> Optional[int]:
        if threshold is None:
            return None
        if threshold <= 0:
            raise ValidationError(_("La soglia è un numero positivo"))
        totale = sheet.total
        if totale == 0:
            raise ValidationError(
                _(
                    "Per una soglia serve almeno una voce «a riusciti»: "
                    "le altre non fanno totale."
                )
            )
        if threshold > totale:
            raise ValidationError(
                _(
                    "La soglia non può superare il totale della scheda, "
                    "che è %(n)s.",
                    n=totale,
                )
            )
        return threshold

    @staticmethod
    def _fingerprint(sheet: TrainingSheet) -> tuple:
        """Che cosa vogliono dire i numeri di questa scheda, oggi.

        Ci sono dentro le voci attive e il loro «quanto farne», non il nome né
        la soglia: correggere un titolo non è una versione nuova, aggiungere un
        esercizio sì.
        """
        return tuple(
            (item.id, item.position, item.measure, item.amount, item.per_variant)
            for item in sorted(sheet.active_items, key=lambda i: i.position or 0)
        )


__all__ = [
    "TrainingSheetService",
    "SheetItemSpec",
    "MAX_LEVEL",
    "MAX_STREAK",
    "MAX_WEEKS",
]
