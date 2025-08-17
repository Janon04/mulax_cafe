from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime
from app.extensions import db
from app.auth.forms import TableForm
from app.models import Table, Order
from app import db
from flask import current_app

bp = Blueprint('tables', __name__)

from flask import current_app

@bp.route('/')
@login_required
def list_tables():
    """List all tables with their status"""
    try:
        tables = Table.query.filter_by(is_archived=False).order_by(Table.number).all()
        
        # Get counts of active orders per table
        for table in tables:
            table.active_orders_count = Order.query.filter(
                Order.table_id == table.id,
                Order.status.in_(['pending', 'preparing', 'served'])
            ).count()
        
        return render_template('tables/list.html', 
                            tables=tables, 
                            Order=Order)
    
    except Exception as e:
        current_app.logger.error(f"Error in list_tables: {str(e)}", exc_info=True)
        flash('An error occurred while loading tables', 'danger')
        return redirect(url_for('tables.list_tables'))    
@bp.route('/archived')
@login_required
def list_archived_tables():
    """List all archived tables"""
    try:
        tables = Table.query.filter_by(is_archived=True).order_by(Table.number).all()
        
        # Optional: count active orders for archived tables (usually zero)
        for table in tables:
            table.active_orders_count = Order.query.filter(
                Order.table_id == table.id,
                Order.status.in_(['pending', 'preparing', 'served'])
            ).count()
        
        return render_template('tables/archived.html', tables=tables)
    
    except Exception as e:
        current_app.logger.error(f"Error in list_archived_tables: {str(e)}", exc_info=True)
        flash('An error occurred while loading archived tables', 'danger')
        return redirect(url_for('tables.list_tables'))

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
            is_occupied=False,
            is_archived=False
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
    if table.is_archived:
        flash('Cannot edit an archived table', 'danger')
        return redirect(url_for('tables.list_tables'))
    
    form = TableForm(obj=table)

    if form.validate_on_submit():
        table.capacity = form.capacity.data
        table.location = form.location.data
        db.session.commit()
        flash('Table updated successfully!', 'success')
        return redirect(url_for('tables.list_tables'))

    return render_template('tables/edit.html', form=form, table=table)

@bp.route('/<int:table_id>/archive', methods=['POST'])
@login_required
def archive_table(table_id):
    """Archive a table safely, preventing archiving if it has active orders"""
    try:
        table = Table.query.get_or_404(table_id)

        # Check for active orders
        active_orders_count = Order.query.filter(
            Order.table_id == table.id,
            Order.status.in_(['pending', 'preparing', 'served'])
        ).count()

        if active_orders_count > 0:
            flash('Cannot archive table with active orders', 'danger')
        else:
            table.is_archived = True
            table.is_occupied = False  # Ensure archived tables are not marked as occupied
            db.session.commit()
            flash(f'Table {table.number} archived successfully', 'success')

    except Exception as e:
        current_app.logger.error(f"Error archiving table {table_id}: {str(e)}", exc_info=True)
        flash('An error occurred while archiving the table. Please try again.', 'danger')

    return redirect(url_for('tables.list_tables'))

@bp.route('/<int:table_id>/restore', methods=['POST'])
@login_required
def restore_table(table_id):
    """Restore an archived table"""
    table = Table.query.get_or_404(table_id)
    table.is_archived = False
    db.session.commit()
    flash('Table restored successfully', 'success')
    return redirect(url_for('tables.list_archived_tables'))

@bp.route('/<int:table_id>/toggle', methods=['POST'])
@login_required
def toggle_table(table_id):
    """Toggle table occupied status"""
    table = Table.query.get_or_404(table_id)
    if table.is_archived:
        flash('Cannot toggle status of an archived table', 'danger')
        return redirect(url_for('tables.list_tables'))
    
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
@bp.route('/<int:table_id>/delete', methods=['POST'])
@login_required
def delete_table(table_id):
    """Permanently delete a table"""
    table = Table.query.get_or_404(table_id)

    # Prevent deleting tables that still have orders
    active_orders = Order.query.filter(
        Order.table_id == table.id,
        Order.status.in_(['pending', 'preparing', 'served'])
    ).count()
    
    if active_orders > 0:
        flash('Cannot delete table with active orders', 'danger')
        return redirect(url_for('tables.list_tables'))

    db.session.delete(table)
    db.session.commit()
    flash('Table deleted successfully', 'success')
    return redirect(url_for('tables.list_tables'))
