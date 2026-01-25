# routes/admin/user.py - Add at end of file

@user_bp.route("/user/<int:user_id>/toggle_gamification_override", methods=["POST"])
@admin_required
def toggle_gamification_override(user_id):
    """Toggle gamification_override for a user (admin bypass)"""
    try:
        user = db.session.get(User, user_id)
        if not user:
            flash("Utente non trovato.", "error")
            return redirect(url_for("admin.user.users_list"))
        
        # Toggle the override
        user.gamification_override = not user.gamification_override
        db.session.commit()
        
        status = "attivato" if user.gamification_override else "disattivato"
        flash(f"Gamification Override {status} per {user.username}.", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "error")
    
    return redirect(url_for("admin.user.user_detail", user_id=user_id))
