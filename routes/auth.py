# routes/auth.py - Route di autenticazione
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Pagina di login"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('main.dashboard'))
        else:
            flash('Username o password errati.')
    
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Pagina di registrazione"""
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        phone = request.form.get('phone', '')
        
        if User.query.filter_by(username=username).first():
            flash('Username già esistente.')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email già registrata.')
            return render_template('register.html')
        
        user = User(
            username=username,
            email=email,
            phone=phone
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        flash('Registrazione completata!')
        return redirect(url_for('main.dashboard'))
    
    return render_template('register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """Logout utente"""
    logout_user()
    return redirect(url_for('main.index'))