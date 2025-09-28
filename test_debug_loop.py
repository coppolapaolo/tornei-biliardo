import pytest
from typing import List
from models import User

@pytest.mark.integration
class TestDebugLoop:

    @pytest.fixture
    def admin_user(self, db_session) -> User:
        """Create admin user for test."""
        import uuid
        from models.user.role_enum import UserRole

        print("Creating admin_user...")
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("admin123")
        db_session.add(admin)
        db_session.commit()
        return admin

    @pytest.fixture
    def director_user(self, db_session) -> User:
        """Create director user for test."""
        import uuid
        from models.user.role_enum import UserRole

        print("Creating director_user...")
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()
        return director

    @pytest.fixture
    def co_director_user(self, db_session) -> User:
        """Create co-director user for test."""
        import uuid
        from models.user.role_enum import UserRole

        print("Creating co_director_user...")
        unique_id = str(uuid.uuid4())[:8]
        co_director = User(
            username=f"co_director_{unique_id}",
            email=f"co_director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        co_director.set_password("co_director123")
        db_session.add(co_director)
        db_session.commit()
        return co_director

    @pytest.fixture
    def players_10(self, db_session) -> List[User]:
        """Create 10 players for testing."""
        import uuid
        from models.user.role_enum import UserRole

        print("Creating players_10...")
        batch_id = str(uuid.uuid4())[:8]
        players = []
        for i in range(10):
            player = User(
                username=f"player_{i}_{batch_id}",
                email=f"player_{i}_{batch_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            players.append(player)

        db_session.add_all(players)
        db_session.commit()
        return players

    def test_minimal_fixture_usage(
        self,
        admin_user: User,
        director_user: User,
        co_director_user: User,
        players_10: List[User],
        db_session,
        client,
    ):
        """Test that just uses the fixtures without doing anything else."""
        print("Test started!")
        assert admin_user is not None
        assert director_user is not None
        assert co_director_user is not None
        assert len(players_10) == 10
        print("Test completed!")