from flask import render_template, flash, redirect, url_for
from app import db
from app.forms import LoginForm
from app.models import User
from flask_login import current_user, login_user, logout_user
from flask import Blueprint

bp = Blueprint('main', __name__)

@bp.route('/', methods=['GET', 'POST'])
def index():
    # If the user is already authenticated, maybe we just show the form anyway
    # or a "Logged in" message? The prompt says "just do a simple login page".
    # I will stick to showing the login page at root.
    # But if I want to support login functionality, I should handle POST.

    # Actually, the user says "Delete all the content on this proyect and instead just do a simple login page".
    # I will make '/' the login page.

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(dni=form.dni.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('DNI o contraseña inválidos')
            return redirect(url_for('main.index'))
        login_user(user)
        # Redirect to same page or show success?
        # If the goal is "just a login page", maybe after login nothing happens or it says "Welcome".
        # For now I'll just flash success.
        flash('Inicio de sesión exitoso')
        return redirect(url_for('main.index'))

    return render_template('login.html', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))
