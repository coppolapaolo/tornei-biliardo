"""
Temporary file containing all non-user models
This will be broken down in subsequent phases
"""
from datetime import datetime
from models.base import db


class Classification(db.Model):
    """Classifica generale del torneo"""

    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(
        db.Integer, db.ForeignKey("tournament.id"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    position = db.Column(db.Integer)
    total_matches_won = db.Column(db.Integer, default=0)
    total_point_difference = db.Column(db.Integer, default=0)
    provas_played = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<Classification {self.user_id} -> {self.position}>"


class Playoff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(
        db.Integer, db.ForeignKey("tournament.id"), nullable=False
    )
    category = db.Column(db.String(20), nullable=False)  # elite, academy
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    qualified_position = db.Column(db.Integer)  # posizione che dava diritto
    confirmation_status = db.Column(
        db.String(20), default="pending"
    )  # pending, confirmed, declined
    confirmed_at = db.Column(db.DateTime)

    def __repr__(self):
        return f"<Playoff {self.user_id} ({self.category})>"


class PlayerEncounter(db.Model):
    """Tracking degli incontri tra giocatori per anti-reincontro"""

    __tablename__ = "player_encounter"

    id = db.Column(db.Integer, primary_key=True)
    player1_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    prova_id = db.Column(db.Integer, db.ForeignKey("prova.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    player1 = db.relationship("User", foreign_keys=[player1_id])
    player2 = db.relationship("User", foreign_keys=[player2_id])
    prova = db.relationship("Prova")

    # Constraint: evita duplicati
    __table_args__ = (
        db.UniqueConstraint(
            "player1_id", "player2_id", "prova_id", name="unique_player_encounter"
        ),
    )

    @staticmethod
    def have_played_together(player1_id, player2_id, prova_id):
        """Verifica se due giocatori si sono già incontrati in questa prova"""
        # Cerca in entrambe le direzioni
        encounter = PlayerEncounter.query.filter(
            db.or_(
                db.and_(
                    PlayerEncounter.player1_id == player1_id,
                    PlayerEncounter.player2_id == player2_id,
                ),
                db.and_(
                    PlayerEncounter.player1_id == player2_id,
                    PlayerEncounter.player2_id == player1_id,
                ),
            ),
            PlayerEncounter.prova_id == prova_id,
        ).first()
        return encounter is not None

    @staticmethod
    def record_encounter(player1_id, player2_id, prova_id, round_number):
        """Registra un incontro tra due giocatori"""
        # Assicurati che player1_id < player2_id per consistenza
        if player1_id > player2_id:
            player1_id, player2_id = player2_id, player1_id

        encounter = PlayerEncounter(
            player1_id=player1_id,
            player2_id=player2_id,
            prova_id=prova_id,
            round_number=round_number,
        )
        db.session.add(encounter)
        db.session.commit()
        return encounter

    def __repr__(self):
        return (
            f"<PlayerEncounter {self.player1_id} vs {self.player2_id} "
            f"(Round {self.round_number})>"
        )


class RoundClassification(db.Model):
    """Classifiche dinamiche dopo ogni turno per algoritmo Amalfi"""

    __tablename__ = "round_classification"

    id = db.Column(db.Integer, primary_key=True)
    prova_id = db.Column(db.Integer, db.ForeignKey("prova.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Dati classifica
    position = db.Column(db.Integer, nullable=False)
    matches_won = db.Column(db.Integer, default=0)
    rack_difference = db.Column(db.Integer, default=0)  # rack_vinti - rack_persi
    previous_position = db.Column(db.Integer)  # posizione turno precedente

    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relations
    prova = db.relationship("Prova")
    user = db.relationship("User")

    # Constraint: una sola voce per giocatore per turno
    __table_args__ = (
        db.UniqueConstraint(
            "prova_id", "round_number", "user_id", name="unique_round_classification"
        ),
    )

    @staticmethod
    def calculate_classification_after_round(prova_id, round_number):
        """Calcola la classifica dopo un turno"""
        from match.models import Match

        # Ottieni tutti i match completati fino a questo turno
        completed_matches = Match.query.filter(
            Match.prova_id == prova_id,
            Match.round_number <= round_number,
            Match.status == "completed",
            Match.is_bye.is_(False),
        ).all()

        # Calcola statistiche per ogni giocatore
        player_stats = {}
        for match in completed_matches:
            # Aggiorna statistiche player1
            if match.player1_id not in player_stats:
                player_stats[match.player1_id] = {
                    "matches_won": 0,
                    "total_racks_won": 0,
                    "total_racks_lost": 0,
                }
            if match.winner_id == match.player1_id:
                player_stats[match.player1_id]["matches_won"] += 1
            player_stats[match.player1_id]["total_racks_won"] += match.player1_score
            player_stats[match.player1_id]["total_racks_lost"] += match.player2_score

            # Aggiorna statistiche player2
            if match.player2_id not in player_stats:
                player_stats[match.player2_id] = {
                    "matches_won": 0,
                    "total_racks_won": 0,
                    "total_racks_lost": 0,
                }
            if match.winner_id == match.player2_id:
                player_stats[match.player2_id]["matches_won"] += 1
            player_stats[match.player2_id]["total_racks_won"] += match.player2_score
            player_stats[match.player2_id]["total_racks_lost"] += match.player1_score

        # Calcola rack_difference per ogni giocatore
        for player_id, stats in player_stats.items():
            stats["rack_difference"] = (
                stats["total_racks_won"] - stats["total_racks_lost"]
            )

        # Ordina per vittorie (decrescente) e poi per rack_difference (decrescente)
        sorted_players = sorted(
            player_stats.items(),
            key=lambda x: (x[1]["matches_won"], x[1]["rack_difference"]),
            reverse=True,
        )

        # Salva o aggiorna le classifiche
        for position, (player_id, stats) in enumerate(sorted_players, 1):
            # Ottieni la posizione precedente se esiste
            previous_classification = RoundClassification.query.filter_by(
                prova_id=prova_id,
                round_number=round_number - 1,
                user_id=player_id,
            ).first()
            previous_position = (
                previous_classification.position if previous_classification else None
            )

            # Crea o aggiorna la classifica
            classification = RoundClassification.query.filter_by(
                prova_id=prova_id,
                round_number=round_number,
                user_id=player_id,
            ).first()

            if classification:
                # Aggiorna esistente
                classification.position = position
                classification.matches_won = stats["matches_won"]
                classification.rack_difference = stats["rack_difference"]
                classification.previous_position = previous_position
            else:
                # Crea nuova
                classification = RoundClassification(
                    prova_id=prova_id,
                    round_number=round_number,
                    user_id=player_id,
                    position=position,
                    matches_won=stats["matches_won"],
                    rack_difference=stats["rack_difference"],
                    previous_position=previous_position,
                )
                db.session.add(classification)

        db.session.commit()
        return sorted_players

    def __repr__(self):
        return (
            f"<RoundClassification {self.user_id} -> {self.position} "
            f"(Round {self.round_number})>"
        )
