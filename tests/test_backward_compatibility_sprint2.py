"""
Test backward compatibility after Sprint 2 changes.

Ensures that existing code continues to work with nullable tournament_id.
"""

import pytest
from models import db, User, Tournament, Prova, Inscription
from datetime import datetime, timedelta


class TestBackwardCompatibility:
    """Test that existing functionality is not broken."""

    def test_existing_prova_with_tournament(self, app):
        """Test that existing Prova with tournament continues to work."""
        with app.app_context():
            # Create tournament
            tournament = Tournament(
                name="Existing Tournament", tournament_type="Amalfi"
            )
            db.session.add(tournament)
            db.session.commit()

            # Create prova the old way (only tournament_id)
            prova = Prova(
                tournament_id=tournament.id,
                number=1,
                name="Old Style Prova",
                date=datetime.now().date(),
                discipline="palla_8",
                distance=9,
                rounds_count=3,
            )
            db.session.add(prova)
            db.session.commit()

            # Verify it works
            assert prova.tournament == tournament
            assert prova.tournament_id == tournament.id
            assert prova.director_id is None
            assert not prova.is_standalone

            # Test relationships
            assert prova in tournament.provas

    def test_inscription_works_both_types(self, app):
        """Test inscriptions work for both tournament and standalone provas."""
        with app.app_context():
            # Create users
            player = User(username="player", email="player@test.com")
            player.set_password("password")
            director = User(username="director", email="director@test.com")
            director.set_password("password")
            db.session.add_all([player, director])

            # Create tournament and prova
            tournament = Tournament(name="Test Tournament")
            db.session.add(tournament)
            db.session.commit()

            prova_tournament = Prova(
                tournament_id=tournament.id,
                number=1,
                name="Tournament Prova",
                date=datetime.now().date() + timedelta(days=10),
                discipline="palla_8",
                distance=9,
                status="inscription",
                inscription_start=datetime.now() - timedelta(days=1),
                inscription_end=datetime.now() + timedelta(days=7),
            )

            prova_standalone = Prova(
                director_id=director.id,
                number=2,
                name="Standalone Prova",
                date=datetime.now().date() + timedelta(days=15),
                discipline="palla_9",
                distance=7,
                status="inscription",
                inscription_start=datetime.now() - timedelta(days=1),
                inscription_end=datetime.now() + timedelta(days=7),
            )

            db.session.add_all([prova_tournament, prova_standalone])
            db.session.commit()

            # Test inscriptions
            inscription1 = Inscription(user_id=player.id, prova_id=prova_tournament.id)
            inscription2 = Inscription(user_id=player.id, prova_id=prova_standalone.id)

            db.session.add_all([inscription1, inscription2])
            db.session.commit()

            # Verify
            assert prova_tournament.is_user_inscribed(player.id)
            assert prova_standalone.is_user_inscribed(player.id)
            assert len(player.inscriptions) == 2

    def test_prova_queries_still_work(self, app):
        """Test that existing queries continue to work."""
        with app.app_context():
            # Create test data
            tournament = Tournament(name="Query Test Tournament")
            db.session.add(tournament)
            db.session.commit()

            director = User(username="querydir", email="qd@test.com")
            director.set_password("password")
            db.session.add(director)
            db.session.commit()

            # Mix of tournament and standalone provas
            provas = []
            for i in range(3):
                prova = Prova(
                    tournament_id=tournament.id,
                    number=i + 1,
                    name=f"Tournament Prova {i+1}",
                    date=datetime.now().date(),
                    discipline="palla_8",
                    distance=9,
                    status="setup",
                )
                provas.append(prova)

            for i in range(2):
                prova = Prova(
                    director_id=director.id,
                    number=i + 4,
                    name=f"Standalone Prova {i+1}",
                    date=datetime.now().date(),
                    discipline="palla_9",
                    distance=7,
                    status="inscription",
                )
                provas.append(prova)

            db.session.add_all(provas)
            db.session.commit()

            # Test queries
            all_provas = Prova.query.all()
            assert len(all_provas) == 5

            # Filter by tournament (old style query)
            tournament_provas = Prova.query.filter_by(tournament_id=tournament.id).all()
            assert len(tournament_provas) == 3

            # Filter by status
            inscription_provas = Prova.query.filter_by(status="inscription").all()
            assert len(inscription_provas) == 2

            # Join queries still work
            from sqlalchemy.orm import joinedload

            prova_with_tournament = (
                Prova.query.options(joinedload(Prova.tournament))
                .filter(Prova.tournament_id.isnot(None))
                .first()
            )

            assert prova_with_tournament.tournament.name == "Query Test Tournament"

    def test_null_handling_in_methods(self, app):
        """Test that methods handle null tournament gracefully."""
        with app.app_context():
            director = User(username="nulltest", email="null@test.com")
            director.set_password("password")
            db.session.add(director)
            db.session.commit()

            prova = Prova(
                director_id=director.id,
                number=1,
                name="Null Test Prova",
                date=datetime.now().date(),
                discipline="palla_8",
                distance=9,
            )
            db.session.add(prova)
            db.session.commit()

            # These should not raise errors
            assert prova.can_be_modified()
            assert prova.can_be_deleted()
            assert prova.can_modify_inscription_dates()
            assert (
                prova.get_winning_score() == 9
            )  # best_of default is False, so returns distance
            assert prova.is_match_finished(9, 3)  # 9 is winning score
            assert not prova.is_match_finished(8, 3)  # 8 is not enough
