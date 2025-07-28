from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime
from app.models import db, User, Employee, Order
from app.auth.forms import admin_required

# Define the Blueprint
bp = Blueprint('employees_bp', __name__, url_prefix='/api/employees')

@bp.route('/', methods=['GET'])
@login_required
@admin_required
def get_employees():
    employees = Employee.query.all()
    return jsonify([emp.to_dict() for emp in employees])

@bp.route('/<int:employee_id>', methods=['GET'])
@login_required
def get_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    return jsonify(employee.to_dict())

@bp.route('/', methods=['POST'])
@login_required
@admin_required
def create_employee():
    data = request.get_json()
    
    required_fields = ['user_id', 'position', 'department']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    user = User.query.get(data['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if Employee.query.get(user.id):
        return jsonify({'error': 'Employee record already exists for this user'}), 400
    
    try:
        employee = Employee(
            user=user,
            position=data['position'],
            department=data['department'],
            employee_id=data.get('employee_id'),
            hire_date=datetime.strptime(data['hire_date'], '%Y-%m-%d').date() if 'hire_date' in data else None,
            is_active=data.get('is_active', True)
        )
        
        db.session.add(employee)
        db.session.commit()
        
        return jsonify(employee.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@bp.route('/<int:employee_id>', methods=['PUT'])
@login_required
@admin_required
def update_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    data = request.get_json()
    
    try:
        if 'position' in data:
            employee.position = data['position']
        if 'department' in data:
            employee.department = data['department']
        if 'employee_id' in data:
            employee.employee_id = data['employee_id']
        if 'hire_date' in data:
            employee.hire_date = datetime.strptime(data['hire_date'], '%Y-%m-%d').date()
        if 'is_active' in data:
            employee.is_active = data['is_active']
        
        db.session.commit()
        return jsonify(employee.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@bp.route('/<int:employee_id>/orders', methods=['GET'])
@login_required
def get_employee_orders(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    orders = Order.query.filter_by(served_by=employee.id)\
                       .order_by(Order.served_at.desc())\
                       .all()
    
    return jsonify([{
        'id': order.id,
        'table_number': order.table_number,
        'total_amount': order.total_amount,
        'served_at': order.served_at.isoformat() if order.served_at else None,
        'status': order.status,
        'server_name': order.server_name
    } for order in orders])

@bp.route('/assign', methods=['POST'])
@login_required
def assign_order_to_employee():
    data = request.get_json()
    
    if 'order_id' not in data or 'employee_id' not in data:
        return jsonify({'error': 'Missing order_id or employee_id'}), 400
    
    order = Order.query.get_or_404(data['order_id'])
    employee = Employee.query.get_or_404(data['employee_id'])
    user = User.query.get_or_404(employee.id)
    
    try:
        order.served_by = employee.id
        order.server_name = user.username
        order.served_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': f'Order {order.id} assigned to {user.username}',
            'order': {
                'id': order.id,
                'server': {
                    'id': employee.id,
                    'name': user.username,
                    'employee_id': employee.employee_id
                },
                'server_name': user.username,
                'served_at': order.served_at.isoformat()
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/active', methods=['GET'])
@login_required
def get_active_employees():
    employees = Employee.query.filter_by(is_active=True).all()
    return jsonify([{
        'id': emp.id,
        'employee_id': emp.employee_id,
        'name': emp.name,
        'position': emp.position
    } for emp in employees])

