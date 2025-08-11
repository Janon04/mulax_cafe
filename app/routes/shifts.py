from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from datetime import time, datetime
import pytz
from app.models import Shift, User, Attendance
from app.extensions import db
from app.auth.forms import ShiftForm
from app.utils.shift_utils import get_current_shift
from app.auth.decorators import requires_shift_management
from flask import jsonify


bp = Blueprint('shifts', __name__, url_prefix='/shifts')
shifts_bp = Blueprint('shifts', __name__)

@bp.route('/list.html')  # Single /shifts prefix
@login_required
def shift_list():
    shifts = Shift.query.order_by(Shift.start_time).all()
    # Annotate each shift with a display_name property for day/night
    for shift in shifts:
        if shift.start_time == time(7, 0) and shift.end_time == time(17, 0):
            shift.display_name = 'Day Shift'
        else:
            shift.display_name = 'Night Shift'
    return render_template('shifts/list.html', shifts=shifts)


@bp.route('/current')
@login_required
def current_shift():
    current_shift = get_current_shift()
    if current_shift:
        # Determine display_name for dashboard
        if current_shift.start_time == time(7, 0) and current_shift.end_time == time(17, 0):
            display_name = 'Day Shift'
        else:
            display_name = 'Night Shift'
        return jsonify({
            'id': current_shift.id,
            'name': display_name,
            'start_time': current_shift.start_time.strftime('%H:%M'),
            'end_time': current_shift.end_time.strftime('%H:%M'),
            'is_active': current_shift.is_active,
            'current_time': datetime.now(pytz.timezone('Africa/Kigali')).strftime('%H:%M'),
            'is_currently_active': current_shift.is_currently_active()
        })
    return jsonify({'message': 'We have closed!!'}), 404
   
@bp.route('/create', methods=['GET', 'POST'])
@login_required
@requires_shift_management
def create_shift():
    form = ShiftForm()

    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                # Combine time parts into 12-hour format strings
                start_time_str = f"{form.start_hour.data}:{form.start_minute.data} {form.start_ampm.data}"
                end_time_str = f"{form.end_hour.data}:{form.end_minute.data} {form.end_ampm.data}"

                # Parse 12-hour format with AM/PM
                try:
                    start_time = datetime.strptime(start_time_str, '%I:%M %p').time()
                    end_time = datetime.strptime(end_time_str, '%I:%M %p').time()
                except ValueError:
                    flash('Invalid time format. Please use HH:MM AM/PM format (e.g. 07:00 AM).', 'danger')
                    return render_template('shifts/create.html', form=form)

                if start_time >= end_time:
                    flash('End time must be after start time', 'danger')
                    return render_template('shifts/create.html', form=form)

                # Check for overlapping shifts
                overlapping_shift = Shift.query.filter(
                    db.or_(
                        db.and_(Shift.start_time <= start_time, Shift.end_time > start_time),
                        db.and_(Shift.start_time < end_time, Shift.end_time >= end_time),
                        db.and_(Shift.start_time >= start_time, Shift.end_time <= end_time)
                    )
                ).first()

                if overlapping_shift:
                    flash(
                        f'This shift overlaps with existing shift: {overlapping_shift.name} '
                        f'({overlapping_shift.start_time.strftime("%I:%M %p")} - '
                        f'{overlapping_shift.end_time.strftime("%I:%M %p")})',
                        'danger'
                    )
                    return render_template('shifts/create.html', form=form)

                if not 0 <= form.grace_period.data <= 60:
                    flash('Grace period must be between 0 and 60 minutes', 'danger')
                    return render_template('shifts/create.html', form=form)

                shift = Shift(
                    name=form.name.data.strip(),
                    start_time=start_time,
                    end_time=end_time,
                    description=form.description.data.strip() if form.description.data else None,
                    grace_period=form.grace_period.data,
                    is_active=form.is_active.data,
                    created_by=current_user.id,
                    created_at=datetime.now(pytz.timezone('Africa/Kigali'))
                )

                db.session.add(shift)
                db.session.commit()

                current_app.logger.info(
                    f"Shift created - ID: {shift.id}, Name: {shift.name}, "
                    f"Time: {start_time_str} to {end_time_str}, By: {current_user.username}"
                )
                flash('Shift created successfully', 'success')
                return redirect(url_for('shifts.shift_list'))

            except IntegrityError as e:
                db.session.rollback()
                current_app.logger.error(f"Integrity error creating shift: {str(e)}")
                flash('Shift with this name already exists', 'danger')
            except ValueError as e:
                db.session.rollback()
                flash(f'Invalid data: {str(e)}', 'danger')
            except SQLAlchemyError as e:
                db.session.rollback()
                flash('Database error occurred. Please try again.', 'danger')
            except Exception as e:
                db.session.rollback()
                flash('An unexpected error occurred. Please contact support.', 'danger')
        else:
            flash('Please correct the errors in the form.', 'danger')
        return render_template('shifts/create.html', form=form)

    # GET request
    return render_template('shifts/create.html', form=form)

@bp.route('/<int:shift_id>/edit', methods=['GET', 'POST'])
@login_required
@requires_shift_management
def edit_shift(shift_id):
    shift = Shift.query.get_or_404(shift_id)
    form = ShiftForm(obj=shift)

    if request.method == 'GET':
        form.start_time.data = shift.start_time.strftime('%H:%M')
        form.end_time.data = shift.end_time.strftime('%H:%M')

    if form.validate_on_submit():
        try:
            new_start = datetime.strptime(form.start_time.data, '%H:%M').time()
            new_end = datetime.strptime(form.end_time.data, '%H:%M').time()

            if new_start >= new_end:
                flash('End time must be after start time', 'danger')
                return render_template('shifts/edit.html', form=form, shift=shift)

            overlapping = Shift.query.filter(
                Shift.id != shift_id,
                ((Shift.start_time <= new_start) & (Shift.end_time > new_start)) |
                ((Shift.start_time < new_end) & (Shift.end_time >= new_end)) |
                ((Shift.start_time >= new_start) & (Shift.end_time <= new_end))
            ).first()

            if overlapping:
                flash(f'This shift overlaps with {overlapping.name} shift', 'danger')
                return render_template('shifts/edit.html', form=form, shift=shift)

            shift.name = form.name.data
            shift.start_time = new_start
            shift.end_time = new_end
            shift.description = form.description.data
            shift.grace_period = form.grace_period.data
            shift.is_active = form.is_active.data

            db.session.commit()
            flash('Shift updated successfully', 'success')
            return redirect(url_for('shifts.shift_list'))

        except ValueError as e:
            db.session.rollback()
            flash(f'Invalid time format: {str(e)}', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            flash('Error updating shift. Please try again.', 'danger')

    return render_template('shifts/edit.html', form=form, shift=shift)

@bp.route('/<int:shift_id>/delete', methods=['POST'])
@login_required
@requires_shift_management
def delete_shift(shift_id):
    shift = Shift.query.get_or_404(shift_id)
    try:
        has_attendance = db.session.query(Attendance.query.filter_by(shift_id=shift_id).exists()).scalar()
        has_users = db.session.query(User.query.filter_by(current_shift_id=shift_id).exists()).scalar()

        if has_attendance or has_users:
            flash('Cannot delete shift as it has associated records', 'danger')
            return redirect(url_for('shifts.list'))

        db.session.delete(shift)
        db.session.commit()
        flash('Shift deleted successfully', 'success')

    except SQLAlchemyError as e:
        db.session.rollback()
        flash('Error deleting shift. Please try again.', 'danger')

    return redirect(url_for('shifts.shift_list'))

@bp.route('/current')
@login_required
def current_shift():
    current_shift = get_current_shift()
    if current_shift:
        return jsonify({
            'id': current_shift.id,
            'name': current_shift.name,
            'start_time': current_shift.start_time.strftime('%H:%M'),
            'end_time': current_shift.end_time.strftime('%H:%M'),
            'is_active': current_shift.is_active,
            'current_time': datetime.now(pytz.timezone('Africa/Kigali')).strftime('%H:%M'),
            'is_currently_active': current_shift.is_currently_active()
        })
    return jsonify({'message': 'No active shift found'}), 404

@bp.route('/<int:shift_id>/users')
@login_required
@requires_shift_management
def shift_users(shift_id):
    shift = Shift.query.get_or_404(shift_id)
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('ITEMS_PER_PAGE', 10)

    users = User.query.filter_by(current_shift_id=shift_id).paginate(page=page, per_page=per_page)
    return render_template('shifts/users.html', shift=shift, users=users)

@bp.route('/<int:shift_id>/attendance')
@login_required
@requires_shift_management
def shift_attendance(shift_id):
    shift = Shift.query.get_or_404(shift_id)
    date_filter = request.args.get('date', datetime.now(pytz.timezone('Africa/Kigali')).date().isoformat())

    try:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
    except ValueError:
        filter_date = datetime.now(pytz.timezone('Africa/Kigali')).date()

    attendance = Attendance.query.filter(
        Attendance.shift_id == shift_id,
        db.func.date(Attendance.login_time) == filter_date
    ).order_by(Attendance.login_time.desc()).all()

    return render_template('shifts/attendance.html', shift=shift, attendance=attendance, filter_date=filter_date)

@bp.route('/auto-assign', methods=['POST'])
@login_required
@requires_shift_management
def auto_assign_shifts():
    try:
        users = User.query.filter(User.is_admin == False, User.is_system_control == False).all()
        assigned = 0

        for user in users:
            current_shift = get_current_shift()
            if current_shift and user.current_shift_id != current_shift.id:
                user.current_shift = current_shift
                assigned += 1

        db.session.commit()
        flash(f'Successfully auto-assigned {assigned} users to current shift', 'success')

    except SQLAlchemyError as e:
        db.session.rollback()
        flash('Error auto-assigning shifts. Please try again.', 'danger')

    return redirect(url_for('shifts.shift_list'))
