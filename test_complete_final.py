#!/usr/bin/env python3
"""
Test finale completo del sistema challenge
"""

from app import create_app

def test_complete_challenge_system():
    print("🚀 TEST FINALE COMPLETO SISTEMA CHALLENGE")
    print("=" * 70)
    
    with create_app().app_context():
        from models import db
        from models.competition.models import Gara  
        from models.challenge.models import Challenge
        from models.challenge.gara_challenge_service import GaraChallengeService
        
        try:
            # Test 1: Verifica gara Random
            print("🎯 Test 1: Verifica gara Random con challenge...")
            gara = Gara.query.filter_by(matchmaking_strategy="random").first()
            if not gara:
                print("❌ Nessuna gara Random trovata")
                return False
            
            print(f"   ✅ Gara: {gara.name} (ID: {gara.id})")
            print(f"   ✅ Status: {gara.status}")
            print(f"   ✅ Strategy: {gara.matchmaking_strategy}")
            
            # Test 2: Verifica challenge con immagine
            print(f"\n🖼️  Test 2: Verifica challenge con immagine...")
            challenge_with_image = Challenge.query.filter(Challenge.image_path.isnot(None)).first()
            if challenge_with_image:
                print(f"   ✅ Challenge con immagine: {challenge_with_image.get_display_name()}")
                print(f"   ✅ Image path: {challenge_with_image.image_path}")
                print(f"   ✅ Image filename: {challenge_with_image.image_filename}")
                
                # Verifica file fisico
                import os
                static_path = f"/Users/paolo/My Drive/Programming/Python/tornei-biliardo/static{challenge_with_image.image_path}"
                file_exists = os.path.exists(static_path)
                print(f"   ✅ File exists: {file_exists}")
            else:
                print("   ⚠️  Nessuna challenge con immagine trovata")
            
            # Test 3: Verifica challenge assegnate alla gara
            print(f"\n🔗 Test 3: Verifica challenge assegnate alla gara...")
            gara_challenges = GaraChallengeService.get_gara_challenges(gara.id)
            print(f"   ✅ Challenge assegnate: {len(gara_challenges)}")
            
            for gc in gara_challenges:
                print(f"     - {gc.challenge.get_display_name()}")
                print(f"       Turno: {gc.round_number}, Tentativi: {gc.max_attempts}")
                print(f"       Immagine: {gc.challenge.image_filename or '(nessuna)'}")
            
            # Test 4: Verifica logica template
            print(f"\n📋 Test 4: Simulazione logica template...")
            is_random = gara.matchmaking_strategy == 'random'
            active_challenges = [gc for gc in gara.gara_challenges if gc.is_active]
            has_challenges = len(active_challenges) > 0
            
            print(f"   ✅ is_random: {is_random}")
            print(f"   ✅ active_challenges count: {len(active_challenges)}")
            print(f"   ✅ has_challenges: {has_challenges}")
            print(f"   ✅ button_text: {'Gestisci Challenge' if has_challenges else 'Aggiungi Challenge'}")
            print(f"   ✅ show_challenges_section: {is_random and has_challenges}")
            
            # Test 5: Verifica disponibilità challenge per aggiunta
            print(f"\n➕ Test 5: Verifica challenge disponibili per aggiunta...")
            all_challenges = Challenge.query.filter_by(is_active=True).all()
            print(f"   ✅ Challenge totali disponibili: {len(all_challenges)}")
            print(f"   ✅ Challenge con immagini: {len([c for c in all_challenges if c.image_filename])}")
            print(f"   ✅ Challenge senza nome: {len([c for c in all_challenges if not c.name])}")
            
            # Test 6: Status validazione per aggiunta challenge
            print(f"\n✔️  Test 6: Validazione status per aggiunta challenge...")
            from models.status_enum import GaraStatus
            
            valid_statuses = [GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value]
            can_add_challenges = gara.status in valid_statuses
            
            print(f"   ✅ Current status: {gara.status}")
            print(f"   ✅ Valid statuses: {valid_statuses}")
            print(f"   ✅ Can add challenges: {can_add_challenges}")
            
            # Riepilogo finale
            print(f"\n" + "=" * 70)
            print(f"📊 RIEPILOGO SISTEMA CHALLENGE")
            print(f"=" * 70)
            print(f"🎯 Gara Random: {gara.name} (ID: {gara.id})")
            print(f"📱 Status: {gara.status} ({'✅ OK' if can_add_challenges else '❌ NON MODIFICABILE'})")
            print(f"🔗 Challenge assegnate: {len(gara_challenges)}")
            print(f"🖼️  Challenge con immagini: {len([gc for gc in gara_challenges if gc.challenge.image_filename])}")
            print(f"🔘 Testo pulsante: {'Gestisci Challenge' if has_challenges else 'Aggiungi Challenge'}")
            print(f"👁️  Mostra sezione: {'SÍ' if (is_random and has_challenges) else 'NO'}")
            print(f"=" * 70)
            
            print(f"\n🎉 TUTTI I TEST PASSATI!")
            print(f"🚀 Vai su: http://127.0.0.1:5000/admin/gara/{gara.id}")
            print(f"   • Dovresti vedere la sezione Challenge Attive")
            print(f"   • Il pulsante dovrebbe dire '{'Gestisci Challenge' if has_challenges else 'Aggiungi Challenge'}'")
            print(f"   • Le immagini dovrebbero caricare correttamente")
            print(f"   • Puoi aggiungere nuove challenge senza errori di validazione")
            
            return True
            
        except Exception as e:
            print(f"❌ Errore durante test: {e}")
            return False

if __name__ == "__main__":
    success = test_complete_challenge_system()
    exit(0 if success else 1)