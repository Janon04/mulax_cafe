from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime
import pytz
from app.models import Order, OrderItem, Product, User, Table, Shift, Waiter, NotificationLog, CoffeeSale
from app.auth.forms import OrderForm
from app import db
from flask import jsonify
from datetime import timedelta
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from jinja2 import TemplateNotFound
from sqlalchemy import func


bp = Blueprint('orders', __name__, url_prefix='/orders')

@bp.route('/')
@login_required
def list_orders():
    """List all orders with filtering options"""
    try:
        # Get filter parameters
        status = request.args.get('status', 'all')
        shift_id = request.args.get('shift_id')
        user_id = request.args.get('user_id')
        date_filter = request.args.get('date_filter') or request.args.get('date')
        search = request.args.get('search', '').strip()
        sort = request.args.get('sort', 'date_desc')
        
        # Base query with joined loading for performance
        query = Order.query.options(
            db.joinedload(Order.table),
            db.joinedload(Order.waiter),
            db.joinedload(Order.shift),
            db.joinedload(Order.user)) 
        
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
        
        # Search functionality
        if search:
            search = f"%{search}%"
            query = query.join(Table).join(User).filter(
                db.or_(
                    Order.id.cast(db.String).ilike(search),
                    Table.number.ilike(search),
                    Order.notes.ilike(search),
                    User.username.ilike(search)
                )
            )
        
        # Apply sorting
        if sort == 'date_asc':
            query = query.order_by(Order.date.asc())
        elif sort == 'date_desc':
            query = query.order_by(Order.date.desc())
        elif sort == 'amount_asc':
            query = query.order_by(Order.total_amount.asc())
        elif sort == 'amount_desc':
            query = query.order_by(Order.total_amount.desc())
        else:
            query = query.order_by(Order.date.desc())
            
        # For non-admin users, only show their own orders
        if current_user.role not in ['admin', 'manager']:
            query = query.filter(Order.user_id == current_user.id)
            
        # Get active shifts and users for filter dropdowns
        active_shifts = Shift.query.filter_by(is_active=True).order_by(Shift.name).all()
        active_users = User.query.filter_by(active=True).order_by(User.username).all()
        
        # Execute query with limit
        orders = query.limit(100).all()
        
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
    """Create a new order with items"""
    form = OrderForm()
    products = Product.query.order_by(Product.name).all()
    tables = Table.query.order_by(Table.number).all()
    waiters = Waiter.query.filter_by(is_active=True).order_by(Waiter.name).all()

    # Determine current shift
    now = datetime.now(pytz.timezone('Africa/Kigali')).time()
    day_shift_start = datetime.strptime('07:00', '%H:%M').time()
    night_shift_start = datetime.strptime('17:00', '%H:%M').time()
    
    current_shift = Shift.query.filter(
        ((Shift.name == 'Day Shift') & (day_shift_start <= now < night_shift_start)) |
        ((Shift.name == 'Night Shift') & (not (day_shift_start <= now < night_shift_start))),
        Shift.is_active == True
    ).first()

    if request.method == 'POST':
        table_id = request.form.get('table_id')
        notes = request.form.get('notes', '')
        waiter_id = request.form.get('waiter_id')
        payment_mode = request.form.get('payment_mode')
        amount_tendered = request.form.get('amount_tendered', 0)

        # Validate inputs
        if not table_id:
            flash('Table selection is required', 'danger')
            return render_template('orders/new.html',
                                form=form,
                                products=products,
                                tables=tables,
                                waiters=waiters,
                                current_shift=current_shift)

        table = Table.query.get(table_id)
        if not table:
            flash('Invalid table selected', 'danger')
            return render_template('orders/new.html',
                                form=form,
                                products=products,
                                tables=tables,
                                waiters=waiters,
                                current_shift=current_shift)

        if table.is_occupied:
            flash('This table is currently occupied', 'danger')
            return render_template('orders/new.html',
                                form=form,
                                products=products,
                                tables=tables,
                                waiters=waiters,
                                current_shift=current_shift)

        # Create order
        try:
            order = Order(
                table_id=table_id,
                waiter_id=waiter_id,
                status='pending',
                notes=notes,
                total_amount=0,
                shift_id=current_shift.id if current_shift else None,
                user_id=current_user.id,
                payment_mode=payment_mode,
                amount_tendered=float(amount_tendered) if amount_tendered else 0
            )

            # Mark table as occupied
            table.is_occupied = True

            db.session.add(order)
            db.session.flush()

            # Process order items
            total_amount = 0
            items_added = False

            for product in products:
                quantity = float(request.form.get(f'product_{product.id}', 0))
                if quantity > 0:
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
    try:
        order = Order.query.options(
            db.joinedload(Order.table),
            db.joinedload(Order.waiter),
            db.joinedload(Order.shift),
            db.joinedload(Order.user),
            db.joinedload(Order.items).joinedload(OrderItem.product),
            db.joinedload(Order.server)
        ).get_or_404(order_id)

        if current_user.role == 'server' and order.user_id != current_user.id:
            flash('You can only view your own orders', 'danger')
            return redirect(url_for('orders.list_orders'))

        return render_template('orders/view.html', order=order)

    except SQLAlchemyError as e:
        current_app.logger.error(f"Error viewing order {order_id}: {str(e)}")
        flash('Error loading order details. Please try again.', 'danger')
        return redirect(url_for('orders.list_orders'))

@bp.route('/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_order(order_id):
    """Edit an existing order"""
    order = Order.query.get_or_404(order_id)
    if current_user.role == 'server' and order.user_id != current_user.id:
        flash('You can only edit your own orders', 'danger')
        return redirect(url_for('orders.list_orders'))
    
    products = Product.query.order_by(Product.name).all()
    tables = Table.query.order_by(Table.number).all()
    form = OrderForm(obj=order)
    
    if request.method == 'POST':
        new_table_id = request.form.get('table_id')
        order.notes = request.form.get('notes', '')
        order.payment_mode = request.form.get('payment_mode')
        order.amount_tendered = float(request.form.get('amount_tendered', 0))
        
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
            quantity = float(request.form.get(f'product_{product.id}', 0))
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
    if current_user.role == 'server' and order.user_id != current_user.id:
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
    old_status = order.status
    
    if new_status in ['pending', 'preparing', 'served', 'completed', 'cancelled']:
        # Free table if order is completed or cancelled
        if new_status in ['completed', 'cancelled'] and order.table:
            order.table.is_occupied = False
        
        # Occupy table if order is being reactivated
        if new_status in ['pending', 'preparing', 'served'] and order.table:
            order.table.is_occupied = True
            
        order.status = new_status
        
        # If order is cancelled, restore product stock
        if new_status == 'cancelled' and old_status != 'cancelled':
            for item in order.items:
                product = Product.query.get(item.product_id)
                if product:
                    product.current_stock += item.quantity
        
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
        count = Order.query.filter_by(status='pending', user_id=current_user.id).count()
    return jsonify({'count': count})

@bp.route('/today-stats')
@login_required
def get_today_stats():
    today = datetime.now(pytz.timezone('Africa/Kigali')).date()
    
    query = Order.query.filter(
        db.func.date(Order.date) == today,
        Order.status != 'cancelled'
    )
    
    if current_user.role == 'server':
        query = query.filter(Order.user_id == current_user.id)
    
    count = query.count()
    revenue = db.session.query(
        db.func.coalesce(db.func.sum(Order.total_amount), 0)
    ).filter(
        db.func.date(Order.date) == today,
        Order.status != 'cancelled'
    ).scalar() or 0
    
    return jsonify({
        'count': count,
        'revenue': float(revenue)
    })

@bp.route('/recent-orders-data')
@login_required
def get_recent_orders_data():
    two_hours_ago = datetime.now(pytz.timezone('Africa/Kigali')) - timedelta(hours=2)
    
    query = Order.query.filter(Order.date >= two_hours_ago).order_by(Order.date.desc())
    
    if current_user.role == 'server':
        query = query.filter(Order.user_id == current_user.id)
    
    count = query.count()
    recent_orders = query.limit(5).all()
    
    orders_data = [{
        'id': order.id,
        'table_number': order.table.number if order.table else None,
        'items_count': len(order.items),
        'total_amount': float(order.total_amount),
        'status': order.status,
        'date': order.date.isoformat()
    } for order in recent_orders]
    
    return jsonify({
        'count': count,
        'orders': orders_data
    })

@bp.route('/<int:order_id>/receipt')
@login_required
def print_receipt(order_id):
    """Generate a printable receipt for an order"""
    try:
        # Eager load all necessary relationships
        order = Order.query.options(
            db.joinedload(Order.table),
            db.joinedload(Order.waiter),
            db.joinedload(Order.server),
            db.joinedload(Order.user),
            db.joinedload(Order.items).joinedload(OrderItem.product),
            db.joinedload(Order.shift)
        ).get_or_404(order_id)
        
        if not order.items:
            flash('Cannot generate receipt for an empty order', 'warning')
            return redirect(url_for('orders.view_order', order_id=order_id))

        # Get current time in Rwanda timezone
        rwanda_tz = pytz.timezone('Africa/Kigali')
        current_time = datetime.now(rwanda_tz)

        # Prepare receipt data with proper null checks
        receipt_data = {
            'order_id': order.id,
            'created_at': order.date.astimezone(rwanda_tz).strftime('%Y-%m-%d %H:%M') if order.date else 'N/A',
            'print_time': current_time.strftime('%Y-%m-%d %H:%M'),
            'table_number': order.table.number if order.table else 'N/A',
            'waiter': order.waiter.name if order.waiter else 'N/A',
            'waiter_phone': order.waiter.phone_number if order.waiter else '',
            'served_at': order.served_at.astimezone(rwanda_tz).strftime('%Y-%m-%d %H:%M') if order.served_at else None,
            'served_by': order.server.username if order.server else 'N/A',
            'shift': order.shift.name if order.shift else 'Not assigned',
            'notes': order.notes or '',
            'status': order.status.title(),
            'payment_mode': order.payment_mode or 'Not specified',
            'amount_tendered': float(order.amount_tendered) if order.amount_tendered else 0,
            'items': [{
                'name': item.product.name,
                'quantity': item.quantity,
                'unit': item.product.unit or '',
                'unit_price': float(item.unit_price),
                'subtotal': float(item.quantity * item.unit_price),
                'notes': item.special_instructions or ''
            } for item in order.items],
            'total_amount': float(order.total_amount)
        }

        # Add change calculation if amount tendered exists
        if receipt_data['amount_tendered'] > 0:
            receipt_data['change'] = receipt_data['amount_tendered'] - receipt_data['total_amount']

        return render_template('orders/receipt.html', order=receipt_data)

    except Exception as e:
        current_app.logger.error(f"Error generating receipt for order {order_id}: {str(e)}", exc_info=True)
        flash('Failed to generate receipt. Please check the order details and try again.', 'danger')
        return redirect(url_for('orders.view_order', order_id=order_id))

@bp.route('/combined_report')
@login_required
def combined_report():
    """Generate a combined sales report including direct sales and orders"""
    try:
        tz = pytz.timezone('Africa/Kigali')
        end_date = datetime.now(tz)
        start_date = end_date - timedelta(days=30)  # Last 30 days by default

        # 1. Get direct coffee sales data
        coffee_sales_by_product = db.session.query(
            Product.name,
            func.sum(CoffeeSale.quantity_sold).label('total_quantity'),
            func.sum(CoffeeSale.total_sales).label('total_sales')
        ).join(CoffeeSale.product)\
         .filter(
             CoffeeSale.date >= start_date,
             CoffeeSale.date <= end_date
         ).group_by(Product.name).all()

        coffee_sales_by_payment = db.session.query(
            CoffeeSale.payment_mode,
            func.sum(CoffeeSale.total_sales).label('total_sales')
        ).filter(
            CoffeeSale.date >= start_date,
            CoffeeSale.date <= end_date
        ).group_by(CoffeeSale.payment_mode).all()

        recent_coffee_sales = CoffeeSale.query\
            .options(db.joinedload(CoffeeSale.product))\
            .filter(
                CoffeeSale.date >= start_date,
                CoffeeSale.date <= end_date
            ).order_by(CoffeeSale.date.desc()).limit(10).all()

        # 2. Get order data
        recent_orders = Order.query.filter(
            Order.status == 'completed',
            Order.date >= start_date,
            Order.date <= end_date
        ).options(
            db.joinedload(Order.table),
            db.joinedload(Order.items).joinedload(OrderItem.product)
        ).order_by(Order.date.desc()).limit(10).all()

        # 3. Combine sales by product
        combined_sales_by_product = []
        all_products = Product.query.order_by(Product.name).all()
        
        for product in all_products:
            # Direct coffee sales
            coffee_sale = next(
                (s for s in coffee_sales_by_product if s.name == product.name),
                {'total_quantity': 0, 'total_sales': 0}
            )
            
            # Order sales for this product
            order_sales = db.session.query(
                func.sum(OrderItem.quantity).label('total_quantity'),
                func.sum(OrderItem.quantity * OrderItem.unit_price).label('total_sales')
            ).join(Order)\
             .filter(
                OrderItem.product_id == product.id,
                Order.status == 'completed',
                Order.date >= start_date,
                Order.date <= end_date
            ).first()
            
            combined_sales_by_product.append({
                'name': product.name,
                'total_quantity': float(getattr(coffee_sale, 'total_quantity', 0)) + (order_sales[0] or 0),
                'coffee_sales': float(getattr(coffee_sale, 'total_sales', 0)),
                'order_sales': order_sales[1] or 0,
                'total_sales': float(getattr(coffee_sale, 'total_sales', 0)) + (order_sales[1] or 0)
            })

        # 4. Combine sales by payment mode
        payment_modes = ['Cash', 'Mobile Money', 'Card', 'Other']
        combined_sales_by_payment = []
        
        for mode in payment_modes:
            # Direct coffee sales
            coffee_sale = next(
                (s for s in coffee_sales_by_payment if s.payment_mode == mode),
                {'total_sales': 0}
            )
            
            # Order sales for this payment mode
            order_sales = db.session.query(
                func.sum(Order.total_amount).label('total_sales')
            ).filter(
                Order.payment_mode == mode,
                Order.status == 'completed',
                Order.date >= start_date,
                Order.date <= end_date
            ).scalar() or 0
            
            combined_sales_by_payment.append({
                'payment_mode': mode,
                'coffee_sales': float(getattr(coffee_sale, 'total_sales', 0)),
                'order_sales': order_sales or 0,
                'total_sales': float(getattr(coffee_sale, 'total_sales', 0)) + (order_sales or 0)
            })

        return render_template(
            'coffee/combined_report.html',
            combined_sales_by_product=combined_sales_by_product,
            combined_sales_by_payment=combined_sales_by_payment,
            recent_coffee_sales=recent_coffee_sales,
            recent_orders=recent_orders,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d')
        )

    except Exception as e:
        current_app.logger.error(f"Error generating combined report: {str(e)}", exc_info=True)
        flash('Error generating report. Please try again.', 'danger')
        return redirect(url_for('main.dashboard'))