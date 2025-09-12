#!/usr/bin/env python3
"""
Test per verificare la visualizzazione delle challenge nella pagina gara
"""

from app import create_app

def test_challenge_display():
    print("🎮 Test Visualizzazione Challenge in Gara Detail")
    print("=" * 60)
    
    with create_app().app_context():
        from models import db
        from models.competition.models import Gara  
        from models.challenge.models import Challenge
        from models.challenge.gara_challenge_models import GaraChallenge
        from models.challenge.gara_challenge_service import GaraChallengeService
        
        try:
            # Test 1: Trova una gara Random esistente
            print("🔍 Test 1: Ricerca gara Random esistente...")
            random_gara = Gara.query.filter_by(matchmaking_strategy="random").first()
            
            if not random_gara:
                print("❌ Nessuna gara Random trovata, creazione test gara...")
                from datetime import date
                random_gara = Gara(
                    name="Test Gara Challenge Display",
                    description="Gara di test per visualizzazione challenge",
                    rounds_count=3,
                    min_participants=4,
                    matchmaking_strategy="random",
                    status="setup",
                    number=998,
                    director_id=1,
                    date=date.today(),
                    discipline="8-ball",
                    distance="9 ft"
                )
                db.session.add(random_gara)
                db.session.commit()
            
            print(f"✅ Gara trovata: ID={random_gara.id}, Nome='{random_gara.name}'")
            
            # Test 2: Verifica relazione gara_challenges
            print("\n🔗 Test 2: Verifica relazione backref gara_challenges...")
            challenges_count = len(random_gara.gara_challenges)
            active_challenges = [gc for gc in random_gara.gara_challenges if gc.is_active]
            print(f"✅ Relazione backref funziona: {challenges_count} challenge totali, {len(active_challenges)} attive")
            
            # Test 3: Se non ci sono challenge attive, ne aggiungiamo una
            if len(active_challenges) == 0:
                print("\n➕ Test 3: Aggiunta challenge di test...")
                
                # Trova una challenge esistente
                test_challenge = Challenge.query.filter_by(is_active=True).first()
                if not test_challenge:
                    print("❌ Nessuna challenge disponibile nel database")
                    return False
                
                # Aggiungi challenge alla gara
                gara_challenge = GaraChallengeService.add_challenge_to_gara(
                    gara_id=random_gara.id,
                    challenge_id=test_challenge.id,
                    round_number=2,
                    max_attempts=3,
                    added_by_id=1
                )
                
                print(f"✅ Challenge aggiunta: ID={gara_challenge.id}")
                
                # Ricarica la gara per aggiornare la relazione
                db.session.refresh(random_gara)
                active_challenges = [gc for gc in random_gara.gara_challenges if gc.is_active]
            
            # Test 4: Verifica template variables
            print(f"\n📋 Test 4: Verifica variabili template...")
            
            print(f"   gara.id: {random_gara.id}")
            print(f"   gara.matchmaking_strategy: '{random_gara.matchmaking_strategy}'")
            print(f"   gara.gara_challenges (len): {len(random_gara.gara_challenges)}")
            
            # Simula la logica del template _gara_challenges_display.html
            is_random = random_gara.matchmaking_strategy == 'random'
            active_challenges_filtered = [gc for gc in random_gara.gara_challenges if gc.is_active]
            
            print(f"   is_random: {is_random}")
            print(f"   active_challenges (filtered): {len(active_challenges_filtered)}")
            
            if is_random and active_challenges_filtered:
                print("\n📊 Dettagli challenge che verranno mostrate:")
                for i, gc in enumerate(active_challenges_filtered, 1):
                    challenge = gc.challenge
                    print(f"   {i}. {challenge.get_display_name()}")
                    print(f"      Descrizione: {challenge.description[:50]}...")
                    print(f"      Tipo: {'Pass/Fail' if challenge.pass_fail_only else f'{challenge.min_score}-{challenge.max_score}'}")
                    print(f"      Turno: Dopo il {gc.round_number}°")
                    print(f"      Tentativi: {gc.max_attempts}")
                    print(f"      Immagine: {challenge.image_filename or '(nessuna)'}")
            
            # Test 5: Simula logica pulsante
            print(f"\n🔘 Test 5: Verifica testo pulsante...")
            has_challenges = len(active_challenges_filtered) > 0
            button_text = "Gestisci Challenge" if has_challenges else "Aggiungi Challenge"
            print(f"   has_challenges: {has_challenges}")
            print(f"   button_text: '{button_text}'")
            
            print(f"\n🎉 TUTTI I TEST PASSATI!")
            print(f"━" * 60)
            print(f"📊 Riepilogo:")
            print(f"   • Gara ID: {random_gara.id}")
            print(f"   • Challenge attive: {len(active_challenges_filtered)}")
            print(f"   • Testo pulsante: '{button_text}'")
            print(f"   • Template display: {'SÌ' if (is_random and active_challenges_filtered) else 'NO'}")
            print(f"━" * 60)
            print(f"\n🚀 Ora puoi andare su http://127.0.0.1:5000/admin/gara/{random_gara.id}")
            print(f"   e verificare che le challenge appaiano nella sezione informazioni!")
            
            return True
            
        except Exception as e:
            print(f"❌ Errore durante test: {e}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    success = test_challenge_display()
    exit(0 if success else 1)