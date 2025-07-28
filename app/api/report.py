from flask_restx import Namespace, Resource, fields,reqparse
from flask import request
from flask_login import current_user, login_required
from app.models import db, CoffeeSale, Order, Product
from app.extensions import api
from datetime import datetime, timedelta
from sqlalchemy import func

ns = Namespace('reports', description='Reporting operations')

# Models
inventory_summary_model = ns.model('InventorySummary', {
    'total_products': fields.Integer(),
    'low_stock_items': fields.Integer(),
    'out_of_stock_items': fields.Integer(),
    'total_inventory_value': fields.Float()
})

sales_report_model = ns.model('SalesReport', {
    'start_date': fields.DateTime(dt_format='iso8601'),
    'end_date': fields.DateTime(dt_format='iso8601'),
    'total_sales': fields.Float(),
    'total_quantity': fields.Float(),
    'top_products': fields.List(fields.Raw),
    'payment_methods': fields.Raw()
})

# Parser
report_parser = reqparse.RequestParser()
report_parser.add_argument('start_date', type=str, required=True)
report_parser.add_argument('end_date', type=str, required=True)

@ns.route('/inventory')
class InventoryReportAPI(Resource):
    @ns.marshal_with(inventory_summary_model)
    @login_required
    def get(self):
        """Get inventory summary"""
        summary = {
            'total_products': Product.query.count(),
            'low_stock_items': Product.query.filter(
                Product.current_stock <= Product.min_stock
            ).count(),
            'out_of_stock_items': Product.query.filter(
                Product.current_stock <= 0
            ).count(),
            'total_inventory_value': db.session.query(
                func.sum(Product.current_stock * Product.cost_price)
            ).scalar() or 0
        }
        return summary

@ns.route('/sales')
class SalesReportAPI(Resource):
    @ns.marshal_with(sales_report_model)
    @login_required
    def get(self):
        """Generate sales report"""
        args = report_parser.parse_args()
        start_date = datetime.strptime(args['start_date'], '%Y-%m-%d')
        end_date = datetime.strptime(args['end_date'], '%Y-%m-%d') + timedelta(days=1)
        
        # Get sales data
        sales = CoffeeSale.query.filter(
            CoffeeSale.date >= start_date,
            CoffeeSale.date <= end_date
        ).all()
        
        # Calculate totals
        total_sales = sum(sale.total_sales for sale in sales)
        total_quantity = sum(sale.quantity_sold for sale in sales)
        
        # Get payment methods breakdown
        payment_methods = db.session.query(
            CoffeeSale.payment_mode,
            func.sum(CoffeeSale.total_sales).label('total')
        ).filter(
            CoffeeSale.date >= start_date,
            CoffeeSale.date <= end_date
        ).group_by(CoffeeSale.payment_mode).all()
        
        # Get top products
        top_products = db.session.query(
            Product.name,
            func.sum(CoffeeSale.quantity_sold).label('quantity'),
            func.sum(CoffeeSale.total_sales).label('total')
        ).join(CoffeeSale).filter(
            CoffeeSale.date >= start_date,
            CoffeeSale.date <= end_date
        ).group_by(Product.name).order_by(
            func.sum(CoffeeSale.total_sales).desc()
        ).limit(5).all()
        
        return {
            'start_date': start_date,
            'end_date': end_date - timedelta(days=1),
            'total_sales': total_sales,
            'total_quantity': total_quantity,
            'payment_methods': {pmt.payment_mode: pmt.total for pmt in payment_methods},
            'top_products': [
                {'name': p.name, 'quantity': p.quantity, 'total': p.total}
                for p in top_products
            ]
        }