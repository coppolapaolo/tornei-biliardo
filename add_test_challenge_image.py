#!/usr/bin/env python3
"""
Aggiungi immagine di test a una challenge esistente
"""

import os
from PIL import Image, ImageDraw, ImageFont
from app import create_app


def create_test_image():
    """Crea un'immagine di test semplice"""
    print("🎨 Creazione immagine di test...")

    # Crea immagine 200x150 con colore di sfondo
    img = Image.new("RGB", (200, 150), color="#FF6B35")
    draw = ImageDraw.Draw(img)

    # Aggiungi testo
    try:
        # Prova con font di sistema
        font = ImageFont.load_default()
    except:
        font = None

    # Testo centrato
    text = "BREAK SHOT\nCHALLENGE"
    if font:
        # Calcola posizione centrata
        lines = text.split("\n")
        total_height = len(lines) * 20
        y = (150 - total_height) // 2

        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (200 - text_width) // 2
            draw.text((x, y + i * 20), line, fill="white", font=font)

    # Salva l'immagine
    upload_dir = "/Users/paolo/My Drive/Programming/Python/tornei-biliardo/static/uploads/challenges"
    os.makedirs(upload_dir, exist_ok=True)

    img_path = os.path.join(upload_dir, "break_shot_test.jpg")
    img.save(img_path, "JPEG")
    print(f"✅ Immagine creata: {img_path}")

    return "break_shot_test.jpg"


def update_challenge_with_image():
    print("📝 Aggiornamento challenge con immagine di test...")

    with create_app().app_context():
        from models import db
        from models.challenge.models import Challenge

        try:
            # Crea immagine di test
            filename = create_test_image()

            # Trova una challenge senza immagine
            challenge = Challenge.query.filter_by(name="Tiro da 8 pallini").first()
            if not challenge:
                challenge = Challenge.query.filter_by(is_active=True).first()

            if challenge:
                challenge.image_path = f"/uploads/challenges/{filename}"
                db.session.commit()

                print(f"✅ Challenge aggiornata: ID={challenge.id}")
                print(f"   Nome: {challenge.name or challenge.get_display_name()}")
                print(f"   Image path: {challenge.image_path}")
                print(f"   Image filename: {challenge.image_filename}")

            return True

        except Exception as e:
            print(f"❌ Errore: {e}")
            return False


if __name__ == "__main__":
    try:
        success = update_challenge_with_image()
        if success:
            print(f"\n🎉 Immagine di test aggiunta con successo!")
            print(f"🚀 Ora ricarica la pagina e dovresti vedere l'immagine!")
    except ImportError:
        print("❌ Pillow non installato. Installa con: pip install Pillow")
    except Exception as e:
        print(f"❌ Errore imprevisto: {e}")
