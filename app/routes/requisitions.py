from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app.models import Requisition, Product, User
from app.extensions import db
from config import Config
from app.services.notifications import EmailNotifier
from flask import current_app
from functools import wraps

bp = Blueprint('requisitions', __name__)

def admin_or_manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or (current_user.role not in ['admin', 'manager']):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/')
@login_required
def list_requisitions():
    if current_user.role in ['admin', 'manager']:
        requisitions = Requisition.query.order_by(Requisition.date.desc()).all()
    else:
        requisitions = Requisition.query.filter_by(user_id=current_user.id).order_by(Requisition.date.desc()).all()
    return render_template('requisitions/list.html', requisitions=requisitions)

@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_requisition():
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        requested_qty = float(request.form.get('quantity'))
        
        product = Product.query.get_or_404(product_id)
        
        requisition = Requisition(
            product_id=product.id,
            user_id=current_user.id,
            current_stock=product.current_stock,
            requested_qty=requested_qty,
            unit=product.unit,
            status='pending'
        )
        
        db.session.add(requisition)
        db.session.commit()
        
        try:
            notifier = EmailNotifier()
            notifier.notify_new_requisition(requisition.id)
        except Exception as e:
            current_app.logger.error(f"Failed to send email notification: {str(e)}")
        
        flash('Requisition submitted successfully', 'success')
        return redirect(url_for('requisitions.list_requisitions'))
    
    products = Product.query.order_by(Product.name).all()
    return render_template('requisitions/new.html', products=products)

@bp.route('/<int:id>/approve', methods=['POST'])
@login_required
@admin_or_manager_required
def approve_requisition(id):
    requisition = Requisition.query.get_or_404(id)
    
    if requisition.status != 'pending':
        flash('This requisition has already been processed', 'warning')
        return redirect(url_for('requisitions.list_requisitions'))
    
    product = Product.query.get(requisition.product_id)
    product.current_stock += requisition.requested_qty
    
    requisition.status = 'approved'
    requisition.approved_by = current_user.id
    requisition.approval_date = datetime.utcnow()
    
    db.session.commit()
    
    try:
        notifier = EmailNotifier()
        subject = f"✅ Requisition #{requisition.id} Approved"
        message = (
            f"Product: {requisition.product.name}\n"
            f"Quantity: {requisition.requested_qty} {requisition.unit}\n"
            f"Approved by: {current_user.username}\n"
            f"New stock level: {product.current_stock}"
        )
        notifier.send_email(
            current_app.config.get('ADMIN_EMAIL', notifier.default_recipient),
            subject,
            message
        )
    except Exception as e:
        current_app.logger.error(f"Failed to send approval notification: {str(e)}")
    
    flash('Requisition approved and stock updated', 'success')
    return redirect(url_for('requisitions.list_requisitions'))

@bp.route('/<int:id>/reject', methods=['POST'])
@login_required
@admin_or_manager_required
def reject_requisition(id):
    requisition = Requisition.query.get_or_404(id)
    
    if requisition.status != 'pending':
        flash('This requisition has already been processed', 'warning')
        return redirect(url_for('requisitions.list_requisitions'))
    
    requisition.status = 'rejected'
    requisition.approved_by = current_user.id
    requisition.approval_date = datetime.utcnow()
    
    db.session.commit()
    
    try:
        notifier = EmailNotifier()
        subject = f"❌ Requisition #{requisition.id} Rejected"
        message = (
            f"Product: {requisition.product.name}\n"
            f"Requested Quantity: {requisition.requested_qty} {requisition.unit}\n"
            f"Rejected by: {current_user.username}\n"
            f"Reason: {request.form.get('rejection_reason', 'No reason provided')}"
        )
        notifier.send_email(
            current_app.config.get('ADMIN_EMAIL', notifier.default_recipient),
            subject,
            message
        )
    except Exception as e:
        current_app.logger.error(f"Failed to send rejection notification: {str(e)}")
    
    flash('Requisition rejected', 'info')
    return redirect(url_for('requisitions.list_requisitions'))

@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_or_manager_required
def edit_requisition(id):
    requisition = Requisition.query.get_or_404(id)
    
    time_since_submission = (datetime.utcnow() - requisition.date).total_seconds()
    can_edit = (requisition.user_id == current_user.id and 
                requisition.status == 'pending' and 
                time_since_submission < Config.REQUISITION_EDIT_WINDOW)
    
    if not can_edit:
        flash('You cannot edit this requisition', 'danger')
        return redirect(url_for('requisitions.list_requisitions'))
    
    if request.method == 'POST':
        requested_qty = float(request.form.get('quantity'))
        
        requisition.requested_qty = requested_qty
        db.session.commit()
        
        try:
            notifier = EmailNotifier()
            subject = f"✏️ Requisition #{requisition.id} Edited"
            message = (
                f"Product: {requisition.product.name}\n"
                f"New Quantity: {requisition.requested_qty} {requisition.unit}\n"
                f"Edited by: {current_user.username}"
            )
            notifier.send_email(
                current_app.config.get('ADMIN_EMAIL', notifier.default_recipient),
                subject,
                message
            )
        except Exception as e:
            current_app.logger.error(f"Failed to send edit notification: {str(e)}")
        
        flash('Requisition updated successfully', 'success')
        return redirect(url_for('requisitions.list_requisitions'))
    
    products = Product.query.order_by(Product.name).all()
    return render_template('requisitions/edit.html', requisition=requisition, products=products)