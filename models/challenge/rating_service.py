"""Il voto di un giocatore a un esercizio (ADR-065, decisione D6).

Tre regole, e stanno tutte qui:

* **vota solo chi ha provato** — e «ha provato» è la stessa definizione del
  contatore sulla card (``popularity.has_tried``): un numero che dice «14
  giocatori» e un voto rifiutato a uno di quei quattordici sarebbe un difetto
  che nessun test di un lato solo vede;
* il voto va **da 1 a 5**, intero;
* **uno per giocatore**, e rivotare sostituisce. Si può anche togliere: chi ha
  toccato una stella per sbaglio non deve restare con un voto che non ha dato.

Il voto non entra (ancora) nei consigli: serve a scegliere, non a ordinare il
mondo — con tre voti per esercizio una media è un'opinione, non una misura.
"""

from __future__ import annotations

from typing import Optional

from flask_babel import gettext as _

from ..base import db
from ..exceptions import NotFoundError, PermissionDeniedError, ValidationError
from ..transaction.manager import transactional
from .models import Challenge, ChallengeRating
from .popularity import ChallengePopularity, has_tried, popularity_for

MIN_RATING = 1
MAX_RATING = 5


class ChallengeRatingService:
    @staticmethod
    def get(user_id: Optional[int], challenge_id: int) -> Optional[int]:
        """Il voto che questo giocatore ha dato, o ``None``."""
        if not user_id:
            return None
        riga = (
            db.session.query(ChallengeRating.rating)
            .filter_by(user_id=user_id, challenge_id=challenge_id)
            .first()
        )
        return riga[0] if riga else None

    @staticmethod
    def can_rate(user_id: Optional[int], challenge_id: int) -> bool:
        return bool(user_id) and has_tried(int(user_id or 0), challenge_id)

    @staticmethod
    @transactional(domain="challenge")
    def rate(user_id: int, challenge_id: int, rating: object) -> ChallengePopularity:
        """Dà o cambia il voto. Torna i numeri aggiornati dell'esercizio.

        Raises:
            NotFoundError: l'esercizio non esiste
            ValidationError: il voto non è un intero fra 1 e 5
            PermissionDeniedError: chi vota non ha mai concluso una prova
        """
        if db.session.get(Challenge, challenge_id) is None:
            raise NotFoundError(_("Esercizio non trovato"))
        try:
            valore = int(str(rating))
        except (TypeError, ValueError):
            raise ValidationError(_("Il voto è un numero da 1 a 5"))
        if isinstance(rating, bool) or not MIN_RATING <= valore <= MAX_RATING:
            raise ValidationError(_("Il voto è un numero da 1 a 5"))
        if not has_tried(user_id, challenge_id):
            raise PermissionDeniedError(
                _("Si vota un esercizio dopo averlo provato almeno una volta")
            )

        riga = (
            db.session.query(ChallengeRating)
            .filter_by(user_id=user_id, challenge_id=challenge_id)
            .first()
        )
        if riga is None:
            db.session.add(
                ChallengeRating(
                    user_id=user_id, challenge_id=challenge_id, rating=valore
                )
            )
        else:
            riga.rating = valore
        db.session.flush()
        return popularity_for([challenge_id])[challenge_id]

    @staticmethod
    @transactional(domain="challenge")
    def clear(user_id: int, challenge_id: int) -> ChallengePopularity:
        """Toglie il voto. Non averne uno non è un errore."""
        db.session.query(ChallengeRating).filter_by(
            user_id=user_id, challenge_id=challenge_id
        ).delete()
        db.session.flush()
        return popularity_for([challenge_id])[challenge_id]
