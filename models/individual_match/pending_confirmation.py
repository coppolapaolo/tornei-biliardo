"""Sfide a due che aspettano la conferma di un giocatore (2026-09-14).

Una sfida a due si chiude con la **doppia conferma** dei giocatori (ADR-051).
Quando si raggiunge la distanza chi vince firma d'ufficio
(``IndividualRackService.add_rack_for_player``); nel formato libero firma chi
preme «Termina». Da quel momento la partita aspetta la firma dell'altro — ed è
lì che resta, quando l'altro non la dà mai.

Regole, decise dall'utente il 2026-09-14 (``SPECIFICHE.md``, nota datata):

* **dashboard** — passato un giorno dalla prima firma
  (:data:`DASHBOARD_GRACE`), la partita non compare più fra le sfide in corso
  della dashboard, né per chi deve firmare né per chi aspetta. Resta
  nell'elenco delle sfide con lo stato «In attesa di conferma»;
* **blocco** — chi ha almeno una partita che aspetta la **sua** firma non può
  lanciare né accettare altre sfide individuali finché non la conferma o la
  rifiuta. Il blocco scatta subito, non dopo un giorno: il giorno riguarda
  solo la dashboard. Chi aspetta non è mai bloccato per questo.

«Aspetta la firma di X» vuol dire: partita in corso, pronta per la validazione,
l'avversario ha già confermato e X no. Una partita senza nessuna firma non
aspetta nessuno in particolare: nel formato libero è «pronta» fin dal primo
triangolo, mentre i due stanno ancora giocando.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from flask_babel import ngettext
from sqlalchemy import and_, or_

from ..base import utc_now
from ..exceptions import ConflictError
from ..status_enum import MatchStatus
from .match_models import IndividualMatch

#: Quanto resta in dashboard una partita che aspetta una conferma, contato
#: dalla prima firma.
DASHBOARD_GRACE = timedelta(hours=24)


class PendingConfirmationError(ConflictError):
    """Il giocatore ha partite da confermare prima di altre sfide (HTTP 409).

    ``match_ids`` elenca le partite che aspettano la sua firma: la route le usa
    per proporgli di chiuderle invece di un errore secco.
    """

    def __init__(self, match_ids: List[int], message: Optional[str] = None):
        self.match_ids = list(match_ids)
        if message is None:
            message = ngettext(
                "Hai una partita che aspetta la tua conferma: confermala o "
                "rifiutala prima di altre sfide.",
                "Hai %(num)d partite che aspettano la tua conferma: confermale o "
                "rifiutale prima di altre sfide.",
                len(self.match_ids),
            )
        super().__init__(message)


class PendingConfirmationService:
    """Chi deve firmare cosa, e cosa ne consegue."""

    @staticmethod
    def pending_for(user_id: int) -> List[IndividualMatch]:
        """Le partite che aspettano la firma di ``user_id``, dalla più vecchia."""
        candidate = (
            IndividualMatch.query.filter(
                IndividualMatch.status == MatchStatus.IN_PROGRESS,
                or_(
                    and_(
                        IndividualMatch.player1_id == user_id,
                        IndividualMatch.player2_confirmed.is_(True),
                        IndividualMatch.player1_confirmed.is_(False),
                    ),
                    and_(
                        IndividualMatch.player2_id == user_id,
                        IndividualMatch.player1_confirmed.is_(True),
                        IndividualMatch.player2_confirmed.is_(False),
                    ),
                ),
            )
            .order_by(IndividualMatch.id.asc())
            .all()
        )
        # Il filtro SQL guarda le firme; «pronta per la validazione» dipende
        # dalla distanza effettiva (Distance VO), e si chiede al modello.
        return [m for m in candidate if m.awaiting_confirmation_from_id == user_id]

    @staticmethod
    def ensure_none_pending(user_id: int) -> None:
        """Solleva :class:`PendingConfirmationError` se qualcuna aspetta lui."""
        pending = PendingConfirmationService.pending_for(user_id)
        if pending:
            raise PendingConfirmationError([m.id for m in pending])

    @staticmethod
    def is_hidden_from_dashboard(
        match: IndividualMatch, now: Optional[datetime] = None
    ) -> bool:
        """Vero se la partita aspetta una firma da più di un giorno.

        Vale per entrambi i giocatori: per chi aspetta non c'è niente da fare,
        per chi deve firmare il promemoria è il blocco sulle sfide nuove.
        Senza l'orario della prima firma (righe antecedenti alla colonna) il
        giorno non si può contare, e la partita resta visibile.
        """
        since = match.awaiting_confirmation_since
        if since is None:
            return False
        return (now or utc_now()) - since > DASHBOARD_GRACE


__all__ = [
    "DASHBOARD_GRACE",
    "PendingConfirmationError",
    "PendingConfirmationService",
]
