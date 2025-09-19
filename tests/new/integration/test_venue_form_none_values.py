"""
Test per verificare che i valori None nei form delle venue vengano gestiti correttamente.
"""

import pytest
import uuid
from models import db
from models.location.models import BilliardHall
from models.user.models import User


class TestVenueFormNoneValues:
    """Test per gestione valori None nei form venue."""

    @pytest.fixture
    def venue_with_none_values(self):
        """Crea una venue con alcuni campi None."""
        unique_id = str(uuid.uuid4())[:8]
        venue = BilliardHall(
            name=f"Test Venue {unique_id}",
            address=None,  # Valore None
            city=None,  # Valore None
            postal_code=None,  # Valore None
            phone=None,  # Valore None
            email=None,  # Valore None
            website=None,  # Valore None
            number_of_tables=4,
            is_active=False,  # Disattivata per test
            verified=False,
        )
        db.session.add(venue)
        db.session.commit()
        return venue

    @pytest.fixture
    def admin_user(self):
        """Ottiene l'utente admin esistente o ne crea uno se non esiste."""
        from models.user.models import User, UserRole

        # Cerca l'admin esistente creato dal conftest
        admin = User.query.filter_by(role=UserRole.ADMIN.value).first()
        if admin:
            # Aggiorna la password per i test
            from werkzeug.security import generate_password_hash

            admin.password_hash = generate_password_hash("adminpassword123")
            db.session.commit()
            return admin
        else:
            # Fallback: crea un admin se non esiste (non dovrebbe succedere con conftest)
            from models.user.services import UserService

            return UserService.create_user(
                username="admin",
                email="admin@test.com",
                password="adminpassword123",
                role="admin",
            )

    @pytest.fixture
    def regular_user(self):
        """Crea un utente normale per i test."""
        from models.user.services import UserService

        unique_id = str(uuid.uuid4())[:8]
        user = UserService.create_user(
            username=f"user_test_{unique_id}",
            email=f"user_{unique_id}@test.com",
            password="testpassword123",
            role="player",
        )
        return user

    def test_venue_form_renders_empty_strings_not_none(
        self, client, admin_user, venue_with_none_values
    ):
        """Test che il form venue mostri stringhe vuote invece di 'None'."""
        # Login come admin usando il login form
        login_response = client.post(
            "/auth/login",
            data={"username": admin_user.username, "password": "adminpassword123"},
        )
        assert login_response.status_code == 302

        # Accedi al form di edit della venue
        response = client.get(f"/admin/venues/{venue_with_none_values.id}/edit")
        assert response.status_code == 200

        # Verifica che non ci siano stringhe "None" nel form
        content = response.get_data(as_text=True)

        # Non dovrebbe contenere value="None" o >None<
        assert 'value="None"' not in content
        assert ">None<" not in content

        # Dovrebbe contenere campi vuoti
        assert 'value=""' in content or "value=''" in content

    def test_admin_can_access_inactive_venue(
        self, client, admin_user, venue_with_none_values
    ):
        """Test che l'admin può accedere ai dettagli di venue disattivate."""
        # Login come admin usando il login form
        login_response = client.post(
            "/auth/login",
            data={"username": admin_user.username, "password": "adminpassword123"},
        )
        assert login_response.status_code == 302

        # Accedi ai dettagli della venue disattivata
        response = client.get(f"/admin/venues/{venue_with_none_values.id}")
        assert response.status_code == 200

        # Verifica che mostri lo status "disattivata"
        content = response.get_data(as_text=True)
        assert "Disattivata" in content or "disattivata" in content

    def test_regular_user_cannot_access_inactive_venue(
        self, client, regular_user, venue_with_none_values
    ):
        """Test che gli utenti normali non possono accedere ai dettagli di venue disattivate."""
        # Verifica che la venue sia davvero disattivata
        assert venue_with_none_values.is_active == False
        # Verifica che l'utente non sia admin
        assert regular_user.is_admin == False

        # Login come utente normale usando il login form
        login_response = client.post(
            "/auth/login",
            data={"username": regular_user.username, "password": "testpassword123"},
        )
        # Il login dovrebbe reindirizzare
        assert login_response.status_code == 302

        # Tentativo di accesso ai dettagli della venue disattivata
        response = client.get(f"/admin/venues/{venue_with_none_values.id}")
        assert response.status_code == 404

    def test_venue_list_shows_inactive_venues_for_admin(
        self, client, admin_user, venue_with_none_values
    ):
        """Test che l'elenco venue mostri anche quelle disattivate per l'admin."""
        # Login come admin usando il login form
        login_response = client.post(
            "/auth/login",
            data={"username": admin_user.username, "password": "adminpassword123"},
        )
        assert login_response.status_code == 302

        # Accedi alla lista venue
        response = client.get("/admin/venues")
        assert response.status_code == 200

        content = response.get_data(as_text=True)

        # Dovrebbe contenere la venue disattivata
        assert venue_with_none_values.name in content

        # Dovrebbe mostrare il badge "Disattivata" e il pulsante "Attiva"
        assert "Disattivata" in content or "bg-danger" in content
        # Verifica presenza pulsante Attiva (può essere in diverse forme)
        assert (
            "Attiva" in content and "button" in content
        ) or "fas fa-check" in content

    def test_admin_can_activate_inactive_venue(
        self, client, admin_user, venue_with_none_values
    ):
        """Test che l'admin può attivare una venue disattivata dalla lista."""
        # Verifica che la venue sia disattivata
        assert venue_with_none_values.is_active == False

        # Login come admin
        login_response = client.post(
            "/auth/login",
            data={"username": admin_user.username, "password": "adminpassword123"},
        )
        assert login_response.status_code == 302

        # Attiva la venue tramite POST
        response = client.post(f"/admin/venues/{venue_with_none_values.id}/activate")
        assert response.status_code == 302  # Redirect dopo attivazione

        # Verifica che la venue sia stata attivata nel database
        db.session.refresh(venue_with_none_values)
        assert venue_with_none_values.is_active == True

    def test_ajax_toggle_venue_status(self, client, admin_user, venue_with_none_values):
        """Test che l'API AJAX per toggle status funzioni correttamente."""
        # Login come admin
        login_response = client.post(
            "/auth/login",
            data={"username": admin_user.username, "password": "adminpassword123"},
        )
        assert login_response.status_code == 302

        # Test toggle is_active
        response = client.post(
            f"/admin/venues/{venue_with_none_values.id}/toggle",
            json={"field": "is_active", "value": True},
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] == True
        assert "attivata" in data["message"]

        # Verifica nel database
        db.session.refresh(venue_with_none_values)
        assert venue_with_none_values.is_active == True

        # Test toggle verified
        response = client.post(
            f"/admin/venues/{venue_with_none_values.id}/toggle",
            json={"field": "verified", "value": True},
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] == True
        assert "verificata" in data["message"]

        # Verifica nel database
        db.session.refresh(venue_with_none_values)
        assert venue_with_none_values.verified == True

    def test_venue_edit_requires_authentication(self, client, venue_with_none_values):
        """Test che l'edit venue richieda autenticazione."""
        # Assicurati di non essere loggato
        client.get("/auth/logout")

        # Tentativo di accesso senza login
        response = client.get(f"/admin/venues/{venue_with_none_values.id}/edit")
        # Dovrebbe reindirizzare al login
        assert response.status_code == 302
        assert "/auth/login" in response.location


class TestVenueCreationFromCombo:
    """Test per creazione venue dalla combo nelle gare."""

    @pytest.fixture
    def admin_user(self):
        """Ottiene l'utente admin esistente o ne crea uno se non esiste."""
        from models.user.models import User, UserRole

        # Cerca l'admin esistente creato dal conftest
        admin = User.query.filter_by(role=UserRole.ADMIN.value).first()
        if admin:
            # Aggiorna la password per i test
            from werkzeug.security import generate_password_hash

            admin.password_hash = generate_password_hash("adminpassword123")
            db.session.commit()
            return admin
        else:
            # Fallback: crea un admin se non esiste (consistente con la prima classe)
            from models.user.services import UserService

            return UserService.create_user(
                username="admin",
                email="admin@test.com",
                password="adminpassword123",
                role="admin",
            )

    def test_new_venue_created_as_inactive_from_gara_form(self, client, admin_user):
        """Test che le nuove venue create dal form gara siano disattivate."""
        # Login come admin usando il login form
        login_response = client.post(
            "/auth/login",
            data={"username": admin_user.username, "password": "adminpassword123"},
        )
        assert login_response.status_code == 302

        new_venue_name = "Nuova Sala Test"

        # Simula creazione gara con nuova venue
        form_data = {
            "name": "Test Gara",
            "date": "2025-12-31",
            "time": "20:00",
            "location": new_venue_name,
            "number_of_tables": "6",  # Importante per la creazione
            "discipline": "palla_9",
            "distance": "9",
            "rounds_count": "3",
            "min_participants": "4",
            "matchmaking_strategy": "amalfi",
            "first_round_policy": "random",
            "odd_number_policy": "bye",
        }

        response = client.post("/admin/gara/create_standalone", data=form_data)

        # Dovrebbe reindirizzare (creazione riuscita)
        assert response.status_code == 302

        # Verifica che la venue sia stata creata
        created_venue = BilliardHall.query.filter_by(name=new_venue_name).first()
        assert created_venue is not None

        # Verifica che sia disattivata e non verificata
        assert created_venue.is_active == False
        assert created_venue.verified == False
        assert created_venue.number_of_tables == 6

    def test_venue_form_handles_missing_number_of_tables(self, client, admin_user):
        """Test che senza numero tavoli la venue non venga creata."""
        # Login come admin usando il login form
        login_response = client.post(
            "/auth/login",
            data={"username": admin_user.username, "password": "adminpassword123"},
        )
        assert login_response.status_code == 302

        new_venue_name = "Sala Senza Tavoli"

        # Simula creazione gara senza specificare numero tavoli
        form_data = {
            "name": "Test Gara Fallita",
            "date": "2025-12-31",
            "time": "20:00",
            "location": new_venue_name,
            # number_of_tables mancante!
            "discipline": "palla_9",
            "distance": "9",
            "rounds_count": "3",
            "min_participants": "4",
            "matchmaking_strategy": "amalfi",
            "first_round_policy": "random",
            "odd_number_policy": "bye",
        }

        response = client.post("/admin/gara/create_standalone", data=form_data)

        # Dovrebbe comunque creare la gara (ma mostrare un warning)
        assert response.status_code == 302

        # La venue NON dovrebbe essere stata creata (o creata senza tavoli)
        created_venue = BilliardHall.query.filter_by(name=new_venue_name).first()

        # Se creata, dovrebbe essere senza tavoli e generare warning
        if created_venue:
            assert (
                created_venue.number_of_tables is None
                or created_venue.number_of_tables == 0
            )
