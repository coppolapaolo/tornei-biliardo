# 🏗️ Architettura Webapp Tornei Biliardo

> **Documentazione tecnica** dell'architettura software, database design e struttura del progetto.

## 📊 Panoramica Architetturale

### Pattern Architetturale: **Model-View-Controller (MVC)**
- **Models** (`models.py`): SQLAlchemy ORM per data layer
- **Views** (`templates/`): Jinja2 templates per presentation layer  
- **Controllers** (`routes/`): Flask blueprints per business logic

### Design Patterns Utilizzati:
- **Blueprint Pattern**: Route organizzate per funzionalità
- **Factory Pattern**: App creation con configurazioni multiple
- **Repository Pattern**: Data access attraverso SQLAlchemy
- **Decorator Pattern**: Autorizzazioni e validazioni

---

## 📁 Struttura Progetto

```
tornei-biliardo/
├── 📄 app.py                    # Application factory
├── ⚙️ config.py                 # Configurazioni ambiente
├── 🗄️ models.py                 # Database models (SQLAlchemy)
├── 🛠️ utils.py                  # Helper functions e decorators
├── 📋 requirements.txt          # Dipendenze Python
│
├── 📂 routes/                   # Blueprint organizzati per feature
│   ├── __init__.py             # Registrazione blueprints
│   ├── auth.py                 # Autenticazione (login/register/logout)
│   ├── admin.py                # Gestione tornei e admin tools
│   ├── player.py               # Dashboard giocatori e iscrizioni
│   └── main.py                 # Homepage, reset, redirects
│
├── 📂 templates/               # Jinja2 templates
│   ├── base.html               # Template base con navbar e debug
│   ├── index.html              # Homepage multi-torneo
│   ├── login.html              # Sistema autenticazione
│   ├── register.html           # Registrazione utenti
│   ├── match_detail.html       # Dettaglio partite e risultati
│   ├── reset.html              # Reset database (debug)
│   │
│   ├── 📂 admin/               # Templates amministratore
│   │   ├── dashboard.html      # Dashboard tornei
│   │   ├── tournament_detail.html  # Gestione torneo
│   │   ├── tournament_edit.html    # Modifica torneo
│   │   ├── prova_detail.html       # Gestione prova
│   │   ├── prova_edit.html         # Modifica prova
│   │   ├── users_list.html         # Lista utenti
│   │   ├── user_detail.html        # Dettaglio utente
│   │   └── prova_results_overview.html  # Overview risultati
│   │
│   └── 📂 player/              # Templates giocatore  
│       ├── dashboard.html      # Dashboard personale
│       ├── profile.html        # Profilo e statistiche
│       └── delete_account.html # Cancellazione account
│
├── 📂 instance/                # SQLite database (gitignored)
└── 📂 static/ (futuro)         # CSS, JS, images
```

---

## 🗄️ Database Schema

### Diagramma ER Semplificato
```
User (1) ←→ (N) Inscription (N) ←→ (1) Prova (N) ←→ (1) Tournament
  ↓                                        ↓
  └→ (N) Match ←→ (N) Rack              Match
           ↓                              ↓
        MatchResult                  Classification
```

### 👥 User Management

#### **User**
```python
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations
    inscriptions = db.relationship('Inscription', backref='user')
    match_results = db.relationship('MatchResult', foreign_keys='MatchResult.user_id')
    classifications = db.relationship('Classification', backref='user')
```

**Funzionalità**:
- Autenticazione con password hash
- Ruoli admin/player
- Statistiche automatiche
- Gestione cancellazione account

### 🏆 Tournament Structure

#### **Tournament**
```python
class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tournament_type = db.Column(db.String(50), default='Amalfi')
    without_x = db.Column(db.Boolean, default=False)  # Senza X
    final_playoffs = db.Column(db.Boolean, default=True)
    challenge_mode = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations
    provas = db.relationship('Prova', backref='tournament', cascade='all, delete-orphan')
```

**Features**:
- Multi-torneo con gestione simultanea
- Configurazioni specifiche Amalfi
- Stato attivo/inattivo
- Cascading delete per prove

#### **Prova**
```python
class Prova(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'))
    number = db.Column(db.Integer, nullable=False)  # 1-20
    name = db.Column(db.String(100))
    date = db.Column(db.Date, nullable=False)
    
    # Location & Participation
    location = db.Column(db.String(200))
    description = db.Column(db.Text)
    min_participants = db.Column(db.Integer, default=2)
    max_participants = db.Column(db.Integer)
    entry_fee = db.Column(db.Float, default=0.0)
    
    # Game Configuration
    discipline = db.Column(db.String(50), nullable=False)  # palla 8/9/10
    distance = db.Column(db.Integer, nullable=False)       # numero rack
    best_of = db.Column(db.Boolean, default=False)         # modalità gioco
    rounds_count = db.Column(db.Integer, default=3)        # turni totali
    
    # Registration Management
    inscription_start = db.Column(db.DateTime)
    inscription_end = db.Column(db.DateTime)
    
    # State Management
    status = db.Column(db.String(20), default='setup')  # setup/inscription/playing/completed
    current_round = db.Column(db.Integer, default=0)    # 0=non iniziata
    
    # Relations
    inscriptions = db.relationship('Inscription', backref='prova')
    matches = db.relationship('Match', backref='prova')
```

**Features**:
- Configurazione completa prova
- Gestione iscrizioni timezone-aware
- Stati dinamici con validazione date
- Modalità "al meglio di" vs "esatto numero"

### 🎮 Match System

#### **Inscription**
```python
class Inscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    prova_id = db.Column(db.Integer, db.ForeignKey('prova.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    initial_order = db.Column(db.Integer)  # ordine sorteggio
```

#### **Match**
```python
class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prova_id = db.Column(db.Integer, db.ForeignKey('prova.id'))
    round_number = db.Column(db.Integer, nullable=False)
    
    # Players
    player1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    player2_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_bye = db.Column(db.Boolean, default=False)  # partita vs X
    
    # Results
    player1_score = db.Column(db.Integer, default=0)
    player2_score = db.Column(db.Integer, default=0)
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # State
    status = db.Column(db.String(20), default='pending')  # pending/playing/completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relations
    player1 = db.relationship('User', foreign_keys=[player1_id])
    player2 = db.relationship('User', foreign_keys=[player2_id])
    winner = db.relationship('User', foreign_keys=[winner_id])
    racks = db.relationship('Rack', backref='match')
```

#### **Rack**
```python
class Rack(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'))
    rack_number = db.Column(db.Integer, nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Confirmation System
    reported_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    confirmed_by_player = db.Column(db.Boolean, default=False)
    validated_by_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

**Features**:
- Sistema conferma punti tra giocatori
- Validazione admin override
- Tracciabilità inserimento risultati

### 📊 Statistics & Classification

#### **Classification**
```python
class Classification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    position = db.Column(db.Integer)
    total_matches_won = db.Column(db.Integer, default=0)
    total_point_difference = db.Column(db.Integer, default=0)
    provas_played = db.Column(db.Integer, default=0)
```

#### **MatchResult** (Tracking Submitters)
```python
class MatchResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    player1_score = db.Column(db.Integer)
    player2_score = db.Column(db.Integer)
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

---

## 🔧 Estensioni Future (STEP 3)

### Sistema Amalfi - Nuovi Models

#### **PlayerEncounter** (Anti-reincontro)
```python
class PlayerEncounter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    player2_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    prova_id = db.Column(db.Integer, db.ForeignKey('prova.id'))
    round_number = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('player1_id', 'player2_id', 'prova_id'),
    )
```

#### **RoundClassification** (Classifiche dinamiche)
```python
class RoundClassification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prova_id = db.Column(db.Integer, db.ForeignKey('prova.id'))
    round_number = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    position = db.Column(db.Integer)
    matches_won = db.Column(db.Integer)
    rack_difference = db.Column(db.Integer)
    previous_position = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

#### **TrioMatch** (Gestione trii)
```python
class TrioMatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'))
    player1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    player2_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    player3_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Current State
    current_player1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    current_player2_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    waiting_player_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Scores
    player1_racks = db.Column(db.Integer, default=0)
    player2_racks = db.Column(db.Integer, default=0)
    player3_racks = db.Column(db.Integer, default=0)
```

---

## 🔄 Business Logic Layer

### Core Utilities (`utils.py`)

#### Decorators
```python
@admin_required          # Richiede privilegi admin
@login_required          # Richiede autenticazione (Flask-Login)
```

#### Helper Functions
```python
def get_database_stats()                    # Statistiche debug
def create_round_matches()                  # Abbinamenti turno 1
def calculate_round_classification()        # Classifica post-turno
def create_default_users()                  # Setup utenti test
def create_sample_tournament()              # Dati esempio
```

#### Future Amalfi Engine
```python
def calculate_amalfi_classification()       # Classifiche Amalfi
def create_amalfi_round_matches()          # Abbinamenti Amalfi
def handle_trio_match_logic()              # Gestione trii  
def validate_amalfi_configuration()        # Validazione setup
def get_player_encounters()                # Anti-reincontro
```

### Configuration Management (`config.py`)

#### Environment Configs
```python
class DevelopmentConfig(Config):
    DEBUG = True
    DEBUG_MODE = True                       # Debug features attive
    SQLALCHEMY_DATABASE_URI = 'sqlite:///billiard_tournament.db'

class ProductionConfig(Config):
    DEBUG = False
    DEBUG_MODE = False                      # Debug disabilitato
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
```

---

## 🌐 Route Architecture

### Blueprint Organization

#### **main_bp** (`routes/main.py`)
- **GET** `/` - Homepage multi-torneo
- **GET** `/reset` - Reset database (debug only)
- **POST** `/reset/confirm` - Conferma reset
- **GET** `/dashboard` - Redirect dashboard appropriato
- **GET** `/debug/login/<username>` - Quick login (debug only)

#### **auth_bp** (`routes/auth.py`)
- **GET/POST** `/auth/login` - Login utenti
- **GET/POST** `/auth/register` - Registrazione
- **GET** `/auth/logout` - Logout

#### **admin_bp** (`routes/admin.py`)
- **GET** `/admin/` - Dashboard amministratore
- **POST** `/admin/tournament/create` - Crea torneo
- **GET** `/admin/tournament/<id>` - Dettaglio torneo
- **GET/POST** `/admin/tournament/<id>/edit` - Modifica torneo
- **POST** `/admin/tournament/<id>/delete` - Elimina torneo
- **POST** `/admin/prova/create` - Crea prova
- **GET** `/admin/prova/<id>` - Dettaglio prova
- **GET/POST** `/admin/prova/<id>/edit` - Modifica prova
- **POST** `/admin/prova/<id>/open_inscriptions` - Apri iscrizioni
- **POST** `/admin/prova/<id>/start_first_round` - Avvia turno 1
- **GET** `/admin/match/<id>` - Dettaglio partita
- **POST** `/admin/match/<id>/add_rack` - Aggiungi rack
- **POST** `/admin/match/<id>/set_result` - Imposta risultato diretto
- **POST** `/admin/match/<id>/reset` - Reset partita
- **GET** `/admin/users` - Lista utenti
- **GET** `/admin/user/<id>` - Dettaglio utente

#### **player_bp** (`routes/player.py`)
- **GET** `/player/` - Dashboard giocatore
- **POST** `/player/prova/<id>/inscribe` - Iscrizione prova
- **POST** `/player/prova/<id>/unsubscribe` - Disiscrizione
- **GET** `/player/match/<id>` - Dettaglio partita
- **POST** `/player/match/<id>/add_rack` - Aggiungi rack
- **GET** `/player/profile` - Profilo personale
- **GET/POST** `/player/delete_account` - Cancellazione account
- **POST** `/player/rack/<id>/remove` - Rimuovi rack
- **POST** `/player/rack/<id>/confirm` - Conferma rack
- **POST** `/player/rack/<id>/unconfirm` - Rimuovi conferma

---

## 🎨 Frontend Architecture

### Template Hierarchy
```
base.html                           # Layout principale
├── index.html                      # Homepage multi-torneo
├── login.html                      # Autenticazione
├── register.html                   # Registrazione
├── match_detail.html               # Dettaglio partite (shared)
└── admin/
    ├── dashboard.html              # Dashboard admin
    ├── tournament_detail.html      # Gestione torneo
    ├── prova_detail.html          # Gestione prova
    ├── users_list.html            # Lista utenti
    └── user_detail.html           # Dettaglio utente
└── player/
    ├── dashboard.html              # Dashboard giocatore
    ├── profile.html               # Profilo personale
    └── delete_account.html        # Cancellazione account
```

### CSS Framework: **Bootstrap 5**
- **Grid System** responsive per layout
- **Components** pre-built (cards, modals, forms)
- **Utilities** per spacing, colors, typography
- **Custom CSS** minimale per personalizzazioni

### JavaScript Strategy
- **Vanilla JS** per interattività base
- **Fetch API** per chiamate AJAX
- **Bootstrap JS** per componenti interattivi
- **Timezone handling** automatico client-side

---

## 🔒 Security & Authorization

### Authentication
- **Flask-Login** per session management
- **Werkzeug** password hashing (pbkdf2:sha256)
- **Session-based** authentication con cookies

### Authorization Levels
```python
# Public routes
@app.route('/')                      # Homepage
@app.route('/auth/login')            # Login

# Authenticated only  
@login_required
@app.route('/player/dashboard')      # Player features

# Admin only
@admin_required  
@app.route('/admin/dashboard')       # Admin features
```

### Data Validation
- **Flask-WTF** forms con CSRF protection
- **SQLAlchemy** constraints a livello database
- **Custom validators** per business rules
- **Input sanitization** automatica

### Privacy & GDPR
- **Account deletion** completa con data cleanup
- **Data minimization** solo dati necessari
- **Audit trail** per azioni sensibili
- **Consent management** per dati opzionali

---

## 📈 Performance & Scalability

### Database Optimization
```python
# Eager loading per evitare N+1 queries
inscriptions = Inscription.query.join(Prova).join(Tournament).all()

# Indexes su foreign keys e query frequenti
class User(db.Model):
    username = db.Column(db.String(80), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)

# Query pagination per grandi dataset
users = User.query.paginate(page=1, per_page=20)
```

### Caching Strategy (Future)
- **SQLAlchemy caching** per query ripetitive
- **Template caching** per pagine statiche
- **Redis** per session storage in produzione
- **CDN** per static assets

### Monitoring & Logging
```python
import logging

# Application logging
app.logger.info(f"User {user.username} created tournament {tournament.name}")
app.logger.error(f"Failed to create match: {str(e)}")

# Performance monitoring
@app.before_request
def before_request():
    g.start_time = time.time()

@app.after_request  
def after_request(response):
    duration = time.time() - g.start_time
    app.logger.info(f"Request {request.endpoint} took {duration:.2f}s")
```

---

## 🚀 Deployment & Infrastructure

### Development Environment
```bash
# Local setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
# → http://localhost:5000
```

### Production Environment (PythonAnywhere)
```bash
# Deployment
cd /home/username/mysite
git pull origin main
# → Web tab: Reload webapp
# → https://username.pythonanywhere.com
```

### Environment Variables
```python
# config.py
SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key'
DATABASE_URL = os.environ.get('DATABASE_URL') or 'sqlite:///tournament.db'
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'False').lower() == 'true'
```

### Backup Strategy
- **Git repository** per codice versioning
- **Database dumps** automatici settimanali
- **File uploads** backup su cloud storage
- **Configuration** backup separato

---

## 🔧 Tools & Development

### IDE Setup
- **VS Code** con estensioni Python, Flask, SQLAlchemy
- **Database viewer** per SQLite (DB Browser)
- **Git integration** per version control
- **Terminal integration** per comando rapido

### Debugging Tools
```python
# Debug mode features
if app.config['DEBUG_MODE']:
    # Footer debug informazioni
    # Quick login per test
    # Database statistics
    # Error stack traces
```

### Code Quality
- **PEP 8** style guide compliance
- **Type hints** per funzioni critiche  
- **Docstrings** per moduli e classi principali
- **Error handling** robusto con try/catch

---

*Documentazione architettura aggiornata: 27 luglio 2025*  
*Stack: Python Flask + SQLAlchemy + Bootstrap 5*  
*Database: SQLite (dev) / PostgreSQL (prod)*