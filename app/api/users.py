from flask_restx import Namespace, Resource, reqparse, fields
from flask import request
from flask_login import current_user, login_required
from app.models import db, User
from app.extensions import api 



ns = Namespace('users', description='User operations')

# Models
user_model = ns.model('User', {
    'id': fields.Integer(readOnly=True),
    'username': fields.String(required=True),
    'role': fields.String(required=True, enum=['system_control', 'manager', 'employee']),
    'is_admin': fields.Boolean(default=False),
    'active': fields.Boolean(default=True)
})

user_create_model = ns.model('UserCreate', {
    'username': fields.String(required=True),
    'password': fields.String(required=True),
    'role': fields.String(required=True),
    'is_admin': fields.Boolean(default=False)
})

# Routes
@ns.route('/')
class UserListAPI(Resource):
    @ns.marshal_list_with(user_model)
    @login_required
    def get(self):
        """List all users"""
        return User.query.all()

    @ns.expect(user_create_model)
    @ns.marshal_with(user_model, code=201)
    @login_required
    def post(self):
        """Create a new user"""
        data = request.get_json()
        user = User(
            username=data['username'],
            role=data['role'],
            is_admin=data.get('is_admin', False)
        )
        user.set_password(data['password'])
        db.session.add(user)
        db.session.commit()
        return user, 201

@ns.route('/<int:id>')
class UserAPI(Resource):
    @ns.marshal_with(user_model)
    @login_required
    def get(self, id):
        """Get user details"""
        return User.query.get_or_404(id)

    @ns.expect(user_create_model)
    @ns.marshal_with(user_model)
    @login_required
    def put(self, id):
        """Update user"""
        user = User.query.get_or_404(id)
        data = request.get_json()
        user.username = data['username']
        if 'password' in data:
            user.set_password(data['password'])
        db.session.commit()
        return user

    @login_required
    def delete(self, id):
        """Delete user"""
        user = User.query.get_or_404(id)
        db.session.delete(user)
        db.session.commit()
        return {'message': 'User deleted'}, 204