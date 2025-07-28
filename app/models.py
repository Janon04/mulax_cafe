from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session, redirect, url_for
from flask_login import UserMixin, current_user
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from app.extensions import db
from sqlalchemy.exc import SQLAlchemyError
from flask_restx import Api, Namespace, fields
from flask import Flask

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='employee')  # Possible values: 'system_control', 'manager', 'employee'
    is_admin = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    must_change_password = db.Column(db.Boolean, default=True)

    # Relationships
    stock_movements = db.relationship('StockMovement', back_populates='user')
    requisitions = db.relationship(
        'Requisition', 
        back_populates='requester', 
        foreign_keys='[Requisition.user_id]'
    )
    approved_requisitions = db.relationship(
        'Requisition',
        back_populates='approver',
        foreign_keys='[Requisition.approved_by]'
    )
    coffee_sales = db.relationship('CoffeeSale', back_populates='recorder')
    orders_recorded = db.relationship('Order', back_populates='recorder', foreign_keys='[Order.recorded_by]')
    orders_served = db.relationship('Order', back_populates='server', foreign_keys='[Order.served_by]')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # Role checking methods
    def is_system_control(self):
        """Check if user has system control role"""
        return self.role == 'system_control' or self.is_admin
    
    def is_manager(self):
        """Check if user has manager role"""
        return self.role == 'manager' or self.is_admin
    
    def is_employee(self):
        """Check if user has employee role"""
        return self.role == 'employee'
    
    def can_view_user_management(self):
        """Check if user can view user management"""
        return self.is_admin or self.is_manager() or self.is_system_control()


class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(100))
    description = db.Column(db.Text)
    category = db.Column(db.String(50), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    current_stock = db.Column(db.Float, default=0)
    unit_price = db.Column(db.Float, default=0)
    cost_price = db.Column(db.Float)
    supplier = db.Column(db.String(100))
    remarks = db.Column(db.String(200))
    tax_rate = db.Column(db.Float, nullable=True)
    reorder_qty = db.Column(db.Float, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    min_stock = db.Column(db.Float, default=5.0)
    
    # Relationships
    stock_movements = db.relationship(
        'StockMovement', 
        back_populates='product', 
        cascade='all, delete-orphan'
    )
    requisitions = db.relationship('Requisition', back_populates='product')
    coffee_sales = db.relationship('CoffeeSale', back_populates='product')
    order_items = db.relationship('OrderItem', back_populates='product')

    def update_stock(self, quantity, movement_type, user_id, notes=None):
        """Helper method to safely update stock"""
        try:
            movement = StockMovement(
                product=self,
                opening_stock=self.current_stock,
                stock_in=quantity if movement_type == 'in' else 0,
                stock_out=quantity if movement_type == 'out' else 0,
                closing_stock=self.current_stock + (quantity if movement_type == 'in' else -quantity),
                movement_type=movement_type,
                user_id=user_id,
                notes=notes
            )
            
            db.session.add(movement)
            self.current_stock = movement.closing_stock
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            return False


class StockMovement(db.Model):
    __tablename__ = 'stock_movements'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    opening_stock = db.Column(db.Float, nullable=False)
    stock_in = db.Column(db.Float, default=0)
    stock_out = db.Column(db.Float, default=0)
    closing_stock = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, default=0)
    movement_type = db.Column(db.String(50), nullable=False)  # 'purchase', 'sale', 'adjustment'
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relationships
    product = db.relationship('Product', back_populates='stock_movements')
    user = db.relationship('User', back_populates='stock_movements')

    def __init__(self, **kwargs):
        if 'product_id' not in kwargs and 'product' not in kwargs:
            raise ValueError("Either product_id or product must be provided")
            
        if 'product' in kwargs:
            kwargs['product_id'] = kwargs.pop('product').id
            
        super().__init__(**kwargs)


class Requisition(db.Model):
    __tablename__ = 'requisitions'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    current_stock = db.Column(db.Float)
    requested_qty = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending')
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approval_date = db.Column(db.DateTime)
    notes = db.Column(db.String(200))
    
    # Relationships
    product = db.relationship('Product', back_populates='requisitions')
    requester = db.relationship('User', back_populates='requisitions', foreign_keys=[user_id])
    approver = db.relationship('User', back_populates='approved_requisitions', foreign_keys=[approved_by])


class CoffeeSale(db.Model):
    __tablename__ = 'coffee_sales'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity_sold = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_sales = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(20))
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relationships
    product = db.relationship('Product', back_populates='coffee_sales')
    recorder = db.relationship('User', back_populates='coffee_sales')


class Client(db.Model):
    __tablename__ = 'clients'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    
    # Relationships
    orders = db.relationship('Order', back_populates='client')


class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'))
    table_id = db.Column(db.Integer, db.ForeignKey('tables.id'), nullable=False)  # Changed from table_number
    status = db.Column(db.String(20), default='pending')
    notes = db.Column(db.Text)
    total_amount = db.Column(db.Float, default=0.0)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    served_at = db.Column(db.DateTime)
    served_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Relationships
    client = db.relationship('Client', back_populates='orders')
    items = db.relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')
    recorder = db.relationship('User', back_populates='orders_recorded', foreign_keys=[recorded_by])
    server = db.relationship('User', back_populates='orders_served', foreign_keys=[served_by])
    table = db.relationship('Table', back_populates='orders')  # New relationship


    # Add to your models.py
class Table(db.Model):
    __tablename__ = 'tables'
    
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, unique=True, nullable=False)
    is_occupied = db.Column(db.Boolean, default=False)
    capacity = db.Column(db.Integer, nullable=False, default=2)
    location = db.Column(db.String(50))  # e.g., "Patio", "Main Dining", "Bar"
    
    orders = db.relationship('Order', back_populates='table', lazy='dynamic')
    
class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    special_instructions = db.Column(db.String(200))
    
    # Relationships
    order = db.relationship('Order', back_populates='items')
    product = db.relationship('Product', back_populates='order_items')

    def __repr__(self):
        return f'<OrderItem {self.id} - Product {self.product_id} x{self.quantity}>'


class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))


class SecureModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))
    
from flask_restx import fields

# Common fields reused across models
timestamp_fields = {
    'created_at': fields.DateTime(dt_format='iso8601', description='Creation timestamp'),
    'updated_at': fields.DateTime(dt_format='iso8601', description='Last update timestamp')
}
class NotificationLog(db.Model):
    __tablename__ = 'notification_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    notification_type = db.Column(db.String(20), nullable=False)  # EMAIL, SMS, etc.
    recipient = db.Column(db.String(255), nullable=False)  # Email address or phone number
    subject = db.Column(db.String(255))  # Added for email subject lines
    content = db.Column(db.Text, nullable=False)  # The message content
    status = db.Column(db.String(20), nullable=False)  # SENT, FAILED, PENDING, DELIVERED
    error_message = db.Column(db.Text)  # Stores any error details
    retry_count = db.Column(db.Integer, default=0)  # Added for tracking retry attempts
    last_retry_at = db.Column(db.DateTime)  # Added for tracking last retry time
    
    # Relationships
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship('User', backref='notification_logs')
    
    # Indexes for better query performance
    __table_args__ = (
        db.Index('ix_notification_logs_timestamp', 'timestamp'),
        db.Index('ix_notification_logs_status', 'status'),
        db.Index('ix_notification_logs_recipient', 'recipient'),
    )
    
    def __repr__(self):
        return f'<NotificationLog {self.id} {self.notification_type} to {self.recipient} ({self.status})>'
    
    def to_dict(self):
        """Convert the notification log to a dictionary for API responses"""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'notification_type': self.notification_type,
            'recipient': self.recipient,
            'subject': self.subject,
            'status': self.status,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'last_retry_at': self.last_retry_at.isoformat() if self.last_retry_at else None,
            'user_id': self.user_id
        }
    
    def mark_as_failed(self, error_message=None):
        """Mark notification as failed and increment retry count"""
        self.status = 'FAILED'
        self.error_message = error_message
        self.retry_count += 1
        self.last_retry_at = datetime.utcnow()
        db.session.add(self)
        db.session.commit()
    
    def mark_as_sent(self):
        """Mark notification as successfully sent"""
        self.status = 'SENT'
        self.last_retry_at = datetime.utcnow()
        db.session.add(self)
        db.session.commit()