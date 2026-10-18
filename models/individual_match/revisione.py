"""La revisione delle partite dopo il riscatto (emendamento del 2026-10-18).

Regola decisa dall'utente: «se qualcuno riscatta l'utente, allora gli si può
chiedere se vuole rivedere tutti i match passati ed eventualmente contestarne
alcuni oppure riconoscerli tutti oppure contestarli tutti. I match contestati
rimangono all'utente che li ha registrati come contestati e contribuiscono a
ELO solo nel calcolo più generale.»

Le partite da rivedere sono quelle che aspettano il **suo** riconoscimento:

* le sfide *registrate da uno* contro il giocatore non registrato che ha
  riscattato (`IndividualMatch.awaits_review_from`): riconoscerla la rende
  confermata da entrambi, contestarla la lascia a chi l'ha registrata, solo
  fra «Tutte» e nell'``ELO_ALL``, e la toglie dalle sue liste;
* le partite di altri due (ADR-084) in cui il non registrato era uno dei due
  giocatori e che aspettano la sua decisione: lì valgono le regole già in
  vigore, quindi riconoscere è **confermare** per sé e contestare è
  **rifiutare** — e un rifiuto basta, per tutti e due.

La revisione è **facoltativa e senza scadenza**: le partite non rivedute
restano come sono, *In attesa*, e non bloccano niente. Le partite di gara
restano fuori: le certifica il torneo.

**Quali partite erano del non registrato** (2026-10-18). Dopo l'unione non lo
dice più la partita: `ClaimService.approve` lo scrive prima, in
`ClaimRequestMatch`, e le partite di altri due compaiono solo se sono lì. Una
partita di altri due in cui l'utente era un giocatore dall'inizio la decide
dalla sua pagina, come sempre. Le sfide registrate da uno non ne hanno
bisogno: si chiudono così solo contro un non registrato, quindi una che
aspetta la revisione di un utente registrato viene per forza da un riscatto
(o da un'unione dell'admin). Per i riscatti approvati prima di quella data
la traccia non c'è: valgono le sole registrate da uno.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from flask_babel import gettext as _
from sqlalchemy import or_

from ..base import db
from ..exceptions import ValidationError
from ..status_enum import MatchStatus
from ..transaction.manager import transactional
from .match_models import IndividualMatch


@dataclass(frozen=True)
class EsitoRevisione:
    """Quante partite ha riconosciuto e quante ha contestato."""

    riconosciute: int
    contestate: int


class RevisioneService:
    """Chi deve rivedere cosa, e il gesto che lo fa."""

    @staticmethod
    def riscattate(user_id: int, richiesta_id: Optional[int] = None):
        """Sottoquery: gli id delle sfide che i riscatti di ``user_id`` gli
        hanno portato (`ClaimRequestMatch`), o quelle di una richiesta sola."""
        from models.status_enum import ClaimRequestStatus
        from models.user.claim_request import ClaimRequest, ClaimRequestMatch

        query = (
            db.session.query(ClaimRequestMatch.individual_match_id)
            .join(ClaimRequest, ClaimRequest.id == ClaimRequestMatch.request_id)
            .filter(
                ClaimRequest.claimant_id == user_id,
                ClaimRequest.status == ClaimRequestStatus.APPROVED.value,
            )
        )
        if richiesta_id is not None:
            query = query.filter(ClaimRequest.id == richiesta_id)
        return query

    @staticmethod
    def da_rivedere(
        user_id: int, richiesta_id: Optional[int] = None
    ) -> List[IndividualMatch]:
        """Le partite che aspettano il riconoscimento di ``user_id``.

        Le partite di altri due solo se erano del giocatore riscattato
        (`riscattate`); le registrate da uno sempre, perché vengono per forza
        da un non registrato. Con ``richiesta_id`` solo quelle di quel
        riscatto: l'invito conta le sue.

        Dalla più vecchia: si rivedono nell'ordine in cui sono state giocate.
        """
        riscattate = RevisioneService.riscattate(user_id, richiesta_id)
        registrata_da_uno = (
            (IndividualMatch.status == MatchStatus.CLOSED_UNILATERALLY)
            & IndividualMatch.recorded_by_id.isnot(None)
            & (IndividualMatch.recorded_by_id != user_id)
            & IndividualMatch.contested_at.is_(None)
        )
        if richiesta_id is not None:
            registrata_da_uno = registrata_da_uno & IndividualMatch.id.in_(riscattate)
        candidate = (
            IndividualMatch.query.filter(
                or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                ),
                or_(
                    # Registrata da uno, non ancora rivista.
                    registrata_da_uno,
                    # Partita di un terzo che aspetta la sua decisione, ed era
                    # del giocatore riscattato.
                    IndividualMatch.scorer_id.isnot(None)
                    & (IndividualMatch.status == MatchStatus.IN_PROGRESS)
                    & IndividualMatch.id.in_(riscattate),
                ),
            )
            .order_by(IndividualMatch.ended_at.asc(), IndividualMatch.id.asc())
            .all()
        )
        return [
            m
            for m in candidate
            if m.awaits_review_from(user_id)
            or (m.is_scored_by_third_party and m.awaits_decision_from(user_id))
        ]

    @staticmethod
    @transactional(domain="individual_match")
    def rivedi(
        user_id: int, rivedute: Iterable[int], contestate: Iterable[int]
    ) -> EsitoRevisione:
        """Riconosce le ``rivedute`` e contesta quelle fra le ``contestate``.

        ``rivedute`` sono le partite che chi rivede aveva davanti: riconoscere
        tutte, contestare tutte o sceglierne alcune sono la stessa chiamata
        con ``contestate`` vuota, piena o a metà. Una partita che nel
        frattempo non aspetta più la sua revisione si salta: non è più sua da
        decidere. Senza nessuna partita da decidere è un errore, perché il
        gesto non ha fatto niente.
        """
        from .pending_confirmation import avvisa_del_rifiuto

        da_contestare = {int(i) for i in contestate}
        richieste = {int(i) for i in rivedute} | da_contestare
        partite = [
            m for m in RevisioneService.da_rivedere(user_id) if m.id in richieste
        ]
        if not partite:
            raise ValidationError(_("Non ci sono partite da rivedere."))

        riconosciute = contestate_n = 0
        for partita in partite:
            contesta = partita.id in da_contestare
            if partita.is_scored_by_third_party:
                # ADR-084: contestare è rifiutare, riconoscere è confermare.
                if contesta:
                    partita.reject_as_player(user_id)
                    avvisa_del_rifiuto(partita, rifiutata_da=user_id)
                else:
                    partita.confirm_as_player(user_id)
            elif contesta:
                partita.contest_by(user_id)
                avvisa_della_contestazione(partita, user_id)
            else:
                partita.recognize_by(user_id)
            if contesta:
                contestate_n += 1
            else:
                riconosciute += 1
        db.session.flush()
        return EsitoRevisione(riconosciute=riconosciute, contestate=contestate_n)


def avvisa_della_contestazione(match: IndividualMatch, contestata_da: int) -> None:
    """A chi l'ha registrata: la sfida è contestata, e resta sua.

    Nella lingua di chi riceve (ADR-062): il testo si compone da lì.
    """
    from flask_babel import lazy_gettext as _l

    from models.notification.models import NotificationPriority, NotificationType
    from models.notification.services import NotificationService

    from .pending_confirmation import pagina_della_sfida

    if match.recorded_by_id is None:
        return
    chi = match.player1 if contestata_da == match.player1_id else match.player2
    nome = chi.username if chi is not None else ""
    mio, suo = (
        (match.player1_score, match.player2_score)
        if match.recorded_by_id == match.player1_id
        else (match.player2_score, match.player1_score)
    )
    NotificationService.create_notification(
        user_id=match.recorded_by_id,
        notification_type=NotificationType.MATCH_CANCELLED,
        title=_l("Sfida contestata"),
        message=_l(
            "%(nome)s ha contestato la sfida che avevi registrato (%(mio)s-%(suo)s): "
            "resta fra le tue partite, contestata, e conta solo fra «Tutte».",
            nome=nome,
            mio=mio,
            suo=suo,
        ),
        priority=NotificationPriority.NORMAL,
        related_entities={"individual_match_id": match.id},
        action_url=pagina_della_sfida(match),
        action_text=_l("Apri la sfida"),
    )


__all__ = ["EsitoRevisione", "RevisioneService", "avvisa_della_contestazione"]
