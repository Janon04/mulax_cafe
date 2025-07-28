from flask_restx import Namespace, Resource, reqparse, fields
from flask import request
from flask_login import current_user, login_required
from app.models import db, Product
from app.extensions import api

# Create namespace
ns = Namespace('products', description='Product operations')

# Models
product_model = ns.model('Product', {
    'id': fields.Integer(readOnly=True, description='Product ID'),
    'sku': fields.String(required=True, description='Stock keeping unit'),
    'name': fields.String(required=True, description='Product name'),
    'brand': fields.String(description='Brand name'),
    'description': fields.String(description='Product description'),
    'category': fields.String(required=True, description='Product category'),
    'unit': fields.String(required=True, description='Measurement unit'),
    'current_stock': fields.Float(default=0, description='Current stock quantity'),
    'unit_price': fields.Float(default=0, description='Selling price per unit'),
    'cost_price': fields.Float(description='Cost price per unit'),
    'supplier': fields.String(description='Supplier information'),
    'tax_rate': fields.Float(description='Tax rate percentage'),
    'reorder_qty': fields.Float(default=0, description='Reorder quantity threshold'),
    'min_stock': fields.Float(default=5.0, description='Minimum stock level')
})

product_create_model = ns.model('ProductCreate', {
    'sku': fields.String(required=True, description='Stock keeping unit'),
    'name': fields.String(required=True, description='Product name'),
    'category': fields.String(required=True, description='Product category'),
    'unit': fields.String(required=True, description='Measurement unit'),
    'unit_price': fields.Float(default=0, description='Selling price per unit'),
    'current_stock': fields.Float(default=0, description='Initial stock quantity'),
    'min_stock': fields.Float(default=5.0, description='Minimum stock level')
})

# Parsers
product_parser = reqparse.RequestParser()
product_parser.add_argument('page', type=int, default=1)
product_parser.add_argument('per_page', type=int, default=20)
product_parser.add_argument('category', type=str)

# Routes
@ns.route('/')
class ProductListAPI(Resource):
    @ns.marshal_list_with(product_model)
    @login_required
    def get(self):
        """List all products with filtering"""
        args = product_parser.parse_args()
        query = Product.query
        
        if args['category']:
            query = query.filter_by(category=args['category'])
            
        return query.paginate(
            page=args['page'],
            per_page=args['per_page']
        ).items

    @ns.expect(product_create_model)
    @ns.marshal_with(product_model, code=201)
    @login_required
    def post(self):
        """Create a new product"""
        data = request.get_json()
        if Product.query.filter_by(sku=data['sku']).first():
            return {"message": "SKU already exists"}, 400
            
        product = Product(
            sku=data['sku'],
            name=data['name'],
            category=data['category'],
            unit=data['unit'],
            unit_price=data.get('unit_price', 0),
            current_stock=data.get('current_stock', 0),
            min_stock=data.get('min_stock', 5.0)
        )
        db.session.add(product)
        db.session.commit()
        return product, 201

@ns.route('/<int:id>')
class ProductAPI(Resource):
    @ns.marshal_with(product_model)
    @login_required
    def get(self, id):
        """Get product details"""
        return Product.query.get_or_404(id)

    @ns.expect(product_create_model)
    @ns.marshal_with(product_model)
    @login_required
    def put(self, id):
        """Update product"""
        product = Product.query.get_or_404(id)
        data = request.get_json()
        
        if 'sku' in data and data['sku'] != product.sku:
            if Product.query.filter_by(sku=data['sku']).first():
                return {"message": "SKU already exists"}, 400
            product.sku = data['sku']
            
        for field in ['name', 'category', 'unit', 'unit_price', 'min_stock']:
            if field in data:
                setattr(product, field, data[field])
        
        db.session.commit()
        return product

    @login_required
    def delete(self, id):
        """Delete product"""
        if not current_user.is_admin:
            return {"message": "Admin required"}, 403
            
        product = Product.query.get_or_404(id)
        db.session.delete(product)
        db.session.commit()
        return {'message': 'Product deleted'}, 204