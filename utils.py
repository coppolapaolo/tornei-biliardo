# utils.py - STEP 1: Aggiornato per nuovi models
from datetime import datetime
from werkzeug.security import generate_password_hash
from models import db, User, Tournament, Prova, Match, Inscription, Rack
from functools import wraps
from flask_login import current_user
from flask import flash, redirect, url_for
import random

def admin_required(f):
    """Decorator per richiedere privilegi admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Accesso riservato agli amministratori.')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def get_database_stats():
    """Statistiche database per debug"""
    try:
        return {
            'users': User.query.count(),
            'tournaments': Tournament.query.count(),
            'provas': Prova.query.count(),
            'inscriptions': Inscription.query.count(),
            'matches': Match.query.count(),
        }
    except:
        return {'error': 'Database not accessible'}

def create_round_matches(prova, players_or_inscriptions, round_number):
    """Crea gli abbinamenti per un turno - AGGIORNATO per nuova logica prova"""
    if isinstance(players_or_inscriptions[0], Inscription):
        players = [insc.user for insc in players_or_inscriptions]
    else:
        players = players_or_inscriptions
    
    matches = []
    
    if len(players) % 2 == 1:
        # Numero dispari: ultimo giocatore ha un bye
        bye_player = players[-1]
        
        # Usa la nuova logica per il punteggio bye
        if prova.best_of:
            bye_score = prova.get_winning_score()
        else:
            bye_score = prova.distance
            
        match = Match(
            prova_id=prova.id,
            round_number=round_number,
            player1_id=bye_player.id,
            is_bye=True,
            player1_score=bye_score,
            winner_id=bye_player.id,
            status='completed'
        )
        matches.append(match)
        players = players[:-1]
    
    # Crea abbinamenti per giocatori pari
    for i in range(0, len(players), 2):
        match = Match(
            prova_id=prova.id,
            round_number=round_number,
            player1_id=players[i].id,
            player2_id=players[i+1].id
        )
        matches.append(match)
    
    db.session.add_all(matches)
    return matches

def calculate_round_classification(prova_id, round_number):
    """Calcola la classifica dopo un turno"""
    matches = Match.query.filter_by(prova_id=prova_id, round_number=round_number).all()
    players_stats = {}
    
    for match in matches:
        if match.is_bye:
            # Bye: vittoria automatica
            if match.player1_id not in players_stats:
                players_stats[match.player1_id] = {
                    'matches_won': 0, 'point_diff': 0, 'initial_order': 0
                }
            players_stats[match.player1_id]['matches_won'] += 1
            players_stats[match.player1_id]['point_diff'] += match.player1_score
        else:
            # Match normale
            for player_id in [match.player1_id, match.player2_id]:
                if player_id not in players_stats:
                    inscription = Inscription.query.filter_by(
                        user_id=player_id, prova_id=prova_id
                    ).first()
                    players_stats[player_id] = {
                        'matches_won': 0, 
                        'point_diff': 0, 
                        'initial_order': inscription.initial_order if inscription else 999
                    }
            
            if match.status == 'completed' and match.winner_id:
                # Aggiorna statistiche vincitore
                players_stats[match.winner_id]['matches_won'] += 1
                
                # Calcola differenza punti
                if match.winner_id == match.player1_id:
                    diff = match.player1_score - match.player2_score
                    players_stats[match.player1_id]['point_diff'] += diff
                    players_stats[match.player2_id]['point_diff'] -= diff
                else:
                    diff = match.player2_score - match.player1_score
                    players_stats[match.player2_id]['point_diff'] += diff
                    players_stats[match.player1_id]['point_diff'] -= diff
    
    # Ordina per: match vinti (desc), differenza punti (desc), ordine iniziale (asc)
    sorted_players = sorted(
        players_stats.items(),
        key=lambda x: (-x[1]['matches_won'], -x[1]['point_diff'], x[1]['initial_order'])
    )
    
    return [(player_id, stats) for player_id, stats in sorted_players]

def create_default_users():
    """Crea utenti predefiniti per il reset"""
    # Admin
    admin = User(
        username='admin',
        email='admin@tournament.com',
        is_admin=True
    )
    admin.set_password('admin123')
    
    # Mario
    mario = User(
        username='mario',
        email='mario@test.com',
        is_admin=False
    )
    mario.set_password('mario123')
    
    # Pino
    pino = User(
        username='pino',
        email='pino@test.com',
        is_admin=False
    )
    pino.set_password('pino123')
    
    db.session.add_all([admin, mario, pino])
    db.session.commit()
    
    return admin, mario, pino

def create_sample_tournament():
    """Crea un torneo di esempio - AGGIORNATO per nuovo model"""
    tournament = Tournament(
        name='Torneo Test',
        tournament_type='Amalfi',
        without_x=False,
        final_playoffs=True,
        challenge_mode=False,
        is_active=True
    )
    db.session.add(tournament)
    db.session.commit()
    
    # Prova di esempio con NUOVI CAMPI
    from datetime import date
    prova = Prova(
        tournament_id=tournament.id,
        number=1,
        name='Prima Prova',
        date=date(2025, 8, 1),
        location='Circolo Biliardo Centro',
        description='Prima prova del torneo di esempio',
        rounds_count=3,
        min_participants=2,
        max_participants=16,
        entry_fee=10.0,
        discipline='palla 9',
        distance=7,
        best_of=True,  # Al meglio di 7 (vince con 4)
        status='setup'
    )
    db.session.add(prova)
    db.session.commit()
    
    return tournament

def create_admin_if_not_exists():
    """Crea l'utente admin se non esiste"""
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@tournament.com',
            is_admin=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Admin user created: admin/admin123")
    return admin