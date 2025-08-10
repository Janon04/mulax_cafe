from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, time
from app.models import Shift, Attendance, User, Order
from app.extensions import db
from app.auth.decorators import admin_required, requires_shift_management
from sqlalchemy.exc import SQLAlchemyError
from datetime import timedelta


bp = Blueprint('attendance', __name__, url_prefix='/attendance')

def get_current_shift():
    """Helper function to get the current active shift based on time"""
    now = datetime.now().time()
    return Shift.query.filter(
        Shift.is_active == True,
        Shift.start_time <= now,
        Shift.end_time >= now
    ).first()

@bp.route('/clock-in', methods=['POST'])
@login_required
def clock_in():
    """Clock in an employee and assign to current shift"""
    current_shift = get_current_shift()
    
    if not current_shift:
        flash('No active shift currently', 'danger')
        return redirect(request.referrer or url_for('main.dashboard'))
    
    # Check if already clocked in today
    existing_attendance = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        db.func.date(Attendance.clock_in_time) == date.today(),
        Attendance.clock_out_time == None
    ).first()
    
    if existing_attendance:
        flash('You are already clocked in', 'warning')
        return redirect(request.referrer or url_for('main.dashboard'))
    
    try:
        # Assign user to current shift
        current_user.current_shift = current_shift
        
        # Create attendance record
        attendance = Attendance(
            user_id=current_user.id,
            shift_id=current_shift.id,
            date=date.today(),
            clock_in_time=datetime.now(),
            status='present'
        )
        
        db.session.add(attendance)
        db.session.commit()
        
        flash(f'Clocked in to {current_shift.name} shift successfully', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash('Error clocking in. Please try again.', 'danger')
    
    return redirect(request.referrer or url_for('main.dashboard'))

@bp.route('/clock-out', methods=['POST'])
@login_required
def clock_out():
    """Clock out an employee from current shift"""
    # Find active attendance record
    attendance = Attendance.query.filter(
        Attendance.user_id == current_user.id,
        db.func.date(Attendance.clock_in_time) == date.today(),
        Attendance.clock_out_time == None
    ).first()
    
    if not attendance:
        flash('No active attendance record found', 'warning')
        return redirect(request.referrer or url_for('main.dashboard'))
    
    try:
        attendance.clock_out_time = datetime.now()
        
        # Calculate hours worked
        time_worked = attendance.clock_out_time - attendance.clock_in_time
        attendance.hours_worked = time_worked.total_seconds() / 3600  # Convert to hours
        
        # Remove user from shift assignment
        if current_user.current_shift_id == attendance.shift_id:
            current_user.current_shift_id = None
        
        db.session.commit()
        flash('Clocked out successfully', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        flash('Error clocking out. Please try again.', 'danger')
    
    return redirect(request.referrer or url_for('main.dashboard'))

@bp.route('/records')
@login_required
@requires_shift_management
def list_attendance():
    """List attendance records with shift filtering"""
    # Get filter parameters
    date_filter = request.args.get('date', date.today().isoformat())
    user_filter = request.args.get('user_id')
    shift_filter = request.args.get('shift_id')
    status_filter = request.args.get('status', 'all')
    
    query = Attendance.query.join(User).join(Shift)
    
    # Apply filters
    try:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
        query = query.filter(db.func.date(Attendance.clock_in_time) == filter_date)
    except ValueError:
        filter_date = date.today()
        flash('Invalid date format', 'warning')
    
    if user_filter:
        query = query.filter(Attendance.user_id == user_filter)
    
    if shift_filter:
        query = query.filter(Attendance.shift_id == shift_filter)
    
    if status_filter != 'all':
        query = query.filter(Attendance.status == status_filter)
    
    # Get results
    attendances = query.order_by(
        Attendance.clock_in_time.desc()
    ).all()
    
    # Get filter options
    users = User.query.filter_by(active=True).order_by(User.username).all()
    shifts = Shift.query.filter_by(is_active=True).order_by(Shift.name).all()
    
    return render_template('attendance/records.html',
                         attendances=attendances,
                         users=users,
                         shifts=shifts,
                         current_date=filter_date,
                         filters={
                             'date': date_filter,
                             'user_id': user_filter,
                             'shift_id': shift_filter,
                             'status': status_filter
                         })

@bp.route('/shift-performance')
@login_required
@requires_shift_management
def shift_performance():
    """Show performance metrics by shift"""
    shift_id = request.args.get('shift_id')
    start_date = request.args.get('start_date', (date.today() - timedelta(days=7)).isoformat()
    end_date = request.args.get('end_date', date.today().isoformat())
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        start_date = date.today() - timedelta(days=7)
        end_date = date.today()
        flash('Invalid date format', 'warning')
    
    # Base query for shift performance
    shift_query = db.session.query(
        Shift.name,
        db.func.count(Attendance.id).label('total_attendances'),
        db.func.avg(Attendance.hours_worked).label('avg_hours_worked'),
        db.func.count(Order.id).label('total_orders'),
        db.func.sum(Order.total_amount).label('total_sales')
    ).outerjoin(Attendance, Shift.id == Attendance.shift_id
    ).outerjoin(Order, Shift.id == Order.shift_id
    ).filter(
        db.func.date(Attendance.clock_in_time).between(start_date, end_date)
    )
    
    if shift_id:
        shift_query = shift_query.filter(Shift.id == shift_id)
    
    shift_stats = shift_query.group_by(Shift.id).all()
    
    # Get all active shifts for filter dropdown
    shifts = Shift.query.filter_by(is_active=True).order_by(Shift.name).all()
    
    return render_template('attendance/shift_performance.html',
                         shift_stats=shift_stats,
                         shifts=shifts,
                         selected_shift=shift_id,
                         start_date=start_date,
                         end_date=end_date)

@bp.route('/user-shift-report/<int:user_id>')
@login_required
@requires_shift_management
def user_shift_report(user_id):
    """Generate report of user's shifts and performance"""
    user = User.query.get_or_404(user_id)
    
    # Get date range filters
    start_date = request.args.get('start_date', (date.today() - timedelta(days=30)).isoformat()
    end_date = request.args.get('end_date', date.today()).isoformat()
    
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        start_date = date.today() - timedelta(days=30)
        end_date = date.today()
        flash('Invalid date format', 'warning'))
    
    # Get attendance records
    attendances = Attendance.query.filter(
        Attendance.user_id == user_id,
        db.func.date(Attendance.clock_in_time).between(start_date, end_date)
    ).order_by(Attendance.clock_in_time.desc()).all()
    
    # Get order statistics
    order_stats = db.session.query(
        Shift.name,
        db.func.count(Order.id).label('order_count'),
        db.func.sum(Order.total_amount).label('total_sales')
    ).join(Order, Order.shift_id == Shift.id
    ).filter(
        Order.user_id == user_id,
        db.func.date(Order.created_at).between(start_date, end_date)
    ).group_by(Shift.name).all()
    
    return render_template('attendance/user_shift_report.html',
                         user=user,
                         attendances=attendances,
                         order_stats=order_stats,
                         start_date=start_date,
                         end_date=end_date))