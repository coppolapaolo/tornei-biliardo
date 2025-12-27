from __future__ import annotations

"""
utils/reset_data.py — Dataset demo v2 (agosto 2025)
"""

from datetime import date, datetime, timedelta
from typing import Dict, List

from flask import has_app_context, current_app
from utils import create_admin_if_not_exists

from models import User
from models.base import db
from models.campionato.models import Campionato
from models.user.models import TournamentDirector
from models.user.services import UserService
from models.user.role_enum import UserRole
from models.competition.services import (
    GaraService,
    InscriptionService,
)


def reset_database_enhanced() -> Dict[str, object]:
    db.drop_all()
    db.create_all()
    return _reset_database_core()


def reset_database_enhanced_cli() -> None:
    if has_app_context():
        reset_database_enhanced()
        print("✅ Database reset (context esistente)")
        return
    from importlib import import_module

    app_module = import_module("app")
    app = app_module.create_app()
    with app.app_context():
        reset_database_enhanced()
        print("✅ Database reset (nuovo app_context)")


def _reset_database_core() -> Dict[str, object]:
    try:
        # Utenti: garantisci un admin per il seed.
        admin = create_admin_if_not_exists()
        if admin is None:
            cfg = current_app.config if has_app_context() else {}
            # In produzione pretendiamo le credenziali esplicite
            if cfg.get("ADMIN_PASSWORD_REQUIRED", False):
                raise RuntimeError(
                    "Variabili ADMIN_USERNAME/ADMIN_PASSWORD "
                    "richieste per il seed in produzione."
                )
            # Siamo in sviluppo: fallback locale sicuro per il SOLO seed
            username = (cfg.get("ADMIN_USERNAME") or "admin").strip()
            email = (cfg.get("ADMIN_EMAIL") or f"{username}@campionato.local").strip()
            password = (cfg.get("ADMIN_PASSWORD") or "admin123").strip()
            existing = (
                User.query.filter_by(role=UserRole.ADMIN.value)
                .filter(User.deleted_at.is_(None))
                .first()
            )
            admin = existing or UserService.create_user(
                username=username, email=email, password=password, role=UserRole.ADMIN.value
            )

        # Create the specific users requested: mario and pino
        mario = UserService.create_user(
            "mario", "mario@pippo.it", "mario123", role="player"
        )
        pino = UserService.create_user("pino", "pino@pippo.it", "pino123", role="player")

        maxdir = UserService.create_user(
            "max", "max@campionati.com", "123456", role="director"
        )
        paolodir = UserService.create_user(
            "paolo", "paolo@campionati.com", "123456", role="director"
        )
        players: List[User] = [mario, pino]
        for n in range(1, 21):
            uname = f"player{n:02d}"
            player = UserService.create_user(
                uname, f"{uname}@campionati.com", "123456", role="player"
            )
            players.append(player)

        # Campionati
        garetta = Campionato(name="La Garetta", campionato_type="Amalfi")
        mercoledi = Campionato(name="Mercoledì", campionato_type="Amalfi")
        db.session.add_all([garetta, mercoledi])
        db.session.flush()

        # Assegnazioni direttori (includere assigned_by_id per vincolo NOT NULL)
        links = [
            TournamentDirector(
                user_id=maxdir.id,
                entity_type="campionato",
                entity_id=garetta.id,
                assigned_by_id=admin.id,
            ),
            TournamentDirector(
                user_id=paolodir.id,
                entity_type="campionato",
                entity_id=garetta.id,
                assigned_by_id=admin.id,
            ),
            TournamentDirector(
                user_id=paolodir.id,
                entity_type="campionato",
                entity_id=mercoledi.id,
                assigned_by_id=admin.id,
            ),
        ]
        db.session.add_all(links)
        db.session.flush()

        # Gare
        today = date.today()
        gara_garetta = GaraService.create_gara(
            name="La Garetta #1",
            number=1,
            date=today + timedelta(days=7),
            discipline="9-ball",
            distance=5,
            campionato_id=garetta.id,
            director_id=paolodir.id,
        )
        gara_mercoledi = GaraService.create_gara(
            name="Mercoledì #1",
            number=1,
            date=today + timedelta(days=10),
            discipline="10-ball",
            distance=5,
            campionato_id=mercoledi.id,
            director_id=paolodir.id,
        )

        # Apertura iscrizioni + 8 iscritti su La Garetta
        GaraService.to_inscription(
            gara_garetta.id, datetime.utcnow(), datetime.utcnow() + timedelta(days=3)
        )
        for u in players[:8]:
            InscriptionService.inscribe_user(u.id, gara_garetta.id)

        # Competizione stand‑alone
        standalone = GaraService.create_gara(
            name="Salamopen",
            number=1,
            date=today + timedelta(days=3),
            discipline="8-ball",
            distance=5,
            campionato_id=None,
            director_id=maxdir.id,
        )

        db.session.commit()
        return {
            "admin": admin,
            "mario": mario,
            "pino": pino,
            "max": maxdir,
            "paolo": paolodir,
            "players": players,
            "campionato_garetta": garetta,
            "campionato_mercoledi": mercoledi,
            "gara_garetta": gara_garetta,
            "gara_mercoledi": gara_mercoledi,
            "gara_standalone": standalone,
        }
    except Exception as e:
        db.session.rollback()
        raise RuntimeError(f"Errore durante il reset del database: {str(e)}") from e


__all__ = ["reset_database_enhanced", "reset_database_enhanced_cli"]

if __name__ == "__main__":
    reset_database_enhanced_cli()
