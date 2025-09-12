#!/usr/bin/env python3
"""
Test script per verificare il funzionamento del sistema challenge
"""

import os
from app import create_app

def test_challenge_system():
    print("🧪 Test del Sistema Challenge")
    print("=" * 50)
    
    # Test 3: Test del modello Challenge
    with create_app().app_context():
        try:
            from models.challenge.models import Challenge
            from models.challenge.services import ChallengeService
            
            # Test creazione challenge senza nome
            challenge = Challenge(
                description="Test challenge per verificare il sistema",
                min_score=0,
                max_score=10,
                pass_fail_only=False
            )
            print("✅ Creazione oggetto Challenge senza nome funziona")
            
            # Test metodo get_display_name
            challenge.id = 999
            display_name = challenge.get_display_name()
            print(f"✅ Display name generato: '{display_name}'")
            
            # Test metodo image_filename
            challenge.image_path = "/uploads/challenges/test.jpg"
            filename = challenge.image_filename
            print(f"✅ Image filename: '{filename}'")
            
        except Exception as e:
            print(f"❌ Errore nel test del modello Challenge: {e}")
    
    # Test 4: Verifica directory uploads
    upload_dir = "/Users/paolo/My Drive/Programming/Python/tornei-biliardo/static/uploads/challenges"
    if os.path.exists(upload_dir):
        print(f"✅ Directory uploads esiste: {upload_dir}")
    else:
        print(f"❌ Directory uploads non esiste: {upload_dir}")
    
    # Test 5: Test JavaScript del modal
    modal_file = "/Users/paolo/My Drive/Programming/Python/tornei-biliardo/templates/components/_challenge_management_modal.html"
    if os.path.exists(modal_file):
        print(f"✅ File modal esiste: {modal_file}")
        
        # Leggi il file e verifica che contenga le funzioni JavaScript
        with open(modal_file, 'r') as f:
            content = f.read()
            
        if 'selectChallenge(' in content:
            print("✅ Funzione selectChallenge trovata nel modal")
        else:
            print("❌ Funzione selectChallenge NON trovata nel modal")
            
        if 'populateChallengeSelect(' in content:
            print("✅ Funzione populateChallengeSelect trovata nel modal")
        else:
            print("❌ Funzione populateChallengeSelect NON trovata nel modal")
            
    else:
        print(f"❌ File modal non esiste: {modal_file}")
    
    # Test 6: Test del pulsante nella gara
    management_file = "/Users/paolo/My Drive/Programming/Python/tornei-biliardo/templates/components/_gara_management.html"
    if os.path.exists(management_file):
        with open(management_file, 'r') as f:
            content = f.read()
            
        if 'Gestisci Challenge' in content:
            print("✅ Pulsante 'Gestisci Challenge' trovato nel template")
        else:
            print("❌ Pulsante 'Gestisci Challenge' NON trovato nel template")
            
        if 'challengeManagementModal' in content:
            print("✅ Riferimento al modal trovato")
        else:
            print("❌ Riferimento al modal NON trovato")
    
    print("\n🔍 Possibili cause del problema:")
    print("1. L'utente non è loggato come admin")
    print("2. La gara non è di tipo 'random'")
    print("3. Errori JavaScript nel browser")
    print("4. Problemi di autenticazione negli endpoint AJAX")
    print("5. Database non aggiornato con le nuove colonne")

if __name__ == "__main__":
    test_challenge_system()