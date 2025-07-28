from flask_restx import Namespace, Resource, reqparse, fields
from flask import request
from flask_login import current_user, login_required
from app.models import db, Order, OrderItem, Client, Product
from app.extensions import api
from datetime import datetime

ns = Namespace('orders', description='Order operations')

# Models
order_item_model = ns.model('OrderItem', {
    'id': fields.Integer(readOnly=True),
    'product_id': fields.Integer(required=True),
    'quantity': fields.Float(required=True),
    'unit_price': fields.Float(required=True),
    'special_instructions': fields.String()
})

order_item_create_model = ns.model('OrderItemCreate', {
    'product_id': fields.Integer(required=True),
    'quantity': fields.Float(required=True),
    'special_instructions': fields.String()
})

order_model = ns.model('Order', {
    'id': fields.Integer(readOnly=True),
    'client_id': fields.Integer(),
    'table_number': fields.Integer(required=True),
    'status': fields.String(enum=['pending', 'preparing', 'served', 'cancelled', 'paid']),
    'total_amount': fields.Float(),
    'notes': fields.String(),
    'date': fields.DateTime(dt_format='iso8601'),
    'items': fields.List(fields.Nested(order_item_model))
})

order_create_model = ns.model('OrderCreate', {
    'client_id': fields.Integer(),
    'table_number': fields.Integer(required=True),
    'items': fields.List(fields.Nested(order_item_create_model), required=True),
    'notes': fields.String()
})

order_update_model = ns.model('OrderUpdate', {
    'status': fields.String(enum=['preparing', 'served', 'cancelled', 'paid']),
    'served_by': fields.Integer()
})

# Parser
order_parser = reqparse.RequestParser()
order_parser.add_argument('status', type=str)
order_parser.add_argument('date', type=str)

@ns.route('/')
class OrderListAPI(Resource):
    @ns.marshal_list_with(order_model)
    @login_required
    def get(self):
        """List orders with filters"""
        args = order_parser.parse_args()
        query = Order.query
        
        if args['status']:
            query = query.filter_by(status=args['status'])
        if args['date']:
            query = query.filter(db.func.date(Order.date) == args['date'])
            
        return query.order_by(Order.date.desc()).all()

    @ns.expect(order_create_model)
    @ns.marshal_with(order_model, code=201)
    @login_required
    def post(self):
        """Create new order"""
        data = request.get_json()
        
        order = Order(
            client_id=data.get('client_id'),
            table_number=data['table_number'],
            status='pending',
            recorded_by=current_user.id,
            total_amount=0  # Will be calculated
        )
        
        # Process items
        total = 0
        for item_data in data['items']:
            product = Product.query.get_or_404(item_data['product_id'])
            order_item = OrderItem(
                product_id=item_data['product_id'],
                quantity=item_data['quantity'],
                unit_price=product.unit_price,
                special_instructions=item_data.get('special_instructions')
            )
            total += order_item.quantity * order_item.unit_price
            order.items.append(order_item)
        
        order.total_amount = total
        db.session.add(order)
        db.session.commit()
        return order, 201

@ns.route('/<int:id>')
class OrderAPI(Resource):
    @ns.marshal_with(order_model)
    @login_required
    def get(self, id):
        """Get order details"""
        return Order.query.get_or_404(id)

    @ns.expect(order_update_model)
    @ns.marshal_with(order_model)
    @login_required
    def put(self, id):
        """Update order status"""
        order = Order.query.get_or_404(id)
        data = request.get_json()
        
        if 'status' in data:
            order.status = data['status']
            if data['status'] == 'served':
                order.served_by = current_user.id
                order.served_at = datetime.utcnow()
        
        db.session.commit()
        return order