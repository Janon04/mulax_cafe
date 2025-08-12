from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user 
from app.models import Product, StockMovement
from app import db
from app.auth.decorators import manager_required
from datetime import datetime
from app.models import User


bp = Blueprint('kitchen', __name__)

@bp.route('/inventory')
@login_required
def inventory():
    # Get filter parameters
    search_query = request.args.get('q', '')
    category_filter = request.args.get('category')
    sort = request.args.get('sort', 'name_asc')
    
    # Base query
    query = Product.query
    
    # Apply filters
    if search_query:
        query = query.filter(
            db.or_(
                Product.name.ilike(f'%{search_query}%'),
                Product.description.ilike(f'%{search_query}%'),
                Product.sku.ilike(f'%{search_query}%')
            )
        )
    
    if category_filter:
        query = query.filter(Product.category == category_filter)
    
    # Apply sorting
    if sort == 'name_desc':
        query = query.order_by(Product.name.desc())
    elif sort == 'stock_asc':
        query = query.order_by(Product.current_stock.asc())
    elif sort == 'stock_desc':
        query = query.order_by(Product.current_stock.desc())
    else:  # Default: name_asc
        query = query.order_by(Product.name.asc())
    
    # Get all products and categories
    products = query.all()
    all_categories = db.session.query(Product.category.distinct()).order_by(Product.category).all()
    all_categories = [c[0] for c in all_categories]
    
    # Group products by category
    categories = {}
    for product in products:
        if product.category not in categories:
            categories[product.category] = []
        categories[product.category].append(product)
    
    return render_template('kitchen/list.html', 
                         categories=categories,
                         all_categories=all_categories)
@bp.route('/usage', methods=['GET', 'POST'])
@login_required
def record_usage():
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        quantity = float(request.form.get('quantity'))
        notes = request.form.get('notes', 'Kitchen usage')
        
        product = Product.query.get_or_404(product_id)
        
        if product.current_stock < quantity:
            flash(f'Not enough stock available. Only {product.current_stock} {product.unit} left', 'danger')
            return redirect(url_for('kitchen.record_usage'))
        
        opening_stock = product.current_stock
        product.current_stock -= quantity
        closing_stock = product.current_stock
        
        movement = StockMovement(
            product_id=product_id,
            opening_stock=opening_stock,
            stock_out=quantity,
            closing_stock=closing_stock,
            movement_type='usage',
            notes=notes,
            date=datetime.utcnow(),
            user_id=current_user.id 
        )
        
        db.session.add(movement)
        db.session.commit()
        
        flash('Stock usage recorded successfully', 'success')
        return redirect(url_for('kitchen.inventory'))
    
    products = Product.query.order_by(Product.name).all()
    return render_template('kitchen/form.html', products=products)

@bp.route('/movements')
@login_required
@manager_required
def stock_movements():
    # Get filter parameters
    search_query = request.args.get('q', '')
    movement_type = request.args.get('type')
    sort = request.args.get('sort', 'date_desc')
    
    # Base query
    query = StockMovement.query
    
    # Apply filters
    if search_query:
        query = query.join(Product).filter(
            db.or_(
                Product.name.ilike(f'%{search_query}%'),
                StockMovement.notes.ilike(f'%{search_query}%'),
                User.username.ilike(f'%{search_query}%')
            )
        )
    
    if movement_type:
        query = query.filter(StockMovement.movement_type == movement_type)
    
    # Apply sorting
    if sort == 'date_asc':
        query = query.order_by(StockMovement.date.asc())
    elif sort == 'quantity_desc':
        # Use func.abs to sort by absolute quantity regardless of direction
        query = query.order_by(
            db.func.abs(db.func.coalesce(StockMovement.stock_in, StockMovement.stock_out)).desc()
        )
    else:  # Default: date_desc
        query = query.order_by(StockMovement.date.desc())
    
    movements = query.all()
    return render_template('kitchen/movements.html', movements=movements)
@bp.route('/dashboard')
@login_required
def dashboard():
    selected_date_str = request.args.get('selected_date')

    if selected_date_str:
        # Parse selected date
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d')
        # Create start and end range for that day
        start = datetime.combine(selected_date.date(), datetime.min.time())
        end = datetime.combine(selected_date.date(), datetime.max.time())

        # Filter stock movements for that day
        movements = StockMovement.query.filter(
            StockMovement.date >= start,
            StockMovement.date <= end
        ).all()
    else:
        movements = StockMovement.query.order_by(StockMovement.date.desc()).limit(50).all()

    return render_template('dashboard.html', movements=movements, now=datetime.utcnow())
