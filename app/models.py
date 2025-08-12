from datetime import datetime, time
import pytz
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session, redirect, url_for
from flask_login import UserMixin, current_user
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from app.extensions import db
from sqlalchemy.exc import SQLAlchemyError
from flask_restx import Api, Namespace, fields
from flask import Flask

class Shift(db.Model):
    __tablename__ = 'shifts'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.Time, nullable=False)  # e.g., 07:00:00
    end_time = db.Column(db.Time, nullable=False)   # e.g., 17:00:00
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    users = db.relationship('User', back_populates='current_shift')
    attendances = db.relationship('Attendance', back_populates='shift')
    orders = db.relationship('Order', back_populates='shift')

    def is_currently_active(self):
        import pytz
        now = datetime.now(pytz.timezone('Africa/Kigali')).time()

class Attendance(db.Model):
    __tablename__ = 'attendances'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(pytz.timezone('Africa/Kigali')).date())
    login_time = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(pytz.timezone('Africa/Kigali')))
    logout_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='present')  # present, late, absent, etc.
    
    # Relationships
    user = db.relationship('User', back_populates='attendances')
    shift = db.relationship('Shift', back_populates='attendances')

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='employee')  # Possible values: 'system_control', 'manager', 'employee'
    is_admin = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(pytz.timezone('Africa/Kigali')))
    last_login = db.Column(db.DateTime)
    must_change_password = db.Column(db.Boolean, default=True)
    current_shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'))
    
    # Relationships
    current_shift = db.relationship('Shift', back_populates='users')
    attendances = db.relationship('Attendance', back_populates='user')
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
    orders_created = db.relationship('Order', back_populates='user', foreign_keys='Order.user_id')

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
    
    def get_current_shift(self):
        """Get the current active shift for this user"""
        if self.is_admin or self.is_system_control():
            return None  # Admins can see all shifts
        return self.current_shift

    def can_manage_shifts(self):
        """Check if user can manage shifts"""
        return self.is_admin or self.role == 'manager'



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
    last_updated = db.Column(db.DateTime, 
                           default=lambda: datetime.now(pytz.timezone('Africa/Kigali')), 
                           onupdate=lambda: datetime.now(pytz.timezone('Africa/Kigali')))
    min_stock = db.Column(db.Float, default=5.0)
    
    # Soft delete fields
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    deleted_at = db.Column(db.DateTime)
    
    # Relationships with modified queries to handle soft deletes
    stock_movements = db.relationship(
        'StockMovement', 
        back_populates='product',
        primaryjoin="and_(Product.id==StockMovement.product_id, Product.is_active==True)"
    )
    
    requisitions = db.relationship(
        'Requisition',
        back_populates='product',
        primaryjoin="and_(Product.id==Requisition.product_id, Product.is_active==True)"
    )
    
    coffee_sales = db.relationship(
        'CoffeeSale',
        back_populates='product',
        primaryjoin="and_(Product.id==CoffeeSale.product_id, Product.is_active==True)"
    )
    
    order_items = db.relationship(
        'OrderItem',
        back_populates='product',
        primaryjoin="and_(Product.id==OrderItem.product_id, Product.is_active==True)"
    )

    def update_stock(self, quantity, movement_type, user_id, notes=None):
        """Helper method to safely update stock"""
        if not self.is_active:
            raise ValueError("Cannot update stock for inactive product")
            
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

    def soft_delete(self):
        """Mark product as inactive"""
        self.is_active = False
        self.deleted_at = datetime.now(pytz.timezone('Africa/Kigali'))
        db.session.commit()

    def restore(self):
        """Reactivate a soft-deleted product"""
        self.is_active = True
        self.deleted_at = None
        db.session.commit()

    @classmethod
    def get_active(cls):
        """Query only active products"""
        return cls.query.filter_by(is_active=True)

    @classmethod
    def get_inactive(cls):
        """Query only inactive products"""
        return cls.query.filter_by(is_active=False)

    def __repr__(self):
        return f'<Product {self.sku} - {self.name} ({"Active" if self.is_active else "Inactive"})>'


class StockMovement(db.Model):
    __tablename__ = 'stock_movements'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    date = db.Column(db.DateTime, default=lambda: datetime.now(pytz.timezone('Africa/Kigali')), nullable=False)
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
    date = db.Column(db.DateTime, default=lambda: datetime.now(pytz.timezone('Africa/Kigali')))
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    current_stock = db.Column(db.Float)
    requested_qty = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending')
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approval_date = db.Column(db.DateTime)
    notes = db.Column(db.String(200))
    shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'), nullable=True)
    
    # Relationships
    product = db.relationship('Product', back_populates='requisitions')
    requester = db.relationship('User', back_populates='requisitions', foreign_keys=[user_id])
    approver = db.relationship('User', back_populates='approved_requisitions', foreign_keys=[approved_by])
    shift = db.relationship('Shift')


class CoffeeSale(db.Model):
    __tablename__ = 'coffee_sales'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=lambda: datetime.now(pytz.timezone('Africa/Kigali')))
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity_sold = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_sales = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(20))
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    waiter_id = db.Column(db.Integer, db.ForeignKey('waiters.id'), nullable=True)
    shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'), nullable=True)

    # Relationships
    product = db.relationship('Product', back_populates='coffee_sales')
    recorder = db.relationship('User', back_populates='coffee_sales')
    waiter = db.relationship('Waiter', foreign_keys=[waiter_id])
    shift = db.relationship('Shift')


class Client(db.Model):
    __tablename__ = 'clients'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(pytz.timezone('Africa/Kigali')))
    notes = db.Column(db.Text)
    
    # Relationships
    orders = db.relationship('Order', back_populates='client')


class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'))
    table_id = db.Column(db.Integer, db.ForeignKey('tables.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    notes = db.Column(db.Text)
    total_amount = db.Column(db.Float, default=0.0)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # For legacy compatibility
    waiter_id = db.Column(db.Integer, db.ForeignKey('waiters.id'), nullable=True)
    date = db.Column(db.DateTime, default=lambda: datetime.now(pytz.timezone('Africa/Kigali')))
    served_at = db.Column(db.DateTime)
    served_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Customer who placed the order
    
    # Relationships - all explicitly specifying foreign keys
    client = db.relationship('Client', back_populates='orders')
    items = db.relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')
    recorder = db.relationship('User', 
                             back_populates='orders_recorded', 
                             foreign_keys=[recorded_by])
    server = db.relationship('User', 
                           back_populates='orders_served', 
                           foreign_keys=[served_by])
    table = db.relationship('Table', back_populates='orders')
    shift = db.relationship('Shift', back_populates='orders')
    user = db.relationship('User',  # This is the customer relationship
                         back_populates='orders_created', 
                         foreign_keys=[user_id])
    waiter = db.relationship('Waiter', foreign_keys=[waiter_id])
    
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
    
    def get_query(self):
        """Override to filter by shift if user is not admin"""
        query = super().get_query()
        
        if not current_user.is_admin and not current_user.is_system_control():
            if hasattr(self.model, 'user') and hasattr(self.model.user, 'current_shift'):
                # Filter by current user's shift
                return query.join(self.model.user).filter(
                    User.current_shift_id == current_user.current_shift_id
                )
            elif hasattr(self.model, 'shift'):
                # Filter by shift directly
                return query.filter_by(shift_id=current_user.current_shift_id)
        
        return query

    def get_list(self, page, sort_field, sort_desc, search, filters, page_size=None):
        """Override list view to show shift info"""
        count, data = super().get_list(page, sort_field, sort_desc, search, filters, page_size)
        
        # Add shift info to context if not admin
        if not current_user.is_admin and not current_user.is_system_control():
            self._template_args['current_shift'] = current_user.current_shift
        
        return count, data
class NotificationLog(db.Model):
    __tablename__ = 'notification_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(pytz.timezone('Africa/Kigali')), index=True)
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
        self.last_retry_at = datetime.now(pytz.timezone('Africa/Kigali'))
        db.session.add(self)
        db.session.commit()
    
    def mark_as_sent(self):
        """Mark notification as successfully sent"""
        self.status = 'SENT'
        self.last_retry_at = datetime.now(pytz.timezone('Africa/Kigali'))
        db.session.add(self)
        db.session.commit()
class Waiter(db.Model):
    __tablename__ = 'waiters'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True, unique=True)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<Waiter {self.name}>"