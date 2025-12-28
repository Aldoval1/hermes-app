import os
import random
import string
import requests  # --- DISCORD INTEGRATION: Necesario para notificaciones
from datetime import datetime, timedelta, date
from flask import render_template, flash, redirect, url_for, request, current_app, jsonify, make_response
from app import db
from app.forms import (
    LoginForm, RegistrationForm, OfficialLoginForm, OfficialRegistrationForm,
    SearchUserForm, CriminalRecordForm, TrafficFineForm, CommentForm,
    TransferForm, LoanForm, LoanRepayForm, SavingsForm, CardCustomizationForm,
    LotteryTicketForm, AdjustBalanceForm, GovFundAdjustForm, SalaryForm, AppointmentForm,
    CreateLeaderForm
)
from app.models import (
    User, Comment, TrafficFine, License, CriminalRecord,
    CriminalRecordSubjectPhoto, CriminalRecordEvidencePhoto,
    BankAccount, BankTransaction, BankLoan, BankSavings,
    Lottery, LotteryTicket, GovernmentFund, PayrollRequest, PayrollItem,
    Appointment
)
from flask_login import current_user, login_user, logout_user, login_required
from flask import Blueprint
from werkzeug.utils import secure_filename
from sqlalchemy import or_
from fpdf import FPDF
import io

bp = Blueprint('main', __name__)

# --- Configuración de Licencias ---
LICENSE_TYPES = {
    'piloto': {'name': 'Licencia de Piloto', 'price': 10000},
    'funcionamiento': {'name': 'Licencia de Funcionamiento', 'price': 4000},
    'alcohol_tabaco': {'name': 'Licencia para Venta de Alcohol y Tabaco', 'price': 3000},
    'drogas_farmacas': {'name': 'Licencia para Venta de Drogas Fármacas', 'price': 2500},
    'reparacion_vehiculos': {'name': 'Licencia para Reparación y Renovación de Vehículos', 'price': 3500},
    'especiales': {'name': 'Licencias Especiales', 'price': 3000},
    'stripping': {'name': 'Licencia de Stripping', 'price': 3000}
}

# --- Helper Functions ---

# --- DISCORD INTEGRATION START ---
def notify_discord_bot(user, message):
    """
    Envía una notificación al bot de Discord si el usuario tiene su cuenta vinculada.
    """
    if not user.discord_id:
        return
    
    # Asegúrate de tener esta variable en Railway en el proyecto de la WEB
    bot_url = os.environ.get('BOT_URL')
    
    if not bot_url:
        print("ADVERTENCIA: Variable 'BOT_URL' no configurada en la Web.")
        return

    try:
        payload = {
            'discord_id': user.discord_id,
            'message': message
        }
        # Timeout corto para no bloquear la web
        requests.post(f"{bot_url}/notify", json=payload, timeout=2)
    except Exception as e:
        print(f"Error enviando notificación a Discord: {e}")
# --- DISCORD INTEGRATION END ---

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
            base_date = loan.last_penalty_check if loan.last_penalty_check else loan.due_date
            diff = datetime.utcnow() - base_date
            if diff.days >= 2:
                intervals = diff.days // 2
                penalty_amount = (loan.amount_due * 0.01) * intervals

                loan.amount_due += penalty_amount
                account.balance -= penalty_amount
                loan.last_penalty_check = datetime.utcnow()

                trans = BankTransaction(
                    account_id=account.id,
                    type='loan_fee',
                    amount=penalty_amount,
                    description=f'Cargo por mora ({intervals * 1}%)'
                )
                db.session.add(trans)
                db.session.commit()
                
                # --- DISCORD NOTIFICATION ---
                notify_discord_bot(account.owner, f"⚠️ **Cargo por Mora**\nSe ha aplicado una penalización de ${penalty_amount:,.2f} a tu préstamo vencido.")

def get_lottery_state():
    """Ensure lottery record exists and handle daily draw."""
    lottery = Lottery.query.first()
    if not lottery:
        lottery = Lottery(current_jackpot=50000.0, last_run_date=datetime.utcnow().date())
        db.session.add(lottery)
        db.session.commit()

    today = datetime.utcnow().date()
    if today > lottery.last_run_date:
        winning_number = ''.join(random.choices(string.digits, k=5))

        # Draw for tickets bought on the last_run_date (yesterday/previous active day)
        winning_tickets = LotteryTicket.query.filter_by(date=lottery.last_run_date, numbers=winning_number).all()

        if winning_tickets:
            prize_per_winner = lottery.current_jackpot / len(winning_tickets)
            for ticket in winning_tickets:
                winner_acc = ticket.owner.bank_account
                if winner_acc:
                    winner_acc.balance += prize_per_winner
                    trans = BankTransaction(
                        account_id=winner_acc.id, type='lottery_win', amount=prize_per_winner,
                        description=f'Premio Lotería (Núm: {winning_number})'
                    )
                    db.session.add(trans)
                    # --- DISCORD NOTIFICATION ---
                    notify_discord_bot(ticket.owner, f"🎉 **¡GANASTE LA LOTERÍA!**\nTu número {winning_number} ha sido premiado con ${prize_per_winner:,.2f}.")
            lottery.current_jackpot = 50000.0

        lottery.last_run_date = today
        db.session.commit()

    return lottery

def get_gov_fund():
    fund = GovernmentFund.query.first()
    if not fund:
        fund = GovernmentFund(balance=1000000.0)
        db.session.add(fund)
        db.session.commit()
    return fund

# --- API ROUTES FOR DISCORD BOT (NEW) ---

@bp.route('/api/check_citizen/<dni>', methods=['GET'])
def check_citizen_api(dni):
    """El bot consulta esta ruta para verificar si un DNI existe."""
    user = User.query.filter_by(dni=dni).first()
    if user:
        return jsonify({
            'found': True,
            'first_name': user.first_name,
            'last_name': user.last_name
        })
    return jsonify({'found': False}), 404

@bp.route('/api/link_discord', methods=['POST'])
def link_discord_api():
    """El bot llama a esta ruta para vincular un DNI con un ID de Discord."""
    data = request.get_json()
    dni = data.get('dni')
    discord_id = data.get('discord_id')
    
    user = User.query.filter_by(dni=dni).first()
    if user:
        user.discord_id = str(discord_id)
        db.session.commit()
        # Notificar éxito
        notify_discord_bot(user, f"✅ **Cuenta Vinculada**\nBienvenido, {user.first_name}. Ahora recibirás notificaciones aquí.")
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Usuario no encontrado'}), 404

# --- Main Routes ---

@bp.route('/', methods=['GET', 'POST'])
def index():
    if current_user.is_authenticated:
        if current_user.badge_id:
             return redirect(url_for('main.official_dashboard'))
        return render_template('citizen_dashboard.html')

    form = LoginForm()
    if form.validate_on_submit():
        # Citizen login: Ensure we don't pick up an official account (which has a badge_id)
        user = User.query.filter_by(dni=form.dni.data, badge_id=None).first()
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
        # Check if citizen account exists
        user_exist = User.query.filter_by(dni=form.dni.data, badge_id=None).first()
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

# --- Licenses Routes ---

@bp.route('/licenses')
@login_required
def licenses():
    if current_user.badge_id:
        return redirect(url_for('main.official_dashboard'))

    # Active licenses
    active_licenses = [
        l for l in current_user.licenses
        if l.status == 'Activa' and (l.expiration_date is None or l.expiration_date >= datetime.utcnow().date())
    ]

    # Calculate days remaining for display
    now = datetime.utcnow().date()
    for l in active_licenses:
        if l.expiration_date:
            l.days_remaining = (l.expiration_date - now).days
        else:
            l.days_remaining = 'N/A'

    return render_template('licenses.html', license_types=LICENSE_TYPES, active_licenses=active_licenses)

@bp.route('/licenses/buy/<type_key>', methods=['POST'])
@login_required
def buy_license(type_key):
    if type_key not in LICENSE_TYPES:
        flash('Tipo de licencia inválido.')
        return redirect(url_for('main.licenses'))

    license_info = LICENSE_TYPES[type_key]
    price = license_info['price']
    account = current_user.bank_account

    if not account:
        flash('Necesitas una cuenta bancaria para comprar licencias.')
        return redirect(url_for('main.licenses'))

    if account.balance < price:
        flash('Fondos insuficientes.')
        return redirect(url_for('main.licenses'))

    # Check if already has valid license of this type
    existing = License.query.filter_by(
        user_id=current_user.id,
        type=license_info['name'],
        status='Activa'
    ).first()

    if existing and existing.expiration_date and existing.expiration_date >= datetime.utcnow().date():
         flash('Ya tienes esta licencia activa.')
         return redirect(url_for('main.licenses'))

    # Deduct Money
    account.balance -= price

    # Add to Government Income (Optional tracking, user said "Net Benefits" needs to be tracked)
    # We will assume GovernmentFund tracks the "State Reserve" or "Net Income"
    fund = get_gov_fund()
    fund.balance += price

    # Create Transaction
    trans = BankTransaction(
        account_id=account.id,
        type='license_buy',
        amount=price,
        description=f'Compra: {license_info["name"]}'
    )

    # Create License
    expiration = datetime.utcnow().date() + timedelta(days=30)
    new_license = License(
        type=license_info['name'],
        status='Activa',
        expiration_date=expiration,
        user_id=current_user.id
    )

    db.session.add(trans)
    db.session.add(new_license)
    db.session.commit()

    # --- DISCORD NOTIFICATION ---
    notify_discord_bot(current_user, f"📄 **Licencia Adquirida**\nHas comprado la {license_info['name']} por ${price:,.2f}.\nVence en 30 días.")

    flash(f'Has comprado la {license_info["name"]} por ${price}.')
    return redirect(url_for('main.licenses'))

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

    # Add money to Gov Fund (assuming fines go to gov?)
    fund = get_gov_fund()
    fund.balance += fine.amount

    db.session.commit()
    
    # --- DISCORD NOTIFICATION ---
    notify_discord_bot(current_user, f"✅ **Multa Pagada**\nHas pagado exitosamente la multa de ${fine.amount:,.2f} por: {fine.reason}.")

    flash(f'Multa de ${fine.amount} pagada con éxito.')
    return redirect(url_for('main.my_fines'))

# --- Appointments Routes ---

@bp.route('/appointments')
@login_required
def appointments():
    if current_user.badge_id:
        return redirect(url_for('main.official_dashboard'))

    officials = User.query.filter_by(department='Gobierno', official_status='Aprobado').all()
    form = AppointmentForm()

    return render_template('appointments.html', officials=officials, form=form)

@bp.route('/appointments/book/<int:official_id>', methods=['POST'])
@login_required
def book_appointment(official_id):
    form = AppointmentForm()
    if form.validate_on_submit():
        official = User.query.get_or_404(official_id)
        if official.department != 'Gobierno':
            flash('Solo puedes solicitar citas con funcionarios del Gobierno.')
            return redirect(url_for('main.appointments'))

        combined_dt = datetime.combine(form.date.data, form.time.data)

        appt = Appointment(
            citizen_id=current_user.id,
            official_id=official.id,
            date=combined_dt,
            reason=form.description.data,
            status='Pending'
        )
        db.session.add(appt)
        db.session.commit()
        
        # --- DISCORD NOTIFICATIONS ---
        # Al ciudadano
        notify_discord_bot(current_user, f"📅 **Cita Solicitada**\nTu cita con el oficial {official.last_name} ha sido registrada para el {combined_dt}.")
        # Al oficial
        notify_discord_bot(official, f"📅 **Nueva Cita Recibida**\nEl ciudadano {current_user.first_name} {current_user.last_name} solicita cita para el {combined_dt}.\nMotivo: {form.description.data}")
        
        flash('Cita solicitada con éxito.')
    else:
        flash('Error al solicitar la cita. Revisa los datos.')

    return redirect(url_for('main.appointments'))

# --- My Documents Routes ---

@bp.route('/my_documents')
@login_required
def my_documents():
    if current_user.badge_id:
        return redirect(url_for('main.official_dashboard'))

    # Calculate account age
    if current_user.created_at:
        account_age = (datetime.utcnow() - current_user.created_at).days
    else:
        account_age = 0

    return render_template('my_documents.html', account_age=account_age)

@bp.route('/my_documents/download_criminal_record')
@login_required
def download_criminal_record():
    records = current_user.criminal_records

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Reporte de Antecedentes Penales", ln=True, align='C')
    pdf.ln(10)

    # User Info
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 8, txt=f"Ciudadano: {current_user.first_name} {current_user.last_name}", ln=True)
    pdf.cell(200, 8, txt=f"DNI: {current_user.dni}", ln=True)
    pdf.cell(200, 8, txt=f"Fecha de Emisión: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}", ln=True)
    pdf.ln(10)

    if not records:
        pdf.cell(200, 10, txt="No se encontraron antecedentes penales.", ln=True)
    else:
        for record in records:
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(200, 8, txt=f"Delito: {record.crime} (CP: {record.penal_code})", ln=True)
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 6, txt=f"Fecha: {record.date.strftime('%d/%m/%Y')}", ln=True)
            pdf.multi_cell(0, 6, txt=f"Informe: {record.report_text}")

            # Images
            # Note: FPDF image requires file path.
            if record.subject_photos:
                pdf.ln(5)
                pdf.cell(200, 6, txt="Fotos del Sujeto:", ln=True)
                x_start = 10
                for photo in record.subject_photos:
                    img_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename)
                    if os.path.exists(img_path):
                        # Simple layout: add image, maybe new page if big.
                        # Scaling image to width 50
                        pdf.image(img_path, x=x_start, y=pdf.get_y(), w=50)
                        x_start += 55
                        if x_start > 150: # Wrap row
                            x_start = 10
                            pdf.ln(55) # Approx height of image + gap
                pdf.ln(60) # Space after image row

            if record.evidence_photos:
                pdf.ln(5)
                pdf.cell(200, 6, txt="Evidencia:", ln=True)
                x_start = 10
                for photo in record.evidence_photos:
                    img_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo.filename)
                    if os.path.exists(img_path):
                        pdf.image(img_path, x=x_start, y=pdf.get_y(), w=50)
                        x_start += 55
                        if x_start > 150:
                            x_start = 10
                            pdf.ln(55)
                pdf.ln(60)

            pdf.ln(10)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(10)

    # fpdf2 output() returns bytes (if dest='S') or bytearray. No need to encode.
    pdf_bytes = pdf.output()
    response = make_response(bytes(pdf_bytes))
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=antecedentes_{current_user.dni}.pdf'
    return response

# --- Banking Routes ---

@bp.route('/banking')
@login_required
def banking_dashboard():
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
    check_loan_penalties(account)

    transfer_form = TransferForm()
    loan_form = LoanForm()
    repay_form = LoanRepayForm()
    savings_form = SavingsForm()
    card_form = CardCustomizationForm()

    active_loan = BankLoan.query.filter_by(account_id=account.id, status='Active').first()

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

    for t in transactions:
        t.is_positive = t.type in ['transfer_in', 'loan_received', 'savings_withdrawal', 'interest', 'lottery_win', 'salary', 'government_adjustment_add']

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
            account.balance -= amount
            target_acc.balance += amount

            trans_out = BankTransaction(
                account_id=account.id, type='transfer_out', amount=amount,
                related_account=target_acc.account_number,
                description=f'Transferencia a {target_acc.owner.first_name}'
            )
            trans_in = BankTransaction(
                account_id=target_acc.id, type='transfer_in', amount=amount,
                related_account=account.account_number,
                description=f'Transferencia de {account.owner.first_name}'
            )

            db.session.add(trans_out)
            db.session.add(trans_in)
            db.session.commit()
            
            # --- DISCORD NOTIFICATIONS ---
            notify_discord_bot(current_user, f"💸 **Transferencia Enviada**\nHas enviado ${amount:,.2f} a {target_acc.owner.first_name} {target_acc.owner.last_name}.")
            notify_discord_bot(target_acc.owner, f"💸 **Transferencia Recibida**\nHas recibido ${amount:,.2f} de {account.owner.first_name} {account.owner.last_name}.")
            
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
            # Grant loan from Government Fund? Prompt says "se pondra o se retirara el dinero usado para prestamos" from Gov Fund.
            # Does fund have enough? Assuming Gov Fund can go negative or has plenty.
            # Let's say it can handle it.
            fund = get_gov_fund()
            fund.balance -= 5500

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
            
            # --- DISCORD NOTIFICATION ---
            notify_discord_bot(current_user, f"💰 **Préstamo Aprobado**\nHas recibido $5,500.00. Deberás pagar $6,000.00 en 14 días.")
            
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
                pay_amount = loan.amount_due
                loan.amount_due = 0
                loan.status = 'Paid'
                flash('¡Préstamo pagado en su totalidad!')
            else:
                pay_amount = amount
                loan.amount_due -= amount
                flash(f'Pago parcial de ${amount} realizado.')

            account.balance -= pay_amount
            trans = BankTransaction(
                account_id=account.id, type='loan_payment', amount=pay_amount,
                description='Pago de Préstamo'
            )

            # Repayment goes back to Gov Fund
            fund = get_gov_fund()
            fund.balance += pay_amount

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

        db.session.commit()
        flash('Diseño de tarjeta actualizado.')
    return redirect(url_for('main.banking_dashboard'))

# --- Lottery Routes ---

@bp.route('/lottery', methods=['GET', 'POST'])
@login_required
def lottery():
    lottery = get_lottery_state()
    form = LotteryTicketForm()

    today = datetime.utcnow().date()
    my_tickets = LotteryTicket.query.filter_by(user_id=current_user.id, date=today).all()

    return render_template('lottery.html', lottery=lottery, form=form, my_tickets=my_tickets)

@bp.route('/lottery/buy', methods=['POST'])
@login_required
def buy_lottery_ticket():
    lottery = get_lottery_state()
    form = LotteryTicketForm()
    account = current_user.bank_account

    if not account:
        flash('Necesitas una cuenta bancaria para jugar.')
        return redirect(url_for('main.lottery'))

    if form.validate_on_submit():
        if account.balance < 500:
            flash('Fondos insuficientes.')
        else:
            account.balance -= 500
            lottery.current_jackpot += 250

            # Add remaining 250 to Government Fund
            fund = get_gov_fund()
            fund.balance += 250

            ticket = LotteryTicket(
                user_id=current_user.id,
                numbers=form.numbers.data,
                date=datetime.utcnow().date()
            )

            trans = BankTransaction(
                account_id=account.id, type='lottery_ticket', amount=500,
                description=f'Ticket Lotería: {form.numbers.data}'
            )

            db.session.add(ticket)
            db.session.add(trans)
            db.session.commit()
            flash(f'Ticket {form.numbers.data} comprado con éxito.')

    return redirect(url_for('main.lottery'))

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
        # Find Citizen Account
        citizen = User.query.filter_by(dni=form.dni.data, badge_id=None).first()
        if not citizen:
            flash('Debes estar registrado como ciudadano primero (DNI no encontrado).')
            return redirect(url_for('main.official_register'))

        if not citizen.check_password(form.password.data):
             flash('Contraseña incorrecta. Usa tu contraseña de ciudadano.')
             return redirect(url_for('main.official_register'))

        if User.query.filter_by(badge_id=form.badge_id.data).first():
            flash('Esa Placa ID ya está registrada.')
            return redirect(url_for('main.official_register'))

        # Check account number validity and ownership (Citizen must own it)
        if not citizen.bank_account or citizen.bank_account.account_number != form.account_number.data:
            flash('El número de cuenta bancaria no coincide con tu cuenta personal.')
            return redirect(url_for('main.official_register'))

        photo_file = form.photo.data
        photo_filename = secure_filename(photo_file.filename)

        if not os.path.exists(current_app.config['UPLOAD_FOLDER']):
            os.makedirs(current_app.config['UPLOAD_FOLDER'])

        photo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], photo_filename)
        photo_file.save(photo_path)

        # Create separate Official User
        user = User(
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            dni=form.dni.data, # Shared DNI
            badge_id=form.badge_id.data,
            department=form.department.data,
            selfie_filename=photo_filename,
            official_status='Pendiente',
            official_rank='Miembro',
            salary_account_number=form.account_number.data # Link for payroll
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
    # If Government Leader (Admin), show ALL pending users, or at least help debug.
    # The requirement says: "A base 'Admin' account (DNI 000, Pass 000) for 'Gobierno' is needed to approve leaders."
    # So the Admin (Gobierno) needs to see pending users of ANY department who might be leaders?
    # Or just all pending users. Let's show all pending users for Governo Admin.

    if current_user.department == 'Gobierno' and current_user.official_rank == 'Lider':
         pending_users = User.query.filter_by(official_status='Pendiente').all()
    elif current_user.official_rank == 'Lider':
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

# --- Government Dashboard & Payroll ---

@bp.route('/government/dashboard')
@login_required
def government_dashboard():
    if current_user.department != 'Gobierno':
        return redirect(url_for('main.official_dashboard'))

    fund = get_gov_fund()
    pending_payrolls = PayrollRequest.query.filter_by(status='Pending').order_by(PayrollRequest.created_at.desc()).all()
    fund_form = GovFundAdjustForm()
    create_leader_form = CreateLeaderForm()

    # --- Financial Stats Calculation ---

    # 1. Total User Money
    # We sum all bank balances.
    # Note: Using db.session.query for efficiency if possible, or python sum.
    # Python sum for simplicity given scale.
    all_accounts = BankAccount.query.all()
    total_user_money = sum(acc.balance for acc in all_accounts)

    # 2. Total Debt
    all_loans = BankLoan.query.filter_by(status='Active').all()
    total_debt = sum(loan.amount_due for loan in all_loans)

    # 3. Expenses (Salaries) & Benefits (Income)
    # We look at BankTransactions.
    # Income Types (for state): 'fine_payment', 'license_buy', 'loan_fee' (maybe?), 'loan_payment' (interest part? or principal? Principal goes back to fund).
    # Expense Types (for state): 'salary', 'loan_received' (money leaving fund).

    # Let's define:
    # Income = Fines + Licenses + Taxes (if any)
    # Expenses = Salaries

    # We query ALL time or just current period? Prompt implies "breakdown of how money is organized... expenses... net benefits".
    # Usually "Net Benefit" implies a P&L (Profit & Loss) over time or total. I'll use total historical sum.

    income_transactions = BankTransaction.query.filter(
        BankTransaction.type.in_(['fine_payment', 'license_buy'])
    ).all()
    total_income = sum(t.amount for t in income_transactions)

    expense_transactions = BankTransaction.query.filter_by(type='salary').all()
    total_expenses = sum(t.amount for t in expense_transactions)

    net_benefits = total_income - total_expenses

    stats = {
        'total_user_money': total_user_money,
        'total_debt': total_debt,
        'total_expenses': total_expenses,
        'net_benefits': net_benefits
    }

    return render_template('government_dashboard.html', fund=fund, pending_payrolls=pending_payrolls,
                           fund_form=fund_form, create_leader_form=create_leader_form, stats=stats)

@bp.route('/government/create_leader', methods=['POST'])
@login_required
def government_create_leader():
    if current_user.department != 'Gobierno':
        return redirect(url_for('main.official_dashboard'))

    form = CreateLeaderForm()
    if form.validate_on_submit():
        citizen = User.query.filter_by(dni=form.dni.data, badge_id=None).first()
        if not citizen:
            flash('El ciudadano no existe (DNI no encontrado). Debe registrarse primero.')
            return redirect(url_for('main.government_dashboard'))

        if User.query.filter_by(badge_id=form.badge_id.data).first():
            flash('Esa Placa ID ya está registrada.')
            return redirect(url_for('main.government_dashboard'))

        # Bank Account Check and Ownership
        if not citizen.bank_account or citizen.bank_account.account_number != form.account_number.data:
            flash('El número de cuenta bancaria no coincide con el del ciudadano.')
            return redirect(url_for('main.government_dashboard'))

        # Create separate Official User
        user = User(
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            dni=form.dni.data,
            badge_id=form.badge_id.data,
            department=form.department.data,
            official_status='Aprobado',
            official_rank='Lider',
            selfie_filename='default.jpg', # Default
            dni_photo_filename='default.jpg',
            salary_account_number=form.account_number.data
        )
        user.set_password(form.password.data)

        db.session.add(user)
        db.session.commit()

        flash(f'Líder de {form.department.data} creado con éxito.')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error en {getattr(form, field).label.text}: {error}")

    return redirect(url_for('main.government_dashboard'))

@bp.route('/government/balance/update', methods=['POST'])
@login_required
def government_balance_update():
    if current_user.department != 'Gobierno':
        return redirect(url_for('main.official_dashboard'))

    form = GovFundAdjustForm()
    if form.validate_on_submit():
        fund = get_gov_fund()
        if form.operation.data == 'add':
            fund.balance += form.amount.data
            flash(f'Se añadieron ${form.amount.data} al fondo.')
        else:
            fund.balance -= form.amount.data
            flash(f'Se retiraron ${form.amount.data} del fondo.')
        db.session.commit()
    return redirect(url_for('main.government_dashboard'))

@bp.route('/government/payroll/action/<int:req_id>/<action>', methods=['POST'])
@login_required
def government_payroll_action(req_id, action):
    if current_user.department != 'Gobierno':
        return redirect(url_for('main.official_dashboard'))

    req = PayrollRequest.query.get_or_404(req_id)
    if req.status != 'Pending':
        flash('Esta solicitud ya fue procesada.')
        return redirect(url_for('main.government_dashboard'))

    if action == 'approve':
        fund = get_gov_fund()
        # Removed insufficient funds check as requested.
        # Government fund balance is now treated as a reserve/tracker, not a hard limit for salaries.

        # We assume salary payments come from the "State" (Minted or Debt), but we still track it.
        # If user wants to "desglosar" (breakdown) expenses, we should still deduct it from the fund
        # to keep the "Reserva Estatal" accurate if it represents the treasury.
        # BUT the prompt said "En vez de descontar dinero ... quiero que se desglose".
        # This implies: Do NOT deduct from the balance number that is displayed as "Total Money".
        # However, we have a "Reserva Estatal / Tesoro (Editable)" in the new dashboard.
        # If I don't deduct, where does the money come from? Thin air (Inflation).
        # And the "Gastos Totales" stat tracks it.
        # So I will NOT deduct from `fund.balance`.

        # fund.balance -= req.total_amount  <-- REMOVED

        # Distribute
        count = 0
        for item in req.items:
            user = item.user
            if user:
                target_acc = None
                if user.salary_account_number:
                    target_acc = BankAccount.query.filter_by(account_number=user.salary_account_number).first()
                elif user.bank_account:
                    target_acc = user.bank_account

                if target_acc:
                    target_acc.balance += item.amount
                    trans = BankTransaction(
                        account_id=target_acc.id,
                        type='salary',
                        amount=item.amount,
                        description=f'Nómina {req.department} ({req.created_at.strftime("%d/%m")})'
                    )
                    db.session.add(trans)
                    # --- DISCORD NOTIFICATION ---
                    notify_discord_bot(target_acc.owner, f"💰 **Nómina Recibida**\nHas recibido tu sueldo de ${item.amount:,.2f} correspondiente al departamento {req.department}.")
                    count += 1

        req.status = 'Approved'
        db.session.commit()
        flash(f'Nómina aprobada. Se pagó a {count} empleados. Total: ${req.total_amount}')

    elif action == 'reject':
        req.status = 'Rejected'
        db.session.commit()
        flash('Nómina rechazada.')

    return redirect(url_for('main.government_dashboard'))

@bp.route('/official/salaries')
@login_required
def official_salaries():
    if not current_user.badge_id or current_user.official_rank != 'Lider':
        return redirect(url_for('main.official_dashboard'))

    members = User.query.filter_by(department=current_user.department, official_status='Aprobado').all()
    salary_form = SalaryForm()

    return render_template('manage_salaries.html', members=members, salary_form=salary_form)

@bp.route('/official/salaries/update/<int:user_id>', methods=['POST'])
@login_required
def update_salary(user_id):
    if not current_user.badge_id or current_user.official_rank != 'Lider':
        return redirect(url_for('main.official_dashboard'))

    target_user = User.query.get_or_404(user_id)
    if target_user.department != current_user.department:
        flash('No puedes editar este usuario.')
        return redirect(url_for('main.official_salaries'))

    form = SalaryForm()
    if form.validate_on_submit():
        target_user.salary = form.salary.data
        db.session.commit()
        flash(f'Sueldo de {target_user.first_name} actualizado a ${target_user.salary}.')

    return redirect(url_for('main.official_salaries'))

@bp.route('/official/payroll/submit', methods=['POST'])
@login_required
def submit_payroll():
    if not current_user.badge_id or current_user.official_rank != 'Lider':
        return redirect(url_for('main.official_dashboard'))

    members = User.query.filter_by(department=current_user.department, official_status='Aprobado').all()
    total = sum(m.salary for m in members if m.salary and m.salary > 0)

    if total <= 0:
        flash('El total de la nómina es 0. Asigna sueldos primero.')
        return redirect(url_for('main.official_salaries'))

    req = PayrollRequest(
        department=current_user.department,
        total_amount=total
    )
    db.session.add(req)
    db.session.commit() # Commit to get ID

    for m in members:
        if m.salary and m.salary > 0:
            item = PayrollItem(
                request_id=req.id,
                user_id=m.id,
                amount=m.salary
            )
            db.session.add(item)

    db.session.commit()
    flash(f'Nómina enviada para aprobación del Gobierno. Total: ${total}')
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

    # Permissions
    # PD, Sheriff, SABES, Gobierno can edit/add/view
    can_edit_reports = current_user.department in ['Policia', 'Sheriff', 'SABES', 'Gobierno'] # Can add comments/fines
    # Note: Gov can add fines too per prompt "a diferencia de PD ... pueda ser posible poder poner multas"

    can_adjust_balance = current_user.department == 'Gobierno'

    # Forms
    comment_form = CommentForm()
    fine_form = TrafficFineForm()
    criminal_form = CriminalRecordForm()
    adjust_balance_form = AdjustBalanceForm()

    return render_template('citizen_profile.html', citizen=citizen,
                           can_edit=can_edit_reports,
                           can_adjust_balance=can_adjust_balance,
                           comment_form=comment_form, fine_form=fine_form,
                           criminal_form=criminal_form, adjust_balance_form=adjust_balance_form)

@bp.route('/official/citizen/<int:user_id>/add_comment', methods=['POST'])
@login_required
def add_comment(user_id):
    if not current_user.badge_id:
        return redirect(url_for('main.index'))

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
    else:
        flash('Error al agregar comentario.')

    return redirect(url_for('main.citizen_profile', user_id=user_id))

@bp.route('/official/citizen/<int:user_id>/add_traffic_fine', methods=['POST'])
@login_required
def add_traffic_fine(user_id):
    if not current_user.badge_id:
        return redirect(url_for('main.index'))

    form = TrafficFineForm()
    citizen = User.query.get_or_404(user_id)
    if form.validate_on_submit():
        fine = TrafficFine(
            amount=form.amount.data,
            reason=form.reason.data,
            user_id=user_id,
            author_id=current_user.id
        )
        db.session.add(fine)
        db.session.commit()
        
        # --- DISCORD NOTIFICATION ---
        notify_discord_bot(citizen, f"🚨 **Has recibido una Multa**\nMonto: ${form.amount.data:,.2f}\nRazón: {form.reason.data}\nAgente: {current_user.first_name} {current_user.last_name} ({current_user.department})")

        flash(f'Multa de ${form.amount.data} impuesta.')
    else:
        flash('Error al imponer multa.')

    return redirect(url_for('main.citizen_profile', user_id=user_id))

@bp.route('/official/citizen/<int:user_id>/add_criminal_record', methods=['POST'])
@login_required
def add_criminal_record(user_id):
    if not current_user.badge_id:
        return redirect(url_for('main.index'))

    # Check permissions (maybe restrict to Police/Sheriff/Gobierno/SABES)
    if current_user.department not in ['Policia', 'Sheriff', 'SABES', 'Gobierno']:
         flash('No tienes permiso para agregar antecedentes penales.')
         return redirect(url_for('main.citizen_profile', user_id=user_id))
    
    citizen = User.query.get_or_404(user_id)
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
        db.session.commit() # Commit to get ID for photos

        # Handle Photos
        if not os.path.exists(current_app.config['UPLOAD_FOLDER']):
            os.makedirs(current_app.config['UPLOAD_FOLDER'])

        for file in form.subject_photos.data:
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                photo = CriminalRecordSubjectPhoto(filename=filename, record_id=record.id)
                db.session.add(photo)

        for file in form.evidence_photos.data:
             if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                photo = CriminalRecordEvidencePhoto(filename=filename, record_id=record.id)
                db.session.add(photo)

        db.session.commit()
        
        # --- DISCORD NOTIFICATION ---
        notify_discord_bot(citizen, f"⚖️ **Nuevo Antecedente Penal**\nDelito: {form.crime.data}\nCódigo Penal: {form.penal_code.data}\nAgente: {current_user.first_name} {current_user.last_name}")
        
        flash('Antecedente penal registrado.')
    else:
        flash('Error en el formulario.')

    return redirect(url_for('main.citizen_profile', user_id=user_id))

@bp.route('/official/citizen/<int:user_id>/adjust_balance', methods=['POST'])
@login_required
def adjust_citizen_balance(user_id):
    if current_user.department != 'Gobierno':
        flash('No tienes permiso.')
        return redirect(url_for('main.citizen_profile', user_id=user_id))

    citizen = User.query.get_or_404(user_id)
    if not citizen.bank_account:
        flash('El ciudadano no tiene cuenta bancaria.')
        return redirect(url_for('main.citizen_profile', user_id=user_id))

    form = AdjustBalanceForm()
    if form.validate_on_submit():
        amount = form.amount.data
        if form.operation.data == 'add':
            citizen.bank_account.balance += amount
            desc_type = 'government_adjustment_add'
            flash(f'Se añadieron ${amount} a la cuenta.')
            # --- DISCORD NOTIFICATION ---
            notify_discord_bot(citizen, f"📈 **Ajuste de Saldo (Gobierno)**\nSe han AÑADIDO ${amount:,.2f} a tu cuenta.\nRazón: {form.reason.data}")
        else:
            citizen.bank_account.balance -= amount
            desc_type = 'government_adjustment_sub'
            flash(f'Se quitaron ${amount} de la cuenta.')
            # --- DISCORD NOTIFICATION ---
            notify_discord_bot(citizen, f"📉 **Ajuste de Saldo (Gobierno)**\nSe han RETIRADO ${amount:,.2f} de tu cuenta.\nRazón: {form.reason.data}")

        trans = BankTransaction(
            account_id=citizen.bank_account.id,
            type=desc_type,
            amount=amount,
            description=f'Ajuste Gobierno: {form.reason.data}'
        )
        db.session.add(trans)
        db.session.commit()

    return redirect(url_for('main.citizen_profile', user_id=user_id))
