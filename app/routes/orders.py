from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime
import pytz
from app.models import Order, OrderItem, Product, User, Table
from app.auth.forms import OrderForm
from app import db
from flask import jsonify
from datetime import timedelta
from flask import current_app
from app.models import Shift
from app.models import NotificationLog
from app.models import Waiter



bp = Blueprint('orders', __name__, url_prefix='/orders')

@bp.route('/')
@login_required
def list_orders():
    """List all orders with filtering options including shift filtering"""
    try:
        # Get filter parameters
        status = request.args.get('status', 'all')
        shift_id = request.args.get('shift_id')
        user_id = request.args.get('user_id')
        date_filter = request.args.get('date')
        
        # Base query with joined loading for performance
        query = Order.query.options(
            db.joinedload(Order.client),
            db.joinedload(Order.table),
            db.joinedload(Order.shift),
            db.joinedload(Order.user),
            db.joinedload(Order.recorder)
        ).order_by(Order.date.desc())
        
        # Apply filters
        if status != 'all':
            query = query.filter(Order.status == status)
            
        if shift_id:
            query = query.filter(Order.shift_id == shift_id)
            
        if user_id:
            query = query.filter(Order.user_id == user_id)
            
        if date_filter:
            try:
                filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
                query = query.filter(db.func.date(Order.date) == filter_date)
            except ValueError:
                flash('Invalid date format. Using default filter.', 'warning')
        
        # For non-admin users, only show their own orders
        if current_user.role not in ['admin', 'manager']:
            query = query.filter(Order.user_id == current_user.id)
            
        # Get active shifts and users for filter dropdowns
        active_shifts = Shift.query.filter_by(is_active=True).order_by(Shift.name).all()
        active_users = User.query.filter_by(active=True).order_by(User.username).all()
        
        # Execute query with limit
        orders = query.limit(100).all()
        
        from app.models import Waiter
        waiters = Waiter.query.filter_by(is_active=True).all()
        return render_template('orders/list.html',
                            orders=orders,
                            status=status,
                            shift_id=shift_id,
                            user_id=user_id,
                            date_filter=date_filter,
                            active_shifts=active_shifts,
                            active_users=active_users,
                            waiters=waiters)
    
    except Exception as e:
        current_app.logger.error(f"Error listing orders: {str(e)}")
        flash('Error loading orders. Please try again.', 'danger')
        return redirect(url_for('main.dashboard'))
    
@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_order():
    """Create a new order with items in one step"""
    form = OrderForm()
    products = Product.query.order_by(Product.name).all()
    tables = Table.query.order_by(Table.number).all()

    waiters = Waiter.query.filter_by(is_active=True).order_by(Waiter.name).all()

    # Automatically determine current shift based on time
    now = datetime.now(pytz.timezone('Africa/Kigali')).time()
    morning_start = datetime.strptime('07:00', '%H:%M').time()
    evening_start = datetime.strptime('17:00', '%H:%M').time()
    midnight = datetime.strptime('00:00', '%H:%M').time()
    current_shift = None
    if morning_start <= now < evening_start:
        current_shift = Shift.query.filter_by(name='Morning', is_active=True).first()
    elif evening_start <= now or now < morning_start:
        current_shift = Shift.query.filter_by(name='Evening', is_active=True).first()

    if request.method == 'POST':
        table_id = request.form.get('table_id')
        notes = request.form.get('notes', '')
        waiter_id_raw = request.form.get('waiter_id')
        try:
            waiter_id = int(waiter_id_raw) if waiter_id_raw else None
        except (TypeError, ValueError):
            waiter_id = None

        # Validate table selection
        if not table_id:
            flash('Table selection is required', 'danger')
            return render_template('orders/new.html',
                                   form=form,
                                   products=products,
                                   tables=tables,
                                   waiters=waiters,
                                   current_shift=None)

        table = Table.query.get(table_id)
        if not table:
            flash('Invalid table selected', 'danger')
            return render_template('orders/new.html',
                                   form=form,
                                   products=products,
                                   tables=tables,
                                   waiters=waiters,
                                   current_shift=None)

        if table.is_occupied:
            flash('This table is currently occupied', 'danger')
            return render_template('orders/new.html',
                                   form=form,
                                   products=products,
                                   tables=tables,
                                   waiters=waiters,
                                   current_shift=None)

        # Verify waiter exists
        if waiter_id:
            waiter = Waiter.query.get(waiter_id)
            if not waiter or not waiter.is_active:
                flash('Invalid waiter selected', 'danger')
                return render_template('orders/new.html',
                                       form=form,
                                       products=products,
                                       tables=tables,
                                       waiters=waiters,
                                       current_shift=None)

        # Create order
        try:
            order = Order(
                table_id=table_id,
                waiter_id=waiter_id,
                status='pending',
                notes=notes,
                total_amount=0,
                shift_id=current_shift.id if current_shift else None,
                user_id=current_user.id
            )

            # Mark table as occupied
            table.is_occupied = True

            db.session.add(order)
            db.session.flush()

            # Process order items
            total_amount = 0
            items_added = False

            for product in products:
                quantity_raw = request.form.get(f'product_{product.id}', 0)
                try:
                    quantity = float(quantity_raw)
                except (TypeError, ValueError):
                    quantity = 0
                if quantity > 0:
                    # Check stock before adding item
                    if product.current_stock < quantity:
                        db.session.rollback()
                        flash(f'Not enough stock for {product.name}. Only {product.current_stock} {product.unit} left.', 'danger')
                        return render_template('orders/new.html',
                                               form=form,
                                               products=products,
                                               tables=tables,
                                               waiters=waiters,
                                               current_shift=current_shift)
                    items_added = True
                    item = OrderItem(
                        order_id=order.id,
                        product_id=product.id,
                        quantity=quantity,
                        unit_price=product.unit_price,
                        special_instructions=request.form.get(f'notes_{product.id}', '')
                    )
                    db.session.add(item)
                    total_amount += quantity * product.unit_price
                    # Deduct from inventory
                    product.current_stock -= quantity

            if not items_added:
                db.session.rollback()
                flash('You must add at least one item to the order', 'danger')
                return render_template('orders/new.html',
                                       form=form,
                                       products=products,
                                       tables=tables,
                                       waiters=waiters,
                                       current_shift=current_shift)

            order.total_amount = total_amount
            db.session.commit()

            flash('Order created successfully', 'success')
            return redirect(url_for('orders.view_order', order_id=order.id))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating order: {str(e)}")
            flash('An error occurred while creating the order. Please try again.', 'danger')
            return render_template('orders/new.html',
                                   form=form,
                                   products=products,
                                   tables=tables,
                                   waiters=waiters,
                                   current_shift=current_shift)

    return render_template('orders/new.html',
                           form=form,
                           products=products,
                           tables=tables,
                           waiters=waiters,
                           current_shift=current_shift)

@bp.route('/<int:order_id>')
@login_required
def view_order(order_id):
    """View order details"""
    order = Order.query.get_or_404(order_id)
    if current_user.role == 'server' and order.recorded_by != current_user.id:
        flash('You can only view your own orders', 'danger')
        return redirect(url_for('orders.list_orders'))
    return render_template('orders/view.html', order=order)

@bp.route('/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_order(order_id):
    """Edit an existing order"""
    order = Order.query.get_or_404(order_id)
    if current_user.role == 'server' and order.recorded_by != current_user.id:
        flash('You can only edit your own orders', 'danger')
        return redirect(url_for('orders.list_orders'))
    
    products = Product.query.order_by(Product.name).all()
    tables = Table.query.order_by(Table.number).all()
    form = OrderForm(obj=order)
    
    if request.method == 'POST':
        new_table_id = request.form.get('table_id')
        order.notes = request.form.get('notes', '')
        
        # Update table status if changed
        if str(order.table_id) != new_table_id:
            old_table = Table.query.get(order.table_id)
            if old_table:
                old_table.is_occupied = False
            
            new_table = Table.query.get(new_table_id)
            if new_table:
                if new_table.is_occupied:
                    flash('The selected table is already occupied', 'danger')
                    return render_template('orders/edit.html', order=order, form=form, products=products, tables=tables)
                
                new_table.is_occupied = True
                order.table_id = new_table_id
        
        # Clear existing items and recreate
        OrderItem.query.filter_by(order_id=order.id).delete()
        
        total_amount = 0
        for product in products:
            raw_value = request.form.get(f'product_{product.id}', '0').strip()
            quantity = float(raw_value) if raw_value else 0.0

            if quantity > 0:
                item = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=product.unit_price,
                    special_instructions=request.form.get(f'notes_{product.id}', '')
                )
                db.session.add(item)
                total_amount += quantity * product.unit_price
        
        if total_amount == 0:
            db.session.rollback()
            flash('Order must have at least one item', 'danger')
            return render_template('orders/edit.html', order=order, form=form, products=products, tables=tables)
        
        order.total_amount = total_amount
        db.session.commit()
        flash('Order updated successfully', 'success')
        return redirect(url_for('orders.view_order', order_id=order.id))
    
    return render_template('orders/edit.html', order=order, form=form, products=products, tables=tables)

@bp.route('/<int:order_id>/delete', methods=['POST'])
@login_required
def delete_order(order_id):
    """Delete an order"""
    order = Order.query.get_or_404(order_id)
    if current_user.role == 'server' and order.recorded_by != current_user.id:
        flash('You can only delete your own orders', 'danger')
        return redirect(url_for('orders.list_orders'))
    
    if order.status not in ['pending', 'preparing']:
        flash('Only pending or preparing orders can be deleted', 'danger')
        return redirect(url_for('orders.view_order', order_id=order.id))
    
    # Free the table when order is deleted
    if order.table:
        order.table.is_occupied = False
    
    OrderItem.query.filter_by(order_id=order.id).delete()
    db.session.delete(order)
    db.session.commit()
    flash('Order deleted successfully', 'success')
    return redirect(url_for('orders.list_orders'))

@bp.route('/<int:order_id>/update-status', methods=['POST'])
@login_required
def update_status(order_id):
    """Update order status"""
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    
    if new_status in ['pending', 'preparing', 'served', 'completed', 'cancelled']:
        # Free table if order is completed or cancelled
        if new_status in ['completed', 'cancelled'] and order.table:
            order.table.is_occupied = False
        
        # Occupy table if order is being reactivated
        if new_status in ['pending', 'preparing', 'served'] and order.table:
            order.table.is_occupied = True
            
        order.status = new_status
        if new_status == 'served':
            order.served_by = current_user.id
            order.served_at = datetime.now(pytz.timezone('Africa/Kigali'))
        db.session.commit()
        flash(f'Order status updated to {new_status}', 'success')
    
    return redirect(url_for('orders.view_order', order_id=order.id))

@bp.route('/pending-count')
@login_required
def get_pending_count():
    count = Order.query.filter_by(status='pending').count()
    if current_user.role == 'server':
        count = Order.query.filter_by(
            status='pending',
            recorded_by=current_user.id
        ).count()
    return jsonify({'count': count})

@bp.route('/today-stats')
@login_required
def get_today_stats():
    today = datetime.now(pytz.timezone('Africa/Kigali')).date()
    
    # Base query for today's orders
    query = Order.query.filter(
        db.func.date(Order.date) == today,
        Order.status != 'cancelled'
    )
    
    if current_user.role == 'server':
        query = query.filter(Order.recorded_by == current_user.id)
    
    count = query.count()
    revenue = db.session.query(
        db.func.coalesce(db.func.sum(Order.total_amount), 0)
    ).filter(
        db.func.date(Order.date) == today,
        Order.status != 'cancelled'
    ).scalar() or 0
    
    if current_user.role == 'server':
        revenue = db.session.query(
            db.func.coalesce(db.func.sum(Order.total_amount), 0)
        ).filter(
            db.func.date(Order.date) == today,
            Order.status != 'cancelled',
            Order.recorded_by == current_user.id
        ).scalar() or 0
    
    return jsonify({
        'count': count,
        'revenue': float(revenue)
    })
# ...................................
@bp.route('/recent-orders-data')
@login_required
def get_recent_orders_data():
    # Define "recent" as orders from the last 2 hours
    two_hours_ago = datetime.now(pytz.timezone('Africa/Kigali')) - timedelta(hours=2)
    
    query = Order.query.filter(Order.date >= two_hours_ago).order_by(Order.date.desc())
    
    if current_user.role == 'server':
        query = query.filter(Order.recorded_by == current_user.id)
    
    # Get count
    count = query.count()
    
    # Get limited orders data for the table (last 5)
    recent_orders = query.limit(5).all()
    
    # Serialize orders data
    orders_data = [{
        'id': order.id,
        'client_name': order.client.name if order.client else None,
        'items_count': len(order.items),
        'total_amount': float(order.total_amount),
        'status': order.status,
        'date': order.date.isoformat()
    } for order in recent_orders]
    
    return jsonify({
        'count': count,
        'orders': orders_data
    })

