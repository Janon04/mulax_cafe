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
from flask import request

@bp.route('/dashboard')
@login_required
def dashboard():
    # Get date from query param, default to today
    date_str = request.args.get('date')
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except Exception:
        selected_date = date.today()

    # Show a simplified dashboard for employees
    if current_user.role == 'employee' and not current_user.is_admin:
        total_sales_today = db.session.query(
            func.sum(CoffeeSale.total_sales)
        ).filter(
            func.date(CoffeeSale.date) == selected_date
        ).scalar() or 0
        recent_sales = CoffeeSale.query.filter_by(user_id=current_user.id).filter(
            func.date(CoffeeSale.date) == selected_date
        ).order_by(
            CoffeeSale.date.desc()
        ).limit(5).all()
        return render_template('main/dashboard_employee.html',
            total_sales_today=total_sales_today,
            recent_sales=recent_sales,
            now=datetime.now(pytz.timezone('Africa/Kigali')),
            selected_date=selected_date
        )

    # Always define total_sales_today for managers/admins
    total_sales_today = db.session.query(
        func.sum(CoffeeSale.total_sales)
    ).filter(
        func.date(CoffeeSale.date) == selected_date
    ).scalar() or 0

    # Full dashboard for managers, system_control, admins
    total_products = Product.query.count()
    today = selected_date
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = date(today.year, today.month, 1)
    total_sales_all_time = db.session.query(
        func.sum(CoffeeSale.total_sales)
    ).scalar() or 0
    today_orders_count = db.session.query(CoffeeSale).filter(
        func.date(CoffeeSale.date) == today
    ).count() or 0
    today_revenue = db.session.query(
        func.sum(CoffeeSale.total_sales)
    ).filter(
        func.date(CoffeeSale.date) == today
    ).scalar()
    if today_revenue is None:
        today_revenue = 0
    total_sales_this_week = db.session.query(
        func.sum(CoffeeSale.total_sales)
    ).filter(
        func.date(CoffeeSale.date) >= start_of_week,
        func.date(CoffeeSale.date) <= today
    ).scalar()
    if total_sales_this_week is None:
        total_sales_this_week = 0
    total_sales_this_month = db.session.query(
        func.sum(CoffeeSale.total_sales)
    ).filter(
        func.date(CoffeeSale.date) >= start_of_month,
        func.date(CoffeeSale.date) <= today
    ).scalar()
    if total_sales_this_month is None:
        total_sales_this_month = 0
    sales_by_payment = db.session.query(
        CoffeeSale.payment_mode,
        func.sum(CoffeeSale.total_sales).label('total_sales')
    ).filter(
        func.date(CoffeeSale.date) == today
    ).group_by(CoffeeSale.payment_mode).all() or []
    top_products = db.session.query(
        Product.name,
        func.sum(CoffeeSale.quantity_sold).label('total_quantity'),
        func.sum(CoffeeSale.total_sales).label('total_sales')
    ).join(CoffeeSale).filter(
        func.date(CoffeeSale.date) == today
    ).group_by(Product.name).order_by(
        func.sum(CoffeeSale.total_sales).desc()
    ).limit(5).all() or []
    pending_requisitions = Requisition.query.filter_by(status='pending').count() or 0
    low_stock_items = Product.query.filter(
        Product.current_stock < func.coalesce(Product.min_stock, 5.0)
    ).all() or []
    from sqlalchemy.orm import joinedload
    recent_requisitions = Requisition.query.options(
        joinedload(Requisition.requester)
    ).filter(
        func.date(Requisition.date) == today
    ).order_by(
        Requisition.date.desc()
    ).limit(5).all() or []
    recent_sales = CoffeeSale.query.filter(
        func.date(CoffeeSale.date) == today
    ).order_by(
        CoffeeSale.date.desc()
    ).limit(5).all() or []
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
        now=datetime.now(pytz.timezone('Africa/Kigali')),
        selected_date=selected_date,
        today_orders_count=today_orders_count,
        today_revenue=today_revenue,
        todays_revenue=today_revenue
    )