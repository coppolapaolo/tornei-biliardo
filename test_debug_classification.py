"""
Debug script per testare la logica di visualizzazione delle classificazioni
"""

from app import create_app
from models import db, User, Match
from models.user.role_enum import UserRole
from models.status_enum import MatchStatus
from models.competition.services import (
    GaraService,
    InscriptionService,
    ProvaStateMachine,
)
from models.classification.models import RoundClassification
from datetime import date

# Create app and context
app = create_app()
with app.app_context():
    # Create admin user
    import uuid

    admin_id = str(uuid.uuid4())[:8]
    admin = User(
        username=f"debug_admin_{admin_id}",
        email=f"debug_admin_{admin_id}@test.com",
        role=UserRole.ADMIN.value,
    )
    admin.set_password("admin123")
    db.session.add(admin)
    db.session.commit()

    # Create gara
    gara = GaraService.create_gara(
        number=1,
        name="Debug Classification Test",
        date=date.today(),
        discipline="9-ball",
        distance=5,
        campionato_id=None,
        director_id=admin.id,
        rounds_count=3,
    )

    # Move to inscription
    ProvaStateMachine.to_inscription(gara)

    # Create 4 players
    players = []
    for i in range(4):
        player = User(
            username=f"debug_class_player_{admin_id}_{i}",
            email=f"debug_class_player_{admin_id}_{i}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        db.session.add(player)
        players.append(player)

    db.session.commit()

    # Register players
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)

    # Start tournament and create first round
    ProvaStateMachine.start_playing(gara)
    GaraService.create_round_with_strategy(gara.id, 1)

    print(f"After first round: current_round = {gara.current_round}")

    # Check matches in round 1
    first_round_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
    print(f"First round matches: {len(first_round_matches)}")
    for match in first_round_matches:
        print(
            f"  Match {match.id}: {match.player1.username} vs {match.player2.username if match.player2 else 'BYE'} - Status: {match.status}"
        )

    # Test round completion check BEFORE completing matches
    def is_round_completed(gara_id, round_number):
        round_matches = Match.query.filter_by(
            gara_id=gara_id, round_number=round_number
        ).all()
        if not round_matches:
            return False
        return all(
            match.status == MatchStatus.COMPLETED.value for match in round_matches
        )

    print(
        f"Round 1 completed BEFORE match completion: {is_round_completed(gara.id, 1)}"
    )

    # Complete all matches in round 1
    for i, match in enumerate(first_round_matches):
        if not match.is_bye:
            match.status = MatchStatus.COMPLETED.value
            match.winner_id = match.player1_id
            match.player1_score = 3
            match.player2_score = 1
            db.session.add(match)

    db.session.commit()

    print(f"Round 1 completed AFTER match completion: {is_round_completed(gara.id, 1)}")

    # Check if classifications exist
    round_1_classifications = RoundClassification.query.filter_by(
        gara_id=gara.id, round_number=1
    ).all()
    print(f"Round 1 classifications found: {len(round_1_classifications)}")

    # Try to create classifications manually if none exist
    if len(round_1_classifications) == 0:
        print("Creating manual classifications for round 1...")
        for i, player in enumerate(players):
            classification = RoundClassification(
                gara_id=gara.id,
                round_number=1,
                user_id=player.id,
                position=i + 1,
                matches_won=1 if i == 0 else 0,
                rack_difference=2 if i == 0 else -2,
            )
            db.session.add(classification)
        db.session.commit()

        round_1_classifications = RoundClassification.query.filter_by(
            gara_id=gara.id, round_number=1
        ).all()
        print(
            f"Round 1 classifications after manual creation: {len(round_1_classifications)}"
        )

    # Test the logic from the route
    current_round_classification = None
    latest_round_with_classification = None

    if gara.current_round > 0:
        print(f"Checking rounds from {gara.current_round} down to 1...")
        for round_num in range(gara.current_round, 0, -1):
            print(f"  Checking round {round_num}...")

            if is_round_completed(gara.id, round_num):
                print(f"    Round {round_num} is completed")
                classification = (
                    RoundClassification.query.filter_by(
                        gara_id=gara.id, round_number=round_num
                    )
                    .order_by(RoundClassification.position)
                    .all()
                )

                print(
                    f"    Found {len(classification)} classification entries for round {round_num}"
                )

                if classification:
                    current_round_classification = classification
                    latest_round_with_classification = round_num
                    print(f"    Using classification from round {round_num}")
                    break
            else:
                print(f"    Round {round_num} is NOT completed")

    print(f"\nFinal result:")
    print(
        f"  current_round_classification: {len(current_round_classification) if current_round_classification else 0} entries"
    )
    print(f"  latest_round_with_classification: {latest_round_with_classification}")

    # Test with web request
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin.id)
            sess["_fresh"] = True

        response = client.get(f"/admin/gara/{gara.id}")
        print(f"\nWeb response status: {response.status_code}")

        html_content = response.data.decode("utf-8")
        has_classification = "Classifica dopo Turno" in html_content
        print(f"Has classification in HTML: {has_classification}")

        if has_classification:
            print("Found classification section!")
        else:
            print("No classification section found in HTML")
