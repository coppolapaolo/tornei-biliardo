"""
Test per la lista attesa basata sulla parità (opzione NO).

Regole da docs/reference/CLASSIFICATION_SYSTEM.md sezione 3.5:
- Iscrizione con N pari → N+1 dispari: va in lista attesa
- Iscrizione con N dispari → N+1 pari: si iscrive + primo in lista attesa si iscrive
- Disiscrizione con N pari → N-1 dispari: ultimo iscritto va in lista attesa
- Disiscrizione con N dispari → N-1 pari: normale disiscrizione
"""

import pytest
from datetime import date, time, datetime, timedelta

from models.base import db, utc_now
from models.competition.models import Gara, Inscription, WaitlistReason
from models.competition.inscription_service import InscriptionService
from models.competition.services import GaraService
from models.user.models import User


@pytest.fixture
def app():
    """Create test application."""
    from app import create_app

    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.rollback()
        db.drop_all()


@pytest.fixture
def db_session(app):
    """Create test database session."""
    with app.app_context():
        yield db.session


@pytest.fixture
def director(db_session):
    """Create a director user."""
    import uuid

    user = User(
        username=f"director_{uuid.uuid4().hex[:8]}",
        email=f"director_{uuid.uuid4().hex[:8]}@test.com",
        role="director",
    )
    user.set_password("test123")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def players(db_session):
    """Create multiple player users."""
    import uuid

    users = []
    for i in range(6):
        user = User(
            username=f"player_{i}_{uuid.uuid4().hex[:8]}",
            email=f"player_{i}_{uuid.uuid4().hex[:8]}@test.com",
            role="player",
        )
        user.set_password("test123")
        db_session.add(user)
        users.append(user)
    db_session.commit()
    return users


@pytest.fixture
def gara_with_no_policy(db_session, director):
    """Create a gara with odd_number_policy=NO."""
    now = utc_now()
    gara = Gara(
        number=1,
        name="Gara Test Parità",
        date=date.today() + timedelta(days=7),
        time=time(20, 0),
        discipline="palla_8",
        distance=5,
        is_race_to=True,
        matchmaking_strategy="amalfi",
        odd_number_policy="no",  # Opzione NO attiva
        director_id=director.id,
        min_participants=2,
        inscription_start=now - timedelta(hours=1),
        inscription_end=now + timedelta(days=6),
        status="inscription",
    )
    db_session.add(gara)
    db_session.commit()
    return gara


@pytest.fixture
def gara_with_bye_policy(db_session, director):
    """Create a gara with standard bye policy."""
    now = utc_now()
    gara = Gara(
        number=2,
        name="Gara Test Bye",
        date=date.today() + timedelta(days=7),
        time=time(20, 0),
        discipline="palla_8",
        distance=5,
        is_race_to=True,
        matchmaking_strategy="amalfi",
        odd_number_policy="bye",  # Standard bye
        director_id=director.id,
        min_participants=2,
        inscription_start=now - timedelta(hours=1),
        inscription_end=now + timedelta(days=6),
        status="inscription",
    )
    db_session.add(gara)
    db_session.commit()
    return gara


class TestParityWaitlistInscription:
    """Test iscrizione con opzione NO."""

    def test_first_player_inscribes_normally(
        self, app, db_session, gara_with_no_policy, players
    ):
        """Primo giocatore (0 → 1 dispari) si iscrive normalmente."""
        # Con 0 iscritti, il primo va direttamente iscritto (non in waitlist)
        # perché serve almeno 1 giocatore per iniziare
        inscription = InscriptionService.inscribe_user(
            user_id=players[0].id, gara_id=gara_with_no_policy.id
        )

        assert inscription is not None
        assert inscription.is_waitlist is False

    def test_second_player_inscribes_normally(
        self, app, db_session, gara_with_no_policy, players
    ):
        """Secondo giocatore (1 → 2 pari) si iscrive normalmente."""
        # Primo giocatore
        InscriptionService.inscribe_user(
            user_id=players[0].id, gara_id=gara_with_no_policy.id
        )

        # Secondo giocatore (1 → 2 = pari)
        inscription = InscriptionService.inscribe_user(
            user_id=players[1].id, gara_id=gara_with_no_policy.id
        )

        assert inscription is not None
        assert inscription.is_waitlist is False

    def test_third_player_goes_to_parity_waitlist(
        self, app, db_session, gara_with_no_policy, players
    ):
        """Terzo giocatore (2 pari → 3 dispari) va in lista attesa parità."""
        # Primi due giocatori
        InscriptionService.inscribe_user(
            user_id=players[0].id, gara_id=gara_with_no_policy.id
        )
        InscriptionService.inscribe_user(
            user_id=players[1].id, gara_id=gara_with_no_policy.id
        )

        # Terzo giocatore (2 → 3 = dispari) va in waitlist
        inscription = InscriptionService.inscribe_user(
            user_id=players[2].id, gara_id=gara_with_no_policy.id
        )

        assert inscription is not None
        assert inscription.is_waitlist is True
        assert inscription.waitlist_reason == WaitlistReason.PARITY.value

    def test_fourth_player_promotes_third_from_parity_waitlist(
        self, app, db_session, gara_with_no_policy, players
    ):
        """Quarto giocatore (3 dispari → 4 pari) promuove il terzo dalla lista."""
        # Primi due giocatori
        InscriptionService.inscribe_user(
            user_id=players[0].id, gara_id=gara_with_no_policy.id
        )
        InscriptionService.inscribe_user(
            user_id=players[1].id, gara_id=gara_with_no_policy.id
        )

        # Terzo va in waitlist
        third_inscription = InscriptionService.inscribe_user(
            user_id=players[2].id, gara_id=gara_with_no_policy.id
        )
        assert third_inscription.is_waitlist is True

        # Quarto giocatore (3 → 4 = pari)
        fourth_inscription = InscriptionService.inscribe_user(
            user_id=players[3].id, gara_id=gara_with_no_policy.id
        )

        # Reload third inscription
        db_session.expire(third_inscription)
        third_inscription = db_session.get(Inscription, third_inscription.id)

        # Entrambi devono essere iscritti (non in waitlist)
        assert fourth_inscription.is_waitlist is False
        assert third_inscription.is_waitlist is False

    def test_bye_policy_does_not_use_parity_waitlist(
        self, app, db_session, gara_with_bye_policy, players
    ):
        """Con policy bye, tutti si iscrivono normalmente."""
        for i in range(3):
            inscription = InscriptionService.inscribe_user(
                user_id=players[i].id, gara_id=gara_with_bye_policy.id
            )
            # Nessuno va in waitlist con bye policy
            assert inscription.is_waitlist is False


class TestParityWaitlistUninscription:
    """Test disiscrizione con opzione NO."""

    def test_uninscribe_making_count_odd_moves_last_to_waitlist(
        self, app, db_session, gara_with_no_policy, players
    ):
        """Disiscrizione da pari a dispari: ultimo iscritto va in waitlist."""
        # Iscrivi 4 giocatori (tutti attivi)
        inscriptions = []
        for i in range(4):
            ins = InscriptionService.inscribe_user(
                user_id=players[i].id, gara_id=gara_with_no_policy.id
            )
            # Il terzo va in waitlist, poi viene promosso col quarto
            inscriptions.append(ins)

        # Verifica che tutti siano attivi (non in waitlist)
        for ins in inscriptions:
            db_session.expire(ins)
            ins = db_session.get(Inscription, ins.id)
            assert ins.is_waitlist is False, f"Player {ins.user_id} should be active"

        # Disiscrivi il primo (4 pari → 3 dispari)
        InscriptionService.uninscribe_user(
            user_id=players[0].id, gara_id=gara_with_no_policy.id
        )

        # L'ultimo iscritto (player 3) dovrebbe andare in waitlist
        remaining = (
            db_session.query(Inscription)
            .filter_by(gara_id=gara_with_no_policy.id)
            .all()
        )

        active_count = sum(1 for r in remaining if not r.is_waitlist)
        waitlist_count = sum(1 for r in remaining if r.is_waitlist)

        # Dovrebbero esserci 2 attivi e 1 in waitlist (3 totali, dispari non permesso)
        assert active_count == 2
        assert waitlist_count == 1

    def test_uninscribe_keeping_count_even_is_normal(
        self, app, db_session, gara_with_no_policy, players
    ):
        """Disiscrizione da dispari a pari: normale (nessuno va in waitlist)."""
        # Iscrivi 3 giocatori
        # Player 0 e 1 sono attivi, player 2 è in waitlist
        InscriptionService.inscribe_user(
            user_id=players[0].id, gara_id=gara_with_no_policy.id
        )
        InscriptionService.inscribe_user(
            user_id=players[1].id, gara_id=gara_with_no_policy.id
        )
        third = InscriptionService.inscribe_user(
            user_id=players[2].id, gara_id=gara_with_no_policy.id
        )

        assert third.is_waitlist is True  # In waitlist per parità

        # Disiscrivi il terzo (che è in waitlist)
        # 2 attivi + 1 waitlist - 1 waitlist = 2 attivi (pari, ok)
        InscriptionService.uninscribe_user(
            user_id=players[2].id, gara_id=gara_with_no_policy.id
        )

        remaining = (
            db_session.query(Inscription)
            .filter_by(gara_id=gara_with_no_policy.id)
            .all()
        )

        # Dovrebbero rimanere 2 attivi
        assert len(remaining) == 2
        assert all(not r.is_waitlist for r in remaining)


class TestParityAndCapacityWaitlistInteraction:
    """Test interazione tra waitlist parità e capacità."""

    def test_parity_check_before_capacity_check(
        self, app, db_session, director, players
    ):
        """La parità viene controllata prima della capacità."""
        now = utc_now()
        # Gara con max 4 partecipanti E policy NO
        gara = Gara(
            number=3,
            name="Gara Test Parità+Capacità",
            date=date.today() + timedelta(days=7),
            time=time(20, 0),
            discipline="palla_8",
            distance=5,
            is_race_to=True,
            matchmaking_strategy="amalfi",
            odd_number_policy="no",
            max_participants=4,  # Massimo 4
            director_id=director.id,
            min_participants=2,
            inscription_start=now - timedelta(hours=1),
            inscription_end=now + timedelta(days=6),
            status="inscription",
        )
        db_session.add(gara)
        db_session.commit()

        # Iscrivi 2 giocatori (ok)
        InscriptionService.inscribe_user(user_id=players[0].id, gara_id=gara.id)
        InscriptionService.inscribe_user(user_id=players[1].id, gara_id=gara.id)

        # Terzo giocatore: 2 → 3 dispari, va in waitlist PARITY (non CAPACITY)
        third = InscriptionService.inscribe_user(user_id=players[2].id, gara_id=gara.id)

        assert third.is_waitlist is True
        assert third.waitlist_reason == WaitlistReason.PARITY.value

        # Quarto giocatore: 3 → 4 pari, promuove il terzo
        fourth = InscriptionService.inscribe_user(
            user_id=players[3].id, gara_id=gara.id
        )

        db_session.expire(third)
        third = db_session.get(Inscription, third.id)

        assert third.is_waitlist is False
        assert fourth.is_waitlist is False

        # Quinto giocatore: 4 → 5, ora max raggiunto E dispari
        # Prima si applica parità (waitlist PARITY), ma siamo anche al max
        # Il comportamento dovrebbe essere: va in waitlist CAPACITY (max raggiunto)
        fifth = InscriptionService.inscribe_user(user_id=players[4].id, gara_id=gara.id)

        assert fifth.is_waitlist is True
        # Con max raggiunto, la ragione è CAPACITY
        assert fifth.waitlist_reason == WaitlistReason.CAPACITY.value
