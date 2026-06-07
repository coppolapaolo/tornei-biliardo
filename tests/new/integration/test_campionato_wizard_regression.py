"""Integration tests for campionato wizard route.

Regression tests for wizard template rendering.
"""

import pytest
import uuid


def _create_and_login_director(client, db_session):
    """Create a director user and login via the auth route."""
    from models import User
    from models.user.role_enum import UserRole

    unique_id = str(uuid.uuid4())[:8]
    director = User(
        username=f"director_{unique_id}",
        email=f"director_{unique_id}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("testpass123")
    db_session.add(director)
    db_session.commit()

    # Login via auth route
    client.post(
        "/auth/login",
        data={"username": director.username, "password": "testpass123"},
    )
    return director


@pytest.mark.integration
class TestCampionatoWizardRouteRegression:
    """Regression tests for /admin/campionato/wizard route.

    Bug: Route returned 500 error with 'matchmaking_systems' is undefined
    Root cause: Template used variable not passed by route handler
    Fix: Added classification_compatibility from backend (single source of truth)
    """

    def test_wizard_renders_without_error(self, client, db_session):
        """Wizard step 1 should render without template errors.

        Regression: Previously failed with UndefinedError for 'matchmaking_systems'.
        """
        _create_and_login_director(client, db_session)

        # Request wizard page
        response = client.get("/admin/campionato/wizard")

        # Should not return 500
        assert response.status_code == 200, (
            f"Wizard should render successfully, got {response.status_code}"
        )

    def test_wizard_contains_classification_compatibility_json(self, client, db_session):
        """Wizard page should contain classification_compatibility as JSON.

        The JavaScript needs this data to enable/disable matchmaking options
        based on the selected classification system.
        """
        _create_and_login_director(client, db_session)

        response = client.get("/admin/campionato/wizard")
        html = response.data.decode("utf-8")

        # Should contain the JSON-serialized compatibility map
        assert "validMatchmaking" in html, "JS variable validMatchmaking not found"

        # Should contain strategy values from backend
        assert '"amalfi"' in html or "'amalfi'" in html, "amalfi strategy not in page"
        assert '"random"' in html or "'random'" in html, "random strategy not in page"

    def test_wizard_matchmaking_select_has_options(self, client, db_session):
        """Wizard should render matchmaking strategy select options.

        The select should have Amalfi and Random options without data-systems
        attribute (which was causing the original error).
        """
        _create_and_login_director(client, db_session)

        response = client.get("/admin/campionato/wizard")
        html = response.data.decode("utf-8")

        # Should have select with options
        assert 'id="campionato_type"' in html, "campionato_type select not found"
        assert 'value="amalfi"' in html, "Amalfi option not found"
        assert 'value="random"' in html, "Random option not found"

        # Should NOT have the broken data-systems attribute
        assert "matchmaking_systems" not in html, (
            "Broken matchmaking_systems reference still in template"
        )

    @pytest.mark.skip(reason="Session isolation issue with Flask-Login in test environment")
    def test_wizard_requires_authentication(self, app):
        """Wizard should redirect unauthenticated users to login."""
        # Use fresh client without any session state
        with app.test_client() as fresh_client:
            response = fresh_client.get("/admin/campionato/wizard")

            # Should redirect to login
            assert response.status_code == 302, "Should redirect unauthenticated users"

    def test_wizard_classification_options_present(self, client, db_session):
        """Wizard should have classification system options."""
        _create_and_login_director(client, db_session)

        response = client.get("/admin/campionato/wizard")
        html = response.data.decode("utf-8")

        # Classification system select should be present
        assert 'id="default_classification_system"' in html
        assert 'value="WINS"' in html
        assert 'value="RACK"' in html
