"""
Test per verificare che le notifiche vengano inviate quando
un direttore viene aggiunto o rimosso da gara/campionato.
"""

import pytest
from datetime import date, timedelta
from models.competition.models import Gara, WithdrawPolicy
from models.competition.services import GaraService
from models.campionato.services import TournamentService
from models.notification.models import Notification
from models.status_enum import GaraStatus, Discipline


@pytest.mark.unit
class TestDirectorAssignmentNotifications:
    """Test notifiche per assegnazione/rimozione direttori."""

    def test_notification_on_gara_director_added(
        self, db_session, isolated_admin_user, isolated_director_user
    ):
        """Verifica che venga inviata notifica quando si aggiunge direttore a gara."""
        # Crea gara
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            campionato_id=None,
            number=1,
            name="Test Gara",
            date=tomorrow,
            location="Test Location",
            discipline=Discipline.EIGHT_BALL.value,
            distance=5,
            best_of=True,
            status=GaraStatus.SETUP.value,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value
        )
        db_session.add(gara)
        db_session.commit()

        # Aggiungi direttore
        result = GaraService.add_director(
            gara_id=gara.id,
            user_id=isolated_director_user.id,
            assigned_by_id=isolated_admin_user.id
        )
        db_session.commit()

        assert result is True

        # Verifica notifica
        notif = Notification.query.filter_by(
            user_id=isolated_director_user.id
        ).first()
        assert notif is not None
        assert "Nominato co-direttore" in notif.title
        assert "Test Gara" in notif.message

    def test_notification_on_gara_director_removed(
        self, db_session, isolated_admin_user, isolated_director_user
    ):
        """Verifica che venga inviata notifica quando si rimuove direttore da gara."""
        # Crea gara
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            campionato_id=None,
            number=1,
            name="Test Gara Remove",
            date=tomorrow,
            location="Test Location",
            discipline=Discipline.NINE_BALL.value,
            distance=7,
            best_of=True,
            status=GaraStatus.SETUP.value,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value
        )
        db_session.add(gara)
        db_session.commit()

        # Prima aggiungi
        GaraService.add_director(
            gara_id=gara.id,
            user_id=isolated_director_user.id,
            assigned_by_id=isolated_admin_user.id
        )
        db_session.commit()

        # Poi rimuovi
        result = GaraService.remove_director(
            gara_id=gara.id,
            user_id=isolated_director_user.id
        )
        db_session.commit()

        assert result is True

        # Verifica notifiche (dovrebbero essere 2: aggiunta + rimozione)
        notifs = Notification.query.filter_by(
            user_id=isolated_director_user.id
        ).order_by(Notification.created_at).all()
        assert len(notifs) == 2

        # Prima notifica: aggiunta
        assert "Nominato co-direttore" in notifs[0].title

        # Seconda notifica: rimozione
        assert "Rimosso da co-direttore" in notifs[1].title
        assert "Test Gara Remove" in notifs[1].message

    def test_notification_on_campionato_director_added(
        self, db_session, isolated_admin_user, isolated_director_user
    ):
        """Verifica notifica per aggiunta direttore a campionato."""
        # Crea campionato
        service = TournamentService()
        campionato = service.create_campionato(
            name="Test Campionato",
            campionato_type="Amalfi"
        )
        db_session.commit()

        # Aggiungi direttore
        result = service.add_director(
            campionato_id=campionato.id,
            user_id=isolated_director_user.id,
            assigned_by_id=isolated_admin_user.id
        )
        db_session.commit()

        assert result is True

        # Verifica notifica
        notif = Notification.query.filter_by(
            user_id=isolated_director_user.id
        ).first()
        assert notif is not None
        assert "Nominato co-direttore" in notif.title
        assert "Test Campionato" in notif.message
        assert "campionato" in notif.message

    def test_notification_on_campionato_director_removed(
        self, db_session, isolated_admin_user, isolated_director_user
    ):
        """Verifica notifica per rimozione direttore da campionato."""
        # Crea campionato
        service = TournamentService()
        campionato = service.create_campionato(
            name="Test Campionato Remove",
            campionato_type="Amalfi"
        )
        db_session.commit()

        # Prima aggiungi
        service.add_director(
            campionato_id=campionato.id,
            user_id=isolated_director_user.id,
            assigned_by_id=isolated_admin_user.id
        )
        db_session.commit()

        # Poi rimuovi
        result = service.remove_director(
            campionato_id=campionato.id,
            user_id=isolated_director_user.id
        )
        db_session.commit()

        assert result is True

        # Verifica notifiche
        notifs = Notification.query.filter_by(
            user_id=isolated_director_user.id
        ).order_by(Notification.created_at).all()
        assert len(notifs) == 2

        # Seconda notifica: rimozione
        assert "Rimosso da co-direttore" in notifs[1].title
        assert "Test Campionato Remove" in notifs[1].message
        assert "campionato" in notifs[1].message
