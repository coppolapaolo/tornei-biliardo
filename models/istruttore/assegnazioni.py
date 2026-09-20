"""Proporre una scheda a un allievo, e prenderla (ADR-071, fase 8d).

Il gesto ha due metà, e la seconda è dell'altro: l'istruttore **propone**, e la
scheda nasce solo quando l'allievo **accetta** — sua, con lui proprietario.
Nessuna riga di qui dentro apre niente: il permesso di lettura resta una riga
di `training_sheet_reader`, e l'allievo lo dà nello stesso modulo con cui
accetta, o non lo dà e tiene la scheda lo stesso.

Tre regole, e tutte e tre discendono dall'ADR-069.

1. **Si propone solo a chi ti è già allievo** — a chi ti ha già aperto una
   scheda. La prima mossa resta dell'altro, sempre: la stessa frase che vale
   per i gruppi (ADR-070 §1), e qui vale di più, perché una proposta è un
   messaggio che arriva a qualcuno che spesso è minorenne.
2. **Si propone una scheda tua.** Girare a un allievo la scheda di un altro
   allievo sarebbe far passare il contenuto di uno per le mani dell'altro.
3. **Una proposta in attesa per volta**, per coppia (istruttore, allievo), e a
   imporlo è l'indice unico parziale — non un `if`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from flask_babel import gettext as _

from ..base import db, utc_now
from ..exceptions import ConflictError, NotFoundError, PermissionDeniedError
from ..training_sheet.measure import SheetMeasure
from ..training_sheet.models import TrainingSheet
from ..training_sheet.services import SheetItemSpec, TrainingSheetService
from ..transaction.manager import transactional
from ..user.models import User
from .models import EsitoProposta, TrainingAssignment
from .viste import allievi_di

#: Quanto può essere lungo il messaggio che accompagna la proposta. Due righe:
#: è un biglietto attaccato alla scheda, non la lezione.
MAX_MESSAGGIO = 500


class AssegnazioneService:
    """Le proposte di scheda: farle, prenderle, rifiutarle, ritirarle."""

    # ────────────────────────────────────────────────────────────────────
    # Letture
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def proposte_per(user_id: int) -> List[TrainingAssignment]:
        """Le proposte che aspettano una risposta da questo giocatore."""
        return (
            TrainingAssignment.query.filter(
                TrainingAssignment.user_id == user_id,
                TrainingAssignment.closed_at.is_(None),
            )
            .order_by(TrainingAssignment.proposed_at.asc())
            .all()
        )

    @staticmethod
    def attese_di(instructor_id: int) -> Dict[int, TrainingAssignment]:
        """Per ogni allievo, la proposta che gli hai fatto e che non ha risposto.

        Una query per l'intera pagina «I miei allievi», e non una per riga.
        """
        righe = TrainingAssignment.query.filter(
            TrainingAssignment.instructor_id == instructor_id,
            TrainingAssignment.closed_at.is_(None),
        ).all()
        return {riga.user_id: riga for riga in righe}

    @staticmethod
    def get_proposta(assignment_id: int) -> TrainingAssignment:
        proposta = db.session.get(TrainingAssignment, assignment_id)
        if proposta is None:
            raise NotFoundError(_("Questa proposta non esiste"))
        return proposta

    # ────────────────────────────────────────────────────────────────────
    # Proporre
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="istruttore")
    def proponi(
        actor: User,
        source_sheet_id: int,
        user_ids: Sequence[int],
        *,
        messaggio: Optional[str] = None,
        group_id: Optional[int] = None,
        promuove: Optional[Dict[int, int]] = None,
    ) -> List[TrainingAssignment]:
        """Propone la scheda a uno o più allievi. Torna quelle **nate**.

        Chi ha già una proposta tua in attesa viene **saltato**, non rifiutato:
        mandarne una seconda non aggiungerebbe niente, e far fallire l'invio a
        tutto un gruppo per uno che non ha ancora risposto sarebbe peggio. Chi
        chiama confronta i due numeri e lo dice.

        ``promuove`` è «dagli il livello successivo»: per ogni allievo, quale
        sua scheda questa proposta promuove. Una mappa e non un solo id perché
        la stessa chiamata serve un gruppo, dove ciascuno ha la **sua** scheda
        da promuovere anche se la scheda nuova è una per tutti.
        """
        AssegnazioneService._require_istruttore(actor)
        modello = AssegnazioneService._modello(source_sheet_id, actor)
        testo = AssegnazioneService._messaggio(messaggio)

        allievi = {legame.persona.id for legame in allievi_di(actor.id)}
        estranei = [uid for uid in user_ids if uid not in allievi]
        if estranei:
            raise ConflictError(
                _("Puoi dare una scheda solo a chi te ne ha aperta una")
            )

        gia_in_attesa = AssegnazioneService.attese_di(actor.id)
        nate: List[TrainingAssignment] = []
        for user_id in dict.fromkeys(user_ids):
            if user_id in gia_in_attesa:
                continue
            proposta = TrainingAssignment(
                instructor_id=actor.id,
                user_id=user_id,
                source_sheet_id=modello.id,
                group_id=group_id,
                message=testo,
                promotes_sheet_id=AssegnazioneService._promossa(
                    (promuove or {}).get(user_id), user_id, actor
                ),
            )
            db.session.add(proposta)
            db.session.flush()
            AssegnazioneService._avvisa_proposta(proposta, modello, actor)
            nate.append(proposta)
        return nate

    @staticmethod
    @transactional(domain="istruttore")
    def ritira(assignment_id: int, actor: User) -> TrainingAssignment:
        """L'istruttore si riprende una proposta che nessuno ha ancora aperto.

        Senza avviso: era un invito, e ritirarlo prima che l'altro risponda non
        è una notizia — è non aver detto niente.
        """
        proposta = AssegnazioneService.get_proposta(assignment_id)
        if proposta.instructor_id != getattr(actor, "id", None):
            raise NotFoundError(_("Questa proposta non esiste"))
        AssegnazioneService._chiudi(proposta, EsitoProposta.WITHDRAWN)
        return proposta

    # ────────────────────────────────────────────────────────────────────
    # Rispondere
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="istruttore")
    def accetta(
        assignment_id: int,
        actor: User,
        *,
        apri_lettura: bool = True,
        archivia_promossa: bool = False,
    ) -> TrainingSheet:
        """Fa nascere la scheda dell'allievo, copiando il modello com'è oggi.

        La copia è una scheda come tutte: nasce con ``create_sheet`` e si
        compone con ``save_composition``, cioè passa dalle stesse convalide di
        una composta a mano. Da quel momento è sua e basta — se l'istruttore
        domani cambia il modello, questa non si muove.

        ``apri_lettura`` è la casella del modulo: spuntata apre la scheda a chi
        l'ha proposta, e si toglie quando si vuole da «Chi la legge».

        ``archivia_promossa`` è la seconda casella, e compare solo quando la
        proposta è un passaggio di livello: mette nello storico la scheda
        superata. Le sedute fatte restano — è un'archiviazione, non una
        cancellazione — e resta una scelta sua, perché la scheda è sua.
        """
        proposta = AssegnazioneService._mia(assignment_id, actor)
        modello = proposta.source_sheet
        if modello is None or not modello.active_items:
            raise ConflictError(_("Questa scheda non esiste più"))

        nata = AssegnazioneService._copia(modello, actor)
        proposta.sheet_id = nata.id
        AssegnazioneService._chiudi(proposta, EsitoProposta.ACCEPTED)

        istruttore = proposta.instructor
        aperta = bool(
            apri_lettura and istruttore is not None and istruttore.is_instructor
        )
        if aperta:
            # `avvisa=False`: l'avviso lo manda `_avvisa_risposta`, che sa dire
            # in una frase sola cos'è successo — presa, e te la fa leggere.
            TrainingSheetService.add_reader(nata.id, istruttore.id, actor, avvisa=False)
        promossa = proposta.promotes_sheet
        if archivia_promossa and promossa is not None and promossa.owner_id == actor.id:
            TrainingSheetService.archive_sheet(promossa.id, actor)

        AssegnazioneService._avvisa_risposta(proposta, actor, presa=True, letta=aperta)
        return nata

    @staticmethod
    @transactional(domain="istruttore")
    def rifiuta(assignment_id: int, actor: User) -> TrainingAssignment:
        """«No, grazie»: non nasce niente, e chi l'ha proposta lo sa."""
        proposta = AssegnazioneService._mia(assignment_id, actor)
        AssegnazioneService._chiudi(proposta, EsitoProposta.DECLINED)
        AssegnazioneService._avvisa_risposta(proposta, actor, presa=False)
        return proposta

    # ────────────────────────────────────────────────────────────────────
    # Dentro
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _copia(modello: TrainingSheet, allievo: User) -> TrainingSheet:
        """Una scheda nuova dell'allievo, con la sequenza del modello.

        Non si copiano né i lettori né ``readers_see_notes``: chi legge una
        scheda e chi ne legge le note sono due decisioni del proprietario, e il
        proprietario qui è un altro (ADR-069).
        """
        nata = TrainingSheetService.create_sheet(allievo, modello.name)
        TrainingSheetService.save_composition(
            nata.id,
            allievo,
            name=modello.name,
            items=[
                SheetItemSpec(
                    challenge_id=voce.challenge_id,
                    measure=SheetMeasure.parse(voce.measure),
                    amount=voce.amount,
                    per_variant=voce.per_variant,
                    section=voce.section,
                    day=voce.day,
                )
                for voce in modello.active_items
            ],
            level=modello.level,
            threshold=modello.threshold,
            threshold_streak=modello.threshold_streak or 1,
            weeks=modello.weeks,
            uses_days=bool(modello.uses_days),
            # Anche «chi sancisce il gradino» si copia: un maestro che compone
            # la sua scala dichiarando «lo confermo io» se la ritrova su tutte
            # le copie, senza doverlo ripetere a ciascuno.
            level_up=modello.level_up_kind,
        )
        return nata

    @staticmethod
    def _chiudi(proposta: TrainingAssignment, esito: EsitoProposta) -> None:
        if not proposta.is_pending:
            raise ConflictError(_("A questa proposta hai già risposto"))
        proposta.closed_at = utc_now()
        proposta.outcome = esito.value
        db.session.flush()

    @staticmethod
    def _mia(assignment_id: int, actor: User) -> TrainingAssignment:
        """La proposta, se è indirizzata a chi sta rispondendo.

        `NotFoundError` e non `PermissionDeniedError`: la proposta fatta a un
        altro non è cosa da negare, è cosa da non sapere.
        """
        proposta = AssegnazioneService.get_proposta(assignment_id)
        if proposta.user_id != getattr(actor, "id", None):
            raise NotFoundError(_("Questa proposta non esiste"))
        return proposta

    @staticmethod
    def _require_istruttore(actor: Optional[User]) -> None:
        if actor is None or not getattr(actor, "is_instructor", False):
            raise PermissionDeniedError(_("Le schede le propone un istruttore"))

    @staticmethod
    def _modello(sheet_id: int, actor: User) -> TrainingSheet:
        """La scheda da cui si copia: tua, e con qualcosa dentro."""
        modello = TrainingSheetService.get_sheet(sheet_id)
        if modello.owner_id != actor.id:
            raise PermissionDeniedError(_("Si propone una scheda tua"))
        if not modello.active_items:
            raise ConflictError(_("Questa scheda è ancora vuota: componila prima"))
        return modello

    @staticmethod
    def _promossa(sheet_id: Optional[int], user_id: int, actor: User) -> Optional[int]:
        """La scheda che la proposta promuove: sua, e che tu leggi davvero.

        Se non torna, non si solleva: la proposta parte lo stesso senza il
        legame. Il gradino è il **timbro**, che è un gesto suo e già avvenuto;
        questo è il secondo gesto, e perderne il riferimento non deve far
        fallire il dono della scheda nuova.
        """
        if not sheet_id:
            return None
        promossa = db.session.get(TrainingSheet, sheet_id)
        if promossa is None or promossa.owner_id != user_id:
            return None
        if not TrainingSheetService.can_read(promossa, actor):
            return None
        return promossa.id

    @staticmethod
    def _messaggio(testo: Optional[str]) -> Optional[str]:
        pulito = (testo or "").strip()
        return pulito[:MAX_MESSAGGIO] or None

    # ────────────────────────────────────────────────────────────────────
    # Gli avvisi (ADR-062: testi da comporre, non tradotti da chi preme)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _avvisa_proposta(
        proposta: TrainingAssignment, modello: TrainingSheet, istruttore: User
    ) -> None:
        from flask_babel import lazy_gettext as _l

        from ..notification.models import NotificationPriority, NotificationType
        from ..notification.services import NotificationService

        NotificationService.create_notification(
            user_id=proposta.user_id,
            notification_type=NotificationType.SHEET_PROPOSED,
            title=_l("Un istruttore ti propone una scheda"),
            message=_l(
                "%(istruttore)s ti propone «%(scheda)s». Decidi tu se prenderla.",
                istruttore=istruttore.username,
                scheda=modello.name,
            ),
            priority=NotificationPriority.NORMAL,
            action_url=f"/schede/proposte/{proposta.id}",
            action_text=_l("Guarda la scheda"),
            related_entities={"assignment_id": proposta.id},
        )

    @staticmethod
    def _avvisa_risposta(
        proposta: TrainingAssignment, allievo: User, *, presa: bool, letta: bool = False
    ) -> None:
        from flask_babel import lazy_gettext as _l

        from ..notification.models import NotificationPriority, NotificationType
        from ..notification.services import NotificationService

        if presa:
            titolo = _l("Un allievo ha preso la tua scheda")
            nome = proposta.source_sheet.name if proposta.source_sheet else ""
            testo = (
                _l(
                    "%(allievo)s ha preso «%(scheda)s» e te la fa leggere.",
                    allievo=allievo.username,
                    scheda=nome,
                )
                if letta
                else _l(
                    "%(allievo)s ha preso «%(scheda)s». Non te la fa leggere.",
                    allievo=allievo.username,
                    scheda=nome,
                )
            )
        else:
            titolo = _l("Un allievo ha detto di no")
            testo = _l(
                "%(allievo)s non ha preso «%(scheda)s».",
                allievo=allievo.username,
                scheda=proposta.source_sheet.name if proposta.source_sheet else "",
            )

        NotificationService.create_notification(
            user_id=proposta.instructor_id,
            notification_type=NotificationType.SHEET_ANSWERED,
            title=titolo,
            message=testo,
            priority=NotificationPriority.LOW,
            action_url="/istruttore/allievi",
            action_text=_l("I miei allievi"),
            related_entities={"assignment_id": proposta.id},
        )


__all__ = ["AssegnazioneService", "MAX_MESSAGGIO"]
