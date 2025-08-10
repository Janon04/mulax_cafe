from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash
from urllib.parse import urlparse, urljoin
from app.models import User
from app.extensions import db
from app.auth.forms import LoginForm, UserEditForm
from app.auth.decorators import admin_required
from flask_admin.contrib.sqla import ModelView
from flask_admin.base import AdminIndexView

bp = Blueprint('auth', __name__)

# Flask-Admin secure views
class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return session.get('is_admin', False)

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

class SecureModelView(ModelView):
    def is_accessible(self):
        return session.get('is_admin', False)

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('auth.login'))

# Helper to validate safe redirects after login
def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

# LOGIN ROUTE
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('coffee.new_sale'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('auth.login'))

        if not user.active:
            flash('Your account is disabled', 'warning')
            return redirect(url_for('auth.login'))

        # Update last_login timestamp
        from datetime import datetime
        user.last_login = datetime.utcnow()
        db.session.commit()

        login_user(user, remember=form.remember_me.data)

        # Save key session info
        session['username'] = user.username
        session['is_admin'] = user.is_admin
        session['user_role'] = user.role

        next_page = request.args.get('next')
        if not next_page or not is_safe_url(next_page):
            next_page = url_for('coffee.new_sale')

        return redirect(next_page)

    return render_template('auth/login.html', title='Sign In', form=form)

# LOGOUT ROUTE
@bp.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))

# USER MANAGEMENT: List users
@bp.route('/admin/users')
@login_required
def manage_users():
    users = User.query.order_by(User.username).all()
    # Format last_login for display
    for user in users:
        if user.last_login:
            user.formatted_last_login = user.last_login.strftime('%Y-%m-%d %H:%M')
        else:
            user.formatted_last_login = None
    return render_template('auth/manage_users.html', users=users)


# CREATE USER
@bp.route('/admin/create-user', methods=['GET', 'POST'])
# @login_required
def create_user():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'employee')
        is_admin = 'is_admin' in request.form

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('auth.create_user'))

        new_user = User(username=username, is_admin=is_admin, role=role, active=True)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash('User created successfully', 'success')
        return redirect(url_for('auth.manage_users'))

    return render_template('auth/create_user.html')

# EDIT USER
@bp.route('/admin/edit-user/<int:user_id>', methods=['GET', 'POST'])
# @admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = UserEditForm(original_username=user.username, obj=user)

    if form.validate_on_submit():
        if form.username.data != user.username:
            existing_user = User.query.filter_by(username=form.username.data).first()
            if existing_user and existing_user.id != user.id:
                flash('Username already exists', 'danger')
                return redirect(url_for('auth.edit_user', user_id=user.id))

        user.username = form.username.data
        user.role = form.role.data
        user.is_admin = form.is_admin.data
        user.active = form.active.data

        if form.password.data:
            user.set_password(form.password.data)

        db.session.commit()
        flash('User updated successfully', 'success')
        return redirect(url_for('auth.manage_users'))

    return render_template('auth/edit_user.html', form=form, user=user)


# DELETE USER
@bp.route('/admin/delete-user/<int:user_id>', methods=['POST'])
# @admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    # Prevent self-deletion while logged in
    if user.id == current_user.id:
        flash('You cannot delete your own account while logged in.', 'danger')
        return redirect(url_for('auth.manage_users'))

    # Protect primary admin account
    if user.username.lower() == 'admin':
        flash('Cannot delete the primary admin account.', 'danger')
        return redirect(url_for('auth.manage_users'))

    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} deleted successfully.', 'success')
    return redirect(url_for('auth.manage_users'))