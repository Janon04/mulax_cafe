from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime
from app.models import Order, OrderItem, Product, User, Table
from app.auth.forms import OrderForm
from app import db
from flask import jsonify
from datetime import timedelta



bp = Blueprint('orders', __name__, url_prefix='/orders')

@bp.route('/')
@login_required
def list_orders():
    """List all orders with filtering options"""
    status = request.args.get('status', 'all')
    query = Order.query.order_by(Order.date.desc())
    
    if status != 'all':
        query = query.filter(Order.status == status)
    
    if current_user.role == 'server':
        query = query.filter(Order.recorded_by == current_user.id)
    
    orders = query.limit(100).all()
    return render_template('orders/list.html', orders=orders, status=status)

@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_order():
    """Create a new order with items in one step"""
    form = OrderForm()
    products = Product.query.order_by(Product.name).all()
    tables = Table.query.order_by(Table.number).all()
    
    if request.method == 'POST':
        table_id = request.form.get('table_id')
        notes = request.form.get('notes', '')
        
        if not table_id:
            flash('Table selection is required', 'danger')
            return render_template('orders/new.html', form=form, products=products, tables=tables)
        
        table = Table.query.get(table_id)
        if not table:
            flash('Invalid table selected', 'danger')
            return render_template('orders/new.html', form=form, products=products, tables=tables)
            
        if table.is_occupied:
            flash('This table is currently occupied', 'danger')
            return render_template('orders/new.html', form=form, products=products, tables=tables)
        
        # Create the order
        order = Order(
            table_id=table_id,
            recorded_by=current_user.id,
            status='pending',
            notes=notes,
            total_amount=0  # Will be calculated from items
        )
        
        # Mark table as occupied
        table.is_occupied = True
        
        db.session.add(order)
        db.session.flush()  # Get the order ID
        
        # Process order items
        total_amount = 0
        for product in products:
            quantity = int(request.form.get(f'product_{product.id}', 0))
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
            flash('You must add at least one item to the order', 'danger')
            return render_template('orders/new.html', form=form, products=products, tables=tables)
        
        order.total_amount = total_amount
        db.session.commit()
        flash('Order created successfully', 'success')
        return redirect(url_for('orders.view_order', order_id=order.id))
    
    return render_template('orders/new.html', form=form, products=products, tables=tables)

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
            order.served_at = datetime.utcnow()
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
    today = datetime.utcnow().date()
    
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
    two_hours_ago = datetime.utcnow() - timedelta(hours=2)
    
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

