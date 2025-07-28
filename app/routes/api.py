from flask_restx import Api, Resource, fields, Namespace
from app.extensions import db
from app.models import User, Product, StockMovement, Requisition, CoffeeSale, Client, Order, OrderItem
from flask import request, jsonify
from flask_login import current_user, login_required
from functools import wraps

# Initialize API
api = Api(
    title='Inventory Management API',
    version='1.0',
    description='API for the Inventory Management System',
    doc='/api/docs'  # Swagger UI documentation endpoint
)

# Namespace for better organization
ns = Namespace('api', description='Core API operations')

# Add namespaces to API
api.add_namespace(ns)

# Helper decorator for role-based access
def roles_required(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return {"message": "Authentication required"}, 401
            if not any(getattr(current_user, f'is_{role}')() for role in roles) and not current_user.is_admin:
                return {"message": "Insufficient permissions"}, 403
            return f(*args, **kwargs)
        return decorated_function
    return wrapper