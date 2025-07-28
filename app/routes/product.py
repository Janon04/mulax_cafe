from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from datetime import datetime
from app.models import Product, StockMovement
from app.extensions import db
from openpyxl import Workbook
from flask import send_file
from io import BytesIO
from xhtml2pdf import pisa
from flask import make_response, render_template_string
from app.services.notifications import EmailNotifier, check_low_stock_products

bp = Blueprint('product', __name__, url_prefix='/products')

@bp.route('/')
@login_required
def list_products():
    """List all products with pagination and low stock alerts."""
    # Check for low stock products and send notifications
    notified_count = check_low_stock_products()
    if notified_count > 0:
        flash(f'Low stock alerts sent for {notified_count} products', 'warning')

    page = request.args.get('page', 1, type=int)
    per_page = 20
    products = Product.query.order_by(Product.name).paginate(page=page, per_page=per_page)

    # Fetch low stock products separately for the alert section
    low_stock_products = Product.query.filter(
        Product.current_stock <= Product.min_stock
    ).order_by(Product.name).all()

    return render_template('product/list.html', products=products, low_stock_products=low_stock_products)

@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_product():
    """Create a new product with initial stock movement"""
    if request.method == 'POST':
        try:
            # Generate product code
            category = request.form['category']
            prefix = {
                'food': 'FOD', 
                'drinks': 'DRK', 
                'furniture': 'FUR', 
                'materials': 'MAT'
            }.get(category, 'PRD')
            
            sku = f"{prefix}-{datetime.now().strftime('%Y%m%d')}-{Product.query.count() + 1:04d}"
            current_stock = float(request.form.get('current_stock', 0))
            min_stock = float(request.form.get('min_stock', 5))
            
            # Create new product
            product = Product(
                name=request.form['name'],
                category=category,
                description=request.form.get('description'),
                brand=request.form.get('brand'),
                unit=request.form['unit'],
                current_stock=current_stock,
                min_stock=min_stock,
                reorder_qty=float(request.form.get('reorder_qty', 0)),
                cost_price=float(request.form.get('cost_price', 0)),
                unit_price=float(request.form.get('unit_price', 0)),
                tax_rate=float(request.form.get('tax_rate', 0)),
                sku=sku
            )
            
            db.session.add(product)
            db.session.flush()  # Get the product ID
            
            # Record initial stock if provided
            if current_stock > 0:
                movement = StockMovement(
                    product_id=product.id,
                    opening_stock=0,
                    stock_in=current_stock,
                    closing_stock=current_stock,
                    movement_type='initial',
                    user_id=current_user.id,
                    notes='Initial stock'
                )
                db.session.add(movement)
            
            db.session.commit()
            
            # Check if new product is already below minimum stock
            if current_stock <= min_stock:
                try:
                    notifier = EmailNotifier()
                    notifier.notify_low_stock(product.id)
                except Exception as e:
                    current_app.logger.error(f"Failed to send low stock notification: {str(e)}")
            
            flash('Product added successfully', 'success')
            return redirect(url_for('product.view_product', product_id=product.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating product: {str(e)}', 'danger')
    
    return render_template('product/form.html', product=None)

@bp.route('/<int:product_id>')
@login_required
def view_product(product_id):
    """View product details with stock history"""
    product = Product.query.get_or_404(product_id)
    movements = StockMovement.query.filter_by(product_id=product_id)\
        .order_by(StockMovement.date.desc())\
        .limit(50)\
        .all()
    
    # Show warning if stock is low
    if product.current_stock <= product.min_stock:
        flash(f'Warning: {product.name} is below minimum stock level!', 'danger')
    
    return render_template('product/form.html', product=product, movements=movements)

@bp.route('/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    """Edit existing product details"""
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        try:
            original_stock = product.current_stock
            new_stock = float(request.form.get('current_stock', 0))
            new_min_stock = float(request.form.get('min_stock', 5))
            
            # Check if stock is going below minimum after edit
            will_be_low_stock = new_stock <= new_min_stock
            
            # Update product details
            product.name = request.form['name']
            product.category = request.form['category']
            product.description = request.form.get('description')
            product.brand = request.form.get('brand')
            product.unit = request.form['unit']
            product.min_stock = new_min_stock
            product.reorder_qty = float(request.form.get('reorder_qty', 0))
            product.cost_price = float(request.form.get('cost_price', 0))
            product.unit_price = float(request.form.get('unit_price', 0))
            product.tax_rate = float(request.form.get('tax_rate', 0))
            
            # Record stock adjustment if changed
            if new_stock != original_stock:
                difference = new_stock - original_stock
                movement_type = 'adjustment_in' if difference > 0 else 'adjustment_out'
                
                movement = StockMovement(
                    product_id=product.id,
                    opening_stock=original_stock,
                    stock_in=difference if difference > 0 else 0,
                    stock_out=-difference if difference < 0 else 0,
                    closing_stock=new_stock,
                    movement_type=movement_type,
                    user_id=current_user.id,
                    notes='Manual adjustment'
                )
                db.session.add(movement)
                product.current_stock = new_stock
            
            db.session.commit()
            
            # Send low stock notification if applicable
            if will_be_low_stock:
                try:
                    notifier = EmailNotifier()
                    notifier.notify_low_stock(product.id)
                except Exception as e:
                    current_app.logger.error(f"Failed to send low stock notification: {str(e)}")
            
            flash('Product updated successfully', 'success')
            return redirect(url_for('product.view_product', product_id=product.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating product: {str(e)}', 'danger')
    
    return render_template('product/form.html', product=product)

@bp.route('/<int:product_id>/delete', methods=['POST'])
@login_required
def delete_product(product_id):
    """Delete a product (POST method only for safety)"""
    product = Product.query.get_or_404(product_id)
    try:
        # First delete all stock movements to maintain referential integrity
        StockMovement.query.filter_by(product_id=product_id).delete()
        db.session.delete(product)
        db.session.commit()
        
        # Notify admin about product deletion
        try:
            notifier = EmailNotifier()
            message = (
                f"🗑️ Product Deleted\n\n"
                f"Name: {product.name}\n"
                f"SKU: {product.sku}\n"
                f"Deleted by: {current_user.username}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
            notifier.send_whatsapp_message(
                current_app.config['ADMIN_WHATSAPP_NUMBER'],
                message
            )
        except Exception as e:
            current_app.logger.error(f"Failed to send deletion notification: {str(e)}")
        
        flash('Product deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting product: {str(e)}', 'danger')
    return redirect(url_for('product.list_products'))
    

@bp.route('/<int:product_id>/add_stock', methods=['POST'])
@login_required
def add_stock(product_id):
    """Record a stock addition for a product"""
    product = Product.query.get_or_404(product_id)
    quantity = float(request.form.get('quantity', 0))
    notes = request.form.get('notes', '')
    
    try:
        movement = StockMovement(
            product_id=product.id,
            opening_stock=product.current_stock,
            stock_in=quantity,
            closing_stock=product.current_stock + quantity,
            movement_type='purchase',
            user_id=current_user.id,
            notes=notes
        )
        
        product.current_stock += quantity
        db.session.add(movement)
        db.session.commit()
        
        # Check if stock is still low after addition
        if product.current_stock <= product.min_stock:
            try:
                notifier = EmailNotifier()
                notifier.notify_low_stock(product.id)
            except Exception as e:
                current_app.logger.error(f"Failed to send low stock notification: {str(e)}")
        
        flash(f'Added {quantity} {product.unit} to stock', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding stock: {str(e)}', 'danger')
    
    return redirect(url_for('product.view_product', product_id=product_id))

@bp.route('/download/excel', methods=['GET'])
@login_required
def download_product_excel():
    """Download product list as an Excel file"""
    products = Product.query.order_by(Product.name).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Products"

    # Header
    headers = [
        'SKU', 'Name', 'Category', 'Brand', 'Description',
        'Unit', 'Current Stock', 'Min Stock', 'Reorder Qty',
        'Cost Price', 'Unit Price', 'Tax Rate', 'Stock Status'
    ]
    ws.append(headers)

    # Rows
    for product in products:
        stock_status = 'LOW' if product.current_stock <= product.min_stock else 'OK'
        ws.append([
            product.sku,
            product.name,
            product.category,
            product.brand or '',
            product.description or '',
            product.unit,
            product.current_stock,
            product.min_stock,
            product.reorder_qty,
            product.cost_price,
            product.unit_price,
            product.tax_rate,
            stock_status
        ])

    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="product_list.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@bp.route('/download/pdf', methods=['GET'])
@login_required
def download_product_pdf():
    """Download product list as a PDF file"""
    products = Product.query.order_by(Product.name).all()

    # Simple HTML table (you can replace with a real template if you like)
    html = render_template_string("""
    <html>
    <head>
        <style>
            table, th, td { border: 1px solid black; border-collapse: collapse; padding: 5px; }
            .low-stock { background-color: #ffcccc; }
        </style>
    </head>
    <body>
    <h2>Product List</h2>
    <table>
        <thead>
            <tr>
                <th>SKU</th><th>Name</th><th>Category</th><th>Brand</th>
                <th>Description</th><th>Unit</th><th>Current Stock</th>
                <th>Min Stock</th><th>Reorder Qty</th><th>Cost Price</th>
                <th>Unit Price</th><th>Tax Rate</th><th>Status</th>
            </tr>
        </thead>
        <tbody>
        {% for p in products %}
            <tr {% if p.current_stock <= p.min_stock %}class="low-stock"{% endif %}>
                <td>{{ p.sku }}</td><td>{{ p.name }}</td><td>{{ p.category }}</td><td>{{ p.brand or '' }}</td>
                <td>{{ p.description or '' }}</td><td>{{ p.unit }}</td><td>{{ p.current_stock }}</td>
                <td>{{ p.min_stock }}</td><td>{{ p.reorder_qty }}</td><td>{{ p.cost_price }}</td>
                <td>{{ p.unit_price }}</td><td>{{ p.tax_rate }}</td>
                <td>{% if p.current_stock <= p.min_stock %}LOW{% else %}OK{% endif %}</td>
            </tr>
        {% endfor %}
        </tbody>
    </table>
    </body>
    </html>
    """, products=products)

    # Generate PDF
    result = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=result)

    if pisa_status.err:
        flash("Error generating PDF", "danger")
        return redirect(url_for('product.list_products'))

    result.seek(0)
    return send_file(result, as_attachment=True, download_name="product_list.pdf", mimetype='application/pdf')