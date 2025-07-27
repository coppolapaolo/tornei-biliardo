# models.py - STEP 1: Models aggiornati
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

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
    
    def set_password(self, password):
        """Imposta la password hashata"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verifica la password"""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def get_statistics(self):
        """Restituisce statistiche complete dell'utente"""
        # Tutte le iscrizioni
        total_inscriptions = Inscription.query.filter_by(user_id=self.id).count()
        
        # Tutte le partite giocate
        all_matches = Match.query.filter(
            db.or_(Match.player1_id == self.id, Match.player2_id == self.id),
            Match.status == 'completed'
        ).all()
        
        total_matches = len(all_matches)
        won_matches = len([m for m in all_matches if m.winner_id == self.id])
        lost_matches = total_matches - won_matches
        win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0
        
        # Tornei giocati
        tournaments_played = len(set([
            insc.prova.tournament_id 
            for insc in Inscription.query.filter_by(user_id=self.id).join(Prova).all()
        ]))
        
        return {
            'total_inscriptions': total_inscriptions,
            'total_matches': total_matches,
            'won_matches': won_matches,
            'lost_matches': lost_matches,
            'win_percentage': round(win_percentage, 1),
            'tournaments_played': tournaments_played
        }

class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # RIMOSSO: year, rounds_per_prova
    
    # Campi configurazione
    tournament_type = db.Column(db.String(50), nullable=False, default='Amalfi')
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
        for prova in self.provas:
            if prova.status in ['inscription', 'playing', 'completed']:
                return False
        return True
    
    def can_be_deleted(self):
        """Verifica se il torneo può essere cancellato"""
        for prova in self.provas:
            if prova.inscriptions:  # Se ha iscrizioni
                return False
        return True
    
    def get_status(self):
        """Restituisce lo status del torneo"""
        if not self.provas:
            return 'setup'
        
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
    
    def __repr__(self):
        return f'<Tournament {self.name}>'

class Prova(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    number = db.Column(db.Integer, nullable=False)  # 1-10
    name = db.Column(db.String(100))
    date = db.Column(db.Date, nullable=False)
    
    # NUOVI CAMPI
    location = db.Column(db.String(200))  # Luogo della prova
    description = db.Column(db.Text)  # Descrizione opzionale
    rounds_count = db.Column(db.Integer, nullable=False, default=3)  # Numero di turni per questa prova
    min_participants = db.Column(db.Integer, default=2)  # Minimo iscritti
    max_participants = db.Column(db.Integer)  # Massimo iscritti (opzionale)
    entry_fee = db.Column(db.Float, default=0.0)  # Quota di partecipazione
    
    # Game settings
    discipline = db.Column(db.String(50), nullable=False)  # palla 8, 9, 10
    distance = db.Column(db.Integer, nullable=False)  # numero rack da giocare
    best_of = db.Column(db.Boolean, default=False)  # Se True: "al meglio di", se False: "esatto numero"
    
    # Date iscrizioni
    inscription_start = db.Column(db.DateTime)
    inscription_end = db.Column(db.DateTime)
    
    # Stato della prova
    status = db.Column(db.String(20), default='setup')  # setup, inscription, playing, completed
    current_round = db.Column(db.Integer, default=0)  # 0=non iniziata, 1,2,3=turni
    
    # Relazioni
    inscriptions = db.relationship('Inscription', backref='prova', lazy=True)
    matches = db.relationship('Match', backref='prova', lazy=True)
    
    def get_real_status(self):
        """Restituisce lo status reale considerando le date"""
        from datetime import datetime
        
        if self.status == 'setup':
            return 'setup'
        elif self.status == 'inscription':
            now = datetime.utcnow()
            
            # Verifica se le iscrizioni sono davvero aperte
            if self.inscription_start and self.inscription_end:
                if now < self.inscription_start:
                    return 'inscription_not_started'  # Iscrizioni future
                elif now > self.inscription_end:
                    return 'inscription_closed'  # Iscrizioni scadute
                else:
                    return 'inscription'  # Iscrizioni aperte
            else:
                return 'setup'  # Date non impostate
        elif self.status == 'playing':
            return 'playing'
        elif self.status == 'completed':
            return 'completed'
        else:
            return self.status

    def get_status_badge_info(self):
        """Restituisce classe CSS e testo per il badge status"""
        real_status = self.get_real_status()
        
        status_map = {
            'setup': {'class': 'bg-warning', 'text': 'Setup'},
            'inscription_not_started': {'class': 'bg-info', 'text': 'Iscrizioni Future'},
            'inscription': {'class': 'bg-success', 'text': 'Iscrizioni Aperte'},
            'inscription_closed': {'class': 'bg-danger', 'text': 'Iscrizioni Chiuse'},
            'playing': {'class': 'bg-primary', 'text': 'In Corso'},
            'completed': {'class': 'bg-secondary', 'text': 'Completata'}
        }
        
        return status_map.get(real_status, {'class': 'bg-secondary', 'text': 'Sconosciuto'})

    def can_inscribe(self):
        """Verifica se è possibile iscriversi ora"""
        real_status = self.get_real_status()
        inscriptions_count = len(self.inscriptions)
        
        # Deve essere in periodo iscrizioni E non aver raggiunto il massimo
        if real_status != 'inscription':
            return False
            
        if self.max_participants and inscriptions_count >= self.max_participants:
            return False
            
        return True

    def can_modify_inscription_dates(self):
        """Verifica se è possibile modificare le date di iscrizione"""
        # Può modificare solo se non è ancora stato avviato il primo turno
        return self.current_round == 0
    
    def can_be_modified(self):
        """Verifica se la prova può essere modificata"""
        # Può essere modificata se non ci sono iscrizioni
        return len(self.inscriptions) == 0
    
    def can_be_deleted(self):
        """Verifica se la prova può essere cancellata"""
        # Può essere cancellata se non ci sono iscrizioni
        return len(self.inscriptions) == 0
    
    def get_winning_score(self):
        """Restituisce il punteggio necessario per vincere"""
        if self.best_of:
            # Al meglio di: vince chi arriva a (distance/2)+1
            return (self.distance // 2) + 1
        else:
            # Esatto numero: vince chi ha più punti alla fine
            return self.distance
    
    def is_match_finished(self, score1, score2):
        """Verifica se una partita è finita dati i punteggi"""
        if self.best_of:
            # Al meglio di: qualcuno ha raggiunto la soglia
            winning_score = self.get_winning_score()
            return score1 >= winning_score or score2 >= winning_score
        else:
            # Esatto numero: somma dei punti raggiunge la distanza
            return (score1 + score2) >= self.distance
    
    def copy_settings_from(self, source_prova):
        """Copia le impostazioni da un'altra prova (per auto-popolamento)"""
        self.location = source_prova.location
        self.rounds_count = source_prova.rounds_count
        self.min_participants = source_prova.min_participants
        self.max_participants = source_prova.max_participants
        self.entry_fee = source_prova.entry_fee
        self.discipline = source_prova.discipline
        self.distance = source_prova.distance
        self.best_of = source_prova.best_of
    
    def __repr__(self):
        return f'<Prova {self.number} - {self.discipline}>'

# Resto dei models rimane uguale...
class Inscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    prova_id = db.Column(db.Integer, db.ForeignKey('prova.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    initial_order = db.Column(db.Integer)  # ordine sorteggio iniziale
    
    def __repr__(self):
        return f'<Inscription {self.user.username} -> Prova {self.prova.number}>'

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
    
    def __repr__(self):
        if self.is_bye:
            return f'<Match {self.player1.username} (Bye)>'
        else:
            return f'<Match {self.player1.username} vs {self.player2.username}>'

class Rack(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False)
    rack_number = db.Column(db.Integer, nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # NUOVI CAMPI per conferma punti
    reported_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # chi ha segnato
    confirmed_by_player = db.Column(db.Boolean, default=False)  # confermato dall'altro giocatore
    validated_by_admin = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relazioni
    winner = db.relationship('User', foreign_keys=[winner_id])
    reported_by = db.relationship('User', foreign_keys=[reported_by_id])
    
    def can_be_removed(self, current_user_id):
        """Verifica se questo rack può essere rimosso dall'utente corrente"""
        # Può essere rimosso solo da chi l'ha segnato e se non è confermato
        return (self.reported_by_id == current_user_id and 
                not self.confirmed_by_player and 
                not self.validated_by_admin)
    
    def can_be_confirmed(self, current_user_id):
        """Verifica se questo rack può essere confermato dall'utente corrente"""
        # Può essere confermato dall'altro giocatore (non da chi l'ha segnato)
        return (self.reported_by_id != current_user_id and 
                not self.confirmed_by_player and 
                not self.validated_by_admin)
    
    def can_remove_confirmation(self, current_user_id):
        """Verifica se può rimuovere la conferma"""
        # Può rimuovere la conferma se l'ha confermata lui e non è validata dall'admin
        return (self.reported_by_id != current_user_id and 
                self.confirmed_by_player and 
                not self.validated_by_admin)
    
    def __repr__(self):
        return f'<Rack {self.rack_number} - Winner: {self.winner.username}>'
    
    def can_be_removed(self, current_user_id):
        """Verifica se questo rack può essere rimosso dall'utente corrente"""
        # Può essere rimosso solo da chi l'ha segnato e se non è confermato
        return (self.reported_by_id == current_user_id and 
                not self.confirmed_by_player and 
                not self.validated_by_admin)
    
    def can_be_confirmed(self, current_user_id):
        """Verifica se questo rack può essere confermato dall'utente corrente"""
        # Può essere confermato dall'altro giocatore (non da chi l'ha segnato)
        return (self.reported_by_id != current_user_id and 
                not self.confirmed_by_player and 
                not self.validated_by_admin)
    
    def can_remove_confirmation(self, current_user_id):
        """Verifica se può rimuovere la conferma"""
        # Può rimuovere la conferma se l'ha confermata lui e non è validata dall'admin
        return (self.reported_by_id != current_user_id and 
                self.confirmed_by_player and 
                not self.validated_by_admin)


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
    
    def __repr__(self):
        return f'<MatchResult by {self.reporter.username}>'

class Classification(db.Model):
    """Classifica generale del torneo"""
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    position = db.Column(db.Integer)
    total_matches_won = db.Column(db.Integer, default=0)
    total_point_difference = db.Column(db.Integer, default=0)
    provas_played = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<Classification {self.position}° {self.user.username}>'

class Playoff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    category = db.Column(db.String(20), nullable=False)  # elite, academy
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    qualified_position = db.Column(db.Integer)  # posizione che dava diritto
    confirmation_status = db.Column(db.String(20), default='pending')  # pending, confirmed, declined
    confirmed_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<Playoff {self.category} - {self.user.username}>'