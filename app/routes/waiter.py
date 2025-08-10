# routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from app import db
from app.models import Waiter
from app.auth.forms import WaiterForm

bp = Blueprint('waiters', __name__, url_prefix='/waiters')

@bp.route('/new', methods=['GET', 'POST'])
def register_waiter():
    form = WaiterForm()
    if form.validate_on_submit():
        waiter = Waiter(
            name=form.name.data,
            phone_number=form.phone_number.data,
            email=form.email.data,
            is_active=form.is_active.data
        )
        db.session.add(waiter)
        db.session.commit()
        flash('Waiter registered successfully!', 'success')
        return redirect(url_for('waiters.list_waiters'))
    return render_template('waiters/register_waiter.html', form=form)

@bp.route('/', methods=['GET'])
def list_waiters():
    waiters = Waiter.query.all()
    return render_template('waiters/list_waiters.html', waiters=waiters)


# View waiter details
@bp.route('/<int:waiter_id>', methods=['GET'])
def view_waiter(waiter_id):
    waiter = Waiter.query.get_or_404(waiter_id)
    return render_template('waiters/view_waiter.html', waiter=waiter)

# Edit waiter
@bp.route('/<int:waiter_id>/edit', methods=['GET', 'POST'])
def edit_waiter(waiter_id):
    waiter = Waiter.query.get_or_404(waiter_id)
    form = WaiterForm(obj=waiter)
    if form.validate_on_submit():
        waiter.name = form.name.data
        waiter.phone_number = form.phone_number.data
        waiter.email = form.email.data
        waiter.is_active = form.is_active.data
        db.session.commit()
        flash('Waiter updated successfully!', 'success')
        return redirect(url_for('waiters.list_waiters'))
    return render_template('waiters/edit_waiter.html', form=form, waiter=waiter)

# Delete waiter
@bp.route('/<int:waiter_id>/delete', methods=['POST'])
def delete_waiter(waiter_id):
    waiter = Waiter.query.get_or_404(waiter_id)
    db.session.delete(waiter)
    db.session.commit()
    flash('Waiter deleted successfully!', 'success')
    return redirect(url_for('waiters.list_waiters'))
