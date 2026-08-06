"""Onboarding obbligatorio (ADR-035).

Service che materializza il completamento dell'onboarding: salva la città home
(fallback prossimità ADR-034), crea le disponibilità per sala (ADR-033),
registra gli interessi dichiarati e setta il flag ``onboarding_completed``.

Tutti i campi raccolti sono opt-in: l'onboarding è obbligatorio come *passaggio*
(enforcement server-side via ``before_request``), ma i dati al suo interno non
sono forzati. Completare la pagina = onboarding fatto.

NB: la creazione delle ``UserLocationAvailability`` è **inlinata** qui (non
delega ad ``AvailabilityService.set_venue_availability``, che è a sua volta
``@transactional``) per evitare l'annidamento di savepoint che su SQLite può
fare rollback silenzioso (vedi models/transaction/CLAUDE.md, pattern facade).
"""

from typing import Iterable, List, Optional

from models.base import db
from models.transaction.manager import transactional
from models.user.models import User

# Set chiuso di interessi accettati (allineato al design V3 §7).
VALID_INTERESTS = ("drill", "match", "tornei")


class OnboardingService:
    """Completa l'onboarding di un utente (ADR-035)."""

    @staticmethod
    @transactional(domain="user")
    def complete_onboarding(
        user_id: int,
        home_city: Optional[str] = None,
        venue_ids: Optional[Iterable[int]] = None,
        interests: Optional[Iterable[str]] = None,
    ) -> User:
        """Salva i dati dell'onboarding e marca il flag come completato.

        - ``home_city``: stringa città (opt-in), fallback centroide geo.
        - ``venue_ids``: sale per cui creare ``UserLocationAvailability``.
        - ``interests``: sottoinsieme di :data:`VALID_INTERESTS`.
        """
        user = db.session.get(User, user_id)
        if user is None:
            raise ValueError(f"Utente {user_id} non trovato")

        cleaned_city = (home_city or "").strip() or None
        if cleaned_city:
            user.home_city = cleaned_city

        # Interessi: filtra sul set chiuso, preserva l'ordine canonico.
        chosen = set(interests or [])
        valid = [i for i in VALID_INTERESTS if i in chosen]
        user.onboarding_interests = ",".join(valid) if valid else None

        OnboardingService._upsert_availabilities(
            user_id, OnboardingService._sane_ids(venue_ids)
        )

        user.onboarding_completed = True
        return user

    @staticmethod
    def _upsert_availabilities(user_id: int, venue_ids: List[int]) -> None:
        """Crea/attiva la disponibilità per le sale indicate (inline, ADR-033).

        Solo le sale attive ed esistenti vengono considerate; le altre sono
        ignorate silenziosamente (non devono bloccare l'onboarding).
        """
        if not venue_ids:
            return

        from models.location.models import BilliardHall, UserLocationAvailability

        valid_ids = {
            row.id
            for row in BilliardHall.query.filter(
                BilliardHall.id.in_(venue_ids),
                BilliardHall.is_active.is_(True),
            ).all()
        }

        for vid in venue_ids:
            if vid not in valid_ids:
                continue
            existing = UserLocationAvailability.query.filter_by(
                user_id=user_id, billiard_hall_id=vid
            ).first()
            if existing:
                existing.is_available = True
            else:
                db.session.add(
                    UserLocationAvailability(
                        user_id=user_id,
                        billiard_hall_id=vid,
                        is_available=True,
                    )
                )

    @staticmethod
    def _sane_ids(venue_ids: Optional[Iterable[int]]) -> List[int]:
        """Coerce a list of distinct positive int ids (preserve order)."""
        out: List[int] = []
        seen = set()
        for raw in venue_ids or []:
            try:
                vid = int(raw)
            except (TypeError, ValueError):
                continue
            if vid > 0 and vid not in seen:
                seen.add(vid)
                out.append(vid)
        return out
