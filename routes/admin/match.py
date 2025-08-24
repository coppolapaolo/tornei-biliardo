# routes/admin/match.py
"""Match and rack management blueprint for admin interface."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required

from models import (
    db,
    Match,
    Rack,
)
from utils import (
    match_manager_required,
    rack_manager_required,
)
from models.match.services import MatchService, RackService, MatchResultService
from models.status_enum import MatchStatus

# Match management blueprint
match_bp = Blueprint("match", __name__)


@match_bp.route("/<int:match_id>")
@login_required
@match_manager_required
def match_detail(match_id):
    """Dettaglio partita per admin"""
    match = Match.query.get_or_404(match_id)
    racks = Rack.query.filter_by(match_id=match_id).order_by(Rack.rack_number).all()

    return render_template("match_detail.html", match=match, racks=racks)


@match_bp.route("/<int:match_id>/add_rack", methods=["POST"])
@login_required
@match_manager_required
def add_rack_result(match_id):
    """Aggiungi risultato rack (admin)"""
    match = Match.query.get_or_404(match_id)
    winner_id = int(request.form["winner_id"])

    # Trova il prossimo numero rack
    last_rack = (
        Rack.query.filter_by(match_id=match_id)
        .order_by(Rack.rack_number.desc())
        .first()
    )
    next_rack_number = (last_rack.rack_number + 1) if last_rack else 1

    # Crea il rack tramite il service (reporter = admin; validazione admin attiva)
    RackService.add_rack_result(
        match_id=match.id,
        rack_number=next_rack_number,
        winner_id=winner_id,
        reported_by_id=1,  # Admin user ID
        validated_by_admin=True,  # Admin validation immediate
    )

    # Aggiorna punteggio match
    if winner_id == match.player1_id:
        match.player1_score += 1
    else:
        match.player2_score += 1

    # Se il match è finito, imposta il vincitore tramite il service dedicato
    if match.prova.is_match_finished(match.player1_score, match.player2_score):
        final_winner_id = (
            match.player1_id
            if match.player1_score > match.player2_score
            else match.player2_id
        )
        MatchResultService.submit_result(match.id, final_winner_id)

    # Persisti l'aggiornamento dei punteggi (il rack è già stato committato dal service)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "status": match.status,
        }
    )


@match_bp.route("/<int:match_id>/set_result", methods=["POST"])
@login_required
@match_manager_required
def set_match_result_direct(match_id):
    """Imposta risultato completo di una partita (admin)"""
    match = Match.query.get_or_404(match_id)

    if match.is_bye:
        flash("Non puoi modificare una partita bye!")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))

    try:
        player1_score = int(request.form["player1_score"])
        player2_score = int(request.form["player2_score"])

        # Validazione punteggi
        if player1_score < 0 or player2_score < 0:
            flash("I punteggi non possono essere negativi!")
            return redirect(url_for("admin.match.match_detail", match_id=match_id))

        # Verifica che il risultato sia valido secondo le regole della prova
        total_racks = player1_score + player2_score

        if match.prova.best_of:
            # Al meglio di: uno dei due deve aver raggiunto la soglia
            winning_score = match.prova.get_winning_score()
            if max(player1_score, player2_score) < winning_score:
                flash(
                    f'Nel "al meglio di {match.prova.distance}", uno dei '
                    f"giocatori deve raggiungere {winning_score} punti!"
                )
                return redirect(url_for("admin.match.match_detail", match_id=match_id))
        else:
            # Esatto numero: la somma deve essere esattamente la distanza
            if total_racks != match.prova.distance:
                flash(
                    f'Nel "{match.prova.distance} rack esatti", '
                    f"la somma deve essere esattamente {match.prova.distance}!"
                )
                return redirect(url_for("admin.match.match_detail", match_id=match_id))

        # Determina il vincitore
        if player1_score > player2_score:
            winner_id = match.player1_id
        elif player2_score > player1_score:
            winner_id = match.player2_id
        else:
            flash("Non può esserci un pareggio!")
            return redirect(url_for("admin.match.match_detail", match_id=match_id))

        # Elimina tutti i rack esistenti per questa partita
        existing_racks = Rack.query.filter_by(match_id=match_id).all()
        for rack in existing_racks:
            db.session.delete(rack)

        # Crea i nuovi rack basati sul risultato
        rack_number = 1

        # Crea rack per player1
        for i in range(player1_score):
            RackService.add_rack_result(
                match_id, rack_number, match.player1_id, 1, validated_by_admin=True
            )
            rack_number += 1

        # Crea rack per player2
        for i in range(player2_score):
            RackService.add_rack_result(
                match_id, rack_number, match.player2_id, 1, validated_by_admin=True
            )
            rack_number += 1

        # Aggiorna il match
        match.player1_score = player1_score
        match.player2_score = player2_score
        match.winner_id = winner_id
        MatchService.to_completed(match.id)

        flash("Risultato impostato con successo!")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))

    except ValueError:
        flash("Errore: inserisci numeri validi per i punteggi!")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))
    except Exception as e:
        flash(f"Errore durante l'impostazione del risultato: {str(e)}")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))


@match_bp.route("/<int:match_id>/reset", methods=["POST"])
@login_required
@match_manager_required
def reset_match(match_id):
    """Reset completo di una partita (admin)"""
    match = Match.query.get_or_404(match_id)

    if match.is_bye:
        flash("Non puoi resettare una partita bye!")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))

    try:
        # Elimina tutti i rack
        existing_racks = Rack.query.filter_by(match_id=match_id).all()
        for rack in existing_racks:
            db.session.delete(rack)

        # Reset match
        match.player1_score = 0
        match.player2_score = 0
        match.winner_id = None
        MatchService.reset_to_pending(match.id, clear_validation=True)

        db.session.commit()

        flash("Partita resettata con successo!")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))

    except Exception as e:
        flash(f"Errore durante il reset: {str(e)}")
        return redirect(url_for("admin.match.match_detail", match_id=match_id))


# ============ GESTIONE RACK ADMIN ============


@match_bp.route("/rack/<int:rack_id>/remove", methods=["POST"])
@login_required
@rack_manager_required
def remove_rack_admin(rack_id):
    """Rimuovi un rack (admin)"""
    rack = Rack.query.get_or_404(rack_id)
    match = rack.match

    try:
        # Salva il vincitore per aggiornare il punteggio
        winner_id = rack.winner_id

        # Rimuovi il rack
        db.session.delete(rack)

        # Aggiorna il punteggio del match
        if winner_id == match.player1_id:
            match.player1_score = max(0, match.player1_score - 1)
        else:
            match.player2_score = max(0, match.player2_score - 1)

        # Se il match era completato e ora non ha più i punti per essere vinto,
        # rimettilo in playing
        if match.status == MatchStatus.COMPLETED.value:
            if match.prova.best_of:
                winning_score = match.prova.get_winning_score()
                if max(match.player1_score, match.player2_score) < winning_score:
                    MatchService.to_playing(match.id)
                    match.winner_id = None
            else:  # esatto numero
                if (match.player1_score + match.player2_score) < match.prova.distance:
                    MatchService.to_playing(match.id)
                    match.winner_id = None

        db.session.commit()

        return jsonify(
            {
                "success": True,
                "message": "Rack rimosso (Admin)",
                "player1_score": match.player1_score,
                "player2_score": match.player2_score,
                "status": match.status,
            }
        )

    except Exception as e:
        return jsonify({"error": f"Errore durante la rimozione: {str(e)}"}), 500


@match_bp.route("/rack/<int:rack_id>/validate", methods=["POST"])
@login_required
@rack_manager_required
def validate_rack_admin(rack_id):
    """Valida un rack (admin)"""
    rack = Rack.query.get_or_404(rack_id)

    try:
        # Valida il rack
        rack.validated_by_admin = True
        rack.confirmed_by_player = (
            True  # Automaticamente confermato se validato dall'admin
        )

        db.session.commit()

        return jsonify(
            {"success": True, "message": "Rack validato dall'amministratore"}
        )

    except Exception as e:
        return jsonify({"error": f"Errore durante la validazione: {str(e)}"}), 500