"""
Enhanced reset functionality with comprehensive example data

This module provides rich example data for testing the new user system
and permission workflows.

Author: Refactoring Phase 1 - Task 1.6
Created: 2025-01-31
"""

from datetime import datetime, timedelta, date
from models.user.models import User, TournamentDirector, DirectorRequest
from models.user.services import UserService, DirectorRequestService
from models.legacy_models import Tournament, Prova, Inscription, Match, Rack, Classification, Playoff
from models.base import db


def create_enhanced_users():
    """Create diverse set of example users for testing"""
    
    # Admin users
    admin = UserService.create_user(
        username='admin',
        email='admin@tornei.com',
        password='admin123',
        role='admin'
    )
    
    # Director users
    director1 = UserService.create_user(
        username='mario_rossi',
        email='mario.rossi@email.com',
        password='mario123',
        role='director'
    )
    
    director2 = UserService.create_user(
        username='lucia_verdi',
        email='lucia.verdi@email.com',
        password='lucia123',
        role='director'
    )
    
    # Player users with variety
    players_data = [
        ('giovanni_bianchi', 'giovanni@email.com', 'giovanni123'),
        ('anna_ferrari', 'anna@email.com', 'anna123'),
        ('marco_russo', 'marco@email.com', 'marco123'),
        ('sara_marino', 'sara@email.com', 'sara123'),
        ('luca_greco', 'luca@email.com', 'luca123'),
        ('elena_ricci', 'elena@email.com', 'elena123'),
        ('davide_costa', 'davide@email.com', 'davide123'),
        ('chiara_lombardi', 'chiara@email.com', 'chiara123'),
        ('andrea_conti', 'andrea@email.com', 'andrea123'),
        ('valeria_galli', 'valeria@email.com', 'valeria123'),
    ]
    
    players = []
    for username, email, password in players_data:
        player = UserService.create_user(
            username=username,
            email=email,
            password=password,
            role='player'
        )
        players.append(player)
    
    # Create some director requests for testing admin workflows
    pending_user = UserService.create_user(
        username='aspirante_director',
        email='aspirante@email.com',
        password='aspirante123',
        role='player'
    )
    
    # Create director request
    DirectorRequestService.create_request(pending_user.id)
    
    return {
        'admin': admin,
        'directors': [director1, director2],
        'players': players,
        'pending_request_user': pending_user
    }


def create_enhanced_tournaments():
    """Create comprehensive tournament examples"""
    
    # Torneo 1: Torneo Principale
    tournament1 = Tournament(
        name="Torneo Primavera 2025",
        tournament_type="Amalfi",
        without_x=False,
        final_playoffs=True,
        challenge_mode=False,
        is_active=True,
    )
    db.session.add(tournament1)
    db.session.commit()

    # Torneo 2: Torneo Secondario
    tournament2 = Tournament(
        name="Coppa Estate 2025",
        tournament_type="Amalfi",
        without_x=True,
        final_playoffs=False,
        challenge_mode=True,
        is_active=True,
    )
    db.session.add(tournament2)
    db.session.commit()

    # Torneo 3: Torneo Elite
    tournament3 = Tournament(
        name="Championship Elite 2025",
        tournament_type="Amalfi",
        without_x=False,
        final_playoffs=True,
        challenge_mode=False,
        is_active=True,
    )
    db.session.add(tournament3)
    db.session.commit()

    return [tournament1, tournament2, tournament3]


def create_enhanced_provas(tournaments):
    """Create comprehensive prova examples"""
    
    today = date.today()
    provas = []

    # Prove per Torneo 1
    prova1_t1 = Prova(
        tournament_id=tournaments[0].id,
        number=1,
        name="Prima Prova",
        date=today + timedelta(days=7),
        location="Circolo Biliardo Centro",
        description="Prima prova del torneo primaverile",
        rounds_count=3,
        min_participants=4,
        max_participants=16,
        entry_fee=15.0,
        discipline="palla 9",
        distance=7,
        best_of=True,  # Al meglio di 7 (vince con 4)
        status="setup",
    )
    db.session.add(prova1_t1)
    provas.append(prova1_t1)

    prova2_t1 = Prova(
        tournament_id=tournaments[0].id,
        number=2,
        name="Seconda Prova",
        date=today + timedelta(days=14),
        location="Circolo Biliardo Centro",
        description="Seconda prova del torneo primaverile",
        rounds_count=3,
        min_participants=4,
        max_participants=16,
        entry_fee=15.0,
        discipline="palla 8",
        distance=5,
        best_of=False,  # 5 rack esatti
        status="setup",
    )
    db.session.add(prova2_t1)
    provas.append(prova2_t1)

    # Prove per Torneo 2 (Senza X)
    prova1_t2 = Prova(
        tournament_id=tournaments[1].id,
        number=1,
        name="Prova Senza X",
        date=today + timedelta(days=21),
        location="Circolo Biliardo Periferia",
        description="Prova speciale senza X",
        rounds_count=3,
        min_participants=6,
        max_participants=12,
        entry_fee=20.0,
        discipline="palla 10",
        distance=9,
        best_of=True,
        status="setup",
    )
    db.session.add(prova1_t2)
    provas.append(prova1_t2)

    # Prove per Torneo 3 (Elite)
    prova1_t3 = Prova(
        tournament_id=tournaments[2].id,
        number=1,
        name="Elite Challenge",
        date=today + timedelta(days=28),
        location="Circolo Biliardo Elite",
        description="Prova per giocatori elite",
        rounds_count=3,
        min_participants=8,
        max_participants=16,
        entry_fee=25.0,
        discipline="palla 9",
        distance=11,
        best_of=True,
        status="setup",
    )
    db.session.add(prova1_t3)
    provas.append(prova1_t3)

    db.session.commit()
    return provas


def create_enhanced_inscriptions(users, provas):
    """Create sample inscriptions"""
    
    inscriptions = []
    
    # Get players (exclude admin and directors)
    players = [u for u in users['players']]
    
    # Inscriptions for first prova
    for i, player in enumerate(players[:8]):  # First 8 players
        inscription = Inscription(
            user_id=player.id,
            prova_id=provas[0].id,
            initial_order=i + 1
        )
        db.session.add(inscription)
        inscriptions.append(inscription)
    
    # Inscriptions for second prova
    for i, player in enumerate(players[2:10]):  # Players 3-10
        inscription = Inscription(
            user_id=player.id,
            prova_id=provas[1].id,
            initial_order=i + 1
        )
        db.session.add(inscription)
        inscriptions.append(inscription)
    
    # Inscriptions for third prova (Senza X)
    for i, player in enumerate(players[:6]):  # First 6 players
        inscription = Inscription(
            user_id=player.id,
            prova_id=provas[2].id,
            initial_order=i + 1
        )
        db.session.add(inscription)
        inscriptions.append(inscription)
    
    # Inscriptions for fourth prova (Elite)
    for i, player in enumerate(players[4:]):  # Players 5-10
        inscription = Inscription(
            user_id=player.id,
            prova_id=provas[3].id,
            initial_order=i + 1
        )
        db.session.add(inscription)
        inscriptions.append(inscription)
    
    db.session.commit()
    return inscriptions


def create_enhanced_tournament_directors(users, tournaments):
    """Create tournament director assignments"""
    
    assignments = []
    
    # Assign directors to tournaments
    assignment1 = TournamentDirector(
        user_id=users['directors'][0].id,
        tournament_id=tournaments[0].id,
        assigned_by_id=users['admin'].id
    )
    db.session.add(assignment1)
    assignments.append(assignment1)
    
    assignment2 = TournamentDirector(
        user_id=users['directors'][1].id,
        tournament_id=tournaments[1].id,
        assigned_by_id=users['admin'].id
    )
    db.session.add(assignment2)
    assignments.append(assignment2)
    
    # Both directors assigned to third tournament
    assignment3 = TournamentDirector(
        user_id=users['directors'][0].id,
        tournament_id=tournaments[2].id,
        assigned_by_id=users['admin'].id
    )
    db.session.add(assignment3)
    assignments.append(assignment3)
    
    assignment4 = TournamentDirector(
        user_id=users['directors'][1].id,
        tournament_id=tournaments[2].id,
        assigned_by_id=users['admin'].id
    )
    db.session.add(assignment4)
    assignments.append(assignment4)
    
    db.session.commit()
    return assignments


def create_enhanced_reset_data():
    """Create comprehensive reset data for testing"""
    
    print("🔄 Creating enhanced reset data...")
    
    # Create users
    users = create_enhanced_users()
    print(f"✅ Created {len(users['players'])} players, {len(users['directors'])} directors, 1 admin")
    
    # Create tournaments
    tournaments = create_enhanced_tournaments()
    print(f"✅ Created {len(tournaments)} tournaments")
    
    # Create provas
    provas = create_enhanced_provas(tournaments)
    print(f"✅ Created {len(provas)} provas")
    
    # Create inscriptions
    inscriptions = create_enhanced_inscriptions(users, provas)
    print(f"✅ Created {len(inscriptions)} inscriptions")
    
    # Create tournament director assignments
    assignments = create_enhanced_tournament_directors(users, tournaments)
    print(f"✅ Created {len(assignments)} tournament director assignments")
    
    print("🎉 Enhanced reset data created successfully!")
    print("\n📋 Summary:")
    print(f"   • Admin: {users['admin'].username}")
    print(f"   • Directors: {', '.join([d.username for d in users['directors']])}")
    print(f"   • Players: {len(users['players'])} users")
    print(f"   • Pending director request: {users['pending_request_user'].username}")
    print(f"   • Tournaments: {len(tournaments)}")
    print(f"   • Provas: {len(provas)}")
    print(f"   • Inscriptions: {len(inscriptions)}")
    
    return {
        'users': users,
        'tournaments': tournaments,
        'provas': provas,
        'inscriptions': inscriptions,
        'assignments': assignments
    }


def reset_database_enhanced():
    """Enhanced database reset with comprehensive example data"""
    
    print("⚠️  WARNING: This will delete all existing data!")
    print("🔄 Resetting database...")
    
    # Reset database
    db.drop_all()
    db.create_all()
    
    # Create enhanced data
    data = create_enhanced_reset_data()
    
    print("\n✅ Database reset completed with enhanced data!")
    print("🚀 Ready for testing the new user system and permissions!")
    
    return data 