from flask import Flask, render_template, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap5 import Bootstrap
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_restx import Api
from datetime import datetime, time
from config import Config
from app.extensions import db
import logging
from logging.handlers import RotatingFileHandler
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.services.notifications import check_low_stock_products
from dotenv import load_dotenv
from sqlalchemy import text
from datetime import timedelta


# Global app object for some modules (only use after create_app is called)
app = Flask(__name__)

load_dotenv()

# Initialize extensions
bootstrap = Bootstrap()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
scheduler = BackgroundScheduler()
migrate = Migrate()

def format_currency(value):
    if value is None:
        return ""
    try:
        return "{:,.2f}".format(float(value))
    except (ValueError, TypeError):
        return value

def create_app(config_class=Config):
    app = Flask(__name__)
    try:
        app.config.from_object(config_class)
        if not app.config.get('SQLALCHEMY_DATABASE_URI'):
            raise ValueError("Database URI not configured. Set SQLALCHEMY_DATABASE_URI in config.")
    except Exception as e:
        logging.error(f"Configuration error: {str(e)}")
        raise

    configure_logging(app)

    try:
        db.init_app(app)
        bootstrap.init_app(app)
        login_manager.init_app(app)
        migrate.init_app(app, db)
        with app.app_context():
            db.engine.connect()
            app.logger.info("Database connection established")
    except Exception as e:
        app.logger.error(f"Failed to initialize extensions: {str(e)}")
        raise

    api = Api(
        app,
        version='1.0',
        title='Mulax Cafe API',
        description='API for Mulax Cafe Management System',
        doc='/api/docs',
        prefix='/api',
        security='Bearer Auth'
    )

    app.jinja_env.filters['format_currency'] = format_currency

    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_now():
        return {'now': datetime.utcnow()}

    @app.context_processor
    def inject_user_roles():
        from flask_login import current_user
        return {
            'is_admin': current_user.is_authenticated and (current_user.is_admin or current_user.role == 'system_control'),
            'is_manager': current_user.is_authenticated and current_user.role in ['system_control', 'manager'],
            'is_employee': current_user.is_authenticated and current_user.is_employee(),
            'email_notifications_enabled': app.config.get('EMAIL_NOTIFICATIONS_ENABLED', True),
            'current_user_role': current_user.role if current_user.is_authenticated else None,
            'current_shift': current_user.get_current_shift() if current_user.is_authenticated else None,
            'shift_system_enabled': app.config.get('SHIFT_SYSTEM_ENABLED', True)
        }

    register_blueprints(app)

    with app.app_context():
        from app.utils.error_handlers import register_error_handlers
        register_error_handlers(app)
        initialize_database(app)

    register_api_namespaces(api, app)

    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        init_scheduled_tasks(app)

    @app.context_processor
    def inject_config():
        return {
            'ADMIN_EMAIL': app.config.get('ADMIN_EMAIL', 'janon3030@gmail.com'),
            'REQUISITION_EDIT_WINDOW': app.config.get('REQUISITION_EDIT_WINDOW', 3600),
            'SHIFT_SYSTEM_ENABLED': app.config.get('SHIFT_SYSTEM_ENABLED', True)
        }

    return app

def initialize_database(app):
    try:
        db.create_all()
        app.logger.info("Database tables created successfully.")
        create_default_users(app)
        create_default_shifts(app)
    except Exception as e:
        error_message = str(e)
        if "already exists" in error_message and "index" in error_message:
            handle_index_conflict(app, error_message)
        else:
            app.logger.error(f"Database initialization failed: {e}")
            raise

def handle_index_conflict(app, error_message):
    app.logger.warning(f"Database index conflict: {error_message}")
    try:
        with db.engine.connect() as connection:
            connection.execute(text("DROP INDEX IF EXISTS ix_notification_logs_timestamp"))
            connection.execute(text("DROP INDEX IF EXISTS ix_attendances_user_id"))
            connection.commit()
        app.logger.info("Successfully dropped conflicting indexes.")
        db.create_all()
        app.logger.info("Database tables created successfully after index fix.")
    except Exception as fix_e:
        app.logger.error(f"Failed to resolve index conflicts: {fix_e}")
        raise

def create_default_users(app):
    from app.models import User
    try:
        for user_type, user_data in Config.DEFAULT_USERS.items():
            user = User.query.filter_by(username=user_data['username']).first()
            if not user:
                new_user = User(
                    username=user_data['username'],
                    role=user_data['role'],
                    is_admin=user_data.get('is_admin', False),
                    active=True,
                    must_change_password=True
                )
                new_user.set_password(user_data['password'])
                db.session.add(new_user)
                app.logger.info(f"Created default {user_data['role']} user: {user_data['username']}")
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating default users: {str(e)}")
        raise

def create_default_shifts(app):
    from app.models import Shift
    try:
        # Remove any existing shifts first to ensure clean slate
        Shift.query.delete()
        
        # Create Day Shift (7am to 5pm)
        day_shift = Shift(
            name='Day Shift',
            start_time=time(7, 0, 0),
            end_time=time(17, 0, 0),
            is_active=True
        )
        db.session.add(day_shift)
        app.logger.info("Created Day Shift (7am-5pm)")

        # Create Night Shift (5pm to 00am next day)
        night_shift = Shift(
            name='Night Shift',
            start_time=time(17, 0, 0),
            end_time=time(00, 0, 0),
            is_active=True
        )
        db.session.add(night_shift)
        app.logger.info("Created Night Shift (5pm-00:00am)")

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating default shifts: {str(e)}")
        raise

def cleanup_shift_assignments():
    from app.models import User, Shift, Attendance
    now = datetime.utcnow()
    current_time = now.time()
    try:
        # Handle day shift (7am-5pm)
        if current_time >= time(17, 0) or current_time < time(7, 0):
            day_shift = Shift.query.filter_by(name='Day Shift').first()
            if day_shift:
                users = User.query.filter_by(current_shift_id=day_shift.id).all()
                for user in users:
                    last_attendance = Attendance.query.filter_by(
                        user_id=user.id,
                        shift_id=day_shift.id
                    ).order_by(Attendance.login_time.desc()).first()

                    if last_attendance and not last_attendance.logout_time:
                        last_attendance.logout_time = datetime.combine(
                            last_attendance.login_time.date(),
                            day_shift.end_time
                        )
                        current_app.logger.info(f"Set logout time for user {user.username} in Day Shift")

                    user.current_shift_id = None
                    current_app.logger.info(f"Cleared Day Shift assignment for user {user.username}")

        # Handle night shift (5pm-7am)
        if current_time >= time(7, 0) and current_time < time(17, 0):
            night_shift = Shift.query.filter_by(name='Night Shift').first()
            if night_shift:
                users = User.query.filter_by(current_shift_id=night_shift.id).all()
                for user in users:
                    last_attendance = Attendance.query.filter_by(
                        user_id=user.id,
                        shift_id=night_shift.id
                    ).order_by(Attendance.login_time.desc()).first()

                    if last_attendance and not last_attendance.logout_time:
                        # For night shift, the end time is the next day at 7am
                        logout_date = last_attendance.login_time.date()
                        if last_attendance.login_time.time() >= time(17, 0):
                            logout_date += timedelta(days=1)
                        
                        last_attendance.logout_time = datetime.combine(
                            logout_date,
                            night_shift.end_time
                        )
                        current_app.logger.info(f"Set logout time for user {user.username} in Night Shift")

                    user.current_shift_id = None
                    current_app.logger.info(f"Cleared Night Shift assignment for user {user.username}")

        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Error in shift cleanup: {str(e)}")
        db.session.rollback()

def init_scheduled_tasks(app):
    if app.config.get('EMAIL_NOTIFICATIONS_ENABLED', True):
        try:
            scheduler.add_job(
                func=check_low_stock_products,
                trigger=IntervalTrigger(hours=1),
                id='low_stock_check',
                replace_existing=True,
                max_instances=1
            )
            scheduler.add_job(
                func=cleanup_shift_assignments,
                trigger=IntervalTrigger(minutes=30),
                id='shift_cleanup',
                replace_existing=True,
                max_instances=1
            )
            scheduler.start()
            app.logger.info("Scheduled tasks initialized")
        except Exception as e:
            app.logger.error(f"Failed to start scheduler: {str(e)}")

    @app.teardown_appcontext
    def shutdown_scheduler(exception=None):
        if scheduler.running:
            scheduler.shutdown(wait=False)
            app.logger.info("Scheduler shutdown complete")

def configure_logging(app):
    if not os.path.exists('logs'):
        os.mkdir('logs')

    file_handler = RotatingFileHandler(
        'logs/mulax_cafe.log',
        maxBytes=10240,
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)

    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Mulax Cafe startup')

def register_blueprints(app):
    from app.routes.main import bp as main_bp
    from app.auth.auth import bp as auth_bp
    from app.routes.requisitions import bp as requisitions_bp
    from app.routes.product import bp as product_bp
    from app.routes.coffee import bp as coffee_bp
    from app.routes.kitchen import bp as kitchen_bp
    from app.routes.orders import bp as orders_bp
    from app.routes.tables import bp as tables_bp
    from app.services.notifications import bp as notifications_bp
    from app.routes.shifts import bp as shift_bp
    from app.routes.waiter import bp as waiters_bp
    
    blueprints = [
        (main_bp, None),
        (auth_bp, '/auth'),
        (requisitions_bp, '/requisitions'),
        (product_bp, '/products'),
        (coffee_bp, '/coffee'),
        (kitchen_bp, '/kitchen'),
        (orders_bp, '/orders'),
        (tables_bp, '/tables'),
        (notifications_bp, '/notifications'),
        (shift_bp, '/shifts'),
        (waiters_bp, '/waiters')
    ]

    for bp, url_prefix in blueprints:
        try:
            app.register_blueprint(bp, url_prefix=url_prefix)
            app.logger.info(f"Registered blueprint: {bp.name}")
        except Exception as e:
            app.logger.error(f"Failed to register blueprint {bp.name}: {str(e)}")

def register_api_namespaces(api, app):
    from app.api.users import ns as user_ns
    from app.api.product import ns as product_ns
    from app.api.stock_movements import ns as stock_movement_ns
    from app.api.requisitions import ns as requisition_ns
    from app.api.coffee_sale import ns as coffee_sale_ns
    from app.api.client import ns as client_ns
    from app.api.order import ns as order_ns
    from app.api.report import ns as report_ns
    from app.api.shifts import ns as shift_ns

    namespaces = [
        user_ns,
        product_ns,
        stock_movement_ns,
        requisition_ns,
        coffee_sale_ns,
        client_ns,
        order_ns,
        report_ns,
        shift_ns
    ]

    for ns in namespaces:
        try:
            api.add_namespace(ns)
            app.logger.info(f"Added API namespace: {ns.name}")
        except Exception as e:
            app.logger.error(f"Failed to add API namespace {ns.name}: {str(e)}")