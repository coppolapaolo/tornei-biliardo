"""
Test-Driven Development per RoundService extraction.

Estrazione semplice dei metodi di gestione turni da GaraService
per centralizzare tutta la logica round management in un unico service.
"""

import pytest
from datetime import date, timedelta
from models.base import db
from models.status_enum import GaraStatus
from models.competition.models import Gara, Inscription
from models.user.models import User
from models.user.role_enum import UserRole


class TestRoundServiceTDD:
    """TDD tests per guidare l'estrazione dei metodi di gestione turni."""

    def test_round_service_can_start_first_round(
        self, isolated_director_user, db_session
    ):
        """RoundService deve poter avviare il primo turno."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.INSCRIPTION.value,
        )
        db_session.add(gara)
        db_session.commit()

        # Aggiungi iscrizioni sufficienti (6 per min_participants default)
        inscription1 = Inscription(user_id=isolated_director_user.id, gara_id=gara.id)
        db.session.add(inscription1)

        # Crea 5 giocatori aggiuntivi
        for i in range(2, 7):
            player = User(
                username=f"player{i}_test",
                email=f"player{i}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("password123")
            db.session.add(player)
            db.session.commit()
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db.session.add(inscription)

        db.session.commit()

        from models.competition.services import RoundService

        # Metodo deve essere spostato da GaraService
        result_gara = RoundService.start_first_round(gara.id)

        assert result_gara.status == GaraStatus.PLAYING.value
        assert result_gara.current_round == 1

    def test_round_service_can_cancel_first_round_startup(
        self, isolated_director_user, db_session
    ):
        """RoundService deve avere il metodo cancel_first_round_startup."""
        from models.competition.services import RoundService

        # Test che il metodo esista ed è chiamabile
        assert hasattr(RoundService, "cancel_first_round_startup")
        assert callable(getattr(RoundService, "cancel_first_round_startup"))

    def test_round_service_can_create_round_with_strategy(
        self, isolated_director_user, db_session
    ):
        """RoundService deve gestire creazione turno con strategia."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            rounds_count=3,
        )
        db_session.add(gara)
        db_session.commit()

        # Aggiungi giocatori sufficienti per la strategia Amalfi (minimo 3)
        players = []
        for i in range(4):
            player = User(
                username=f"player_round{i}_test",
                email=f"player_round{i}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("password123")
            db.session.add(player)
            players.append(player)

        db.session.commit()

        # Aggiungi iscrizioni
        for player in players:
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db_session.add(inscription)
        db_session.commit()

        # Crea alcuni match del round 1 per soddisfare i prerequisiti Amalfi
        from models.match.models import Match
        from models.classification.models import RoundClassification

        match1 = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            is_bye=False,
            winner_id=players[0].id,
            player1_score=5,
            player2_score=3,
            status="completed",
        )
        match2 = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[2].id,
            player2_id=players[3].id,
            is_bye=False,
            winner_id=players[2].id,
            player1_score=5,
            player2_score=2,
            status="completed",
        )
        db_session.add(match1)
        db_session.add(match2)
        db_session.commit()

        # Crea classificazione round 1
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        from models.competition.services import RoundService

        # Dovrebbe creare un turno usando la strategia
        result = RoundService.create_round_with_strategy(gara.id, round_number=2)

        # Il risultato dipende dalla strategia ma dovrebbe restituire informazioni sui match
        assert result is not None

    def test_create_round_with_strategy_creates_matches_for_random_strategy(
        self, isolated_director_user, db_session
    ):
        """Test TDD: create_round_with_strategy deve creare match per strategia random."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara Random",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            matchmaking_strategy="random",
            rounds_count=3,
        )
        db_session.add(gara)
        db_session.commit()

        # Aggiungi 4 giocatori per testare abbinamenti
        players = []
        for i in range(4):
            player = User(
                username=f"player{i}_test",
                email=f"player{i}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("password123")
            db.session.add(player)
            players.append(player)

        db.session.commit()

        # Aggiungi iscrizioni
        for player in players:
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db.session.add(inscription)
        db.session.commit()

        from models.competition.round_service import RoundService

        # TDD: Il metodo dovrebbe essere implementato completamente nel RoundService
        result = RoundService.create_round_with_strategy(gara.id, 2)

        # Verifica che il metodo restituisca il tuple atteso
        assert isinstance(result, tuple)
        assert (
            len(result) == 4
        )  # (total_matches, normal_matches, bye_matches, trio_matches)

        total_matches, normal_matches, bye_matches, trio_matches = result
        assert total_matches > 0  # Almeno alcuni match devono essere creati
        assert normal_matches >= 0
        assert bye_matches >= 0
        assert trio_matches >= 0

        # Verifica che i match siano stati effettivamente creati nel database
        from models.match.models import Match

        created_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()
        assert len(created_matches) == total_matches

    def test_create_round_with_strategy_is_idempotent(
        self, isolated_director_user, db_session
    ):
        """Test TDD: create_round_with_strategy deve essere idempotente."""
        tomorrow = date.today() + timedelta(days=1)

        gara = Gara(
            number=1,
            name="Test Gara Idempotent",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.PLAYING.value,
            current_round=1,
            matchmaking_strategy="random",
            rounds_count=3,
        )
        db_session.add(gara)
        db_session.commit()

        # Aggiungi giocatori
        players = []
        for i in range(4):
            player = User(
                username=f"player_idem{i}_test",
                email=f"player_idem{i}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("password123")
            db.session.add(player)
            players.append(player)

        db.session.commit()

        for player in players:
            inscription = Inscription(user_id=player.id, gara_id=gara.id)
            db.session.add(inscription)
        db.session.commit()

        from models.competition.round_service import RoundService

        # Prima chiamata
        result1 = RoundService.create_round_with_strategy(gara.id, 2)

        # Seconda chiamata - dovrebbe restituire gli stessi risultati
        result2 = RoundService.create_round_with_strategy(gara.id, 2)

        # Risultati identici (idempotente)
        assert result1 == result2

        # Verifica che non siano stati creati match duplicati
        from models.match.models import Match

        created_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()
        assert len(created_matches) == result1[0]  # Total matches

    def test_create_round_with_strategy_validates_input(
        self, isolated_director_user, db_session
    ):
        """Test TDD: create_round_with_strategy deve validare input."""
        from models.competition.round_service import RoundService

        # Test gara inesistente
        with pytest.raises(ValueError, match="Gara .* non trovata"):
            RoundService.create_round_with_strategy(99999, 1)

        # Test round number invalido
        tomorrow = date.today() + timedelta(days=1)
        gara = Gara(
            number=1,
            name="Test Validation",
            date=tomorrow,
            discipline="palla 8",
            distance=5,
            director_id=isolated_director_user.id,
            status=GaraStatus.PLAYING.value,
            rounds_count=3,
        )
        db_session.add(gara)
        db_session.commit()

        # Round number troppo alto
        with pytest.raises(ValueError, match="Turno .* non valido"):
            RoundService.create_round_with_strategy(gara.id, 5)  # rounds_count=3

        # Round number troppo basso
        with pytest.raises(ValueError, match="Turno .* non valido"):
            RoundService.create_round_with_strategy(gara.id, 0)
