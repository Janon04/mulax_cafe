from flask_restx import Namespace, Resource, reqparse, fields
from flask import request
from flask_login import current_user, login_required
from app.models import db, CoffeeSale, Product
from app.extensions import api

ns = Namespace('coffee_sales', description='Coffee sale operations')

# Models
coffee_sale_model = ns.model('CoffeeSale', {
    'id': fields.Integer(readOnly=True),
    'date': fields.DateTime(dt_format='iso8601'),
    'product_id': fields.Integer(required=True),
    'quantity_sold': fields.Float(required=True),
    'unit_price': fields.Float(required=True),
    'total_sales': fields.Float(required=True),
    'payment_mode': fields.String(enum=['cash', 'card', 'mobile', 'credit']),
    'recorded_by': fields.Integer()
})

coffee_sale_create_model = ns.model('CoffeeSaleCreate', {
    'product_id': fields.Integer(required=True),
    'quantity_sold': fields.Float(required=True),
    'unit_price': fields.Float(),
    'payment_mode': fields.String(required=True, enum=['cash', 'card', 'mobile', 'credit'])
})

# Parser for filtering
sale_parser = reqparse.RequestParser()
sale_parser.add_argument('start_date', type=str)
sale_parser.add_argument('end_date', type=str)
sale_parser.add_argument('payment_mode', type=str)

@ns.route('/')
class CoffeeSaleListAPI(Resource):
    @ns.marshal_list_with(coffee_sale_model)
    @login_required
    def get(self):
        """List coffee sales with filters"""
        args = sale_parser.parse_args()
        query = CoffeeSale.query
        
        if args['start_date']:
            query = query.filter(CoffeeSale.date >= args['start_date'])
        if args['end_date']:
            query = query.filter(CoffeeSale.date <= args['end_date'])
        if args['payment_mode']:
            query = query.filter_by(payment_mode=args['payment_mode'])
            
        return query.order_by(CoffeeSale.date.desc()).all()

    @ns.expect(coffee_sale_create_model)
    @ns.marshal_with(coffee_sale_model, code=201)
    @login_required
    def post(self):
        """Record new coffee sale"""
        data = request.get_json()
        product = Product.query.get_or_404(data['product_id'])
        
        sale = CoffeeSale(
            product_id=data['product_id'],
            quantity_sold=data['quantity_sold'],
            unit_price=data.get('unit_price', product.unit_price),
            payment_mode=data['payment_mode'],
            recorded_by=current_user.id
        )
        
        # Calculate total
        sale.total_sales = sale.quantity_sold * sale.unit_price
        
        # Update product stock
        product.current_stock -= sale.quantity_sold
        
        db.session.add(sale)
        db.session.commit()
        return sale, 201

@ns.route('/<int:id>')
class CoffeeSaleAPI(Resource):
    @ns.marshal_with(coffee_sale_model)
    @login_required
    def get(self, id):
        """Get coffee sale details"""
        return CoffeeSale.query.get_or_404(id)