# routes/main.py - AGGIORNATO per multi-torneo visibility
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required, logout_user
from datetime import date
from models import db, Tournament, Prova, Classification, User
from utils import create_default_users, create_sample_tournament
from config import Config

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Homepage con TUTTI i tornei attivi - AGGIORNATO"""
    # 🔒 ADMIN AUTO-REDIRECT
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin.dashboard'))

    # Mostra TUTTI i tornei attivi
    active_tournaments = Tournament.query.filter_by(is_active=True).order_by(Tournament.created_at.desc()).all()
    
    if not active_tournaments:
        return render_template('no_tournament.html')
    
    # Raccogli dati per TUTTI i tornei attivi
    tournaments_data = []
    for tournament in active_tournaments:
        # Prossime prove per questo torneo
        upcoming_provas = Prova.query.filter(
            Prova.tournament_id == tournament.id,
            Prova.date >= date.today()
        ).order_by(Prova.date).limit(3).all()
        
        # Classifica generale per questo torneo (top 5)
        top_classifications = Classification.query.filter(
            Classification.tournament_id == tournament.id
        ).order_by(Classification.position).limit(5).all()
        
        tournaments_data.append({
            'tournament': tournament,
            'upcoming_provas': upcoming_provas,
            'top_classifications': top_classifications
        })
    
    return render_template('index.html', 
                         tournaments_data=tournaments_data,
                         active_tournaments=active_tournaments)

@main_bp.route('/reset')
def reset_database():
    """Reset completo del database - SOLO in modalità debug"""
    if not Config.DEBUG_MODE:
        return "Reset non disponibile in produzione", 403
    
    return render_template('reset.html')

@main_bp.route('/reset/confirm', methods=['POST'])
def reset_database_confirm():
    """Conferma reset database"""
    if not Config.DEBUG_MODE:
        return "Reset non disponibile in produzione", 403
    
    password = request.form.get('password', '')
    if password != 'RESET_DB_CONFIRM':
        flash('Password di conferma errata!')
        return redirect(url_for('main.reset_database'))
    
    try:
        # LOGOUT dell'utente corrente prima del reset
        if current_user.is_authenticated:
            logout_user()
        
        # Elimina tutte le tabelle
        db.drop_all()
        
        # Ricrea tutte le tabelle
        db.create_all()
        
        # Crea utenti predefiniti
        create_default_users()
        
        # Crea torneo di esempio
        create_sample_tournament()
        
        flash('Database resettato con successo! Utenti creati: admin/admin123, mario/mario123, pino/pino123')
        flash('Sei stato disconnesso automaticamente. Rieffettua il login.', 'info')
        return redirect(url_for('main.index'))
        
    except Exception as e:
        flash(f'Errore durante il reset: {str(e)}')
        return redirect(url_for('main.reset_database'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Redirect al dashboard appropriato"""
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))
    else:
        return redirect(url_for('player.dashboard'))

@main_bp.route('/debug/login/<username>')
def quick_login(username):
    """Quick login per debug - SOLO in modalità debug"""
    from config import Config
    from flask_login import login_user
    
    if not Config.DEBUG_MODE:
        return "Quick login non disponibile in produzione", 403
    
    user = User.query.filter_by(username=username).first()
    if not user:
        flash(f'Utente {username} non trovato!')
        return redirect(url_for('main.index'))
    
    login_user(user)
    flash(f'Quick login effettuato come {username}!')
    
    # Redirect appropriato
    if user.is_admin:
        return redirect(url_for('admin.dashboard'))
    else:
        return redirect(url_for('player.dashboard'))