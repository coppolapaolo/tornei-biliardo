"""Le informazioni sulla partita: il link al video e la descrizione.

Un servizio solo per le due tabelle delle partite, perché la regola è la
stessa: sono informazioni **sulla** partita, non il suo risultato, quindi si
scrivono in ogni stato — il video arriva spesso giorni dopo la chiusura — e
non toccano punteggio, classifiche né ELO.

* **Sfida individuale** (`IndividualMatch`): video e descrizione. Chi li
  scrive lo decide `IndividualMatch.can_edit_info`, il punto unico del
  permesso.
* **Partita di gara** (`Match`): solo il video. Lo scrivono i due giocatori
  (i tre, in un trio) e chi dirige la gara (`can_manage_competition`, che
  comprende l'admin).

Il link si valida e si normalizza in `utils/video_link.py`; la descrizione
qui, con :func:`normalize_description`, che usano anche l'avvio rapido e la
proposta.
"""

from __future__ import annotations

from typing import Any, Optional

from flask_babel import gettext as _

from ..base import db
from ..exceptions import NotFoundError, PermissionDeniedError, ValidationError
from ..transaction.manager import transactional

#: Una riga che dice che partita è, non un racconto.
DESCRIPTION_MAX_LENGTH = 200


def normalize_description(raw: Optional[str]) -> Optional[str]:
    """La descrizione pulita: spazi tolti, ``None`` se vuota.

    Solleva ``ValidationError`` oltre :data:`DESCRIPTION_MAX_LENGTH`
    caratteri: tagliarla in silenzio salverebbe una frase che nessuno ha
    scritto.
    """
    text = " ".join((raw or "").split())
    if not text:
        return None
    if len(text) > DESCRIPTION_MAX_LENGTH:
        raise ValidationError(
            _(
                "La descrizione può avere al massimo %(n)s caratteri.",
                n=DESCRIPTION_MAX_LENGTH,
            )
        )
    return text


def _is_player_of_gara_match(match: Any, user_id: int) -> bool:
    if match.is_player(user_id):
        return True
    trio = getattr(match, "trio_match", None)
    return trio is not None and user_id in (
        trio.player1_id,
        trio.player2_id,
        trio.player3_id,
    )


class MatchInfoService:
    """Scrive video e descrizione delle partite."""

    @staticmethod
    def can_edit_gara_match_video(match: Any, user: Any) -> bool:
        """I giocatori della partita e i direttori della sua gara."""
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        if _is_player_of_gara_match(match, user.id):
            return True
        return bool(match.gara_id and user.can_manage_competition(match.gara_id))

    @staticmethod
    @transactional(domain="individual_match")
    def update_individual_match_info(
        match_id: int,
        user: Any,
        video_url: Optional[str],
        description: Optional[str],
    ):
        """Riscrive video e descrizione della sfida; un campo vuoto li toglie.

        Entrambi si validano **prima** di scrivere: un link sbagliato non
        cancella quello buono, né salva a metà la descrizione.
        """
        from utils.video_link import normalize_video_url

        from ..individual_match.match_models import IndividualMatch

        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise NotFoundError(_("Sfida non trovata."))
        if not match.can_edit_info(user.id):
            raise PermissionDeniedError(
                _("Video e descrizione li scrivono i due giocatori della sfida.")
            )

        new_video = normalize_video_url(video_url)
        new_description = normalize_description(description)

        match.video_url = new_video
        match.description = new_description
        return match

    @staticmethod
    @transactional(domain="match")
    def update_gara_match_video(match_id: int, user: Any, video_url: Optional[str]):
        """Riscrive il video della partita di gara; un campo vuoto lo toglie."""
        from utils.video_link import normalize_video_url

        from .models import Match

        match = db.session.get(Match, match_id)
        if match is None:
            raise NotFoundError(_("Partita non trovata."))
        if not MatchInfoService.can_edit_gara_match_video(match, user):
            raise PermissionDeniedError(
                _(
                    "Il video lo scrivono i giocatori della partita "
                    "e i direttori della gara."
                )
            )

        match.video_url = normalize_video_url(video_url)
        return match
