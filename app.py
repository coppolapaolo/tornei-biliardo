# app.py - Webapp Completa Torneo Biliardo con Debug e Reset
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import random
import os
from functools import wraps

app = Flask(__name__)

# ============ CONFIGURAZIONE ============
DEBUG_MODE = True  # ⭐ CAMBIA QUI PER ATTIVARE/DISATTIVARE DEBUG

app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///billiard_tournament.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['DEBUG'] = DEBUG_MODE

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ============ MODELS ============

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relazioni
    inscriptions = db.relationship('Inscription', backref='user', lazy=True)
    match_results = db.relationship('MatchResult', foreign_keys='MatchResult.user_id', lazy=True)
    classifications = db.relationship('Classification', backref='user', lazy=True)
    playoff_participations = db.relationship('Playoff', backref='user', lazy=True)

class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    
    # Nuovi campi
    tournament_type = db.Column(db.String(50), nullable=False, default='Amalfi')
    rounds_per_prova = db.Column(db.Integer, nullable=False, default=3)
    without_x = db.Column(db.Boolean, default=False)  # Opzione "senza X"
    final_playoffs = db.Column(db.Boolean, default=True)  # Play off finali
    challenge_mode = db.Column(db.Boolean, default=False)  # Challenge
    
    # Status e date
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relazioni
    provas = db.relationship('Prova', backref='tournament', lazy=True, cascade='all, delete-orphan')
    
    def can_be_modified(self):
        """Verifica se il torneo può essere modificato"""
        # Controlla se esiste almeno una prova con iscrizioni aperte
        for prova in self.provas:
            if prova.status in ['inscription', 'playing', 'completed']:
                return False
        return True
    
    def can_be_deleted(self):
        """Verifica se il torneo può essere cancellato"""
        # Un torneo può essere cancellato solo se non ha prove con iscrizioni
        for prova in self.provas:
            if prova.inscriptions:  # Se ha iscrizioni
                return False
        return True
    
    def get_status(self):
        """Restituisce lo status del torneo"""
        if not self.provas:
            return 'setup'
        
        # Controlla lo stato delle prove
        has_playing = any(p.status == 'playing' for p in self.provas)
        has_completed = any(p.status == 'completed' for p in self.provas)
        has_inscription = any(p.status == 'inscription' for p in self.provas)
        
        if has_playing:
            return 'in_progress'
        elif has_completed and not has_playing and not has_inscription:
            return 'completed'
        elif has_inscription:
            return 'registration_open'
        else:
            return 'setup'
    
    def get_status_badge_class(self):
        """Restituisce la classe CSS per il badge status"""
        status = self.get_status()
        return {
            'setup': 'bg-warning',
            'registration_open': 'bg-info', 
            'in_progress': 'bg-primary',
            'completed': 'bg-success'
        }.get(status, 'bg-secondary')
    
    def get_status_text(self):
        """Restituisce il testo dello status"""
        status = self.get_status()
        return {
            'setup': 'Setup',
            'registration_open': 'Iscrizioni Aperte',
            'in_progress': 'In Corso',
            'completed': 'Completato'
        }.get(status, 'Sconosciuto')

class Prova(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    number = db.Column(db.Integer, nullable=False)  # 1-10
    name = db.Column(db.String(100))
    date = db.Column(db.Date, nullable=False)
    discipline = db.Column(db.String(50), nullable=False)  # palla 8, 9, 10
    distance = db.Column(db.Integer, nullable=False)  # numero rack da giocare

    # Date iscrizioni
    inscription_start = db.Column(db.DateTime)
    inscription_end = db.Column(db.DateTime)

    # Stato della prova
    status = db.Column(db.String(20), default='setup')  # setup, inscription, playing, completed
    current_round = db.Column(db.Integer, default=0)  # 0=non iniziata, 1,2,3=turni

    # Relazioni
    inscriptions = db.relationship('Inscription', backref='prova', lazy=True)
    matches = db.relationship('Match', backref='prova', lazy=True)

class Inscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    prova_id = db.Column(db.Integer, db.ForeignKey('prova.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    initial_order = db.Column(db.Integer)  # ordine sorteggio iniziale

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prova_id = db.Column(db.Integer, db.ForeignKey('prova.id'), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)  # 1, 2, 3

    player1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    player2_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_bye = db.Column(db.Boolean, default=False)  # partita contro X

    # Risultati
    player1_score = db.Column(db.Integer, default=0)
    player2_score = db.Column(db.Integer, default=0)
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    # Stato
    status = db.Column(db.String(20), default='pending')  # pending, playing, completed, validated
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relazioni
    player1 = db.relationship('User', foreign_keys=[player1_id])
    player2 = db.relationship('User', foreign_keys=[player2_id])
    winner = db.relationship('User', foreign_keys=[winner_id])
    racks = db.relationship('Rack', backref='match', lazy=True)

class Rack(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False)
    rack_number = db.Column(db.Integer, nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    # Validazioni
    reported_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # chi ha segnato
    confirmed_by_player = db.Column(db.Boolean, default=False)  # confermato dall'altro giocatore
    validated_by_admin = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relazioni
    winner = db.relationship('User', foreign_keys=[winner_id])
    reported_by = db.relationship('User', foreign_keys=[reported_by_id])

class MatchResult(db.Model):
    """Tabella per tracking risultati inviati dai giocatori"""
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    player1_score = db.Column(db.Integer)
    player2_score = db.Column(db.Integer)
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relazioni
    reporter = db.relationship('User', foreign_keys=[user_id], overlaps="match_results")
    winner = db.relationship('User', foreign_keys=[winner_id])

class Classification(db.Model):
    """Classifica generale del torneo"""
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    position = db.Column(db.Integer)
    total_matches_won = db.Column(db.Integer, default=0)
    total_point_difference = db.Column(db.Integer, default=0)
    provas_played = db.Column(db.Integer, default=0)

class Playoff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    category = db.Column(db.String(20), nullable=False)  # elite, academy
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    qualified_position = db.Column(db.Integer)  # posizione che dava diritto
    confirmation_status = db.Column(db.String(20), default='pending')  # pending, confirmed, declined
    confirmed_at = db.Column(db.DateTime)

# ============ LOGIN MANAGER ============

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ============ CONTEXT PROCESSOR (per debug info) ============

@app.context_processor
def inject_debug():
    """Inietta variabili debug in tutti i template"""
    debug_info = {}
    if DEBUG_MODE:
        debug_info = {
            'debug_mode': True,
            'current_user_info': {
                'id': current_user.id if current_user.is_authenticated else None,
                'username': current_user.username if current_user.is_authenticated else 'Anonymous',
                'is_admin': current_user.is_admin if current_user.is_authenticated else False,
            },
            'request_endpoint': request.endpoint,
            'request_method': request.method,
            'database_stats': get_database_stats() if current_user.is_authenticated else {}
        }
    return {'debug_info': debug_info}

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

# ============ DECORATORS ============

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Accesso riservato agli amministratori.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============ RESET ROUTE (solo in debug) ============

@app.route('/reset')
def reset_database():
    """Reset completo del database - SOLO in modalità debug"""
    if not DEBUG_MODE:
        return "Reset non disponibile in produzione", 403

    return render_template('reset.html')

@app.route('/reset/confirm', methods=['POST'])
def reset_database_confirm():
    """Conferma reset database"""
    if not DEBUG_MODE:
        return "Reset non disponibile in produzione", 403

    password = request.form.get('password', '')
    if password != 'RESET_DB_CONFIRM':
        flash('Password di conferma errata!')
        return redirect(url_for('reset_database'))

    try:
        # Elimina tutte le tabelle
        db.drop_all()

        # Ricrea tutte le tabelle
        db.create_all()

        # Crea utenti predefiniti
        create_default_users()

        # Crea torneo di esempio
        create_sample_tournament()

        flash('Database resettato con successo! Utenti creati: admin/admin123, mario/mario123')
        return redirect(url_for('index'))

    except Exception as e:
        flash(f'Errore durante il reset: {str(e)}')
        return redirect(url_for('reset_database'))

def create_default_users():
    """Crea utenti predefiniti"""
    # Admin
    admin = User(
        username='admin',
        email='admin@tournament.com',
        password_hash=generate_password_hash('admin123'),
        is_admin=True
    )

    # Mario
    mario = User(
        username='mario',
        email='mario@test.com',
        password_hash=generate_password_hash('mario123'),
        is_admin=False
    )

    db.session.add(admin)
    db.session.add(mario)
    db.session.commit()

def create_sample_tournament():
    """Crea un torneo di esempio"""
    tournament = Tournament(
        name='Torneo Test',
        year=2025,
        tournament_type='Amalfi',
        rounds_per_prova=3,
        without_x=False,
        final_playoffs=True,
        challenge_mode=False,
        is_active=True
    )
    db.session.add(tournament)
    db.session.commit()
    
    # Prova di esempio
    prova = Prova(
        tournament_id=tournament.id,
        number=1,
        date=date(2025, 8, 1),
        discipline='palla 9',
        distance=7,
        status='setup'
    )
    db.session.add(prova)
    db.session.commit()
    
# ============ MAIN ROUTES ============

@app.route('/')
def index():
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Username o password errati.')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        phone = request.form.get('phone', '')

        if User.query.filter_by(username=username).first():
            flash('Username già esistente.')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('Email già registrata.')
            return render_template('register.html')

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            phone=phone
        )
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash('Registrazione completata!')
        return redirect(url_for('dashboard'))

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('player_dashboard'))

# ============ ADMIN ROUTES - TOURNAMENTS ============

@app.route('/admin')
@admin_required
def admin_dashboard():
    # Mostra TUTTI i tornei, non solo quello attivo
    tournaments = Tournament.query.order_by(Tournament.created_at.desc()).all()
    return render_template('admin/dashboard.html', tournaments=tournaments)

@app.route('/admin/tournament/create', methods=['POST'])
@admin_required
def create_tournament():
    name = request.form['name']
    year = int(request.form['year'])
    tournament_type = request.form.get('tournament_type', 'Amalfi')
    rounds_per_prova = int(request.form.get('rounds_per_prova', 3))
    without_x = 'without_x' in request.form
    final_playoffs = 'final_playoffs' in request.form
    challenge_mode = 'challenge_mode' in request.form
    
    # NON disattivare più i tornei precedenti
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
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/tournament/<int:tournament_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    
    if not tournament.can_be_modified():
        flash('Impossibile modificare il torneo: alcune prove hanno già delle iscrizioni!')
        return redirect(url_for('admin_tournament_detail', tournament_id=tournament_id))
    
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
        return redirect(url_for('admin_tournament_detail', tournament_id=tournament_id))
    
    return render_template('admin/tournament_edit.html', tournament=tournament)

@app.route('/admin/tournament/<int:tournament_id>/delete', methods=['POST'])
@admin_required
def delete_tournament(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    
    if not tournament.can_be_deleted():
        flash('Impossibile cancellare il torneo: contiene prove con iscrizioni!')
        return redirect(url_for('admin_tournament_detail', tournament_id=tournament_id))
    
    tournament_name = f"{tournament.name} {tournament.year}"
    db.session.delete(tournament)
    db.session.commit()
    
    flash(f'Torneo "{tournament_name}" cancellato con successo!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/tournament/<int:tournament_id>')
@admin_required
def admin_tournament_detail(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    provas = Prova.query.filter_by(tournament_id=tournament_id).order_by(Prova.number).all()
    
    return render_template('admin/tournament_detail.html', 
                         tournament=tournament, 
                         provas=provas)

@app.route('/admin/tournament/<int:tournament_id>/toggle_active', methods=['POST'])
@admin_required
def toggle_tournament_active(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    tournament.is_active = not tournament.is_active
    tournament.updated_at = datetime.utcnow()
    db.session.commit()
    
    status = 'attivato' if tournament.is_active else 'disattivato'
    flash(f'Torneo "{tournament.name} {tournament.year}" {status}!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/prova/create', methods=['POST'])
@admin_required
def create_prova():
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
        return redirect(url_for('admin_tournament_detail', tournament_id=tournament_id))
    
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
    return redirect(url_for('admin_tournament_detail', tournament_id=tournament_id))

@app.route('/admin/prova/<int:prova_id>')
@admin_required
def admin_prova_detail(prova_id):
    prova = Prova.query.get_or_404(prova_id)
    inscriptions = Inscription.query.filter_by(prova_id=prova_id).all()
    matches = Match.query.filter_by(prova_id=prova_id).order_by(Match.round_number, Match.id).all()

    return render_template('admin/prova_detail.html',
                         prova=prova,
                         inscriptions=inscriptions,
                         matches=matches)

@app.route('/admin/prova/<int:prova_id>/open_inscriptions', methods=['POST'])
@admin_required
def open_inscriptions(prova_id):
    prova = Prova.query.get_or_404(prova_id)
    
    # Ottieni le date UTC dal JavaScript
    inscription_start = datetime.strptime(request.form['inscription_start_utc'], '%Y-%m-%dT%H:%M:%S')
    inscription_end = datetime.strptime(request.form['inscription_end_utc'], '%Y-%m-%dT%H:%M:%S')
    
    # Validazioni
    if inscription_start > inscription_end:
        flash('Errore: La data di inizio deve essere precedente alla data di fine!')
        return redirect(url_for('admin_prova_detail', prova_id=prova_id))
    
    prova.inscription_start = inscription_start
    prova.inscription_end = inscription_end
    prova.status = 'inscription'
    
    db.session.commit()
    flash('Iscrizioni aperte! Gli orari sono in UTC nel database ma vengono mostrati nel tuo timezone locale.')
    return redirect(url_for('admin_prova_detail', prova_id=prova_id))

@app.route('/admin/prova/<int:prova_id>/start_first_round', methods=['POST'])
@admin_required
def start_first_round(prova_id):
    prova = Prova.query.get_or_404(prova_id)

    if prova.current_round != 0:
        flash('La prova è già iniziata!')
        return redirect(url_for('admin_prova_detail', prova_id=prova_id))

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
    return redirect(url_for('admin_prova_detail', prova_id=prova_id))

# ============ PLAYER ROUTES ============

@app.route('/player')
@login_required 
def player_dashboard():
    # Mostra tutti i tornei attivi
    active_tournaments = Tournament.query.filter_by(is_active=True).order_by(Tournament.created_at.desc()).all()
    
    if not active_tournaments:
        return render_template('player/dashboard.html', 
                             tournaments=[],
                             my_inscriptions=[],
                             available_provas=[],
                             current_matches=[])
    
    # Per ora usa il primo torneo attivo (TODO: permettere selezione)
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
    
@app.route('/prova/<int:prova_id>/inscribe', methods=['POST'])
@login_required
def inscribe_to_prova(prova_id):
    prova = Prova.query.get_or_404(prova_id)

    # Verifica che le iscrizioni siano aperte
    now = datetime.utcnow()
    if prova.status != 'inscription' or now < prova.inscription_start or now > prova.inscription_end:
        flash('Le iscrizioni non sono disponibili.')
        return redirect(url_for('index'))

    # Verifica che non sia già iscritto
    existing = Inscription.query.filter_by(user_id=current_user.id, prova_id=prova_id).first()
    if existing:
        flash('Sei già iscritto a questa prova.')
        return redirect(url_for('player_dashboard'))

    inscription = Inscription(user_id=current_user.id, prova_id=prova_id)
    db.session.add(inscription)
    db.session.commit()

    flash(f'Iscrizione alla Prova {prova.number} completata!')
    return redirect(url_for('player_dashboard'))

@app.route('/match/<int:match_id>')
@login_required
def match_detail(match_id):
    match = Match.query.get_or_404(match_id)

    # Verifica che l'utente sia coinvolto nel match
    if current_user.id not in [match.player1_id, match.player2_id] and not current_user.is_admin:
        flash('Non hai accesso a questa partita.')
        return redirect(url_for('player_dashboard'))

    racks = Rack.query.filter_by(match_id=match_id).order_by(Rack.rack_number).all()

    return render_template('match_detail.html', match=match, racks=racks)

@app.route('/match/<int:match_id>/add_rack', methods=['POST'])
@login_required
def add_rack_result(match_id):
    match = Match.query.get_or_404(match_id)
    winner_id = int(request.form['winner_id'])

    # Verifica autorizzazioni
    if current_user.id not in [match.player1_id, match.player2_id] and not current_user.is_admin:
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

# ============ HELPER FUNCTIONS ============

def create_round_matches(prova, players_or_inscriptions, round_number):
    """Crea gli abbinamenti per un turno"""
    if isinstance(players_or_inscriptions[0], Inscription):
        players = [insc.user for insc in players_or_inscriptions]
    else:
        players = players_or_inscriptions

    matches = []

    if len(players) % 2 == 1:
        # Numero dispari: ultimo giocatore ha un bye
        bye_player = players[-1]
        match = Match(
            prova_id=prova.id,
            round_number=round_number,
            player1_id=bye_player.id,
            is_bye=True,
            player1_score=prova.distance,
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

# ============ INIZIALIZZAZIONE ============

def create_admin():
    """Crea l'utente admin se non esiste"""
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@tournament.com',
            password_hash=generate_password_hash('admin123'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin user created: admin/admin123")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_admin()
    app.run(debug=DEBUG_MODE)