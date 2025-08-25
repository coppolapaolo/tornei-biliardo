# routes/auth.py - Route di autenticazione
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from models.user.services import UserService
from models.user.models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Pagina di login"""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        # Use service layer for authentication
        user = UserService.authenticate_user(username, password)

        if user:
            login_user(user)
            return redirect(url_for("dashboard.dashboard"))
        else:
            flash("Username o password errati.")

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Pagina di registrazione"""
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        phone = request.form.get("phone", "")

        # Use service layer for user creation
        try:
            user = UserService.create_user(
                username=username,
                email=email,
                password=password,
                phone=phone if phone else None
            )
            
            login_user(user)
            flash("Registrazione completata!")
            return redirect(url_for("dashboard.dashboard"))
            
        except ValueError as e:
            flash(str(e))
            return render_template("register.html")

    return render_template("register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """Logout utente"""
    logout_user()
    return redirect(url_for("main.index"))