#!/usr/bin/env python3
"""
Test finale completo per il sistema Challenge
Verifica tutto il workflow dalla creazione alla visualizzazione
"""

import os
from app import create_app


def test_route_registration():
    """Test della registrazione delle route challenge"""
    print("🛣️  Test Registrazione Route Challenge")
    print("=" * 50)
    
    try:
        app = create_app()
        
        # Verifica che le route siano registrate
        routes = []
        for rule in app.url_map.iter_rules():
            if 'challenge' in rule.rule:
                routes.append((rule.rule, rule.endpoint))
        
        print(f"   ✅ Trovate {len(routes)} route contenenti 'challenge':")
        for route, endpoint in routes:
            print(f"      {route} -> {endpoint}")
        
        # Verifica route specifiche che dovrebbero esistere
        expected_routes = [
            '/admin/gara/challenges/available',
            '/admin/gara/challenges/create',
        ]
        
        registered_routes = [route for route, _ in routes]
        
        all_found = True
        for expected in expected_routes:
            if expected in registered_routes:
                print(f"   ✅ Route {expected} è registrata")
            else:
                print(f"   ❌ Route {expected} NON è registrata")
                all_found = False
        
        return all_found
        
    except Exception as e:
        print(f"❌ Errore nella verifica route: {e}")
        return False


def test_database_challenge_system():
    """Test del sistema challenge tramite modelli"""
    print("\n🗄️  Test Database Challenge System")
    print("=" * 50)
    
    with create_app().app_context():
        try:
            from models import db
            from models.challenge.models import Challenge
            from models.challenge.services import ChallengeService
            from models.competition.models import Gara
            from models.challenge.gara_challenge_models import GaraChallenge
            from models.challenge.gara_challenge_service import GaraChallengeService
            
            # Test 1: Crea challenge di test
            print("\n🧪 Test 1: Creazione challenge via service")
            
            challenge = ChallengeService.create_challenge(
                name=None,  # Test nome vuoto
                description="Test challenge finale per verifica sistema completo",
                min_score=0,
                max_score=20,
                pass_fail_only=False,
                created_by_id=1
            )
            
            print(f"   ✅ Challenge creata: ID={challenge.id}")
            print(f"   ✅ Display Name: '{challenge.get_display_name()}'")
            print(f"   ✅ Image filename: {challenge.image_filename or '(nessuna)'}")
            
            # Test 2: Verifica challenge esistenti
            print("\n📋 Test 2: Verifica challenge nel database")
            all_challenges = Challenge.query.filter_by(is_active=True).all()
            print(f"   ✅ Trovate {len(all_challenges)} challenge attive")
            
            for i, ch in enumerate(all_challenges[:3], 1):
                print(f"   {i}. {ch.get_display_name()}")
                print(f"      Tipo: {'Pass/Fail' if ch.pass_fail_only else f'{ch.min_score}-{ch.max_score}'}")
                print(f"      Immagine: {ch.image_filename or '(nessuna)'}")
            
            # Test 3: Crea una gara Random di test
            print("\n🎯 Test 3: Creazione gara Random per test challenge")
            
            from datetime import date
            
            test_gara = Gara(
                name="Test Gara Challenge Sistema",
                description="Gara di test finale per il sistema challenge",
                rounds_count=3,
                min_participants=4,
                matchmaking_strategy="random",
                status="setup",
                number=999,  # Required field
                director_id=1,  # Required field
                date=date.today(),  # Required field
                discipline="8-ball",  # Required field
                distance="9 ft"  # Required field
            )
            db.session.add(test_gara)
            db.session.commit()
            
            print(f"   ✅ Gara creata: ID={test_gara.id}, Nome='{test_gara.name}'")
            
            # Test 4: Aggiungi challenge alla gara
            print("\n🔗 Test 4: Aggiunta challenge alla gara")
            
            gara_challenge = GaraChallengeService.add_challenge_to_gara(
                gara_id=test_gara.id,
                challenge_id=challenge.id,
                round_number=2,
                max_attempts=3,
                added_by_id=1
            )
            
            print(f"   ✅ Challenge aggiunta alla gara")
            print(f"   ✅ GaraChallenge ID: {gara_challenge.id}")
            print(f"   ✅ Dopo turno: {gara_challenge.round_number}")
            print(f"   ✅ Max tentativi: {gara_challenge.max_attempts}")
            
            # Test 5: Verifica recupero challenge per gara
            print("\n📊 Test 5: Recupero challenge per gara")
            
            gara_challenges = GaraChallengeService.get_gara_challenges(test_gara.id)
            print(f"   ✅ Trovate {len(gara_challenges)} challenge per la gara")
            
            for gc in gara_challenges:
                print(f"   - Challenge: {gc.challenge.get_display_name()}")
                print(f"     Turno: {gc.round_number}, Tentativi: {gc.max_attempts}")
                print(f"     Immagine: {gc.challenge.image_filename or '(nessuna)'}")
            
            # Test 6: Test JSON serialization per endpoint
            print("\n🔄 Test 6: Serializzazione JSON per endpoint")
            
            challenges_data = []
            for ch in all_challenges[:3]:
                challenges_data.append({
                    "id": ch.id,
                    "name": ch.name,
                    "description": ch.description,
                    "pass_fail_only": ch.pass_fail_only,
                    "min_score": ch.min_score,
                    "max_score": ch.max_score,
                    "image_filename": ch.image_filename,
                })
            
            print(f"   ✅ Serializzate {len(challenges_data)} challenge per JSON")
            print(f"   ✅ Challenge con immagini: {len([c for c in challenges_data if c['image_filename']])}")
            print(f"   ✅ Challenge senza nome: {len([c for c in challenges_data if not c['name']])}")
            
            # Cleanup
            print("\n🧹 Cleanup: Rimozione dati di test")
            db.session.delete(test_gara)
            db.session.delete(challenge)
            db.session.commit()
            print("   ✅ Dati di test rimossi")
            
            return True
            
        except Exception as e:
            print(f"❌ Errore nel test database: {e}")
            db.session.rollback()
            return False


def test_ui_components():
    """Test dei componenti UI"""
    print("\n🎨 Test Componenti UI")
    print("=" * 50)
    
    # Test presenza template files
    template_files = [
        "templates/components/_challenge_management_modal.html",
        "templates/components/_gara_management.html",
        "templates/components/_match_challenge_input.html",
        "templates/components/_player_challenge_statistics.html"
    ]
    
    all_exist = True
    for template in template_files:
        if os.path.exists(template):
            print(f"✅ Template exists: {template.split('/')[-1]}")
            
            # Verifica contenuto specifico del modal
            if "challenge_management_modal" in template:
                with open(template, 'r') as f:
                    content = f.read()
                
                # Verifica che gli URL siano corretti
                if '/admin/gara/challenges/available' in content:
                    print("   ✅ URL corretto per /admin/gara/challenges/available")
                else:
                    print("   ❌ URL non corretto per challenges/available")
                    all_exist = False
                    
                if '/admin/gara/challenges/create' in content:
                    print("   ✅ URL corretto per /admin/gara/challenges/create")
                else:
                    print("   ❌ URL non corretto per challenges/create")
                    all_exist = False
                    
                # Verifica presenza funzioni JavaScript
                js_functions = ['selectChallenge', 'populateChallengeSelect', 'loadAvailableChallenges']
                for func in js_functions:
                    if func in content:
                        print(f"   ✅ Funzione JavaScript {func} trovata")
                    else:
                        print(f"   ❌ Funzione JavaScript {func} NON trovata")
                        all_exist = False
                        
        else:
            print(f"❌ Template missing: {template}")
            all_exist = False
    
    return all_exist


if __name__ == "__main__":
    print("🚀 TEST FINALE COMPLETO SISTEMA CHALLENGE")
    print("=" * 60)
    
    success_count = 0
    
    # Test 1: Registrazione route
    if test_route_registration():
        success_count += 1
        print("\n✅ Test Route Registration: PASSATO")
    else:
        print("\n❌ Test Route Registration: FALLITO")
    
    # Test 2: Database e modelli
    if test_database_challenge_system():
        success_count += 1
        print("\n✅ Test Database: PASSATO")
    else:
        print("\n❌ Test Database: FALLITO")
    
    # Test 3: Componenti UI
    if test_ui_components():
        success_count += 1
        print("\n✅ Test UI Components: PASSATO")
    else:
        print("\n❌ Test UI Components: FALLITO")
    
    print("\n" + "=" * 60)
    print(f"🏁 RISULTATO FINALE: {success_count}/3 test passati")
    
    if success_count == 3:
        print("🎉 TUTTI I TEST PASSATI!")
        print("✨ Il sistema Challenge è completamente funzionale!")
        print("🚀 Puoi andare su http://127.0.0.1:5000 e testare:")
        print("   1. Crea una gara Random")
        print("   2. Clicca 'Gestisci Challenge' nella fase setup")
        print("   3. Aggiungi challenge esistenti o crea nuove challenge")
        print("   4. Verifica che le immagini si vedano nella selezione")
    else:
        print("⚠️  Alcuni test sono falliti. Controlla i dettagli sopra.")
    
    print("=" * 60)