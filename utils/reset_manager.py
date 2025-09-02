"""
Reset Manager - Sistema modulare per gestire vari tipi di reset del database
"""

import os
import json
import shutil
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

from flask import has_app_context, current_app
from sqlalchemy import text

from models.base import db
from models import User
from models.tournament.models import Tournament
from models.user.models import TournamentDirector
from models.user.services import UserService
from models.user.role_enum import UserRole
from models.competition.services import ProvaService, InscriptionService
from models.status_enum import ProvaStatus
from utils import create_admin_if_not_exists


class ResetManager:
    """Gestisce i vari tipi di reset del database"""
    
    SNAPSHOTS_DIR = "db_snapshots"
    
    def __init__(self):
        self.reset_options = {
            'base': {
                'name': 'Reset Base',
                'description': 'Azzera il database e crea solo l\'utente admin',
                'function': self.reset_base,
                'deletable': False
            },
            'demo': {
                'name': 'Reset Demo',
                'description': 'Crea admin, torneo "La Garetta", 8 giocatori, mario, pino con iscrizioni',
                'function': self.reset_demo,
                'deletable': False
            }
        }
        self._ensure_snapshots_dir()
    
    def _ensure_snapshots_dir(self):
        """Crea la directory per i snapshot se non esiste"""
        if not os.path.exists(self.SNAPSHOTS_DIR):
            os.makedirs(self.SNAPSHOTS_DIR)
    
    def get_reset_options(self) -> Dict[str, Dict]:
        """Restituisce tutte le opzioni di reset disponibili"""
        # Aggiungi i reset salvati
        saved_resets = self._load_saved_resets()
        all_options = self.reset_options.copy()
        all_options.update(saved_resets)
        return all_options
    
    def _load_saved_resets(self) -> Dict[str, Dict]:
        """Carica i reset salvati dalla directory dei snapshot"""
        saved_resets = {}
        snapshot_path = Path(self.SNAPSHOTS_DIR)
        
        for snapshot_file in snapshot_path.glob("*.db"):
            reset_id = snapshot_file.stem
            metadata_file = snapshot_path / f"{reset_id}.json"
            
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    saved_resets[reset_id] = {
                        'name': metadata.get('name', f'Snapshot {reset_id}'),
                        'description': metadata.get('description', ''),
                        'created_at': metadata.get('created_at', ''),
                        'function': lambda sid=reset_id: self.restore_snapshot(sid),
                        'deletable': True
                    }
        
        return saved_resets
    
    def reset_base(self) -> Dict[str, Any]:
        """Reset base: solo admin"""
        # Drop e ricrea tutte le tabelle
        db.drop_all()
        db.create_all()
        
        # Crea solo l'admin
        admin = self._create_admin()
        
        db.session.commit()
        
        return {
            'status': 'success',
            'message': 'Database resettato con successo (solo admin)',
            'data': {
                'admin': admin
            }
        }
    
    def reset_demo(self) -> Dict[str, Any]:
        """Reset demo con torneo La Garetta e giocatori"""
        # Drop e ricrea tutte le tabelle
        db.drop_all()
        db.create_all()
        
        # Crea admin
        admin = self._create_admin()
        
        # Crea mario e pino
        mario = UserService.create_user(
            "mario", "mario@pippo.it", "mario123", role="player"
        )
        pino = UserService.create_user(
            "pino", "pino@pippo.it", "pino123", role="player"
        )
        
        # Crea 8 giocatori player01-player08
        players = []
        for n in range(1, 9):
            uname = f"player{n:02d}"
            player = UserService.create_user(
                uname, f"{uname}@tornei.com", "123456", role="player"
            )
            players.append(player)
        
        # Crea torneo La Garetta
        garetta = Tournament(name="La Garetta", tournament_type="Amalfi")
        db.session.add(garetta)
        db.session.flush()
        
        # Crea prova con parametri specificati
        today = date.today()
        prova_garetta = ProvaService.create_prova(
            name="La Garetta",
            number=1,
            date=today + timedelta(days=7),
            discipline="9-ball",
            distance=5,
            tournament_id=garetta.id,
            director_id=admin.id,
            min_inscriptions=6,
            matchmaking_type="Amalfi",
            with_handicap=False,
            playoff_rounds=0,  # senza playoff
            scoring_system="classic"
        )
        
        # Apri iscrizioni
        ProvaService.to_inscription(
            prova_garetta.id,
            datetime.now(),
            datetime.now() + timedelta(days=6)
        )
        
        # Iscrivi 5 giocatori (mario, pino e i primi 3 player)
        inscribed_users = [mario, pino] + players[:3]
        for user in inscribed_users:
            InscriptionService.inscribe_user(user.id, prova_garetta.id)
        
        db.session.commit()
        
        return {
            'status': 'success',
            'message': 'Database resettato con dati demo',
            'data': {
                'admin': admin,
                'mario': mario,
                'pino': pino,
                'players': players,
                'tournament': garetta,
                'prova': prova_garetta,
                'inscribed_count': len(inscribed_users)
            }
        }
    
    def save_current_state(self, name: str, description: str = "") -> Dict[str, Any]:
        """Salva lo stato corrente del database come snapshot"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_id = f"snapshot_{timestamp}"
            
            # Copia il file del database
            db_path = self._get_database_path()
            if not db_path:
                return {
                    'status': 'error',
                    'message': 'Database path non trovato'
                }
            
            snapshot_path = os.path.join(self.SNAPSHOTS_DIR, f"{snapshot_id}.db")
            shutil.copy2(db_path, snapshot_path)
            
            # Salva i metadati
            metadata = {
                'name': name,
                'description': description,
                'created_at': datetime.now().isoformat(),
                'snapshot_id': snapshot_id
            }
            
            metadata_path = os.path.join(self.SNAPSHOTS_DIR, f"{snapshot_id}.json")
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            return {
                'status': 'success',
                'message': f'Snapshot "{name}" salvato con successo',
                'snapshot_id': snapshot_id
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Errore nel salvare lo snapshot: {str(e)}'
            }
    
    def restore_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        """Ripristina uno snapshot salvato"""
        try:
            snapshot_path = os.path.join(self.SNAPSHOTS_DIR, f"{snapshot_id}.db")
            
            if not os.path.exists(snapshot_path):
                return {
                    'status': 'error',
                    'message': f'Snapshot {snapshot_id} non trovato'
                }
            
            # Chiudi tutte le connessioni al database
            db.session.close()
            db.engine.dispose()
            
            # Sovrascrivi il database corrente con lo snapshot
            db_path = self._get_database_path()
            if not db_path:
                return {
                    'status': 'error',
                    'message': 'Database path non trovato'
                }
            
            shutil.copy2(snapshot_path, db_path)
            
            # Riconnetti al database
            db.engine.connect()
            
            return {
                'status': 'success',
                'message': f'Snapshot {snapshot_id} ripristinato con successo'
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Errore nel ripristinare lo snapshot: {str(e)}'
            }
    
    def delete_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        """Elimina uno snapshot salvato"""
        try:
            # Non permettere l'eliminazione dei reset predefiniti
            if snapshot_id in ['base', 'demo']:
                return {
                    'status': 'error',
                    'message': 'Non puoi eliminare i reset predefiniti'
                }
            
            snapshot_path = os.path.join(self.SNAPSHOTS_DIR, f"{snapshot_id}.db")
            metadata_path = os.path.join(self.SNAPSHOTS_DIR, f"{snapshot_id}.json")
            
            if os.path.exists(snapshot_path):
                os.remove(snapshot_path)
            if os.path.exists(metadata_path):
                os.remove(metadata_path)
            
            return {
                'status': 'success',
                'message': f'Snapshot {snapshot_id} eliminato con successo'
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Errore nell\'eliminare lo snapshot: {str(e)}'
            }
    
    def execute_reset(self, reset_type: str) -> Dict[str, Any]:
        """Esegue un reset specifico"""
        options = self.get_reset_options()
        
        if reset_type not in options:
            return {
                'status': 'error',
                'message': f'Tipo di reset "{reset_type}" non trovato'
            }
        
        reset_option = options[reset_type]
        return reset_option['function']()
    
    def _create_admin(self) -> User:
        """Crea l'utente admin"""
        admin = create_admin_if_not_exists()
        if admin is None:
            cfg = current_app.config if has_app_context() else {}
            username = (cfg.get("ADMIN_USERNAME") or "admin").strip()
            email = (cfg.get("ADMIN_EMAIL") or f"{username}@tournament.local").strip()
            password = (cfg.get("ADMIN_PASSWORD") or "admin123").strip()
            
            existing = (
                User.query.filter_by(role=UserRole.ADMIN.value)
                .filter(User.deleted_at.is_(None))
                .first()
            )
            admin = existing or UserService.create_user(
                username=username, 
                email=email, 
                password=password, 
                role=UserRole.ADMIN.value
            )
        
        return admin
    
    def _get_database_path(self) -> Optional[str]:
        """Ottiene il percorso del file del database SQLite"""
        if has_app_context():
            db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
            if db_uri.startswith('sqlite:///'):
                db_path = db_uri.replace('sqlite:///', '')
                # Se il percorso è relativo, potrebbe essere nella directory instance
                if not os.path.isabs(db_path):
                    # Prova prima nella directory corrente
                    if os.path.exists(db_path):
                        return db_path
                    # Poi prova nella directory instance
                    instance_path = os.path.join('instance', db_path)
                    if os.path.exists(instance_path):
                        return instance_path
                return db_path
        
        # Fallback: cerca il database nelle posizioni comuni
        possible_paths = [
            'instance/billiard_tournament.db',
            'billiard_tournament.db',
            os.path.join(os.getcwd(), 'instance', 'billiard_tournament.db'),
            os.path.join(os.getcwd(), 'billiard_tournament.db')
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None