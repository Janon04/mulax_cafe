from flask_restx import Namespace, Resource, fields
from app.models import Shift, db
from app.auth.forms import ShiftForm

from flask import request, jsonify
from flask_login import login_required, current_user
from datetime import time
from sqlalchemy.exc import SQLAlchemyError

ns = Namespace('shifts', description='Shift operations')

# Model for API documentation
shift_model = ns.model('Shift', {
    'id': fields.Integer(readonly=True, description='Shift identifier'),
    'name': fields.String(required=True, description='Shift name'),
    'start_time': fields.String(description='Start time (HH:MM)'),
    'end_time': fields.String(description='End time (HH:MM)'),
    'description': fields.String(description='Shift description'),
    'grace_period': fields.Integer(description='Grace period in minutes'),
    'is_active': fields.Boolean(description='Whether shift is active')
})

@ns.route('/')
class ShiftList(Resource):
    @ns.doc('list_shifts')
    @ns.marshal_list_with(shift_model)
    @login_required
    def get(self):
        """List all shifts"""
        return Shift.query.all()

    @ns.doc('create_shift')
    @ns.expect(shift_model)
    @ns.marshal_with(shift_model, code=201)
    @login_required
    def post(self):
        """Create a new shift"""
        if not current_user.can_manage_inventory():
            ns.abort(403, "You don't have permission to create shifts")
        
        form = ShiftForm()
        if not form.validate_on_submit():
            return form.errors, 400
            
        try:
            shift = Shift(
                name=form.name.data,
                start_time=form.start_time.data,
                end_time=form.end_time.data,
                description=form.description.data,
                grace_period=form.grace_period.data,
                is_active=form.is_active.data
            )
            db.session.add(shift)
            db.session.commit()
            return shift, 201
        except SQLAlchemyError as e:
            db.session.rollback()
            ns.abort(400, str(e))

@ns.route('/<int:id>')
@ns.response(404, 'Shift not found')
@ns.param('id', 'The shift identifier')
class ShiftResource(Resource):
    @ns.doc('get_shift')
    @ns.marshal_with(shift_model)
    @login_required
    def get(self, id):
        """Fetch a shift given its identifier"""
        shift = Shift.query.get_or_404(id)
        return shift

    @ns.doc('update_shift')
    @ns.expect(shift_model)
    @ns.marshal_with(shift_model)
    @login_required
    def put(self, id):
        """Update a shift given its identifier"""
        if not current_user.can_manage_inventory():
            ns.abort(403, "You don't have permission to update shifts")
            
        shift = Shift.query.get_or_404(id)
        form = ShiftForm()
        
        if not form.validate_on_submit():
            return form.errors, 400
            
        try:
            shift.name = form.name.data
            shift.start_time = form.start_time.data
            shift.end_time = form.end_time.data
            shift.description = form.description.data
            shift.grace_period = form.grace_period.data
            shift.is_active = form.is_active.data
            db.session.commit()
            return shift
        except SQLAlchemyError as e:
            db.session.rollback()
            ns.abort(400, str(e))

    @ns.doc('delete_shift')
    @ns.response(204, 'Shift deleted')
    @login_required
    def delete(self, id):
        """Delete a shift given its identifier"""
        if not current_user.can_manage_inventory():
            ns.abort(403, "You don't have permission to delete shifts")
            
        shift = Shift.query.get_or_404(id)
        
        # Check if shift is in use
        if shift.attendances.count() > 0 or shift.requisitions.count() > 0:
            ns.abort(400, "Cannot delete shift as it has associated records")
            
        try:
            db.session.delete(shift)
            db.session.commit()
            return '', 204
        except SQLAlchemyError as e:
            db.session.rollback()
            ns.abort(400, str(e))

@ns.route('/current')
class CurrentShift(Resource):
    @ns.doc('get_current_shift')
    def get(self):
        """Get the currently active shift"""
        current_shift = Shift.get_current_shift()
        if current_shift:
            return {
                'id': current_shift.id,
                'name': current_shift.name,
                'start_time': current_shift.start_time.strftime('%H:%M'),
                'end_time': current_shift.end_time.strftime('%H:%M'),
                'is_currently_active': current_shift.is_currently_active
            }
        return {'message': 'No active shift found'}, 404