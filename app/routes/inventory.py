from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.extensions import db
from datetime import timedelta  # ✅ Correct source
from app.models import Product, StockMovement  # ✅ Removed timedelta from here

# Define the blueprint
bp = Blueprint('inventory', __name__)

@bp.route('/inventory')
@login_required
def inventory():
    products = Product.query.order_by(Product.current_stock.asc()).all()
    low_stock_threshold = 5
    low_stock_products = [p for p in products if p.current_stock < low_stock_threshold]
    
    return render_template('inventory/inventory.html',
                           products=products,
                           low_stock_products=low_stock_products,
                           low_stock_threshold=low_stock_threshold)

@bp.route('/inventory/add', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        new_product = Product(
            name=request.form['name'],
            category=request.form['category'],
            current_stock=float(request.form['current_stock']),
            unit=request.form['unit'],
            unit_price=float(request.form['unit_price']),
            min_stock=float(request.form.get('min_stock', 5)),
            supplier=request.form.get('supplier', ''),
            remarks=request.form.get('remarks', '')
        )
        db.session.add(new_product)
        db.session.commit()
        flash('Product added successfully!', 'success')
        return redirect(url_for('inventory.inventory'))
    
    return render_template('inventory/add_product.html')

@bp.route('/inventory/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    if request.method == 'POST':
        product.name = request.form['name']
        product.category = request.form['category']
        product.current_stock = float(request.form['current_stock'])
        product.unit = request.form['unit']
        product.unit_price = float(request.form['unit_price'])
        product.min_stock = float(request.form.get('min_stock', 5))
        product.supplier = request.form.get('supplier', '')
        product.remarks = request.form.get('remarks', '')
        db.session.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('inventory.inventory'))
    
    return render_template('inventory/edit_product.html', product=product)

@bp.route('/inventory/delete/<int:id>', methods=['POST'])
@login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully!', 'success')
    return redirect(url_for('inventory.inventory'))
