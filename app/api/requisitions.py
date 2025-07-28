from flask_restx import Namespace, Resource, fields
from flask import request
from flask_login import current_user, login_required
from app.models import db, Requisition, Product
from app.extensions import api

ns = Namespace('requisitions', description='Requisition operations')

requisition_model = ns.model('Requisition', {
    'id': fields.Integer(readOnly=True),
    'product_id': fields.Integer(required=True),
    'quantity': fields.Float(required=True),
    'status': fields.String(default='pending')
})

@ns.route('/')
class RequisitionListAPI(Resource):
    @ns.marshal_list_with(requisition_model)
    @login_required
    def get(self):
        """List all requisitions"""
        return Requisition.query.all()

    @ns.expect(requisition_model)
    @ns.marshal_with(requisition_model, code=201)
    @login_required
    def post(self):
        """Create requisition"""
        data = request.get_json()
        requisition = Requisition(
            product_id=data['product_id'],
            quantity=data['quantity'],
            user_id=current_user.id
        )
        db.session.add(requisition)
        db.session.commit()
        return requisition, 201