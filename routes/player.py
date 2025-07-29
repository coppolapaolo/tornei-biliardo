# routes/player.py - AGGIORNATO dashboard per multi-torneo
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime
from models import db, Tournament, Prova, Inscription, Match, Rack, Classification, MatchResult, DirectorRequest
from utils import player_only, UserPermissions 

player_bp = Blueprint('player', __name__)

@player_bp.route('/')
@login_required
def dashboard():
    """Dashboard giocatore - AGGIORNATO per multi-torneo con selezione"""
    # Ottieni il torneo selezionato o il primo attivo
    selected_tournament_id = request.args.get('tournament_id', type=int)
    
    # Mostra tutti i tornei attivi
    active_tournaments = Tournament.query.filter_by(is_active=True).order_by(Tournament.created_at.desc()).all()
    
    if not active_tournaments:
        return render_template('player/dashboard.html', 
                             tournaments=[],
                             selected_tournament=None,
                             my_inscriptions=[],
                             available_provas=[],
                             current_matches=[],
                             recent_matches=[],
                             user_stats={})
    
    # Determina il torneo selezionato
    if selected_tournament_id:
        selected_tournament = Tournament.query.filter_by(id=selected_tournament_id, is_active=True).first()
        if not selected_tournament:
            selected_tournament = active_tournaments[0]
    else:
        selected_tournament = active_tournaments[0]
    
    # Iscrizioni del giocatore per il torneo selezionato
    my_inscriptions = Inscription.query.join(Prova).filter(
        Inscription.user_id == current_user.id,
        Prova.tournament_id == selected_tournament.id
    ).all()
    
    # Prove disponibili per iscrizione nel torneo selezionato
    already_inscribed_ids = [insc.prova_id for insc in my_inscriptions]
    
    all_provas = Prova.query.filter(
        Prova.tournament_id == selected_tournament.id,
        ~Prova.id.in_(already_inscribed_ids) if already_inscribed_ids else True
    ).all()
    
    # Filtra usando il nuovo metodo can_inscribe()
    available_provas = [prova for prova in all_provas if prova.can_inscribe()]
    
    # Partite in corso per il torneo selezionato
    current_matches = Match.query.join(Prova).filter(
        db.or_(Match.player1_id == current_user.id, Match.player2_id == current_user.id),
        Match.status.in_(['pending', 'playing']),
        Prova.tournament_id == selected_tournament.id
    ).all()
    
    # ULTIME 2 partite giocate per il torneo selezionato
    recent_matches = Match.query.join(Prova).filter(
        db.or_(Match.player1_id == current_user.id, Match.player2_id == current_user.id),
        Match.status == 'completed',
        Prova.tournament_id == selected_tournament.id
    ).order_by(Prova.number.desc(), Match.round_number.desc())\
     .limit(2).all()
    
    # Statistiche utente per TUTTI i tornei (non solo quello selezionato)
    all_matches = Match.query.filter(
        db.or_(Match.player1_id == current_user.id, Match.player2_id == current_user.id),
        Match.status == 'completed'
    ).all()
    
    total_matches = len(all_matches)
    won_matches = len([m for m in all_matches if m.winner_id == current_user.id])
    win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0
    
    user_stats = {
        'total_matches': total_matches,
        'won_matches': won_matches,
        'lost_matches': total_matches - won_matches,
        'win_percentage': round(win_percentage, 1)
    }
    
    return render_template('player/dashboard.html', 
                         tournaments=active_tournaments,
                         selected_tournament=selected_tournament,
                         my_inscriptions=my_inscriptions,
                         available_provas=available_provas,
                         current_matches=current_matches,
                         recent_matches=recent_matches,
                         user_stats=user_stats)

# Il resto delle route rimane uguale...
@player_bp.route('/prova/<int:prova_id>/inscribe', methods=['POST'])
@login_required
@player_only
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
    # Redirect mantenendo il torneo selezionato
    return redirect(url_for('player.dashboard', tournament_id=prova.tournament_id))

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
    
    # Verifica se il match è finito usando la nuova logica
    if match.prova.is_match_finished(match.player1_score, match.player2_score):
        match.winner_id = match.player1_id if match.player1_score > match.player2_score else match.player2_id
        match.status = 'completed'
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'player1_score': match.player1_score,
        'player2_score': match.player2_score,
        'status': match.status
    })

# ============ PROFILO UTENTE E GESTIONE ACCOUNT ============

@player_bp.route('/profile')
@login_required
@player_only
def profile():
    """Profilo personale del giocatore"""
    
    from sqlalchemy import func
    
    # Iscrizioni dell'utente
    inscriptions = Inscription.query.filter_by(user_id=current_user.id)\
                                  .join(Prova)\
                                  .join(Tournament)\
                                  .order_by(Tournament.created_at.desc(), Prova.number.desc()).all()
    
    # Partite giocate
    matches = Match.query.filter(
        db.or_(Match.player1_id == current_user.id, Match.player2_id == current_user.id)
    ).join(Prova)\
     .join(Tournament)\
     .order_by(Tournament.created_at.desc(), Prova.number.desc(), Match.round_number.desc()).all()
    
    # Statistiche generali
    total_matches = len([m for m in matches if m.status == 'completed'])
    won_matches = len([m for m in matches if m.status == 'completed' and m.winner_id == current_user.id])
    win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0
    
    # Classifiche per torneo
    classifications = Classification.query.filter_by(user_id=current_user.id)\
                                        .join(Tournament)\
                                        .order_by(Tournament.created_at.desc()).all()
    
    # Partite recenti (ultime 10)
    recent_matches = [m for m in matches if m.status == 'completed'][:10]
    
    stats = {
        'total_inscriptions': len(inscriptions),
        'total_matches': total_matches,
        'won_matches': won_matches,
        'lost_matches': total_matches - won_matches,
        'win_percentage': round(win_percentage, 1),
        'tournaments_played': len(set([insc.prova.tournament_id for insc in inscriptions]))
    }
    
    return render_template('player/profile.html', 
                         user=current_user,
                         inscriptions=inscriptions,
                         matches=recent_matches,
                         classifications=classifications,
                         stats=stats)
    
@player_bp.route('/request_director', methods=['POST'])
@login_required
@player_only
def request_director():
    """Richiede la promozione a direttore di gara"""
    if current_user.role != 'player':
        flash('Solo i giocatori possono richiedere di diventare direttori.')
        return redirect(url_for('player.profile'))
    if current_user.director_request:
        flash('Hai già una richiesta in sospeso o è stata valutata.')
        return redirect(url_for('player.profile'))

    req = DirectorRequest(user_id=current_user.id, status='pending')
    db.session.add(req)
    db.session.commit()
    flash('Richiesta inviata. Sarai contattato dall’amministratore.')
    return redirect(url_for('player.profile'))

@player_bp.route('/delete_account', methods=['GET', 'POST'])
@login_required
@player_only
def delete_account():
    """Cancellazione account utente - PROTETTA PER AMMINISTRATORI"""
        
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirmation = request.form.get('confirmation', '')
        
        # Verifica password
        if not current_user.check_password(password):
            flash('Password errata!')
            return render_template('player/delete_account.html')
        
        # Verifica conferma
        if confirmation != 'ELIMINA IL MIO ACCOUNT':
            flash('Conferma non corretta!')
            return render_template('player/delete_account.html')
        
        # Procedi con cancellazione (SOLO per utenti non-admin)
        username = current_user.username
        
        # 1. Rimuovi da tutte le iscrizioni attive
        active_inscriptions = Inscription.query.filter_by(user_id=current_user.id)\
                                              .join(Prova)\
                                              .filter(Prova.status.in_(['setup', 'inscription'])).all()
        
        for inscription in active_inscriptions:
            db.session.delete(inscription)
        
        # 2. Rimuovi da partite non ancora giocate (pending)
        pending_matches = Match.query.filter(
            db.or_(Match.player1_id == current_user.id, Match.player2_id == current_user.id),
            Match.status == 'pending'
        ).all()
        
        for match in pending_matches:
            # Se la partita non è iniziata, rimuovila completamente
            db.session.delete(match)
        
        # 3. Per partite completate, manteniamo i dati storici ma anonimizziamo
        # (Le partite completate rimangono per integrità storica)
        
        # 4. Rimuovi classifiche
        classifications = Classification.query.filter_by(user_id=current_user.id).all()
        for classification in classifications:
            db.session.delete(classification)
        
        # 5. Rimuovi rack results
        rack_results = Rack.query.filter(
            db.or_(Rack.winner_id == current_user.id, Rack.reported_by_id == current_user.id)
        ).all()
        for rack in rack_results:
            db.session.delete(rack)
        
        # 6. Rimuovi match results
        match_results = MatchResult.query.filter_by(user_id=current_user.id).all()
        for result in match_results:
            db.session.delete(result)
        
        # 7. Rimuovi l'utente
        db.session.delete(current_user)
        
        # Logout prima del commit
        from flask_login import logout_user
        logout_user()
        
        # Commit delle modifiche
        db.session.commit()
        
        flash(f'Account "{username}" eliminato con successo!')
        return redirect(url_for('main.index'))
    
    return render_template('player/delete_account.html')

# ============ DISISCRIZIONE TORNEI ============

@player_bp.route('/prova/<int:prova_id>/unsubscribe', methods=['POST'])
@login_required
@player_only
def unsubscribe_from_prova(prova_id):
    """Disiscrizione da una prova"""
    prova = Prova.query.get_or_404(prova_id)
    
    # Verifica che l'utente sia iscritto
    inscription = Inscription.query.filter_by(user_id=current_user.id, prova_id=prova_id).first()
    if not inscription:
        flash('Non sei iscritto a questa prova.')
        return redirect(url_for('player.dashboard'))
    
    # Verifica che la prova non sia ancora iniziata
    if prova.status not in ['setup', 'inscription']:
        flash('Impossibile disiscreversi: la prova è già iniziata!')
        return redirect(url_for('player.dashboard'))
    
    # Verifica che non ci siano partite già create
    existing_matches = Match.query.filter(
        db.or_(Match.player1_id == current_user.id, Match.player2_id == current_user.id),
        Match.prova_id == prova_id
    ).first()
    
    if existing_matches:
        flash('Impossibile disiscreversi: ci sono già partite programmate!')
        return redirect(url_for('player.dashboard'))
    
    # Procedi con la disiscrizione
    db.session.delete(inscription)
    db.session.commit()
    
    flash(f'Disiscrizione dalla Prova {prova.number} completata!')
    # Redirect mantenendo il torneo selezionato
    return redirect(url_for('player.dashboard', tournament_id=prova.tournament_id))

# ============ SISTEMA CONFERMA/RIMOZIONE PUNTI ============

@player_bp.route('/rack/<int:rack_id>/remove', methods=['POST'])
@login_required
def remove_rack(rack_id):
    """Rimuovi un rack inserito per errore"""
    rack = Rack.query.get_or_404(rack_id)
    match = rack.match
    
    # Verifica autorizzazioni
    if current_user.id not in [match.player1_id, match.player2_id]:
        return jsonify({'error': 'Non autorizzato'}), 403
    
    # Verifica che possa essere rimosso
    if not rack.can_be_removed(current_user.id):
        return jsonify({'error': 'Impossibile rimuovere questo rack'}), 400
    
    # Salva il vincitore per aggiornare il punteggio
    winner_id = rack.winner_id
    
    # Rimuovi il rack
    db.session.delete(rack)
    
    # Aggiorna il punteggio del match
    if winner_id == match.player1_id:
        match.player1_score = max(0, match.player1_score - 1)
    else:
        match.player2_score = max(0, match.player2_score - 1)
    
    # Se il match era completato, rimettilo in playing
    if match.status == 'completed':
        match.status = 'playing'
        match.winner_id = None
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Rack rimosso',
        'player1_score': match.player1_score,
        'player2_score': match.player2_score,
        'status': match.status
    })

@player_bp.route('/rack/<int:rack_id>/confirm', methods=['POST'])
@login_required
def confirm_rack(rack_id):
    """Conferma un rack inserito dall'altro giocatore"""
    rack = Rack.query.get_or_404(rack_id)
    match = rack.match
    
    # Verifica autorizzazioni
    if current_user.id not in [match.player1_id, match.player2_id]:
        return jsonify({'error': 'Non autorizzato'}), 403
    
    # Verifica che possa essere confermato
    if not rack.can_be_confirmed(current_user.id):
        return jsonify({'error': 'Impossibile confermare questo rack'}), 400
    
    # Conferma il rack
    rack.confirmed_by_player = True
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Rack confermato'
    })

@player_bp.route('/rack/<int:rack_id>/unconfirm', methods=['POST'])
@login_required
def unconfirm_rack(rack_id):
    """Rimuovi conferma da un rack"""
    rack = Rack.query.get_or_404(rack_id)
    match = rack.match
    
    # Verifica autorizzazioni
    if current_user.id not in [match.player1_id, match.player2_id]:
        return jsonify({'error': 'Non autorizzato'}), 403
    
    # Verifica che possa rimuovere la conferma
    if not rack.can_remove_confirmation(current_user.id):
        return jsonify({'error': 'Impossibile rimuovere la conferma'}), 400
    
    # Rimuovi la conferma
    rack.confirmed_by_player = False
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Conferma rimossa'
    })