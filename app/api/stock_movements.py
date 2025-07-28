from flask_restx import Namespace, Resource, fields
from flask import request
from flask_login import current_user, login_required
from app.models import db, StockMovement, Product
from app.extensions import api

ns = Namespace('stock_movements', description='Stock movement operations')

stock_movement_model = ns.model('StockMovement', {
    'id': fields.Integer(readOnly=True),
    'product_id': fields.Integer(required=True),
    'quantity': fields.Float(required=True),
    'movement_type': fields.String(required=True),
    'notes': fields.String()
})

@ns.route('/')
class StockMovementListAPI(Resource):
    @ns.marshal_list_with(stock_movement_model)
    @login_required
    def get(self):
        """List all stock movements"""
        return StockMovement.query.all()

    @ns.expect(stock_movement_model)
    @ns.marshal_with(stock_movement_model, code=201)
    @login_required
    def post(self):
        """Create stock movement"""
        data = request.get_json()
        product = Product.query.get_or_404(data['product_id'])
        
        movement = StockMovement(
            product_id=data['product_id'],
            quantity=data['quantity'],
            movement_type=data['movement_type'],
            notes=data.get('notes'),
            user_id=current_user.id
        )
        
        db.session.add(movement)
        db.session.commit()
        return movement, 201