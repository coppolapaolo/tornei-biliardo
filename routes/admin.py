# routes/admin.py - STEP 1: Aggiornato per nuovi models
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from datetime import datetime, date
import random
from models import db, Tournament, Prova, Inscription, Match, Rack, MatchResult, User, Classification
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
    """Crea nuovo torneo - AGGIORNATO per nuovo model"""
    name = request.form['name']
    tournament_type = request.form.get('tournament_type', 'Amalfi')
    without_x = 'without_x' in request.form
    final_playoffs = 'final_playoffs' in request.form
    challenge_mode = 'challenge_mode' in request.form
    
    tournament = Tournament(
        name=name,
        tournament_type=tournament_type,
        without_x=without_x,
        final_playoffs=final_playoffs,
        challenge_mode=challenge_mode,
        is_active=True
    )
    db.session.add(tournament)
    db.session.commit()
    
    flash(f'Torneo "{name}" creato con successo!')
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
    """Modifica torneo - AGGIORNATO per nuovo model"""
    tournament = Tournament.query.get_or_404(tournament_id)
    
    if not tournament.can_be_modified():
        flash('Impossibile modificare il torneo: alcune prove hanno già delle iscrizioni!')
        return redirect(url_for('admin.tournament_detail', tournament_id=tournament_id))
    
    if request.method == 'POST':
        tournament.name = request.form['name']
        tournament.tournament_type = request.form.get('tournament_type', 'Amalfi')
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
    
    tournament_name = tournament.name
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
    flash(f'Torneo "{tournament.name}" {status}!')
    return redirect(url_for('admin.dashboard'))

# ============ PROVE ============

@admin_bp.route('/prova/create', methods=['POST'])
@admin_required
def create_prova():
    """Crea nuova prova - COMPLETAMENTE AGGIORNATO per nuovi campi"""
    tournament_id = int(request.form['tournament_id'])
    tournament = Tournament.query.get_or_404(tournament_id)
    
    number = int(request.form['number'])
    
    # Verifica che il numero prova non esista già
    existing = Prova.query.filter_by(tournament_id=tournament_id, number=number).first()
    if existing:
        flash(f'La prova {number} esiste già!')
        return redirect(url_for('admin.tournament_detail', tournament_id=tournament_id))
    
    # Campi base
    name = request.form.get('name', f'Prova {number}')
    date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    
    # Nuovi campi
    location = request.form.get('location', '')
    description = request.form.get('description', '')
    rounds_count = int(request.form.get('rounds_count', 3))
    min_participants = int(request.form.get('min_participants', 2))
    max_participants = request.form.get('max_participants')
    max_participants = int(max_participants) if max_participants else None
    entry_fee = float(request.form.get('entry_fee', 0.0))
    
    # Game settings
    discipline = request.form['discipline']
    distance = int(request.form['distance'])
    # CORREZIONE: exact_number è il contrario di best_of
    exact_number = 'exact_number' in request.form
    best_of = not exact_number  # Inverti la logica
    
    # Crea la prova
    prova = Prova(
        tournament_id=tournament_id,
        number=number,
        name=name,
        date=date,
        location=location,
        description=description,
        rounds_count=rounds_count,
        min_participants=min_participants,
        max_participants=max_participants,
        entry_fee=entry_fee,
        discipline=discipline,
        distance=distance,
        best_of=best_of
    )
    
    # Auto-popolamento da prova precedente (non serve più, è gestito lato client)
    # Il checkbox copy_from_previous è gestito dinamicamente dal JavaScript
    
    db.session.add(prova)
    db.session.commit()
    
    flash(f'Prova {number} creata con successo!')
    return redirect(url_for('admin.tournament_detail', tournament_id=tournament_id))

@admin_bp.route('/prova/<int:prova_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_prova(prova_id):
    """Modifica prova - AGGIORNATO per exact_number"""
    prova = Prova.query.get_or_404(prova_id)
    
    if not prova.can_be_modified():
        flash('Impossibile modificare la prova: ci sono già delle iscrizioni!')
        return redirect(url_for('admin.prova_detail', prova_id=prova_id))
    
    if request.method == 'POST':
        # Aggiorna tutti i campi
        prova.name = request.form.get('name', prova.name)
        prova.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        prova.location = request.form.get('location', '')
        prova.description = request.form.get('description', '')
        prova.rounds_count = int(request.form.get('rounds_count', 3))
        prova.min_participants = int(request.form.get('min_participants', 2))
        
        max_participants = request.form.get('max_participants')
        prova.max_participants = int(max_participants) if max_participants else None
        prova.entry_fee = float(request.form.get('entry_fee', 0.0))
        prova.discipline = request.form['discipline']
        prova.distance = int(request.form['distance'])
        
        # CORREZIONE: exact_number è il contrario di best_of
        exact_number = 'exact_number' in request.form
        prova.best_of = not exact_number  # Inverti la logica
        
        db.session.commit()
        flash('Prova aggiornata con successo!')
        return redirect(url_for('admin.prova_detail', prova_id=prova_id))
    
    return render_template('admin/prova_edit.html', prova=prova)

@admin_bp.route('/prova/<int:prova_id>/delete', methods=['POST'])
@admin_required
def delete_prova(prova_id):
    """Cancella prova - NUOVO"""
    prova = Prova.query.get_or_404(prova_id)
    tournament_id = prova.tournament_id
    
    if not prova.can_be_deleted():
        flash('Impossibile cancellare la prova: ci sono già delle iscrizioni!')
        return redirect(url_for('admin.prova_detail', prova_id=prova_id))
    
    prova_name = f"Prova {prova.number}"
    db.session.delete(prova)
    db.session.commit()
    
    flash(f'{prova_name} cancellata con successo!')
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

@admin_bp.route('/prova/<int:prova_id>/start_first_round', methods=['POST'])
@admin_required
def start_first_round(prova_id):
    """Avvia primo turno della prova - AGGIORNATO per min_participants"""
    prova = Prova.query.get_or_404(prova_id)
    
    if prova.current_round != 0:
        flash('La prova è già iniziata!')
        return redirect(url_for('admin.prova_detail', prova_id=prova_id))
    
    # Verifica numero minimo partecipanti
    inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()
    if len(inscriptions) < prova.min_participants:
        flash(f'Servono almeno {prova.min_participants} iscritti per avviare la prova!')
        return redirect(url_for('admin.prova_detail', prova_id=prova_id))
    
    # Genera il sorteggio iniziale
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

@admin_bp.route('/prova/<int:prova_id>/results_overview')
@admin_required
def prova_results_overview(prova_id):
    """Overview risultati prova per inserimento rapido (admin)"""
    prova = Prova.query.get_or_404(prova_id)
    
    # Organizza partite per turno
    matches_by_round = {}
    for round_num in range(1, prova.rounds_count + 1):
        matches_by_round[round_num] = Match.query.filter_by(
            prova_id=prova_id, 
            round_number=round_num
        ).order_by(Match.id).all()
    
    return render_template('admin/prova_results_overview.html', 
                         prova=prova, 
                         matches_by_round=matches_by_round)

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
    """Aggiungi risultato rack (admin) - AGGIORNATO per nuova logica"""
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

# ============ GESTIONE RISULTATI DIRETTI ADMIN ============

@admin_bp.route('/match/<int:match_id>/set_result', methods=['POST'])
@admin_required
def set_match_result_direct(match_id):
    """Imposta risultato completo di una partita (admin)"""
    match = Match.query.get_or_404(match_id)
    
    if match.is_bye:
        flash('Non puoi modificare una partita bye!')
        return redirect(url_for('admin.match_detail', match_id=match_id))
    
    try:
        player1_score = int(request.form['player1_score'])
        player2_score = int(request.form['player2_score'])
        
        # Validazione punteggi
        if player1_score < 0 or player2_score < 0:
            flash('I punteggi non possono essere negativi!')
            return redirect(url_for('admin.match_detail', match_id=match_id))
        
        # Verifica che il risultato sia valido secondo le regole della prova
        total_racks = player1_score + player2_score
        max_possible = match.prova.distance
        
        if match.prova.best_of:
            # Al meglio di: uno dei due deve aver raggiunto la soglia
            winning_score = match.prova.get_winning_score()
            if max(player1_score, player2_score) < winning_score:
                flash(f'Nel "al meglio di {match.prova.distance}", uno dei giocatori deve raggiungere {winning_score} punti!')
                return redirect(url_for('admin.match_detail', match_id=match_id))
        else:
            # Esatto numero: la somma deve essere esattamente la distanza
            if total_racks != match.prova.distance:
                flash(f'Nel "{match.prova.distance} rack esatti", la somma deve essere esattamente {match.prova.distance}!')
                return redirect(url_for('admin.match_detail', match_id=match_id))
        
        # Determina il vincitore
        if player1_score > player2_score:
            winner_id = match.player1_id
        elif player2_score > player1_score:
            winner_id = match.player2_id
        else:
            flash('Non può esserci un pareggio!')
            return redirect(url_for('admin.match_detail', match_id=match_id))
        
        # Elimina tutti i rack esistenti per questa partita
        existing_racks = Rack.query.filter_by(match_id=match_id).all()
        for rack in existing_racks:
            db.session.delete(rack)
        
        # Crea i nuovi rack basati sul risultato
        rack_number = 1
        
        # Crea rack per player1
        for i in range(player1_score):
            rack = Rack(
                match_id=match_id,
                rack_number=rack_number,
                winner_id=match.player1_id,
                reported_by_id=1,  # Admin user ID
                validated_by_admin=True
            )
            db.session.add(rack)
            rack_number += 1
        
        # Crea rack per player2
        for i in range(player2_score):
            rack = Rack(
                match_id=match_id,
                rack_number=rack_number,
                winner_id=match.player2_id,
                reported_by_id=1,  # Admin user ID
                validated_by_admin=True
            )
            db.session.add(rack)
            rack_number += 1
        
        # Aggiorna il match
        match.player1_score = player1_score
        match.player2_score = player2_score
        match.winner_id = winner_id
        match.status = 'completed'
        
        db.session.commit()
        
        flash('Risultato impostato con successo!')
        return redirect(url_for('admin.match_detail', match_id=match_id))
        
    except ValueError:
        flash('Errore: inserisci numeri validi per i punteggi!')
        return redirect(url_for('admin.match_detail', match_id=match_id))
    except Exception as e:
        flash(f'Errore durante l\'impostazione del risultato: {str(e)}')
        return redirect(url_for('admin.match_detail', match_id=match_id))

@admin_bp.route('/match/<int:match_id>/reset', methods=['POST'])
@admin_required
def reset_match(match_id):
    """Reset completo di una partita (admin)"""
    match = Match.query.get_or_404(match_id)
    
    if match.is_bye:
        flash('Non puoi resettare una partita bye!')
        return redirect(url_for('admin.match_detail', match_id=match_id))
    
    try:
        # Elimina tutti i rack
        existing_racks = Rack.query.filter_by(match_id=match_id).all()
        for rack in existing_racks:
            db.session.delete(rack)
        
        # Reset match
        match.player1_score = 0
        match.player2_score = 0
        match.winner_id = None
        match.status = 'pending'
        
        db.session.commit()
        
        flash('Partita resettata con successo!')
        return redirect(url_for('admin.match_detail', match_id=match_id))
        
    except Exception as e:
        flash(f'Errore durante il reset: {str(e)}')
        return redirect(url_for('admin.match_detail', match_id=match_id))
    
# ============ GESTIONE RACK ADMIN ============

@admin_bp.route('/rack/<int:rack_id>/remove', methods=['POST'])
@admin_required
def remove_rack_admin(rack_id):
    """Rimuovi un rack (admin)"""
    rack = Rack.query.get_or_404(rack_id)
    match = rack.match
    
    try:
        # Salva il vincitore per aggiornare il punteggio
        winner_id = rack.winner_id
        
        # Rimuovi il rack
        db.session.delete(rack)
        
        # Aggiorna il punteggio del match
        if winner_id == match.player1_id:
            match.player1_score = max(0, match.player1_score - 1)
        else:
            match.player2_score = max(0, match.player2_score - 1)
        
        # Se il match era completato e ora non ha più i punti per essere vinto, rimettilo in playing
        if match.status == 'completed':
            if match.prova.best_of:
                winning_score = match.prova.get_winning_score()
                if max(match.player1_score, match.player2_score) < winning_score:
                    match.status = 'playing'
                    match.winner_id = None
            else:  # esatto numero
                if (match.player1_score + match.player2_score) < match.prova.distance:
                    match.status = 'playing'
                    match.winner_id = None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Rack rimosso (Admin)',
            'player1_score': match.player1_score,
            'player2_score': match.player2_score,
            'status': match.status
        })
        
    except Exception as e:
        return jsonify({'error': f'Errore durante la rimozione: {str(e)}'}), 500

@admin_bp.route('/rack/<int:rack_id>/validate', methods=['POST'])
@admin_required
def validate_rack_admin(rack_id):
    """Valida un rack (admin)"""
    rack = Rack.query.get_or_404(rack_id)
    
    try:
        # Valida il rack
        rack.validated_by_admin = True
        rack.confirmed_by_player = True  # Automaticamente confermato se validato dall'admin
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Rack validato dall\'amministratore'
        })
        
    except Exception as e:
        return jsonify({'error': f'Errore durante la validazione: {str(e)}'}), 500

# ============ GESTIONE UTENTI (PUNTO 3) ============

@admin_bp.route('/users')
@admin_required
def users_list():
    """Lista di tutti gli utenti con statistiche - VERSIONE CORRETTA"""
    from sqlalchemy import func, desc, case
    
    # Query CORRETTA per ottenere utenti con statistiche
    users = db.session.query(
        User,
        func.count(Inscription.id).label('total_inscriptions'),
        func.count(Match.id).label('total_matches'),
        # FIX: Sintassi corretta per func.case()
        func.sum(
            case(
                (Match.winner_id == User.id, 1),
                else_=0
            )
        ).label('matches_won')
    ).outerjoin(Inscription, User.id == Inscription.user_id)\
     .outerjoin(Match, db.or_(Match.player1_id == User.id, Match.player2_id == User.id))\
     .group_by(User.id)\
     .order_by(desc('total_inscriptions'), User.username).all()
    
    return render_template('admin/users_list.html', users=users)

@admin_bp.route('/user/<int:user_id>')
@admin_required
def user_detail(user_id):
    """Scheda dettagliata utente"""
    user = User.query.get_or_404(user_id)
    
    # Iscrizioni dell'utente
    inscriptions = Inscription.query.filter_by(user_id=user_id)\
                                  .join(Prova)\
                                  .join(Tournament)\
                                  .order_by(Tournament.created_at.desc(), Prova.number.desc()).all()
    
    # Partite giocate
    matches = Match.query.filter(
        db.or_(Match.player1_id == user_id, Match.player2_id == user_id)
    ).join(Prova)\
     .join(Tournament)\
     .order_by(Tournament.created_at.desc(), Prova.number.desc(), Match.round_number.desc()).all()
    
    # Statistiche generali
    total_matches = len([m for m in matches if m.status == 'completed'])
    won_matches = len([m for m in matches if m.status == 'completed' and m.winner_id == user_id])
    win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0
    
    # Classifiche per torneo
    classifications = Classification.query.filter_by(user_id=user_id)\
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
    
    return render_template('admin/user_detail.html', 
                         user=user, 
                         inscriptions=inscriptions,
                         matches=recent_matches,
                         classifications=classifications,
                         stats=stats)