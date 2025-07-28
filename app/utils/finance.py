from datetime import datetime, timedelta
from app.models import db, CoffeeSale, Product

def calculate_daily_sales(days=7):
    """Calculate daily sales for the last N days"""
    sales_data = []
    for i in range(days):
        date = datetime.utcnow() - timedelta(days=(days-1-i))
        start = datetime(date.year, date.month, date.day)
        end = start + timedelta(days=1)
        
        daily_sales = db.session.query(
            db.func.sum(CoffeeSale.total_sales)
        ).filter(
            CoffeeSale.date >= start,
            CoffeeSale.date < end
        ).scalar() or 0
        
        sales_data.append({
            'date': date.strftime('%Y-%m-%d'),
            'day_name': date.strftime('%a'),
            'total': daily_sales
        })
    
    return sales_data

def get_sales_by_category(start_date=None, end_date=None):
    """Get sales grouped by product category"""
    query = db.session.query(
        Product.category,
        db.func.sum(CoffeeSale.quantity_sold).label('total_quantity'),
        db.func.sum(CoffeeSale.total_sales).label('total_sales')
    ).join(CoffeeSale)
    
    if start_date:
        query = query.filter(CoffeeSale.date >= start_date)
    if end_date:
        query = query.filter(CoffeeSale.date <= end_date)
    
    return query.group_by(Product.category).all()

def calculate_profit(start_date, end_date):
    """Calculate gross profit for a period"""
    # Implementation depends on your cost tracking
    pass