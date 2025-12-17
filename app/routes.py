import os
import random
import string
from datetime import datetime, timedelta
from flask import render_template, flash, redirect, url_for, request, current_app, jsonify
from app import db
from app.forms import (
    LoginForm, RegistrationForm, OfficialLoginForm, OfficialRegistrationForm,
    SearchUserForm, CriminalRecordForm, TrafficFineForm, CommentForm,
    TransferForm, LoanForm, LoanRepayForm, SavingsForm, CardCustomizationForm
)
from app.models import (
    User, Comment, TrafficFine, License, CriminalRecord,
    CriminalRecordSubjectPhoto, CriminalRecordEvidencePhoto,
    BankAccount, BankTransaction, BankLoan, BankSavings
)
from flask_login import current_user, login_user, logout_user, login_required
from flask import Blueprint
from werkzeug.utils import secure_filename
from sqlalchemy import or_

bp = Blueprint('main', __name__)

# --- Helper Functions ---
def generate_account_number():
    while True:
        # Generate 10 digits
        acc_num = ''.join(random.choices(string.digits, k=10))
        if not BankAccount.query.filter_by(account_number=acc_num).first():
            return acc_num

def check_loan_penalties(account):
    """Check for overdue loans and apply penalties."""
    loans = BankLoan.query.filter_by(account_id=account.id, status='Active').all()
    for loan in loans:
        if datetime.utcnow() > loan.due_date:
            # Check if penalty needs to be applied (every 2 days)
            # Logic: (current_time - due_date).days // 2
            # But we need to make sure we don't apply it multiple times for the same period.
            # Use last_penalty_check or due_date as base.
            base_date = loan.last_penalty_check if loan.last_penalty_check else loan.due_date

            # Days since last check/due date
            diff = datetime.utcnow() - base_date
            if diff.days >= 2:
                # Apply 1% penalty for every 2-day period elapsed
                intervals = diff.days // 2
                penalty_amount = (loan.amount_due * 0.01) * intervals

                loan.amount_due += penalty_amount
                # Deduct from account balance (can go negative)
                account.balance -= penalty_amount
                loan.last_penalty_check = datetime.utcnow()

                # Record transaction
                trans = BankTransaction(
                    account_id=account.id,
                    type='loan_fee',
                    amount=penalty_amount,
                    description=f'Cargo por mora ({intervals * 1}%)'
                )
                db.session.add(trans)
                db.session.commit()

# --- Main Routes ---

@bp.route('/', methods=['GET', 'POST'])
def index():
    if current_user.is_authenticated:
        if current_user.badge_id:
             return redirect(url_for('main.official_dashboard'))
        return render_template('citizen_dashboard.html')

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(dni=form.dni.data).first()
        if user is None or not user.check_password(form.password.data):
             flash('DNI o contraseña inválidos')
             return redirect(url_for('main.index'))

        login_user(user, remember=form.remember_me.data)
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

# --- Citizen Fines Routes ---

@bp.route('/my_fines')
@login_required
def my_fines():
    if current_user.badge_id:
        return redirect(url_for('main.official_dashboard'))

    fines = TrafficFine.query.filter_by(user_id=current_user.id, status='Pendiente').all()
    history = TrafficFine.query.filter_by(user_id=current_user.id, status='Pagada').all()

    return render_template('my_fines.html', fines=fines, history=history)

@bp.route('/pay_fine/<int:fine_id>', methods=['POST'])
@login_required
def pay_fine(fine_id):
    fine = TrafficFine.query.get_or_404(fine_id)

    if fine.user_id != current_user.id:
        flash('No tienes permiso para pagar esta multa.')
        return redirect(url_for('main.my_fines'))

    if fine.status != 'Pendiente':
        flash('Esta multa ya está pagada.')
        return redirect(url_for('main.my_fines'))

    account = current_user.bank_account
    if not account:
        flash('Necesitas una cuenta bancaria para pagar multas. Visita la Banca Estatal.')
        return redirect(url_for('main.my_fines'))

    if account.balance < fine.amount:
        flash('Fondos insuficientes en tu cuenta bancaria.')
        return redirect(url_for('main.my_fines'))

    # Process Payment
    account.balance -= fine.amount
    fine.status = 'Pagada'

    trans = BankTransaction(
        account_id=account.id, type='fine_payment', amount=fine.amount,
        description=f'Pago de Multa: {fine.reason}'
    )
    db.session.add(trans)
    db.session.commit()

    flash(f'Multa de ${fine.amount} pagada con éxito.')
    return redirect(url_for('main.my_fines'))

# --- Banking Routes ---

@bp.route('/banking')
@login_required
def banking_dashboard():
    # Check if user has bank account, if not create one
    if not current_user.bank_account:
        new_account = BankAccount(
            account_number=generate_account_number(),
            balance=0.0,
            user_id=current_user.id
        )
        db.session.add(new_account)
        db.session.commit()
        flash(f'¡Bienvenido a Banca Estatal! Tu cuenta ha sido creada: {new_account.account_number}')
        return redirect(url_for('main.banking_dashboard'))

    account = current_user.bank_account

    # Check loan penalties
    check_loan_penalties(account)

    # Prepare data for dashboard
    transfer_form = TransferForm()
    loan_form = LoanForm()
    repay_form = LoanRepayForm()
    savings_form = SavingsForm()
    card_form = CardCustomizationForm()

    active_loan = BankLoan.query.filter_by(account_id=account.id, status='Active').first()

    # Process Savings deposits for view (calculate status/can_withdraw)
    savings_deposits = []
    db_savings = BankSavings.query.filter_by(account_id=account.id, status='Active').order_by(BankSavings.deposit_date.desc()).all()
    for saving in db_savings:
        unlock_date = saving.deposit_date + timedelta(days=30)
        can_withdraw = datetime.utcnow() >= unlock_date
        savings_deposits.append({
            'id': saving.id,
            'amount': saving.amount,
            'unlock_date_str': unlock_date.strftime('%d/%m/%Y'),
            'can_withdraw': can_withdraw
        })

    transactions = BankTransaction.query.filter(
        (BankTransaction.account_id == account.id)
    ).order_by(BankTransaction.timestamp.desc()).all()

    # Add flag for positive/negative display (simplified logic)
    for t in transactions:
        t.is_positive = t.type in ['transfer_in', 'loan_received', 'savings_withdrawal', 'interest']

    return render_template('banking.html', account=account,
                           transfer_form=transfer_form, loan_form=loan_form,
                           repay_form=repay_form, savings_form=savings_form,
                           card_form=card_form, active_loan=active_loan,
                           savings_deposits=savings_deposits, transactions=transactions)

@bp.route('/banking/lookup/<account_number>')
@login_required
def banking_lookup(account_number):
    account = BankAccount.query.filter_by(account_number=account_number).first()
    if account:
        return jsonify({'name': f"{account.owner.first_name} {account.owner.last_name}"})
    return jsonify({'name': None})

@bp.route('/banking/transfer', methods=['POST'])
@login_required
def banking_transfer():
    form = TransferForm()
    account = current_user.bank_account
    if form.validate_on_submit():
        target_acc = BankAccount.query.filter_by(account_number=form.account_number.data).first()
        amount = form.amount.data

        if not target_acc:
            flash('La cuenta destino no existe.')
        elif target_acc.id == account.id:
            flash('No puedes transferirte a ti mismo.')
        elif account.balance < amount:
            flash('Fondos insuficientes.')
        else:
            # Execute Transfer
            account.balance -= amount
            target_acc.balance += amount

            # Record Outgoing
            trans_out = BankTransaction(
                account_id=account.id, type='transfer_out', amount=amount,
                related_account=target_acc.account_number,
                description=f'Transferencia a {target_acc.owner.first_name}'
            )
            # Record Incoming
            trans_in = BankTransaction(
                account_id=target_acc.id, type='transfer_in', amount=amount,
                related_account=account.account_number,
                description=f'Transferencia de {account.owner.first_name}'
            )

            db.session.add(trans_out)
            db.session.add(trans_in)
            db.session.commit()
            flash(f'Transferencia de ${amount} realizada con éxito.')

    return redirect(url_for('main.banking_dashboard'))

@bp.route('/banking/loan/apply', methods=['POST'])
@login_required
def banking_loan_apply():
    form = LoanForm()
    account = current_user.bank_account
    if form.validate_on_submit():
        if BankLoan.query.filter_by(account_id=account.id, status='Active').first():
            flash('Ya tienes un préstamo activo.')
        else:
            # Grant loan
            account.balance += 5500
            loan = BankLoan(
                account_id=account.id,
                amount_due=6000,
                due_date=datetime.utcnow() + timedelta(days=14)
            )
            trans = BankTransaction(
                account_id=account.id, type='loan_received', amount=5500,
                description='Préstamo Bancario'
            )
            db.session.add(loan)
            db.session.add(trans)
            db.session.commit()
            flash('Préstamo de $5500 recibido. A pagar $6000.')
    return redirect(url_for('main.banking_dashboard'))

@bp.route('/banking/loan/repay', methods=['POST'])
@login_required
def banking_loan_repay():
    form = LoanRepayForm()
    account = current_user.bank_account
    loan = BankLoan.query.filter_by(account_id=account.id, status='Active').first()

    if form.validate_on_submit() and loan:
        amount = form.amount.data
        if account.balance < amount:
            flash('Fondos insuficientes para pagar esa cantidad.')
        else:
            if amount >= loan.amount_due:
                # Full payment
                pay_amount = loan.amount_due
                loan.amount_due = 0
                loan.status = 'Paid'
                flash('¡Préstamo pagado en su totalidad!')
            else:
                # Partial payment
                pay_amount = amount
                loan.amount_due -= amount
                flash(f'Pago parcial de ${amount} realizado.')

            account.balance -= pay_amount
            trans = BankTransaction(
                account_id=account.id, type='loan_payment', amount=pay_amount,
                description='Pago de Préstamo'
            )
            db.session.add(trans)
            db.session.commit()

    return redirect(url_for('main.banking_dashboard'))

@bp.route('/banking/savings/deposit', methods=['POST'])
@login_required
def banking_savings_deposit():
    form = SavingsForm()
    account = current_user.bank_account
    if form.validate_on_submit():
        amount = form.amount.data
        if account.balance < amount:
            flash('Fondos insuficientes.')
        else:
            account.balance -= amount
            saving = BankSavings(
                account_id=account.id,
                amount=amount
            )
            trans = BankTransaction(
                account_id=account.id, type='savings_deposit', amount=amount,
                description='Depósito a Ahorros'
            )
            db.session.add(saving)
            db.session.add(trans)
            db.session.commit()
            flash(f'${amount} depositados en ahorros (Bloqueados por 30 días).')
    return redirect(url_for('main.banking_dashboard'))

@bp.route('/banking/savings/withdraw/<int:deposit_id>')
@login_required
def banking_savings_withdraw(deposit_id):
    account = current_user.bank_account
    saving = BankSavings.query.get_or_404(deposit_id)

    if saving.account_id != account.id or saving.status != 'Active':
        flash('Depósito no válido.')
        return redirect(url_for('main.banking_dashboard'))

    unlock_date = saving.deposit_date + timedelta(days=30)
    if datetime.utcnow() < unlock_date:
        flash('Este depósito aún está bloqueado.')
        return redirect(url_for('main.banking_dashboard'))

    # Withdraw with 4% interest
    total_amount = saving.amount * 1.04
    account.balance += total_amount
    saving.status = 'Withdrawn'

    trans = BankTransaction(
        account_id=account.id, type='savings_withdrawal', amount=total_amount,
        description='Retiro de Ahorros + Interés'
    )
    db.session.add(trans)
    db.session.commit()
    flash(f'Retiraste ${"%.2f" % total_amount} de tus ahorros.')

    return redirect(url_for('main.banking_dashboard'))

@bp.route('/banking/card/update', methods=['POST'])
@login_required
def banking_card_update():
    form = CardCustomizationForm()
    account = current_user.bank_account
    if form.validate_on_submit():
        account.card_style = form.style.data
        if form.style.data == 'custom':
            if form.custom_image.data:
                f = form.custom_image.data
                filename = secure_filename(f.filename)
                f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                account.custom_image = filename
            # If no new image, we keep the old one. If none existed, front end should handle it.

        db.session.commit()
        flash('Diseño de tarjeta actualizado.')
    return redirect(url_for('main.banking_dashboard'))

# --- Official Routes (Keeping previous ones) ---

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
            (User.badge_id == None) &
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

    # Permissions: SABES, Policia, Sheriff can add
    can_edit = current_user.department in ['Policia', 'Sheriff', 'SABES']

    # Forms
    comment_form = CommentForm()
    fine_form = TrafficFineForm()
    criminal_form = CriminalRecordForm()

    return render_template('citizen_profile.html', citizen=citizen, can_edit=can_edit,
                           comment_form=comment_form, fine_form=fine_form, criminal_form=criminal_form)

@bp.route('/official/citizen/<int:user_id>/add_comment', methods=['POST'])
@login_required
def add_comment(user_id):
    if not current_user.badge_id or current_user.department not in ['Policia', 'Sheriff', 'SABES']:
        flash('No tienes permiso para realizar esta acción.')
        return redirect(url_for('main.citizen_profile', user_id=user_id))

    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(
            content=form.content.data,
            user_id=user_id,
            author_id=current_user.id
        )
        db.session.add(comment)
        db.session.commit()
        flash('Comentario agregado.')

    return redirect(url_for('main.citizen_profile', user_id=user_id))

@bp.route('/official/citizen/<int:user_id>/add_fine', methods=['POST'])
@login_required
def add_traffic_fine(user_id):
    if not current_user.badge_id or current_user.department not in ['Policia', 'Sheriff', 'SABES']:
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
    if not current_user.badge_id or current_user.department not in ['Policia', 'Sheriff', 'SABES']:
        flash('No tienes permiso para realizar esta acción.')
        return redirect(url_for('main.citizen_profile', user_id=user_id))

    form = CriminalRecordForm()
    if form.validate_on_submit():
        record = CriminalRecord(
            date=form.date.data,
            crime=form.crime.data,
            penal_code=form.penal_code.data,
            report_text=form.report_text.data,
            user_id=user_id,
            author_id=current_user.id
        )
        db.session.add(record)
        db.session.commit()

        # Handle multiple photos
        if form.subject_photos.data:
            for f in form.subject_photos.data:
                if f and f.filename:
                    filename = secure_filename(f.filename)
                    f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                    photo = CriminalRecordSubjectPhoto(filename=filename, record_id=record.id)
                    db.session.add(photo)

        if form.evidence_photos.data:
             for f in form.evidence_photos.data:
                if f and f.filename:
                    filename = secure_filename(f.filename)
                    f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                    photo = CriminalRecordEvidencePhoto(filename=filename, record_id=record.id)
                    db.session.add(photo)

        db.session.commit()
        flash('Antecedente penal registrado.')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error en {field}: {error}")

    return redirect(url_for('main.citizen_profile', user_id=user_id))
