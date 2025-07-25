# routes/admin.py - Route amministrative
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from datetime import datetime, date
import random
from models import db, Tournament, Prova, Inscription, Match, Rack, MatchResult
from utils import admin_required, create_round_matches

admin_bp = Blueprint('admin', __name__)

# ============ DASHBOARD E TORNEI ============

@admin_bp.route('/')
@admin_required
def dashboard():
    """Dashboard amministratore con tutti i tornei"""
    tournaments = Tournament.query.order_by(Tournament.created_at.desc()).all()
    return render_template('admin/dashboard.html', tournaments=tournaments)

@admin_bp.route('/tournament/create', methods=['POST'])
@admin_required
def create_tournament():
    """Crea nuovo torneo"""
    name = request.form['name']
    year = int(request.form['year'])
    tournament_type = request.form.get('tournament_type', 'Amalfi')
    rounds_per_prova = int(request.form.get('rounds_per_prova', 3))
    without_x = 'without_x' in request.form
    final_playoffs = 'final_playoffs' in request.form
    challenge_mode = 'challenge_mode' in request.form
    
    tournament = Tournament(
        name=name, 
        year=year,
        tournament_type=tournament_type,
        rounds_per_prova=rounds_per_prova,
        without_x=without_x,
        final_playoffs=final_playoffs,
        challenge_mode=challenge_mode,
        is_active=True
    )
    db.session.add(tournament)
    db.session.commit()
    
    flash(f'Torneo "{name} {year}" creato con successo!')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/tournament/<int:tournament_id>')
@admin_required
def tournament_detail(tournament_id):
    """Dettaglio torneo con prove"""
    tournament = Tournament.query.get_or_404(tournament_id)
    provas = Prova.query.filter_by(tournament_id=tournament_id).order_by(Prova.number).all()
    
    return render_template('admin/tournament_detail.html', 
                         tournament=tournament, 
                         provas=provas)

@admin_bp.route('/tournament/<int:tournament_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_tournament(tournament_id):
    """Modifica torneo"""
    tournament = Tournament.query.get_or_404(tournament_id)
    
    if not tournament.can_be_modified():
        flash('Impossibile modificare il torneo: alcune prove hanno già delle iscrizioni!')
        return redirect(url_for('admin.tournament_detail', tournament_id=tournament_id))
    
    if request.method == 'POST':
        tournament.name = request.form['name']
        tournament.year = int(request.form['year'])
        tournament.tournament_type = request.form.get('tournament_type', 'Amalfi')
        tournament.rounds_per_prova = int(request.form.get('rounds_per_prova', 3))
        tournament.without_x = 'without_x' in request.form
        tournament.final_playoffs = 'final_playoffs' in request.form
        tournament.challenge_mode = 'challenge_mode' in request.form
        tournament.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash('Torneo aggiornato con successo!')
        return redirect(url_for('admin.tournament_detail', tournament_id=tournament_id))
    
    return render_template('admin/tournament_edit.html', tournament=tournament)

@admin_bp.route('/tournament/<int:tournament_id>/delete', methods=['POST'])
@admin_required
def delete_tournament(tournament_id):
    """Elimina torneo"""
    tournament = Tournament.query.get_or_404(tournament_id)
    
    if not tournament.can_be_deleted():
        flash('Impossibile cancellare il torneo: contiene prove con iscrizioni!')
        return redirect(url_for('admin.tournament_detail', tournament_id=tournament_id))
    
    tournament_name = f"{tournament.name} {tournament.year}"
    db.session.delete(tournament)
    db.session.commit()
    
    flash(f'Torneo "{tournament_name}" cancellato con successo!')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/tournament/<int:tournament_id>/toggle_active', methods=['POST'])
@admin_required
def toggle_tournament_active(tournament_id):
    """Attiva/disattiva torneo"""
    tournament = Tournament.query.get_or_404(tournament_id)
    tournament.is_active = not tournament.is_active
    tournament.updated_at = datetime.utcnow()
    db.session.commit()
    
    status = 'attivato' if tournament.is_active else 'disattivato'
    flash(f'Torneo "{tournament.name} {tournament.year}" {status}!')
    return redirect(url_for('admin.dashboard'))

# ============ PROVE ============

@admin_bp.route('/prova/create', methods=['POST'])
@admin_required
def create_prova():
    """Crea nuova prova"""
    tournament_id = int(request.form['tournament_id'])
    tournament = Tournament.query.get_or_404(tournament_id)
    
    number = int(request.form['number'])
    date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    discipline = request.form['discipline']
    distance = int(request.form['distance'])
    
    # Verifica che il numero prova non esista già
    existing = Prova.query.filter_by(tournament_id=tournament_id, number=number).first()
    if existing:
        flash(f'La prova {number} esiste già!')
        return redirect(url_for('admin.tournament_detail', tournament_id=tournament_id))
    
    prova = Prova(
        tournament_id=tournament_id,
        number=number,
        date=date,
        discipline=discipline,
        distance=distance
    )
    db.session.add(prova)
    db.session.commit()
    
    flash(f'Prova {number} creata con successo!')
    return redirect(url_for('admin.tournament_detail', tournament_id=tournament_id))

@admin_bp.route('/prova/<int:prova_id>')
@admin_required
def prova_detail(prova_id):
    """Dettaglio prova con iscrizioni e partite"""
    prova = Prova.query.get_or_404(prova_id)
    inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()
    matches = Match.query.filter_by(prova_id=prova_id).order_by(Match.round_number, Match.id).all()
    
    return render_template('admin/prova_detail.html', 
                         prova=prova, 
                         inscriptions=inscriptions,
                         matches=matches)

@admin_bp.route('/prova/<int:prova_id>/open_inscriptions', methods=['POST'])
@admin_required
def open_inscriptions(prova_id):
    """Apri iscrizioni per una prova"""
    prova = Prova.query.get_or_404(prova_id)
    
    # Ottieni le date UTC dal JavaScript
    inscription_start = datetime.strptime(request.form['inscription_start_utc'], '%Y-%m-%dT%H:%M:%S')
    inscription_end = datetime.strptime(request.form['inscription_end_utc'], '%Y-%m-%dT%H:%M:%S')
    
    # Validazioni
    if inscription_start > inscription_end:
        flash('Errore: La data di inizio deve essere precedente alla data di fine!')
        return redirect(url_for('admin.prova_detail', prova_id=prova_id))
    
    prova.inscription_start = inscription_start
    prova.inscription_end = inscription_end
    prova.status = 'inscription'
    
    db.session.commit()
    flash('Iscrizioni aperte! Gli orari sono gestiti automaticamente nel tuo timezone locale.')
    return redirect(url_for('admin.prova_detail', prova_id=prova_id))

@admin_bp.route('/prova/<int:prova_id>/start_first_round', methods=['POST'])
@admin_required
def start_first_round(prova_id):
    """Avvia primo turno della prova"""
    prova = Prova.query.get_or_404(prova_id)
    
    if prova.current_round != 0:
        flash('La prova è già iniziata!')
        return redirect(url_for('admin.prova_detail', prova_id=prova_id))
    
    # Genera il sorteggio iniziale
    inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()
    random.shuffle(inscriptions)
    
    # Assegna ordine sorteggio
    for i, inscription in enumerate(inscriptions, 1):
        inscription.initial_order = i
    
    # Crea abbinamenti primo turno
    create_round_matches(prova, inscriptions, 1)
    
    prova.current_round = 1
    prova.status = 'playing'
    db.session.commit()
    
    flash('Primo turno avviato!')
    return redirect(url_for('admin.prova_detail', prova_id=prova_id))

# Aggiungere questa route al file routes/admin.py

@admin_bp.route('/prova/<int:prova_id>/modify_inscription_dates', methods=['POST'])
@admin_required
def modify_inscription_dates(prova_id):
    """Modifica date di iscrizione per una prova"""
    prova = Prova.query.get_or_404(prova_id)
    
    # Verifica che sia possibile modificare
    if not prova.can_modify_inscription_dates():
        flash('Impossibile modificare le date: il primo turno è già stato avviato!')
        return redirect(url_for('admin.prova_detail', prova_id=prova_id))
    
    # Ottieni le date UTC dal JavaScript
    inscription_start = datetime.strptime(request.form['inscription_start_utc'], '%Y-%m-%dT%H:%M:%S')
    inscription_end = datetime.strptime(request.form['inscription_end_utc'], '%Y-%m-%dT%H:%M:%S')
    
    # Validazioni
    if inscription_start > inscription_end:
        flash('Errore: La data di inizio deve essere precedente alla data di fine!')
        return redirect(url_for('admin.prova_detail', prova_id=prova_id))
    
    # Aggiorna le date
    prova.inscription_start = inscription_start
    prova.inscription_end = inscription_end
    
    # Se le iscrizioni ora sono nel futuro, torna a setup
    now = datetime.utcnow()
    if inscription_start > now:
        prova.status = 'setup'
    elif inscription_start <= now <= inscription_end:
        prova.status = 'inscription'
    # Se sono passate, lascia lo status attuale (verrà gestito dai template)
    
    db.session.commit()
    flash('Date di iscrizione aggiornate con successo!')
    return redirect(url_for('admin.prova_detail', prova_id=prova_id))

# ============ GESTIONE PARTITE ============

@admin_bp.route('/match/<int:match_id>')
@admin_required  
def match_detail(match_id):
    """Dettaglio partita per admin"""
    match = Match.query.get_or_404(match_id)
    racks = Rack.query.filter_by(match_id=match_id).order_by(Rack.rack_number).all()
    
    return render_template('match_detail.html', match=match, racks=racks)

@admin_bp.route('/match/<int:match_id>/add_rack', methods=['POST'])
@admin_required
def add_rack_result(match_id):
    """Aggiungi risultato rack (admin)"""
    match = Match.query.get_or_404(match_id)
    winner_id = int(request.form['winner_id'])
    
    # Trova il prossimo numero rack
    last_rack = Rack.query.filter_by(match_id=match_id).order_by(Rack.rack_number.desc()).first()
    next_rack_number = (last_rack.rack_number + 1) if last_rack else 1
    
    rack = Rack(
        match_id=match_id,
        rack_number=next_rack_number,
        winner_id=winner_id,
        reported_by_id=1,  # Admin user ID
        validated_by_admin=True  # Admin validation immediate
    )
    db.session.add(rack)
    
    # Aggiorna punteggio match
    if winner_id == match.player1_id:
        match.player1_score += 1
    else:
        match.player2_score += 1
    
    # Verifica se il match è finito
    if match.player1_score >= match.prova.distance or match.player2_score >= match.prova.distance:
        match.winner_id = match.player1_id if match.player1_score > match.player2_score else match.player2_id
        match.status = 'completed'
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'player1_score': match.player1_score,
        'player2_score': match.player2_score,
        'status': match.status
    })