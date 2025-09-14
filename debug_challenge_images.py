#!/usr/bin/env python3
"""
Debug script per verificare le immagini delle challenge
"""

import os
from app import create_app


def debug_challenge_images():
    print("🖼️  Debug Challenge Images")
    print("=" * 50)

    with create_app().app_context():
        from models.challenge.models import Challenge

        try:
            challenges = Challenge.query.filter_by(is_active=True).all()
            print(f"📊 Trovate {len(challenges)} challenge attive")

            upload_dir = "/Users/paolo/My Drive/Programming/Python/tornei-biliardo/static/uploads/challenges"
            print(f"📂 Directory uploads: {upload_dir}")

            # Verifica file nella directory
            if os.path.exists(upload_dir):
                files_in_dir = os.listdir(upload_dir)
                print(f"   File presenti: {files_in_dir}")
            else:
                print("   ❌ Directory non esiste")

            print(f"\n🔍 Analisi challenge:")
            for i, challenge in enumerate(challenges, 1):
                print(f"\n   {i}. ID: {challenge.id}")
                print(f"      Nome: {challenge.name or '(vuoto)'}")
                print(f"      Descrizione: {challenge.description[:50]}...")
                print(f"      Image path: {challenge.image_path or '(vuoto)'}")
                print(f"      Image filename: {challenge.image_filename or '(vuoto)'}")

                # Verifica se il file esiste
                if challenge.image_path:
                    expected_path = f"/Users/paolo/My Drive/Programming/Python/tornei-biliardo/static{challenge.image_path}"
                    file_exists = os.path.exists(expected_path)
                    print(f"      File exists: {file_exists} ({expected_path})")

                if challenge.image_filename:
                    expected_file = os.path.join(upload_dir, challenge.image_filename)
                    file_exists = os.path.exists(expected_file)
                    print(f"      Filename exists: {file_exists} ({expected_file})")

            print(f"\n💡 Suggerimenti:")
            print(
                f"   1. Se image_path esiste ma file non c'è: rimuovere image_path dal database"
            )
            print(
                f"   2. Se image_filename esiste ma file non c'è: rimuovere image_path dal database"
            )
            print(f"   3. Creare immagini di test nella directory uploads/challenges/")

            # Rimuovi path immagini rotte
            print(f"\n🧹 Pulizia challenge con immagini rotte...")
            fixed_count = 0
            for challenge in challenges:
                if challenge.image_path:
                    expected_path = f"/Users/paolo/My Drive/Programming/Python/tornei-biliardo/static{challenge.image_path}"
                    if not os.path.exists(expected_path):
                        print(
                            f"   Rimosso image_path rotto per challenge {challenge.id}"
                        )
                        challenge.image_path = None
                        fixed_count += 1

            if fixed_count > 0:
                from models import db

                db.session.commit()
                print(f"   ✅ Rimossi {fixed_count} path immagini rotte")
            else:
                print(f"   ✅ Nessun path immagine rotto trovato")

        except Exception as e:
            print(f"❌ Errore: {e}")


if __name__ == "__main__":
    debug_challenge_images()
