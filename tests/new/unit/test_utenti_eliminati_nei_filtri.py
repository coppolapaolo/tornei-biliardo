"""`is_deleted` su `User` è una property, non una colonna.

`User.query.filter_by(is_deleted=False)` non solleva: SQLAlchemy riceve un
confronto già risolto in Python e scrive `WHERE 0 = 1`, quindi la query non
trova mai nessuno. Gli utenti eliminati li toglie già il filtro di sessione
(`models/soft_delete/filter.py`, su `deleted_at`).

Due punti ci erano cascati, e nessuno se ne accorgeva:

- gli avvisi dei traguardi KPI non arrivavano a nessun admin, perché la lista
  degli admin era sempre vuota (restava solo un warning nel log);
- la scheda «performance» della pagina KPI mostrava sempre 0 utenti.
"""

import uuid

from models.base import db
from models.user.role_enum import UserRole


def _user(role: UserRole = UserRole.PLAYER, eliminato: bool = False):
    from models import User

    uid = str(uuid.uuid4())[:8]
    u = User(username=f"u_{uid}", email=f"u_{uid}@test.com", role=role.value)
    u.set_password("pw123456")
    db.session.add(u)
    db.session.commit()
    if eliminato:
        u.anonymize()
        db.session.commit()
    return u


def test_gli_avvisi_kpi_trovano_gli_admin(db_session):
    from models.kpi.notifications import KpiNotificationService

    admin = _user(UserRole.ADMIN)
    _user(UserRole.ADMIN, eliminato=True)
    _user(UserRole.PLAYER)

    assert KpiNotificationService.get_admin_user_ids() == [admin.id]


def test_la_scheda_performance_conta_gli_utenti_non_eliminati(db_session):
    from models.gamification.community_leaderboard_service import (
        CommunityLeaderboardService,
    )

    _user()
    _user(UserRole.DIRECTOR)
    _user(eliminato=True)

    assert CommunityLeaderboardService.performance_stats()["total_users"] == 2
