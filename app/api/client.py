from flask_restx import Namespace, Resource, reqparse, fields
from flask import request
from flask_login import current_user, login_required
from app.models import db, Client
from app.extensions import api

ns = Namespace('clients', description='Client operations')

# Models
client_model = ns.model('Client', {
    'id': fields.Integer(readOnly=True),
    'name': fields.String(required=True),
    'phone': fields.String(),
    'email': fields.String(),
    'address': fields.String(),
    'notes': fields.String()
})

client_create_model = ns.model('ClientCreate', {
    'name': fields.String(required=True),
    'phone': fields.String(),
    'email': fields.String(),
    'address': fields.String()
})

# Parser
client_parser = reqparse.RequestParser()
client_parser.add_argument('search', type=str)

@ns.route('/')
class ClientListAPI(Resource):
    @ns.marshal_list_with(client_model)
    @login_required
    def get(self):
        """List clients with optional search"""
        args = client_parser.parse_args()
        query = Client.query
        
        if args['search']:
            search = f"%{args['search']}%"
            query = query.filter(Client.name.ilike(search))
            
        return query.order_by(Client.name).all()

    @ns.expect(client_create_model)
    @ns.marshal_with(client_model, code=201)
    @login_required
    def post(self):
        """Create new client"""
        data = request.get_json()
        client = Client(
            name=data['name'],
            phone=data.get('phone'),
            email=data.get('email'),
            address=data.get('address')
        )
        db.session.add(client)
        db.session.commit()
        return client, 201

@ns.route('/<int:id>')
class ClientAPI(Resource):
    @ns.marshal_with(client_model)
    @login_required
    def get(self, id):
        """Get client details"""
        return Client.query.get_or_404(id)

    @ns.expect(client_create_model)
    @ns.marshal_with(client_model)
    @login_required
    def put(self, id):
        """Update client"""
        client = Client.query.get_or_404(id)
        data = request.get_json()
        
        client.name = data['name']
        client.phone = data.get('phone')
        client.email = data.get('email')
        client.address = data.get('address')
        
        db.session.commit()
        return client

    @login_required
    def delete(self, id):
        """Delete client"""
        client = Client.query.get_or_404(id)
        db.session.delete(client)
        db.session.commit()
        return {'message': 'Client deleted'}, 204