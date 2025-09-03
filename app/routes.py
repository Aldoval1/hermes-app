import os
from flask import render_template, flash, redirect, url_for, session, request, current_app
from app import db
from app.forms import LoginForm, RegistrationForm, AddProductForm, EditProductForm
from app.models import User, Product, Order, OrderItem, SystemConfig
from flask_login import current_user, login_user, logout_user, login_required
from flask import Blueprint
from werkzeug.utils import secure_filename
from datetime import datetime

bp = Blueprint('main', __name__)

def get_cart_items():
    cart_item_details = {}
    cart = session.get('cart', {})
    for product_id, item_data in cart.items():
        product = Product.query.get(product_id)
        if product:
            cart_item_details[product_id] = {
                'product': product,
                'quantity': item_data['quantity']
            }
    return cart_item_details

# --- Rutas de Autenticación y Principales ---
@bp.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('main.login'))

    cart_items = get_cart_items()

    if current_user.role == 'cliente':
        products = Product.query.filter_by(status='aprobado').all()
        return render_template('cliente_dashboard.html', title='Inicio', products=products, cart_items=cart_items)
    elif current_user.role == 'vendedor':
        return redirect(url_for('main.vendedor_dashboard'))
    elif current_user.role == 'admin':
        return redirect(url_for('main.admin_dashboard'))
    
    return redirect(url_for('main.login'))

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data) or user.role != form.role.data:
            flash('Usuario, contraseña o rol inválidos')
            return redirect(url_for('main.login'))
        login_user(user, remember=True)
        return redirect(url_for('main.index'))
    return render_template('login.html', title='Iniciar Sesión', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.login'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user_exist = User.query.filter_by(username=form.username.data).first()
        if user_exist:
            flash('Ese nombre de usuario ya está en uso.')
            return redirect(url_for('main.register'))
        
        user = User(username=form.username.data, discord=form.discord.data, role=form.role.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('¡Te has registrado con éxito! Ahora puedes iniciar sesión.')
        return redirect(url_for('main.login'))
    return render_template('register.html', title='Registro', form=form)

# --- Rutas del Cliente ---

@bp.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    cart = session.get('cart', {})
    product = Product.query.get(product_id)
    if not product:
        flash('Producto no encontrado.', 'error')
        return redirect(url_for('main.index'))

    product_id_str = str(product_id)
    
    current_quantity = cart.get(product_id_str, {'quantity': 0})['quantity']
    
    if current_quantity + 1 > product.stock:
        flash(f'No puedes añadir más de "{product.name}". ¡No hay suficiente stock!', 'error')
        return redirect(url_for('main.index'))

    if product_id_str in cart:
        cart[product_id_str]['quantity'] += 1
    else:
        cart[product_id_str] = {'quantity': 1}
    
    session['cart'] = cart
    flash(f'¡"{product.name}" añadido al carrito!', 'success')
    return redirect(url_for('main.index'))

@bp.route('/update_cart/<string:product_id>', methods=['POST'])
@login_required
def update_cart(product_id):
    cart = session.get('cart', {})
    product_id_str = str(product_id)
    action = request.form.get('action')

    if product_id_str in cart:
        if action == 'add':
            product = Product.query.get(product_id)
            if product and cart[product_id_str]['quantity'] + 1 > product.stock:
                 flash(f'¡No hay más stock para "{product.name}"!', 'error')
            else:
                cart[product_id_str]['quantity'] += 1
        elif action == 'subtract':
            cart[product_id_str]['quantity'] -= 1
            if cart[product_id_str]['quantity'] <= 0:
                cart.pop(product_id_str)
    
    session['cart'] = cart
    return redirect(request.referrer or url_for('main.index'))

@bp.route('/product/<int:product_id>')
@login_required
def product(product_id):
    product = Product.query.get_or_404(product_id)
    cart_items = get_cart_items()
    return render_template('product.html', title=product.name, product=product, cart_items=cart_items)

@bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_items = get_cart_items()
    if not cart_items:
        flash("Tu carrito está vacío.", "error")
        return redirect(url_for('main.index'))

    total_price = 0
    for item in cart_items.values():
        total_price += item['product'].price * item['quantity']
    
    final_price = total_price * 1.1

    if request.method == 'POST':
        if current_user.balance < final_price:
            flash('¡Fondos insuficientes para completar la compra!', 'error')
            return redirect(url_for('main.checkout'))

        for item_id, item_data in cart_items.items():
            product_check = Product.query.get(item_id)
            if item_data['quantity'] > product_check.stock:
                flash(f'No hay suficiente stock para "{product_check.name}". La compra ha sido cancelada.', 'error')
                session.pop('cart', None)
                return redirect(url_for('main.index'))

        commission = total_price * 0.1
        current_user.balance -= final_price

        order = Order(
            total_price=final_price, 
            customer=current_user,
            keyword=request.form.get('keyword'),
            delivery_datetime=request.form.get('delivery_datetime'),
            delivery_location_x=request.form.get('location_x'),
            delivery_location_y=request.form.get('location_y'),
            extra_details=request.form.get('extra_details')
        )
        db.session.add(order)

        for item_id, item_data in cart_items.items():
            product = Product.query.get(item_id)
            seller = product.seller
            
            amount_to_seller = product.price * item_data['quantity']
            seller.balance += amount_to_seller
            product.stock -= item_data['quantity']
            
            order_item = OrderItem(
                order=order,
                product_id=product.id,
                quantity=item_data['quantity'],
                price_per_item=product.price
            )
            db.session.add(order_item)
        
        hermes_funds_config = SystemConfig.query.filter_by(key='hermes_funds').first()
        if not hermes_funds_config:
            hermes_funds_config = SystemConfig(key='hermes_funds', value=str(commission))
            db.session.add(hermes_funds_config)
        else:
            current_funds = float(hermes_funds_config.value)
            hermes_funds_config.value = str(current_funds + commission)

        db.session.commit()
        
        session.pop('cart', None)
        
        flash('¡Compra realizada con éxito! Tu pedido está siendo procesado.', 'success')
        return redirect(url_for('main.index'))

    return render_template('checkout.html', title='Finalizar Compra', cart_items=cart_items, final_price=final_price)

@bp.route('/my_orders')
@login_required
def my_orders():
    if current_user.role != 'cliente':
        return redirect(url_for('main.index'))
    
    orders = Order.query.filter_by(customer=current_user).order_by(Order.order_date.desc()).all()
    cart_items = get_cart_items()
    return render_template('my_orders.html', title='Mis Pedidos', orders=orders, cart_items=cart_items)

# --- Rutas del Vendedor ---

@bp.route('/vendedor/dashboard')
@login_required
def vendedor_dashboard():
    if current_user.role != 'vendedor':
        return redirect(url_for('main.index'))
    products = Product.query.filter_by(seller=current_user).order_by(Product.id.desc()).all()
    cart_items = get_cart_items()
    return render_template('vendedor_dashboard.html', title='Panel de Vendedor', products=products, cart_items=cart_items)

# --- NUEVA RUTA PARA "MIS VENTAS" ---
@bp.route('/my_sales')
@login_required
def my_sales():
    if current_user.role != 'vendedor':
        return redirect(url_for('main.index'))
    
    # Consulta para obtener los items de productos vendidos por el usuario actual
    sales = db.session.query(OrderItem).join(Product).filter(Product.user_id == current_user.id).order_by(OrderItem.id.desc()).all()
    
    cart_items = get_cart_items()
    return render_template('my_sales.html', title='Mis Ventas', sales=sales, cart_items=cart_items)

@bp.route('/vendedor/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if current_user.role != 'vendedor':
        return redirect(url_for('main.index'))
    form = AddProductForm()
    if form.validate_on_submit():
        filename = secure_filename(form.image.data.filename)
        form.image.data.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
        
        coords = form.meetup_location.data.split(',')
        combined_dt = datetime.combine(form.meetup_date.data, form.meetup_time.data)
        
        new_product = Product(
            name=form.name.data,
            price=form.price.data,
            category=form.category.data,
            description=form.description.data,
            stock=form.stock.data,
            image_file=filename,
            seller=current_user,
            meetup_datetime=combined_dt,
            meetup_location_x=float(coords[0]),
            meetup_location_y=float(coords[1]),
            status='pendiente'
        )
        db.session.add(new_product)
        db.session.commit()
        flash('¡Tu producto ha sido añadido y está pendiente de aprobación!', 'success')
        return redirect(url_for('main.vendedor_dashboard'))
    cart_items = get_cart_items()
    return render_template('add_product.html', title='Añadir Producto', form=form, cart_items=cart_items)

@bp.route('/vendedor/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller != current_user:
        return redirect(url_for('main.index'))
    form = EditProductForm(obj=product)
    if form.validate_on_submit():
        product.name = form.name.data
        product.price = form.price.data
        product.category = form.category.data
        product.description = form.description.data
        product.stock = form.stock.data
        if form.image.data:
            filename = secure_filename(form.image.data.filename)
            form.image.data.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            product.image_file = filename
        
        product.meetup_datetime = datetime.combine(form.meetup_date.data, form.meetup_time.data)
        coords = form.meetup_location.data.split(',')
        product.meetup_location_x=float(coords[0])
        product.meetup_location_y=float(coords[1])
        product.status = 'pendiente'
        
        db.session.commit()
        flash('¡Producto actualizado con éxito! Vuelve a estar pendiente de aprobación.', 'success')
        return redirect(url_for('main.vendedor_dashboard'))
    
    if product.meetup_datetime:
        form.meetup_date.data = product.meetup_datetime.date()
        form.meetup_time.data = product.meetup_datetime.time()
    if product.meetup_location_x is not None:
        form.meetup_location.data = f"{product.meetup_location_x},{product.meetup_location_y}"

    cart_items = get_cart_items()
    return render_template('edit_product.html', title='Editar Producto', form=form, product=product, cart_items=cart_items)

@bp.route('/vendedor/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.seller != current_user:
        return redirect(url_for('main.index'))
    db.session.delete(product)
    db.session.commit()
    flash('Producto eliminado con éxito.', 'success')
    return redirect(url_for('main.vendedor_dashboard'))

# --- Rutas del Administrador ---
@bp.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    pending_products = Product.query.filter_by(status='pendiente').order_by(Product.id.desc()).all()
    cart_items = get_cart_items()
    return render_template('admin_dashboard.html', title='Panel de Admin', products=pending_products, cart_items=cart_items)

@bp.route('/admin/manage_users')
@login_required
def admin_manage_users():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    users = User.query.order_by(User.username).all()
    cart_items = get_cart_items()
    hermes_funds_config = SystemConfig.query.filter_by(key='hermes_funds').first()
    hermes_funds = float(hermes_funds_config.value) if hermes_funds_config else 0.0
    return render_template('admin_manage_users.html', title='Gestionar Usuarios', users=users, cart_items=cart_items, hermes_funds=hermes_funds)

@bp.route('/admin/update_balance/<int:user_id>', methods=['POST'])
@login_required
def admin_update_balance(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    
    user = User.query.get_or_404(user_id)
    try:
        amount = float(request.form.get('amount'))
        action = request.form.get('action')

        if action == 'add':
            user.balance += amount
            flash(f'Se añadieron ${amount:.2f} al balance de {user.username}.', 'success')
        elif action == 'subtract':
            if user.balance >= amount:
                user.balance -= amount
                flash(f'Se quitaron ${amount:.2f} del balance de {user.username}.', 'success')
            else:
                flash(f'{user.username} no tiene suficientes fondos para quitar ${amount:.2f}.', 'error')
        
        db.session.commit()
    except (ValueError, TypeError):
        flash('Por favor, introduce una cantidad válida.', 'error')
        
    return redirect(url_for('main.admin_manage_users'))

@bp.route('/admin/approve_product/<int:product_id>', methods=['POST'])
@login_required
def approve_product(product_id):
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    product = Product.query.get_or_404(product_id)
    product.status = 'aprobado'
    db.session.commit()
    flash(f'Producto "{product.name}" aprobado.', 'success')
    return redirect(url_for('main.admin_dashboard'))

@bp.route('/admin/reject_product/<int:product_id>', methods=['POST'])
@login_required
def reject_product(product_id):
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash(f'Producto "{product.name}" ha sido rechazado y eliminado.', 'success')
    return redirect(url_for('main.admin_dashboard'))

@bp.route('/admin/orders')
@login_required
def admin_manage_orders():
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    orders = Order.query.order_by(Order.order_date.desc()).all()
    cart_items = get_cart_items()
    return render_template('admin_manage_orders.html', title="Gestionar Pedidos", orders=orders, cart_items=cart_items)

@bp.route('/admin/update_order_status/<int:order_id>', methods=['POST'])
@login_required
def update_order_status(order_id):
    if current_user.role != 'admin':
        return redirect(url_for('main.index'))
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    if new_status in ['Procesando', 'En Camino', 'Entregado']:
        order.status = new_status
        db.session.commit()
        flash(f"El estado del pedido #{order.id} ha sido actualizado a '{new_status}'.", 'success')
    else:
        flash("Estado inválido.", 'error')
    return redirect(url_for('main.admin_manage_orders'))