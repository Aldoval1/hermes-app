import os
from flask import render_template, flash, redirect, url_for, request, current_app
from app import db
from app.forms import LoginForm, RegistrationForm, OfficialLoginForm, OfficialRegistrationForm
from app.models import User
from flask_login import current_user, login_user, logout_user, login_required
from flask import Blueprint
from werkzeug.utils import secure_filename

bp = Blueprint('main', __name__)

@bp.route('/', methods=['GET', 'POST'])
def index():
    if current_user.is_authenticated:
        # Check if official
        if current_user.badge_id:
             return redirect(url_for('main.official_dashboard'))
        return render_template('login.html', form=LoginForm(), logged_in=True)

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(dni=form.dni.data).first()
        if user is None or not user.check_password(form.password.data):
             # Ensure this user is NOT an official trying to login here?
             # Or allow officials to login as citizens?
             # For simplicity, if they have badge_id, they should use official login?
             # But a user might have both?
             # Let's just check creds.
             flash('DNI o contraseña inválidos')
             return redirect(url_for('main.index'))

        # If user is official and tries to login here, it works but where do they go?
        # If they use DNI, they are logging in as citizen.
        login_user(user, remember=form.remember_me.data)
        flash('Inicio de sesión exitoso')
        return redirect(url_for('main.index'))

    return render_template('login.html', form=form, logged_in=False)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user_exist = User.query.filter_by(dni=form.dni.data).first()
        if user_exist:
            flash('Ese DNI ya está registrado.')
            return redirect(url_for('main.register'))

        # Save images
        selfie_file = form.selfie.data
        dni_photo_file = form.dni_photo.data

        selfie_filename = secure_filename(selfie_file.filename)
        dni_photo_filename = secure_filename(dni_photo_file.filename)

        if not os.path.exists(current_app.config['UPLOAD_FOLDER']):
            os.makedirs(current_app.config['UPLOAD_FOLDER'])

        selfie_path = os.path.join(current_app.config['UPLOAD_FOLDER'], selfie_filename)
        dni_photo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], dni_photo_filename)

        selfie_file.save(selfie_path)
        dni_photo_file.save(dni_photo_path)

        user = User(
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            dni=form.dni.data,
            selfie_filename=selfie_filename,
            dni_photo_filename=dni_photo_filename
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        flash('¡Cuenta creada con éxito! Ahora puedes iniciar sesión.')
        return redirect(url_for('main.index'))

    return render_template('register.html', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

# --- Official Routes ---

@bp.route('/official/login', methods=['GET', 'POST'])
def official_login():
    if current_user.is_authenticated:
        if current_user.badge_id:
             return redirect(url_for('main.official_dashboard'))
        return redirect(url_for('main.index'))

    form = OfficialLoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(badge_id=form.badge_id.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Placa ID o contraseña inválidos')
            return redirect(url_for('main.official_login'))

        if user.official_status != 'Aprobado':
             flash('Tu cuenta aún no ha sido aprobada por un líder.')
             return redirect(url_for('main.official_login'))

        login_user(user, remember=form.remember_me.data)
        return redirect(url_for('main.official_dashboard'))

    return render_template('official_login.html', form=form)

@bp.route('/official/register', methods=['GET', 'POST'])
def official_register():
    if current_user.is_authenticated:
        return redirect(url_for('main.official_dashboard'))

    form = OfficialRegistrationForm()
    if form.validate_on_submit():
        # Check uniqueness
        if User.query.filter_by(dni=form.dni.data).first():
            flash('Ese DNI ya está registrado.')
            return redirect(url_for('main.official_register'))
        if User.query.filter_by(badge_id=form.badge_id.data).first():
            flash('Esa Placa ID ya está registrada.')
            return redirect(url_for('main.official_register'))

        photo_file = form.photo.data
        photo_filename = secure_filename(photo_file.filename)

        if not os.path.exists(current_app.config['UPLOAD_FOLDER']):
            os.makedirs(current_app.config['UPLOAD_FOLDER'])

        photo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo_filename)
        photo_file.save(photo_path)

        user = User(
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            dni=form.dni.data,
            badge_id=form.badge_id.data,
            department=form.department.data,
            selfie_filename=photo_filename, # Reusing this field for official photo
            official_status='Pendiente',
            official_rank='Miembro'
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        flash('Solicitud enviada. Espera a que un líder apruebe tu cuenta.')
        return redirect(url_for('main.official_login'))

    return render_template('official_register.html', form=form)

@bp.route('/official/dashboard')
@login_required
def official_dashboard():
    if not current_user.badge_id:
        return redirect(url_for('main.index'))

    # Check if Leader
    if current_user.official_rank != 'Lider':
        return f"<h1>Panel de Funcionario</h1><p>Bienvenido, {current_user.first_name}. Tu rango es {current_user.official_rank}.</p><a href='{url_for('main.logout')}'>Salir</a>"

    # Fetch pending users for this department
    pending_users = User.query.filter_by(department=current_user.department, official_status='Pendiente').all()
    return render_template('official_dashboard.html', pending_users=pending_users)

@bp.route('/official/action/<int:user_id>/<action>', methods=['POST'])
@login_required
def official_action(user_id, action):
    if not current_user.badge_id or current_user.official_rank != 'Lider':
        return redirect(url_for('main.index'))

    target_user = User.query.get_or_404(user_id)

    # Verify department match
    if target_user.department != current_user.department:
        flash('No tienes permiso para gestionar este usuario.')
        return redirect(url_for('main.official_dashboard'))

    if action == 'approve':
        target_user.official_status = 'Aprobado'
        flash(f'Usuario {target_user.first_name} {target_user.last_name} aprobado.')
    elif action == 'deny':
        # target_user.official_status = 'Rechazado'
        # Or delete? "aceptar o denegar" usually implies rejecting.
        # If denied, maybe delete so they can try again or keep record?
        # I'll delete for now to keep it clean, or mark rejected.
        db.session.delete(target_user)
        flash(f'Usuario {target_user.first_name} {target_user.last_name} denegado y eliminado.')

    db.session.commit()
    return redirect(url_for('main.official_dashboard'))
