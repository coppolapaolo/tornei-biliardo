"""Unit test del segnale-domanda → director (ADR-036).

Coprono il service: creazione (GPS + fallback home_city), conteggio per raggio,
fronte di salita ≥ soglia con cooldown, e consumo con notifica ai giocatori.
"""

import uuid
from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.user.role_enum import UserRole
from models.demand.models import DemandSignal, DemandSignalStatus
from models.demand.service import (
    DemandSignalService,
    DEMAND_THRESHOLD,
    DEMAND_EXPIRY_DAYS,
)

# Napoli (una sala con coordinate → centroide risolvibile).
NAP_LAT, NAP_LNG = 40.8518, 14.2681


def _user(role=UserRole.PLAYER, home_city=None, radius=30):
    uid = str(uuid.uuid4())[:8]
    from models import User

    u = User(
        username=f"u_{uid}",
        email=f"u_{uid}@test.com",
        role=role.value,
        home_city=home_city,
        signal_radius_km=radius,
    )
    u.set_password("pw123456")
    db.session.add(u)
    db.session.commit()
    return u


def _napoli_venue():
    from models.location.models import BilliardHall

    uid = str(uuid.uuid4())[:8]
    hall = BilliardHall(
        name=f"Sala_{uid}",
        city="Napoli",
        number_of_tables=4,
        is_active=True,
        latitude=NAP_LAT,
        longitude=NAP_LNG,
    )
    db.session.add(hall)
    db.session.commit()
    return hall


def _director_notifications(director_id):
    from models.notification.models import Notification, NotificationType

    return [
        n
        for n in Notification.query.filter_by(user_id=director_id).all()
        if n.notification_type == NotificationType.DEMAND_THRESHOLD_REACHED
    ]


# ── creazione ──────────────────────────────────────────────────────────────


def test_create_signal_with_gps(db_session):
    user = _user()
    signal = DemandSignalService.create_signal(
        user_id=user.id, near_lat=NAP_LAT, near_lng=NAP_LNG
    )
    assert signal.latitude == pytest.approx(NAP_LAT)
    assert signal.longitude == pytest.approx(NAP_LNG)
    assert signal.status == DemandSignalStatus.ACTIVE
    # scadenza ~60 giorni
    delta = signal.expires_at - utc_now()
    assert (
        timedelta(days=DEMAND_EXPIRY_DAYS - 1)
        < delta
        <= timedelta(days=DEMAND_EXPIRY_DAYS)
    )


def test_create_signal_fallback_home_city(db_session):
    _napoli_venue()  # rende risolvibile il centroide di "Napoli"
    user = _user(home_city="Napoli")
    signal = DemandSignalService.create_signal(user_id=user.id)
    assert signal.latitude == pytest.approx(NAP_LAT, abs=1e-6)
    assert signal.longitude == pytest.approx(NAP_LNG, abs=1e-6)


def test_create_signal_no_position_raises(db_session):
    user = _user(home_city=None)  # niente GPS, niente città → niente origine
    with pytest.raises(ValueError):
        DemandSignalService.create_signal(user_id=user.id)


# ── conteggio per raggio ─────────────────────────────────────────────────────


def test_count_active_within_filters_radius_and_status(db_session):
    user = _user()
    # 2 vicini, 1 lontano (~110 km a 1° di latitudine), 1 scaduto
    DemandSignalService.create_signal(user.id, NAP_LAT, NAP_LNG)
    DemandSignalService.create_signal(user.id, NAP_LAT + 0.01, NAP_LNG)
    DemandSignalService.create_signal(user.id, NAP_LAT + 1.0, NAP_LNG)  # lontano
    expired = DemandSignal(
        user_id=user.id,
        latitude=NAP_LAT,
        longitude=NAP_LNG,
        status=DemandSignalStatus.ACTIVE,
        expires_at=utc_now() - timedelta(days=1),
    )
    db.session.add(expired)
    db.session.commit()

    assert DemandSignalService.count_active_within(NAP_LAT, NAP_LNG, 30) == 2


# ── fronte di salita ─────────────────────────────────────────────────────────


def test_rising_edge_notifies_director_once(db_session):
    _napoli_venue()
    director = _user(role=UserRole.DIRECTOR, home_city="Napoli", radius=30)

    # I primi 5 segnali: nessuna notifica (sotto soglia).
    for _ in range(DEMAND_THRESHOLD - 1):
        p = _user()
        DemandSignalService.create_signal(p.id, NAP_LAT, NAP_LNG)
    assert _director_notifications(director.id) == []

    # Il 6° fa scattare il crossing → 1 notifica.
    p6 = _user()
    DemandSignalService.create_signal(p6.id, NAP_LAT, NAP_LNG)
    assert len(_director_notifications(director.id)) == 1

    # Il 7° è sopra soglia → nessuna nuova notifica.
    p7 = _user()
    DemandSignalService.create_signal(p7.id, NAP_LAT, NAP_LNG)
    assert len(_director_notifications(director.id)) == 1


def test_rising_edge_notifies_when_threshold_jumped(db_session):
    """Regressione: se il conteggio SALTA la soglia esatta (segnali già attivi +
    un nuovo create), il director va comunque avvisato. Con ``== soglia`` veniva
    perso; ora ``>= soglia`` (con cooldown anti-spam) lo cattura.
    """
    _napoli_venue()
    director = _user(role=UserRole.DIRECTOR, home_city="Napoli", radius=30)

    # Inseriamo DEMAND_THRESHOLD segnali ATTIVI direttamente, senza passare per
    # create_signal → nessun fronte di salita valutato: il director non è ancora
    # stato avvisato benché la zona sia già a soglia.
    for _ in range(DEMAND_THRESHOLD):
        p = _user()
        db.session.add(
            DemandSignal(
                user_id=p.id,
                latitude=NAP_LAT,
                longitude=NAP_LNG,
                status=DemandSignalStatus.ACTIVE,
                expires_at=utc_now() + timedelta(days=10),
            )
        )
    db.session.commit()
    assert _director_notifications(director.id) == []

    # Un nuovo create porta il conteggio a THRESHOLD+1 (salta la soglia esatta):
    # con >= il director viene avvisato comunque.
    p_new = _user()
    DemandSignalService.create_signal(p_new.id, NAP_LAT, NAP_LNG)
    assert len(_director_notifications(director.id)) == 1


def test_director_outside_radius_not_notified(db_session):
    _napoli_venue()
    # Director con raggio piccolo: i segnali (~1.1 km via +0.01 lat) cadono fuori
    # da un raggio di 1 km? No: usiamo segnali lontani ~110 km invece.
    director = _user(role=UserRole.DIRECTOR, home_city="Napoli", radius=30)
    far_lat = NAP_LAT + 2.0  # ~220 km a nord, fuori dai 30 km
    for _ in range(DEMAND_THRESHOLD):
        p = _user()
        DemandSignalService.create_signal(p.id, far_lat, NAP_LNG)
    assert _director_notifications(director.id) == []


# ── consumo ──────────────────────────────────────────────────────────────────


def test_consume_signals_marks_and_notifies(db_session):
    from datetime import date, timedelta
    from models.notification.models import Notification, NotificationType
    from models.competition.services import GaraService

    director = _user(role=UserRole.DIRECTOR)
    # Gara senza sala geolocalizzata → l'handler evento non consuma nulla:
    # qui testiamo direttamente consume_signals_for_gara con un gara_id reale.
    gara = GaraService.create_gara(
        number=1,
        name="Gara X",
        date=date.today() + timedelta(days=3),
        discipline="palla_8",
        distance=5,
        director_id=director.id,
    )
    gara_id = gara.id

    players = [_user() for _ in range(3)]
    for p in players:
        DemandSignalService.create_signal(p.id, NAP_LAT, NAP_LNG)

    consumed = DemandSignalService.consume_signals_for_gara(
        gara_id=gara_id, venue_lat=NAP_LAT, venue_lng=NAP_LNG, radius_km=30
    )
    assert consumed == 3

    remaining = DemandSignalService.count_active_within(NAP_LAT, NAP_LNG, 30)
    assert remaining == 0
    for p in players:
        signals = DemandSignal.query.filter_by(user_id=p.id).all()
        assert all(s.status == DemandSignalStatus.CONSUMED for s in signals)
        assert all(s.consumed_by_gara_id == gara_id for s in signals)
        notifs = [
            n
            for n in Notification.query.filter_by(user_id=p.id).all()
            if n.notification_type == NotificationType.DEMAND_GARA_NEARBY
        ]
        assert len(notifs) == 1


# ── re-eval alla promozione (ADR-036 open item 1) ────────────────────────────


def _admin_notifications(user_id):
    from models.notification.models import Notification, NotificationType

    return [
        n
        for n in Notification.query.filter_by(user_id=user_id).all()
        if n.notification_type == NotificationType.DEMAND_ZONE_NO_DIRECTOR
    ]


def test_evaluate_zone_for_new_director_notifies_when_threshold(db_session):
    _napoli_venue()
    # 6 segnali nella zona, creati senza alcun director esistente.
    for _ in range(DEMAND_THRESHOLD):
        DemandSignalService.create_signal(_user().id, NAP_LAT, NAP_LNG)

    director = _user(role=UserRole.DIRECTOR, home_city="Napoli", radius=30)
    notified = DemandSignalService.evaluate_zone_for_new_director(director.id)
    assert notified is True
    assert len(_director_notifications(director.id)) == 1


def test_evaluate_zone_for_new_director_silent_below_threshold(db_session):
    _napoli_venue()
    for _ in range(DEMAND_THRESHOLD - 2):
        DemandSignalService.create_signal(_user().id, NAP_LAT, NAP_LNG)

    director = _user(role=UserRole.DIRECTOR, home_city="Napoli", radius=30)
    notified = DemandSignalService.evaluate_zone_for_new_director(director.id)
    assert notified is False
    assert _director_notifications(director.id) == []


def test_promotion_triggers_demand_reeval(db_session):
    from models.user.permission_service import UserPermissionService
    from models import User

    _napoli_venue()
    admin = _user(role=UserRole.ADMIN)
    for _ in range(DEMAND_THRESHOLD):
        DemandSignalService.create_signal(_user().id, NAP_LAT, NAP_LNG)

    candidate = _user(home_city="Napoli")
    cand_id = candidate.id
    UserPermissionService.promote_to_director(cand_id, admin.id)

    # La re-eval (variante NON @transactional, eseguita nella stessa transazione
    # di promozione) ha notificato il neo-director...
    assert len(_director_notifications(cand_id)) == 1
    # ...e soprattutto il cambio di ruolo è PERSISTITO. Regressione del nested
    # @transactional: con la versione decorata chiamata dentro la promozione, il
    # savepoint annidato poteva non persistere su SQLite (vedi
    # models/transaction/CLAUDE.md).
    assert db.session.get(User, cand_id).role == UserRole.DIRECTOR.value


# ── segnale-admin per zona senza director (ADR-036 open item 2) ──────────────


def test_admin_signal_when_no_director_covers_zone(db_session):
    admin = _user(role=UserRole.ADMIN)
    # 6 segnali in una zona senza alcun director.
    for _ in range(DEMAND_THRESHOLD):
        DemandSignalService.create_signal(_user().id, NAP_LAT, NAP_LNG, city="Napoli")

    assert len(_admin_notifications(admin.id)) == 1


def test_no_admin_signal_when_director_covers(db_session):
    _napoli_venue()
    admin = _user(role=UserRole.ADMIN)
    _user(role=UserRole.DIRECTOR, home_city="Napoli", radius=30)

    for _ in range(DEMAND_THRESHOLD):
        DemandSignalService.create_signal(_user().id, NAP_LAT, NAP_LNG, city="Napoli")

    # Il director copre la zona → nessun segnale-admin.
    assert _admin_notifications(admin.id) == []


# ── ciclo di vita scadenza (ADR-036 open item 3) ─────────────────────────────


def _make_signal(user_id, expires_in_days, status=None, reminded=False):
    from datetime import timedelta as td

    s = DemandSignal(
        user_id=user_id,
        latitude=NAP_LAT,
        longitude=NAP_LNG,
        status=status or DemandSignalStatus.ACTIVE,
        expires_at=utc_now() + td(days=expires_in_days),
        reminded_at=(utc_now() if reminded else None),
    )
    db.session.add(s)
    db.session.commit()
    return s


def test_expire_due_signals(db_session):
    u = _user()
    past = _make_signal(u.id, expires_in_days=-1)  # scaduto
    future = _make_signal(u.id, expires_in_days=10)  # valido

    n = DemandSignalService.expire_due_signals()
    assert n == 1
    assert db.session.get(DemandSignal, past.id).status == DemandSignalStatus.EXPIRED
    assert db.session.get(DemandSignal, future.id).status == DemandSignalStatus.ACTIVE


def test_refresh_signal_extends_and_clears_reminder(db_session):
    u = _user()
    s = _make_signal(u.id, expires_in_days=2, reminded=True)
    old_exp = s.expires_at

    ok = DemandSignalService.refresh_signal(s.id, u.id)
    assert ok is True
    refreshed = db.session.get(DemandSignal, s.id)
    assert refreshed.expires_at > old_exp
    assert refreshed.reminded_at is None


def test_refresh_signal_rejects_non_owner(db_session):
    u = _user()
    other = _user()
    s = _make_signal(u.id, expires_in_days=2)
    assert DemandSignalService.refresh_signal(s.id, other.id) is False


# ── auto-refresh per utenti attivi (ADR-036 open item 3) ─────────────────────


def _set_last_active(user_id, days_ago):
    from datetime import timedelta as td
    from models import User

    u = db.session.get(User, user_id)
    u.last_active_at = utc_now() - td(days=days_ago)
    db.session.commit()


def test_process_expiring_auto_refreshes_active_user(db_session):
    u = _user()
    _set_last_active(u.id, days_ago=1)  # attivo
    s = _make_signal(u.id, expires_in_days=2)
    old_exp = s.expires_at

    result = DemandSignalService.process_expiring_signals()
    assert result["refreshed"] == 1
    assert result["reminded"] == 0
    refreshed = db.session.get(DemandSignal, s.id)
    assert refreshed.expires_at > old_exp  # esteso
    assert refreshed.reminded_at is None


def test_process_expiring_prompts_inactive_user(db_session):
    from models.notification.models import Notification, NotificationType

    u = _user()
    _set_last_active(u.id, days_ago=90)  # inattivo
    s = _make_signal(u.id, expires_in_days=2)

    result = DemandSignalService.process_expiring_signals()
    assert result["refreshed"] == 0
    assert result["reminded"] == 1
    assert db.session.get(DemandSignal, s.id).reminded_at is not None
    notifs = [
        n
        for n in Notification.query.filter_by(user_id=u.id).all()
        if n.notification_type == NotificationType.DEMAND_SIGNAL_EXPIRING
    ]
    assert len(notifs) == 1


def test_process_expiring_prompts_user_never_active(db_session):
    u = _user()  # last_active_at None → trattato come inattivo
    s = _make_signal(u.id, expires_in_days=3)
    result = DemandSignalService.process_expiring_signals()
    assert result == {"refreshed": 0, "reminded": 1}
    assert db.session.get(DemandSignal, s.id).reminded_at is not None


def test_process_expiring_ignores_far_signals(db_session):
    u = _user()
    _set_last_active(u.id, days_ago=1)
    _make_signal(u.id, expires_in_days=30)  # fuori finestra (7gg)
    result = DemandSignalService.process_expiring_signals()
    assert result == {"refreshed": 0, "reminded": 0}


def test_touch_user_activity_throttled(db_session):
    from utils.activity import touch_user_activity

    u = _user()
    assert u.last_active_at is None
    # primo touch: scrive
    assert touch_user_activity(u) is True
    from models import User

    ts1 = db.session.get(User, u.id).last_active_at
    assert ts1 is not None
    # secondo touch immediato: throttled, nessuna scrittura
    assert touch_user_activity(u) is False
    assert db.session.get(User, u.id).last_active_at == ts1
