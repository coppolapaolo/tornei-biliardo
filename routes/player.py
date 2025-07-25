# routes/player.py - Route per giocatori
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from models import db, Tournament, Prova, Inscription, Match, Rack

player_bp = Blueprint('player', __name__)

@player_bp.route('/')
@login_required
def dashboard():
    """Dashboard giocatore"""
    # Mostra tutti i tornei attivi
    active_tournaments = Tournament.query.filter_by(is_active=True).order_by(Tournament.created_at.desc()).all()
    
    if not active_tournaments:
        return render_template('player/dashboard.html', 
                             tournaments=[],
                             my_inscriptions=[],
                             available_provas=[],
                             current_matches=[])
    
    # Per ora usa il primo torneo attivo
    tournament = active_tournaments[0]
    
    # Iscrizioni del giocatore
    my_inscriptions = Inscription.query.join(Prova).filter(
        Inscription.user_id == current_user.id,
        Prova.tournament_id == tournament.id
    ).all()
    
    # Prove disponibili per iscrizione
    already_inscribed_ids = [insc.prova_id for insc in my_inscriptions]
    current_time_utc = datetime.utcnow()
    
    available_provas = Prova.query.filter(
        Prova.tournament_id == tournament.id,
        Prova.status == 'inscription',
        Prova.inscription_start <= current_time_utc,
        Prova.inscription_end >= current_time_utc,
        ~Prova.id.in_(already_inscribed_ids)
    ).all()
    
    # Partite in corso
    current_matches = Match.query.filter(
        db.or_(Match.player1_id == current_user.id, Match.player2_id == current_user.id),
        Match.status.in_(['pending', 'playing'])
    ).all()
    
    return render_template('player/dashboard.html', 
                         tournament=tournament,
                         tournaments=active_tournaments,
                         my_inscriptions=my_inscriptions,
                         available_provas=available_provas,
                         current_matches=current_matches)

@player_bp.route('/prova/<int:prova_id>/inscribe', methods=['POST'])
@login_required
def inscribe_to_prova(prova_id):
    """Iscriviti a una prova"""
    prova = Prova.query.get_or_404(prova_id)
    
    # Verifica che le iscrizioni siano aperte
    now = datetime.utcnow()
    if prova.status != 'inscription' or now < prova.inscription_start or now > prova.inscription_end:
        flash('Le iscrizioni non sono disponibili.')
        return redirect(url_for('main.index'))
    
    # Verifica che non sia già iscritto
    existing = Inscription.query.filter_by(user_id=current_user.id, prova_id=prova_id).first()
    if existing:
        flash('Sei già iscritto a questa prova.')
        return redirect(url_for('player.dashboard'))
    
    inscription = Inscription(user_id=current_user.id, prova_id=prova_id)
    db.session.add(inscription)
    db.session.commit()
    
    flash(f'Iscrizione alla Prova {prova.number} completata!')
    return redirect(url_for('player.dashboard'))

@player_bp.route('/match/<int:match_id>')
@login_required
def match_detail(match_id):
    """Dettaglio partita per giocatore"""
    match = Match.query.get_or_404(match_id)
    
    # Verifica che l'utente sia coinvolto nel match
    if current_user.id not in [match.player1_id, match.player2_id]:
        flash('Non hai accesso a questa partita.')
        return redirect(url_for('player.dashboard'))
    
    racks = Rack.query.filter_by(match_id=match_id).order_by(Rack.rack_number).all()
    
    return render_template('match_detail.html', match=match, racks=racks)

@player_bp.route('/match/<int:match_id>/add_rack', methods=['POST'])
@login_required
def add_rack_result(match_id):
    """Aggiungi risultato rack (giocatore)"""
    match = Match.query.get_or_404(match_id)
    winner_id = int(request.form['winner_id'])
    
    # Verifica autorizzazioni
    if current_user.id not in [match.player1_id, match.player2_id]:
        return jsonify({'error': 'Non autorizzato'}), 403
    
    # Trova il prossimo numero rack
    last_rack = Rack.query.filter_by(match_id=match_id).order_by(Rack.rack_number.desc()).first()
    next_rack_number = (last_rack.rack_number + 1) if last_rack else 1
    
    rack = Rack(
        match_id=match_id,
        rack_number=next_rack_number,
        winner_id=winner_id,
        reported_by_id=current_user.id
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