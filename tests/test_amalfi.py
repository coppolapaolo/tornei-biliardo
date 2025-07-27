# tests/test_amalfi.py - Test rapido del Sistema Amalfi

import sys
import os

# Aggiungi la directory parent al path per permettere import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, Tournament, Prova, User, Inscription
from amalfi.engine import validate_amalfi_configuration, AmalfiEngine
from datetime import date, datetime

def test_amalfi_basic():
    """Test rapido delle funzioni Amalfi"""
    
    app = create_app()
    
    with app.app_context():
        print("🧪 Testing Sistema Amalfi...")
        
        # 1. Test che i modelli siano stati creati
        try:
            from models import PlayerEncounter, RoundClassification, TrioMatch
            print("✅ Nuovi modelli importati correttamente")
        except ImportError as e:
            print(f"❌ Errore import modelli: {e}")
            return
        
        # 2. Test che esista almeno un torneo
        tournament = Tournament.query.first()
        if not tournament:
            print("❌ Nessun torneo trovato - fai reset del database")
            return
        print(f"✅ Trovato torneo: {tournament.name}")
        
        # 3. Test creazione prova Amalfi
        try:
            prova = Prova(
                tournament_id=tournament.id,
                number=99,  # Numero test
                name="Test Amalfi",
                date=date.today(),
                discipline="palla 9",
                distance=7,
                best_of=True,
                rounds_count=3,
                status='setup'
            )
            db.session.add(prova)
            db.session.commit()
            print(f"✅ Prova test creata: ID {prova.id}")
            
            # 4. Test validazione configurazione
            validation = validate_amalfi_configuration(prova)
            print(f"✅ Validazione: {validation['is_valid']}")
            if validation['errors']:
                print(f"⚠️  Errori: {validation['errors']}")
            
            # 5. Test creazione AmalfiEngine
            engine = AmalfiEngine(prova)
            print(f"✅ AmalfiEngine creato per prova {prova.number}")
            
            # 6. Cleanup
            db.session.delete(prova)
            db.session.commit()
            print("✅ Cleanup completato")
            
        except Exception as e:
            print(f"❌ Errore durante test: {e}")
            db.session.rollback()
            return
        
        print("\n🎯 Test Sistema Amalfi COMPLETATO!")
        print("📋 Pronto per la Fase 3: Admin Interface")

if __name__ == "__main__":
    test_amalfi_basic()