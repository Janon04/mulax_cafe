from flask import render_template, Blueprint, redirect, url_for, flash
from flask_login import login_required, current_user
from ..models import Product, Requisition, CoffeeSale, StockMovement
from datetime import datetime, timedelta
import pytz
from app.extensions import db
from sqlalchemy import func, or_
from decimal import Decimal
import logging
from app.auth.forms import LoginForm
from datetime import datetime, date


bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)


@bp.route('/')
def index():
    return redirect(url_for('auth.login'))
@bp.route('/dashboard')
@login_required
def dashboard():
    # Show a simplified dashboard for employees
    if current_user.role == 'employee' and not current_user.is_admin:
        # Only show basic info for employees
        today = date.today()
        total_sales_today = db.session.query(
            func.sum(CoffeeSale.total_sales)
        ).filter(
            func.date(CoffeeSale.date) == today
        ).scalar() or 0
        recent_sales = CoffeeSale.query.filter_by(user_id=current_user.id).order_by(
            CoffeeSale.date.desc()
        ).limit(5).all()
        return render_template('main/dashboard_employee.html',
            total_sales_today=total_sales_today,
            recent_sales=recent_sales,
            now=datetime.now(pytz.timezone('Africa/Kigali'))
        )
    # Full dashboard for managers, system_control, admins
    # ...existing code for full dashboard...
    total_products = Product.query.count()
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = date(today.year, today.month, 1)
    total_sales_all_time = db.session.query(
        func.sum(CoffeeSale.total_sales)
    ).scalar() or 0
    total_sales_today = db.session.query(
        func.sum(CoffeeSale.total_sales)
    ).filter(
        func.date(CoffeeSale.date) == today
    ).scalar() or 0
    total_sales_this_week = db.session.query(
        func.sum(CoffeeSale.total_sales)
    ).filter(
        func.date(CoffeeSale.date) >= start_of_week
    ).scalar() or 0
    total_sales_this_month = db.session.query(
        func.sum(CoffeeSale.total_sales)
    ).filter(
        func.date(CoffeeSale.date) >= start_of_month
    ).scalar() or 0
    sales_by_payment = db.session.query(
        CoffeeSale.payment_mode,
        func.sum(CoffeeSale.total_sales).label('total_sales')
    ).group_by(CoffeeSale.payment_mode).all()
    top_products = db.session.query(
        Product.name,
        func.sum(CoffeeSale.quantity_sold).label('total_quantity'),
        func.sum(CoffeeSale.total_sales).label('total_sales')
    ).join(CoffeeSale).group_by(Product.name).order_by(
        func.sum(CoffeeSale.total_sales).desc()
    ).limit(5).all()
    pending_requisitions = Requisition.query.filter_by(status='pending').count()
    low_stock_items = Product.query.filter(
        Product.current_stock < func.coalesce(Product.min_stock, 5.0)
    ).all()
    from sqlalchemy.orm import joinedload
    recent_requisitions = Requisition.query.options(
        joinedload(Requisition.requester)
    ).order_by(
        Requisition.date.desc()
    ).limit(5).all()
    recent_sales = CoffeeSale.query.order_by(
        CoffeeSale.date.desc()
    ).limit(5).all()
    return render_template('main/dashboard.html',
        total_products=total_products,
        total_sales_all_time=total_sales_all_time,
        total_sales_today=total_sales_today,
        total_sales_this_week=total_sales_this_week,
        total_sales_this_month=total_sales_this_month,
        sales_by_payment=sales_by_payment,
        top_products=top_products,
        pending_requisitions=pending_requisitions,
        low_stock_items=low_stock_items,
        recent_requisitions=recent_requisitions,
        recent_sales=recent_sales,
        now=datetime.now(pytz.timezone('Africa/Kigali'))
    )