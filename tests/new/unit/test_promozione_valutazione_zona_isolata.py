"""La promozione a direttore regge un guasto della valutazione della zona.

`UserPermissionService._evaluate_demand_zone` avvolge la valutazione del
segnale-domanda (ADR-036) in un `try/except`: «la promozione non deve fallire
per la valutazione». Fino al 2026-09-13 chiamava la variante non decorata,
nella transazione della promozione. Un errore di **flush** catturato lì lascia
però la sessione da annullare: il `except` lo nascondeva, e al salvataggio la
promozione falliva comunque. Con la variante decorata il guasto annulla solo il
proprio savepoint (ADR-061).
"""

from __future__ import annotations

import uuid

from models.base import db
from models.demand.service import DemandSignalService
from models.user.permission_service import UserPermissionService
from models.user.privacy_models import UserPrivacySetting
from models.user.role_enum import UserRole


def _utente(ruolo: UserRole):
    from models import User

    codice = str(uuid.uuid4())[:8]
    utente = User(
        username=f"u_{codice}", email=f"u_{codice}@test.com", role=ruolo.value
    )
    utente.set_password("pw123456")
    db.session.add(utente)
    db.session.commit()
    return utente


def test_un_errore_di_flush_nella_valutazione_non_annulla_la_promozione(
    db_session, monkeypatch
):
    admin = _utente(UserRole.ADMIN)
    candidato = _utente(UserRole.PLAYER)
    candidato_id = candidato.id

    def origine_che_rompe_il_flush(director):
        # Due impostazioni privacy per lo stesso utente: UNIQUE su user_id.
        db.session.add(UserPrivacySetting(user_id=director.id))
        db.session.add(UserPrivacySetting(user_id=director.id))
        db.session.flush()
        return None

    monkeypatch.setattr(
        DemandSignalService,
        "_director_origin",
        staticmethod(origine_che_rompe_il_flush),
    )

    assert UserPermissionService.promote_to_director(candidato_id, admin.id) is True

    db.session.rollback()
    db.session.expire_all()
    from models import User

    assert db.session.get(User, candidato_id).role == UserRole.DIRECTOR.value
