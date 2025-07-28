from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime
from app.extensions import db
from app.auth.forms import TableForm
from app.models import Table, Order

# Create the blueprint at the top level
bp = Blueprint('tables', __name__)
@bp.route('/')
@login_required
def list_tables():
    """List all tables with their status"""
    tables = Table.query.order_by(Table.number).all()
    
    # Get counts of active orders per table
    for table in tables:
        table.active_orders = Order.query.filter(
            Order.table_id == table.id,
            Order.status.in_(['pending', 'preparing', 'served'])
        ).count()
    
    # Pass Order to template so it is defined inside Jinja2
    return render_template('tables/list.html', tables=tables, Order=Order)


@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_table():
    """Create a new table"""
    form = TableForm()
    
    if form.validate_on_submit():
        table = Table(
            number=form.number.data,
            capacity=form.capacity.data,
            location=form.location.data,
            is_occupied=False
        )
        db.session.add(table)
        db.session.commit()
        flash('Table created successfully!', 'success')
        return redirect(url_for('tables.list_tables'))
    
    return render_template('tables/new.html', form=form)

@bp.route('/<int:table_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_table(table_id):
    """Edit existing table"""
    table = Table.query.get_or_404(table_id)
    form = TableForm(obj=table)
    
    if form.validate_on_submit():
        table.number = form.number.data
        table.capacity = form.capacity.data
        table.location = form.location.data
        db.session.commit()
        flash('Table updated successfully!', 'success')
        return redirect(url_for('tables.list_tables'))
    
    return render_template('tables/edit.html', form=form, table=table)

@bp.route('/<int:table_id>/delete', methods=['POST'])
@login_required
def delete_table(table_id):
    """Delete a table"""
    table = Table.query.get_or_404(table_id)
    
    # Check for active orders
    active_orders = Order.query.filter(
        Order.table_id == table.id,
        Order.status.in_(['pending', 'preparing', 'served'])
    ).count()
    
    if active_orders > 0:
        flash('Cannot delete table with active orders', 'danger')
    else:
        db.session.delete(table)
        db.session.commit()
        flash('Table deleted successfully', 'success')
    
    return redirect(url_for('tables.list_tables'))

@bp.route('/<int:table_id>/toggle', methods=['POST'])
@login_required
def toggle_table(table_id):
    """Toggle table occupied status"""
    table = Table.query.get_or_404(table_id)
    table.is_occupied = not table.is_occupied
    db.session.commit()
    
    status = "occupied" if table.is_occupied else "available"
    flash(f'Table {table.number} marked as {status}', 'info')
    return redirect(url_for('tables.list_tables'))

@bp.route('/<int:table_id>/view')
@login_required
def view_table(table_id):
    """View table details and current orders"""
    table = Table.query.get_or_404(table_id)
    active_orders = Order.query.filter(
        Order.table_id == table.id,
        Order.status.in_(['pending', 'preparing', 'served'])
    ).order_by(Order.date.desc()).all()
    
    return render_template('tables/view.html', 
                         table=table, 
                         orders=active_orders)