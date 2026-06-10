"""Ruota la ENCRYPTION_KEY dei dati PII cifrati (user.email, user.phone).

Decifra ogni valore con la chiave vecchia e lo ri-cifra con quella nuova,
operando sui valori raw del DB (bypassa il TypeDecorator EncryptedString,
che userebbe la chiave globale del processo).

Procedura consigliata in produzione (PythonAnywhere):

    # 0a. DISABILITA la web app (tab Web -> Disable): su PythonAnywhere il
    #     locking SQLite su NFS e' inaffidabile e due writer concorrenti
    #     (console + web app) possono corrompere il DB (incidente 2026-06-10).
    cd ~/mysite
    python scripts/backup_db.py                      # 0b. backup del DB!
    python scripts/rotate_encryption_key.py --generate   # 1. genera una chiave
    python scripts/rotate_encryption_key.py --new-key 'LA-CHIAVE'           # 2. dry-run
    python scripts/rotate_encryption_key.py --new-key 'LA-CHIAVE' --commit  # 3. applica
    # 4. aggiorna ENCRYPTION_KEY nel WSGI file con la chiave nuova
    # 5. riabilita la web app (Enable) e fai Reload dal tab Web
    # 6. d'ora in poi gli script da console che toccano PII vanno lanciati con
    #    ENCRYPTION_KEY='LA-CHIAVE' python scripts/...

Idempotente: i valori gia' cifrati con la chiave nuova vengono saltati, quindi
un'interruzione a meta' si recupera rilanciando lo stesso comando. I valori
che non si decifrano con nessuna delle due chiavi vengono segnalati e NON
toccati (exit code 1 per evidenziarli).
"""

import argparse
import base64
import os
import secrets
import sys
from typing import Any, Dict, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Chiave storica: il default con cui l'app ha sempre cifrato quando
# ENCRYPTION_KEY non era impostata (vedi utils/encryption.py).
HISTORICAL_DEFAULT_KEY = "default-development-key-change-in-production"

_PII_COLUMNS = ("email", "phone")


def _try_decrypt(cipher: Any, stored: str) -> Optional[str]:
    """Decifra un valore raw del DB; None se la chiave non e' quella giusta."""
    try:
        token = base64.urlsafe_b64decode(stored.encode())
        return cipher.decrypt(token).decode()
    except Exception:
        return None


def _encrypt(cipher: Any, plaintext: str) -> str:
    return base64.urlsafe_b64encode(cipher.encrypt(plaintext.encode())).decode()


def rotate_user_pii(
    session: Any, old_key: str, new_key: str, commit: bool
) -> Dict[str, Any]:
    """Ri-cifra user.email/user.phone da old_key a new_key sui valori raw.

    Ritorna un report: rotated, already_rotated, skipped_empty,
    undecryptable (lista di tuple (user_id, colonna), lasciate intatte).
    """
    from sqlalchemy import text

    from utils.encryption import derive_cipher

    old_cipher = derive_cipher(old_key)
    new_cipher = derive_cipher(new_key)

    report: Dict[str, Any] = {
        "rotated": 0,
        "already_rotated": 0,
        "skipped_empty": 0,
        "undecryptable": [],
    }

    # .all() volutamente: snapshot completo prima degli UPDATE. Iterare il
    # cursore in streaming mentre si scrive sulla stessa connessione SQLite
    # e' fragile, e la tabella user e' piccola (centinaia di righe).
    rows = session.execute(text('SELECT id, email, phone FROM "user"')).all()
    for row in rows:
        for column in _PII_COLUMNS:
            stored = getattr(row, column)
            if not stored:
                report["skipped_empty"] += 1
                continue
            if _try_decrypt(new_cipher, stored) is not None:
                report["already_rotated"] += 1
                continue
            plaintext = _try_decrypt(old_cipher, stored)
            if plaintext is None:
                report["undecryptable"].append((row.id, column))
                continue
            session.execute(
                text(f'UPDATE "user" SET {column} = :value WHERE id = :id'),
                {"value": _encrypt(new_cipher, plaintext), "id": row.id},
            )
            report["rotated"] += 1

    if commit:
        session.commit()
    else:
        session.rollback()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ruota la ENCRYPTION_KEY dei dati PII (user.email/phone)."
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Genera e stampa una chiave robusta, senza toccare il DB.",
    )
    parser.add_argument("--new-key", help="La nuova chiave di cifratura.")
    parser.add_argument(
        "--old-key",
        default=HISTORICAL_DEFAULT_KEY,
        help="Chiave attuale (default: la chiave storica di default).",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Applica le modifiche (default: dry-run).",
    )
    args = parser.parse_args()

    if args.generate:
        print(secrets.token_urlsafe(48))
        return 0

    if not args.new_key:
        parser.error("--new-key e' obbligatoria (oppure usa --generate)")
    if args.new_key == args.old_key:
        parser.error("--new-key deve essere diversa da --old-key")

    # L'import dell'app istanzia l'EncryptionManager globale: allinealo alla
    # chiave vecchia cosi' l'import non fallisce nemmeno con
    # FLASK_ENV=production nella shell.
    os.environ.setdefault("ENCRYPTION_KEY", args.old_key)

    from app import create_app  # noqa: E402
    from models import db  # noqa: E402

    app = create_app()
    with app.app_context():
        report = rotate_user_pii(db.session, args.old_key, args.new_key, args.commit)

    print("Rotazione chiave PII (user.email, user.phone)")
    print(f"  ri-cifrati:        {report['rotated']}")
    print(f"  gia' ruotati:      {report['already_rotated']}")
    print(f"  vuoti/NULL:        {report['skipped_empty']}")
    if report["undecryptable"]:
        print(f"  ❌ NON decifrabili ({len(report['undecryptable'])}), non toccati:")
        for user_id, column in report["undecryptable"]:
            print(f"     - user {user_id}, colonna {column}")
    if args.commit:
        print("  ✓ Modifiche committate.")
        print("  → Ora aggiorna ENCRYPTION_KEY nel WSGI file e fai Reload.")
    else:
        print("  ℹ️  DRY RUN: nessuna modifica salvata (usa --commit).")

    return 1 if report["undecryptable"] else 0


if __name__ == "__main__":
    sys.exit(main())
