"""Comporre i gruppi di allievi: creare, riempire, spostare, chiudere.

Le regole sono tre, e tutte e tre discendono dall'ADR-069.

1. **Li fa solo chi è istruttore.** Non perché il gruppo apra qualcosa — non
   apre niente — ma perché è l'attrezzo di un mestiere, e chi non lo fa non ha
   allievi da ordinare.
2. **Ci si mette solo chi ti ha già aperto una scheda.** Un gruppo non è un
   modo per ottenere l'accesso: è un modo per ordinare chi te l'ha già dato.
   Se fosse possibile aggiungere chiunque, il gruppo diventerebbe una richiesta
   che l'altro non ha mai accettato.
3. **Niente si cancella.** Si esce con una data, e chiudere un corso fa uscire
   chi c'era dentro — il giorno in cui il corso è finito.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from flask_babel import gettext as _

from ..base import db, utc_now
from ..exceptions import ConflictError, NotFoundError, PermissionDeniedError
from ..transaction.manager import transactional
from ..user.models import User
from .models import TrainingGroup, TrainingGroupMember
from .viste import allievi_di

#: Lunghezza massima del nome, come per le schede.
MAX_NOME = 120


class GruppoService:
    """I gruppi di un istruttore. Nessuno di questi metodi dà accesso a nulla."""

    # ────────────────────────────────────────────────────────────────────
    # Letture
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def gruppi_di(
        instructor_id: int, *, aperti: Optional[bool] = None
    ) -> List[TrainingGroup]:
        """I gruppi di questo istruttore, i più recenti per primi.

        ``aperti=True`` sono quelli in corso, ``False`` lo storico, ``None``
        tutti. L'ordine è per data d'inizio, e a parità per id: due corsi
        cominciati lo stesso giorno restano nell'ordine in cui sono nati, che
        è l'unico che non cambia sotto gli occhi di chi guarda.
        """
        query = TrainingGroup.query.filter(TrainingGroup.instructor_id == instructor_id)
        if aperti is True:
            query = query.filter(TrainingGroup.closed_at.is_(None))
        elif aperti is False:
            query = query.filter(TrainingGroup.closed_at.isnot(None))
        return query.order_by(
            TrainingGroup.started_on.desc().nullslast(),
            TrainingGroup.id.desc(),
        ).all()

    @staticmethod
    def get_gruppo(group_id: int) -> TrainingGroup:
        gruppo = db.session.get(TrainingGroup, group_id)
        if gruppo is None:
            raise NotFoundError(_("Questo gruppo non esiste"))
        return gruppo

    @staticmethod
    def iscrizioni_correnti(instructor_id: int) -> Dict[int, TrainingGroupMember]:
        """Per ogni allievo, il gruppo in cui sta adesso.

        Una query sola, e non una per allievo: la pagina «I miei allievi» la
        chiama una volta e poi cerca in memoria. L'indice unico parziale
        garantisce che la chiave non si sovrascriva mai — un allievo sta in un
        gruppo solo per volta.
        """
        righe = (
            TrainingGroupMember.query.filter(
                TrainingGroupMember.instructor_id == instructor_id,
                TrainingGroupMember.left_at.is_(None),
            )
            .order_by(TrainingGroupMember.joined_at.asc())
            .all()
        )
        return {riga.user_id: riga for riga in righe}

    @staticmethod
    def membri_passati(group: TrainingGroup) -> List[TrainingGroupMember]:
        """Chi c'è stato e non c'è più, dall'uscita più recente."""
        usciti = [m for m in group.members if m.left_at is not None]
        return sorted(usciti, key=lambda m: m.left_at, reverse=True)

    # ────────────────────────────────────────────────────────────────────
    # Scritture
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="istruttore")
    def crea(
        actor: User,
        nome: str,
        dal: Optional[date] = None,
        al: Optional[date] = None,
    ) -> TrainingGroup:
        """Un gruppo nuovo, vuoto. Gli allievi si aggiungono dopo."""
        GruppoService._require_istruttore(actor)
        gruppo = TrainingGroup(
            instructor_id=actor.id,
            name=GruppoService._nome(nome),
            started_on=dal,
            ended_on=al,
        )
        GruppoService._check_periodo(gruppo.started_on, gruppo.ended_on)
        db.session.add(gruppo)
        db.session.flush()
        return gruppo

    @staticmethod
    @transactional(domain="istruttore")
    def aggiorna(
        group_id: int,
        actor: User,
        *,
        nome: Optional[str] = None,
        dal: Optional[date] = None,
        al: Optional[date] = None,
    ) -> TrainingGroup:
        """Nome e periodo. Le date arrivano sempre tutte e due dal modulo.

        Cambiare il calendario **non** apre né chiude niente: scrivere «al
        15/12» a settembre dichiara quando il corso finirà, e un corso che
        finisce fra tre mesi è in corso adesso. Si chiude con `chiudi`.
        """
        gruppo = GruppoService._mio(group_id, actor)
        if nome is not None:
            gruppo.name = GruppoService._nome(nome)
        gruppo.started_on = dal
        gruppo.ended_on = al
        GruppoService._check_periodo(gruppo.started_on, gruppo.ended_on)
        return gruppo

    @staticmethod
    @transactional(domain="istruttore")
    def chiudi(group_id: int, actor: User) -> TrainingGroup:
        """Chiude il corso oggi, e con lui le iscrizioni di chi c'era.

        Le righe restano: dicono chi c'era e fino a quando.

        Se sul calendario il corso finiva **più in là**, la data si sposta a
        oggi: chiuderlo lo fa finire davvero, e lasciare «al 15/12» su un corso
        chiuso a ottobre scriverebbe nello storico una data mai avvenuta. Una
        data già passata invece si tiene — è quella giusta.
        """
        gruppo = GruppoService._mio(group_id, actor)
        if not gruppo.is_open:
            raise ConflictError(_("Questo gruppo è già chiuso"))
        adesso = utc_now()
        oggi = adesso.date()
        gruppo.closed_at = adesso
        if gruppo.ended_on is None or gruppo.ended_on > oggi:
            gruppo.ended_on = oggi
        GruppoService._fai_uscire_tutti(gruppo, quando=oggi)
        return gruppo

    @staticmethod
    @transactional(domain="istruttore")
    def aggiungi(group_id: int, actor: User, user_id: int) -> TrainingGroupMember:
        """Mette un allievo nel gruppo, togliendolo da quello in cui era.

        «Sposta» non è un comando a parte: mettere qualcuno in un gruppo lo
        toglie dall'altro, perché in due non può stare — e chiedere di
        toglierlo prima sarebbe un passo in più per dire la stessa cosa.
        """
        gruppo = GruppoService._mio(group_id, actor)
        if not gruppo.is_open:
            raise ConflictError(
                _("Questo gruppo è chiuso: riaprilo, o mettilo in uno in corso")
            )
        if not GruppoService._e_un_allievo(actor.id, user_id):
            raise ConflictError(
                _("Puoi mettere in un gruppo solo chi ti ha aperto una scheda")
            )

        corrente = GruppoService.iscrizioni_correnti(actor.id).get(user_id)
        if corrente is not None:
            if corrente.group_id == group_id:
                return corrente
            corrente.left_at = utc_now()
            # Prima di aprire la riga nuova: l'indice unico parziale vede le
            # due righe insieme, e senza questo la seconda verrebbe rifiutata.
            db.session.flush()

        membro = TrainingGroupMember(
            group_id=gruppo.id,
            instructor_id=actor.id,
            user_id=user_id,
        )
        db.session.add(membro)
        db.session.flush()
        return membro

    @staticmethod
    @transactional(domain="istruttore")
    def togli(group_id: int, actor: User, user_id: int) -> None:
        """L'allievo esce dal gruppo. Le sue schede non cambiano di una virgola."""
        gruppo = GruppoService._mio(group_id, actor)
        for membro in gruppo.active_members:
            if membro.user_id == user_id:
                membro.left_at = utc_now()
                return
        raise NotFoundError(_("Questo allievo non fa parte del gruppo"))

    # ────────────────────────────────────────────────────────────────────
    # Dentro
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _require_istruttore(actor: Optional[User]) -> None:
        if actor is None or not getattr(actor, "is_instructor", False):
            raise PermissionDeniedError(_("I gruppi sono dell'istruttore"))

    @staticmethod
    def _mio(group_id: int, actor: User) -> TrainingGroup:
        """Il gruppo, se è di chi sta chiedendo. Altrimenti non esiste.

        `NotFoundError` e non `PermissionDeniedError`: i gruppi di un altro
        istruttore non sono cosa da negare, sono cosa da non sapere.
        """
        GruppoService._require_istruttore(actor)
        gruppo = GruppoService.get_gruppo(group_id)
        if gruppo.instructor_id != actor.id:
            raise NotFoundError(_("Questo gruppo non esiste"))
        return gruppo

    @staticmethod
    def _e_un_allievo(instructor_id: int, user_id: int) -> bool:
        """Se questa persona ti ha aperto almeno una scheda, adesso."""
        return any(legame.persona.id == user_id for legame in allievi_di(instructor_id))

    @staticmethod
    def _fai_uscire_tutti(gruppo: TrainingGroup, quando: date) -> None:
        """Data l'uscita a chi è ancora dentro, col giorno di chiusura.

        L'ora è quella corrente e la data quella del corso: `left_at` è un
        `DateTime`, e inventare mezzanotte renderebbe l'uscita anteriore
        all'ingresso per chi fosse entrato lo stesso giorno.
        """
        adesso = utc_now()
        uscita = (
            adesso
            if quando >= adesso.date()
            else adesso.replace(year=quando.year, month=quando.month, day=quando.day)
        )
        for membro in gruppo.active_members:
            membro.left_at = max(uscita, membro.joined_at)

    @staticmethod
    def _nome(nome: Optional[str]) -> str:
        pulito = (nome or "").strip()
        if not pulito:
            raise ConflictError(_("Il gruppo ha bisogno di un nome"))
        return pulito[:MAX_NOME]

    @staticmethod
    def _check_periodo(dal: Optional[date], al: Optional[date]) -> None:
        if dal is not None and al is not None and al < dal:
            raise ConflictError(_("Il corso non può finire prima di cominciare"))


__all__ = ["GruppoService", "MAX_NOME"]
