# routes/main.py - Route principali (home, reset, ecc.)
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required, logout_user
from datetime import date
from models import db, Tournament, Prova, Classification
from utils import create_default_users, create_sample_tournament
from config import Config

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Homepage con tornei attivi"""
    # Mostra tornei attivi invece di uno solo
    active_tournaments = Tournament.query.filter_by(is_active=True).order_by(Tournament.created_at.desc()).all()
    
    if not active_tournaments:
        return render_template('no_tournament.html')
    
    # Per ora prendi il primo torneo attivo per la homepage
    tournament = active_tournaments[0]
    
    # Prossime prove
    upcoming_provas = Prova.query.filter(
        Prova.tournament_id == tournament.id,
        Prova.date >= date.today()
    ).order_by(Prova.date).limit(3).all()
    
    # Classifica generale (top 10)
    top_classifications = Classification.query.filter(
        Classification.tournament_id == tournament.id
    ).order_by(Classification.position).limit(10).all()
    
    return render_template('index.html', 
                         tournament=tournament,
                         active_tournaments=active_tournaments,
                         upcoming_provas=upcoming_provas,
                         top_classifications=top_classifications)

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