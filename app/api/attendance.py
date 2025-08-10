from flask_restx import Namespace, Resource, fields, reqparse, abort
from flask_login import login_required, current_user
from app.models import Attendance, User, Shift, db
from datetime import datetime, date, timedelta
import pytz
from sqlalchemy import and_

api = Namespace('attendance', description='Attendance operations')

# Rwanda timezone
RWANDA_TZ = pytz.timezone('Africa/Kigali')

# API Models
attendance_model = api.model('Attendance', {
    'id': fields.Integer(readOnly=True),
    'user_id': fields.Integer(required=True),
    'shift_id': fields.Integer(required=True),
    'date': fields.Date(required=True),
    'clock_in_time': fields.DateTime(dt_format='iso8601'),
    'clock_out_time': fields.DateTime(dt_format='iso8601'),
    'status': fields.String(),
    'notes': fields.String(),
    'duration': fields.String(),
    'user': fields.Nested(api.model('User', {
        'id': fields.Integer,
        'username': fields.String,
        'full_name': fields.String
    })),
    'shift': fields.Nested(api.model('Shift', {
        'id': fields.Integer,
        'name': fields.String
    }))
})

# Request parsers
clock_in_parser = reqparse.RequestParser()
clock_in_parser.add_argument('shift_id', type=int, required=True, help='Shift ID')
clock_in_parser.add_argument('notes', type=str)

clock_out_parser = reqparse.RequestParser()
clock_out_parser.add_argument('notes', type=str)

attendance_filter_parser = reqparse.RequestParser()
attendance_filter_parser.add_argument('user_id', type=int)
attendance_filter_parser.add_argument('start_date', type=str)
attendance_filter_parser.add_argument('end_date', type=str)
attendance_filter_parser.add_argument('status', type=str)
attendance_filter_parser.add_argument('shift_id', type=int)


# Helpers
def parse_date(date_str):
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        abort(400, 'Invalid date format. Use YYYY-MM-DD')

def get_rwanda_now():
    return datetime.now(RWANDA_TZ)

def enrich_attendance_data(att):
    return {
        **att.__dict__,
        'duration': str(att.get_duration()) if att.get_duration() else None,
        'user': {
            'id': att.user.id,
            'username': att.user.username,
            'full_name': att.user.full_name
        },
        'shift': {
            'id': att.shift.id,
            'name': att.shift.name
        }
    }


# Routes
@api.route('/')
class AttendanceList(Resource):
    @api.expect(attendance_filter_parser)
    @api.marshal_list_with(attendance_model)
    @login_required
    def get(self):
        """List attendance records with optional filters"""
        args = attendance_filter_parser.parse_args()
        query = Attendance.query.join(User).join(Shift)

        if args.user_id:
            if args.user_id != current_user.id and not current_user.is_system_manager():
                abort(403, 'You can only view your own attendance')
            query = query.filter(Attendance.user_id == args.user_id)

        if args.start_date:
            query = query.filter(Attendance.date >= parse_date(args.start_date))
        if args.end_date:
            query = query.filter(Attendance.date <= parse_date(args.end_date))
        if args.status:
            query = query.filter(Attendance.status == args.status)
        if args.shift_id:
            query = query.filter(Attendance.shift_id == args.shift_id)

        if not current_user.is_system_manager():
            query = query.filter(Attendance.user_id == current_user.id)

        query = query.options(db.joinedload(Attendance.user), db.joinedload(Attendance.shift))

        return [enrich_attendance_data(a) for a in query.order_by(Attendance.date.desc()).all()]


@api.route('/clock-in')
class ClockIn(Resource):
    @api.expect(clock_in_parser)
    @api.marshal_with(attendance_model, code=201)
    @login_required
    def post(self):
        """Clock in for today's shift"""
        args = clock_in_parser.parse_args()
        today = get_rwanda_now().date()

        existing = Attendance.query.filter_by(user_id=current_user.id, date=today).first()
        if existing:
            if not existing.clock_out_time:
                abort(400, 'Already clocked in today')
            abort(400, 'Attendance already completed today')

        try:
            shift = Shift.query.get_or_404(args.shift_id)
            attendance = Attendance(
                user_id=current_user.id,
                shift_id=shift.id,
                clock_in_time=get_rwanda_now(),
                notes=args.notes,
                auto_assigned=False
            )
            db.session.add(attendance)
            db.session.commit()

            attendance.status = attendance.calculate_status()
            db.session.commit()

            return enrich_attendance_data(attendance), 201
        except Exception as e:
            db.session.rollback()
            abort(500, f'Clock-in failed: {e}')


@api.route('/clock-out')
class ClockOut(Resource):
    @api.expect(clock_out_parser)
    @api.marshal_with(attendance_model)
    @login_required
    def post(self):
        """Clock out from current shift"""
        today = get_rwanda_now().date()
        attendance = Attendance.query.filter_by(
            user_id=current_user.id,
            date=today,
            clock_out_time=None
        ).first_or_404()

        try:
            attendance.clock_out_time = get_rwanda_now()
            attendance.notes = clock_out_parser.parse_args().get('notes')
            db.session.commit()
            return enrich_attendance_data(attendance)
        except Exception as e:
            db.session.rollback()
            abort(500, f'Clock-out failed: {e}')


@api.route('/<int:id>')
@api.param('id', 'Attendance ID')
class AttendanceResource(Resource):
    @api.marshal_with(attendance_model)
    @login_required
    def get(self, id):
        """Get attendance record by ID"""
        attendance = Attendance.query.options(
            db.joinedload(Attendance.user),
            db.joinedload(Attendance.shift)
        ).get_or_404(id)

        if attendance.user_id != current_user.id and not current_user.is_system_manager():
            abort(403, 'You can only access your own attendance')

        return enrich_attendance_data(attendance)

    @api.expect(clock_out_parser)
    @api.marshal_with(attendance_model)
    @login_required
    def put(self, id):
        """Update notes (Manager only)"""
        if not current_user.is_system_manager():
            abort(403, 'Only managers can update records')

        attendance = Attendance.query.get_or_404(id)
        args = clock_out_parser.parse_args()
        try:
            if args.notes:
                attendance.notes = args.notes
            db.session.commit()
            return enrich_attendance_data(attendance)
        except Exception as e:
            db.session.rollback()
            abort(500, f'Update failed: {e}')

    @login_required
    def delete(self, id):
        """Delete attendance (Admin only)"""
        if not current_user.is_system_admin():
            abort(403, 'Only admins can delete records')

        attendance = Attendance.query.get_or_404(id)
        try:
            db.session.delete(attendance)
            db.session.commit()
            return {'message': 'Deleted successfully'}, 200
        except Exception as e:
            db.session.rollback()
            abort(500, f'Deletion failed: {e}')


@api.route('/today')
class TodayAttendance(Resource):
    @api.marshal_with(attendance_model)
    @login_required
    def get(self):
        """Get today's attendance for current user"""
        today = get_rwanda_now().date()
        attendance = Attendance.query.options(
            db.joinedload(Attendance.user),
            db.joinedload(Attendance.shift)
        ).filter_by(user_id=current_user.id, date=today).first()

        if not attendance:
            abort(404, 'No attendance record for today')

        return enrich_attendance_data(attendance)


@api.route('/summary')
class AttendanceSummary(Resource):
    @api.expect(attendance_filter_parser)
    @login_required
    def get(self):
        """Summary statistics (Manager only)"""
        if not current_user.is_system_manager():
            abort(403, 'Only managers can view summaries')

        args = attendance_filter_parser.parse_args()
        query = Attendance.query

        if args.user_id:
            query = query.filter_by(user_id=args.user_id)
        if args.start_date:
            query = query.filter(Attendance.date >= parse_date(args.start_date))
        if args.end_date:
            query = query.filter(Attendance.date <= parse_date(args.end_date))
        if args.status:
            query = query.filter_by(status=args.status)
        if args.shift_id:
            query = query.filter_by(shift_id=args.shift_id)

        records = query.all()
        present = sum(1 for r in records if r.status == 'present')
        late = sum(1 for r in records if r.status == 'late')
        absent = sum(1 for r in records if r.clock_in_time is None)

        durations = [r.get_duration().total_seconds() for r in records if r.get_duration()]
        avg_duration = timedelta(seconds=sum(durations)/len(durations)) if durations else None

        return {
            'total_records': len(records),
            'present': present,
            'late': late,
            'absent': absent,
            'average_duration': str(avg_duration) if avg_duration else None,
            'total_hours': round(sum(durations)/3600, 2) if durations else 0
        }

# Export for app/__init__.py
ns = api
