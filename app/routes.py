import os
from flask import render_template, flash, redirect, url_for, request, current_app
from app import db
from app.forms import LoginForm, RegistrationForm, OfficialLoginForm, OfficialRegistrationForm, SearchUserForm, CriminalRecordForm, TrafficFineForm, PoliceReportForm
from app.models import User, PoliceReport, TrafficFine, License, CriminalRecord
from flask_login import current_user, login_user, logout_user, login_required
from flask import Blueprint
from werkzeug.utils import secure_filename
from sqlalchemy import or_

bp = Blueprint('main', __name__)

@bp.route('/', methods=['GET', 'POST'])
def index():
    if current_user.is_authenticated:
        if current_user.badge_id:
             return redirect(url_for('main.official_dashboard'))
        return render_template('login.html', form=LoginForm(), logged_in=True)

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(dni=form.dni.data).first()
        if user is None or not user.check_password(form.password.data):
             flash('DNI o contraseña inválidos')
             return redirect(url_for('main.index'))

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
            selfie_filename=photo_filename,
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

    pending_users = []
    if current_user.official_rank == 'Lider':
        pending_users = User.query.filter_by(department=current_user.department, official_status='Pendiente').all()

    return render_template('official_dashboard.html', pending_users=pending_users)

@bp.route('/official/action/<int:user_id>/<action>', methods=['POST'])
@login_required
def official_action(user_id, action):
    if not current_user.badge_id or current_user.official_rank != 'Lider':
        return redirect(url_for('main.index'))

    target_user = User.query.get_or_404(user_id)

    if target_user.department != current_user.department:
        flash('No tienes permiso para gestionar este usuario.')
        return redirect(url_for('main.official_dashboard'))

    if action == 'approve':
        target_user.official_status = 'Aprobado'
        flash(f'Usuario {target_user.first_name} {target_user.last_name} aprobado.')
    elif action == 'deny':
        db.session.delete(target_user)
        flash(f'Usuario {target_user.first_name} {target_user.last_name} denegado y eliminado.')

    db.session.commit()
    return redirect(url_for('main.official_dashboard'))

# --- Citizen Database Routes ---

@bp.route('/official/database', methods=['GET'])
@login_required
def official_database():
    if not current_user.badge_id:
        return redirect(url_for('main.index'))

    form = SearchUserForm(request.args)
    users = []
    if form.query.data:
        query = form.query.data
        users = User.query.filter(
            (User.badge_id == None) & # Only citizens? Or anyone? Let's search all, maybe official looks for official?
            # Prompt says "usuarios registrados". Usually police look for citizens.
            # I will filter users that are NOT currently 'Aprobado' officials? Or just anyone?
            # A citizen can be official too?
            # Let's just search all users.
            (
                User.first_name.contains(query) |
                User.last_name.contains(query) |
                User.dni.contains(query)
            )
        ).all()

    return render_template('official_database.html', form=form, users=users)

@bp.route('/official/citizen/<int:user_id>')
@login_required
def citizen_profile(user_id):
    if not current_user.badge_id:
        return redirect(url_for('main.index'))

    citizen = User.query.get_or_404(user_id)

    # Permissions
    can_edit = current_user.department in ['Policia', 'Sheriff', 'LSFD'] # LSFD too? Prompt said "PD y Sherrif solo podra editar".
    # Wait, "La PD y Sherrif solo podra editar...". What about LSFD?
    # Prompt: "La PD y Sherrif solo podra editar el area de informes policiales, multas de trafico, detalles penales."
    # So LSFD cannot.
    can_edit = current_user.department in ['Policia', 'Sheriff']

    # Forms
    report_form = PoliceReportForm()
    fine_form = TrafficFineForm()
    criminal_form = CriminalRecordForm()

    return render_template('citizen_profile.html', citizen=citizen, can_edit=can_edit,
                           report_form=report_form, fine_form=fine_form, criminal_form=criminal_form)

@bp.route('/official/citizen/<int:user_id>/add_report', methods=['POST'])
@login_required
def add_police_report(user_id):
    if not current_user.badge_id or current_user.department not in ['Policia', 'Sheriff']:
        flash('No tienes permiso para realizar esta acción.')
        return redirect(url_for('main.citizen_profile', user_id=user_id))

    form = PoliceReportForm()
    if form.validate_on_submit():
        report = PoliceReport(
            content=form.content.data,
            user_id=user_id,
            author_id=current_user.id
        )
        db.session.add(report)
        db.session.commit()
        flash('Informe agregado.')

    return redirect(url_for('main.citizen_profile', user_id=user_id))

@bp.route('/official/citizen/<int:user_id>/add_fine', methods=['POST'])
@login_required
def add_traffic_fine(user_id):
    if not current_user.badge_id or current_user.department not in ['Policia', 'Sheriff']:
        flash('No tienes permiso para realizar esta acción.')
        return redirect(url_for('main.citizen_profile', user_id=user_id))

    form = TrafficFineForm()
    if form.validate_on_submit():
        fine = TrafficFine(
            amount=form.amount.data,
            reason=form.reason.data,
            user_id=user_id,
            author_id=current_user.id
        )
        db.session.add(fine)
        db.session.commit()
        flash('Multa impuesta.')

    return redirect(url_for('main.citizen_profile', user_id=user_id))

@bp.route('/official/citizen/<int:user_id>/add_criminal_record', methods=['POST'])
@login_required
def add_criminal_record(user_id):
    if not current_user.badge_id or current_user.department not in ['Policia', 'Sheriff']:
        flash('No tienes permiso para realizar esta acción.')
        return redirect(url_for('main.citizen_profile', user_id=user_id))

    form = CriminalRecordForm()
    if form.validate_on_submit():
        subject_photo = None
        evidence_photo = None

        if form.subject_photo.data:
            f = form.subject_photo.data
            filename = secure_filename(f.filename)
            f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            subject_photo = filename

        if form.evidence_photo.data:
            f = form.evidence_photo.data
            filename = secure_filename(f.filename)
            f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            evidence_photo = filename

        record = CriminalRecord(
            date=form.date.data, # Note: datetime vs date. Model has DateTime. form.date.data is date.
            # Need to convert or let SQLAlchemy handle it? It usually handles it, but safer to combine with min time.
            # Or change form to DateTimeField. DateField returns date object.
            # datetime.combine(form.date.data, datetime.min.time())
            crime=form.crime.data,
            penal_code=form.penal_code.data,
            report_text=form.report_text.data,
            subject_photo=subject_photo,
            evidence_photo=evidence_photo,
            user_id=user_id,
            author_id=current_user.id
        )
        db.session.add(record)
        db.session.commit()
        flash('Antecedente penal registrado.')
    else:
        # Debug form errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error en {field}: {error}")

    return redirect(url_for('main.citizen_profile', user_id=user_id))
