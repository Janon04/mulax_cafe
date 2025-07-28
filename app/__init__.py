from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap5 import Bootstrap
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_restx import Api
from datetime import datetime
from config import Config
from app.extensions import db
import logging
from logging.handlers import RotatingFileHandler
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.services.notifications import check_low_stock_products
from flask import current_app
from dotenv import load_dotenv
load_dotenv()


# Initialize extensions
bootstrap = Bootstrap()
login_manager = LoginManager()
scheduler = BackgroundScheduler()

def format_currency(value):
    """Format value as Rwandan Francs."""
    if value is None:
        return ""
    try:
        return "Rwf {:,.2f}".format(float(value))
    except (ValueError, TypeError):
        return value

def create_app(config_class=Config):
    """Application factory function"""
    app = Flask(__name__)
    
    # Load configuration
    try:
        app.config.from_object(config_class)
        if not app.config.get('SQLALCHEMY_DATABASE_URI'):
            raise ValueError("Database URI not configured. Set SQLALCHEMY_DATABASE_URI in config.")
    except Exception as e:
        logging.error(f"Configuration error: {str(e)}")
        raise

    # Configure logging
    configure_logging(app)

    # Initialize extensions with error handling
    try:
        db.init_app(app)
        bootstrap.init_app(app)
        login_manager.init_app(app)
        migrate = Migrate(app, db)
        
        # Verify database connection
        with app.app_context():
            db.engine.connect()
            app.logger.info("Database connection established")
    except Exception as e:
        app.logger.error(f"Failed to initialize extensions: {str(e)}")
        raise

    # Setup Flask-RESTx
    api = Api(
        app,
        version='1.0',
        title='Mulax Cafe API',
        description='API for Mulax Cafe Management System',
        doc='/api/docs',
        prefix='/api',
        security='Bearer Auth'
    )

    # Register custom filters
    app.jinja_env.filters['format_currency'] = format_currency

    # Configure Login Manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    login_manager.needs_refresh_message_category = 'info'

    # User loader
    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Context processors
    @app.context_processor
    def inject_now():
        return {'now': datetime.utcnow()}

    @app.context_processor
    def inject_user_roles():
        from flask_login import current_user
        return {
            'is_admin': current_user.is_authenticated and current_user.role == 'admin',
            'is_manager': current_user.is_authenticated and current_user.role in ['admin', 'manager'],
            'is_employee': current_user.is_authenticated and current_user.is_employee(),
            'email_notifications_enabled': app.config.get('EMAIL_NOTIFICATIONS_ENABLED', True),
            'current_user_role': current_user.role if current_user.is_authenticated else None
        }

    # Register blueprints & API namespaces
    register_blueprints(app)
    register_api_namespaces(api)
    
    # Register error handlers
    from app.utils.error_handlers import register_error_handlers
    register_error_handlers(app)

    # Initialize database and default users
    with app.app_context():
        try:
            # Attempt to create all tables. If an index already exists, it will be caught.
            db.create_all()
            app.logger.info("Database tables created successfully.")
        except Exception as e:
            error_message = str(e)
            if "already exists" in error_message and "index" in error_message:
                app.logger.warning(f"Database index already exists: {error_message}. Attempting to drop and recreate.")
                try:
                    # Attempt to drop the specific problematic index
                    from sqlalchemy import text
                    with db.engine.connect() as connection:
                        connection.execute(text("DROP INDEX IF EXISTS ix_notification_logs_timestamp"))
                        connection.commit()
                    app.logger.info("Successfully dropped ix_notification_logs_timestamp.")
                    # Try creating all tables again after dropping the index
                    db.create_all()
                    app.logger.info("Database tables created successfully after index fix.")
                except Exception as fix_e:
                    app.logger.error(f"Failed to fix database index issue: {fix_e}")
                    raise # Re-raise if fixing fails
            else:
                app.logger.error(f"Database initialization failed: {e}")
                raise # Re-raise for other critical database errors

        # Create default users (this should run after tables are ensured to exist)
        try:
            create_default_users(app)
        except Exception as e:
            app.logger.error(f"Error creating default users: {e}")
            # Do not re-raise here, as the app can still function without default users being created on every run

    # Setup scheduled tasks
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        init_scheduled_tasks(app)

    # Additional context processor for config values
    @app.context_processor
    def inject_config():
        return {
            'ADMIN_EMAIL': app.config.get('ADMIN_EMAIL', 'janon3030@gmail.com'),
            'REQUISITION_EDIT_WINDOW': app.config.get('REQUISITION_EDIT_WINDOW', 3600)  # Default 1 hour
        }

    return app

def init_scheduled_tasks(app):
    """Initialize background scheduled tasks"""
    if app.config.get('EMAIL_NOTIFICATIONS_ENABLED', True):
        try:
            scheduler.add_job(
                func=check_low_stock_products,
                trigger=IntervalTrigger(hours=1),
                id='low_stock_check',
                replace_existing=True
            )
            scheduler.start()
            app.logger.info("Scheduled tasks initialized")
        except Exception as e:
            app.logger.error(f"Failed to start scheduler: {str(e)}")
    else:
        app.logger.warning("Email notifications are disabled in configuration")

    @app.teardown_appcontext
    def shutdown_scheduler(exception=None):
        if scheduler.running:
            scheduler.shutdown(wait=False)
            app.logger.info("Scheduler shutdown complete")

def configure_logging(app):
    """Configure application logging"""
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    # File handler
    file_handler = RotatingFileHandler(
        'logs/mulax_cafe.log', 
        maxBytes=10240, 
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Mulax Cafe startup')

def register_blueprints(app):
    """Register all application blueprints"""
    from app.routes.main import bp as main_bp
    from app.auth.auth import bp as auth_bp
    from app.routes.requisitions import bp as requisitions_bp
    from app.routes.product import bp as product_bp
    from app.routes.coffee import bp as coffee_bp
    from app.routes.kitchen import bp as kitchen_bp
    from app.routes.orders import bp as orders_bp
    from app.routes.tables import bp as tables_bp 
    from app.services.notifications import bp as notifications_bp

    blueprints = [
        (main_bp, None),
        (auth_bp, '/auth'),
        (requisitions_bp, '/requisitions'),
        (product_bp, '/products'),
        (coffee_bp, '/coffee'),
        (kitchen_bp, '/kitchen'),
        (orders_bp, '/orders'),
        (tables_bp, '/tables'),
        (notifications_bp, '/notifications')
    ]

    for bp, url_prefix in blueprints:
        try:
            app.register_blueprint(bp, url_prefix=url_prefix)
        except Exception as e:
            app.logger.error(f"Failed to register blueprint {bp.name}: {str(e)}")

def register_api_namespaces(api):
    """Register all API namespaces"""
    from app.api.users import ns as user_ns
    from app.api.product import ns as product_ns
    from app.api.stock_movements import ns as stock_movement_ns
    from app.api.requisitions import ns as requisition_ns
    from app.api.coffee_sale import ns as coffee_sale_ns
    from app.api.client import ns as client_ns
    from app.api.order import ns as order_ns
    from app.api.report import ns as report_ns

    namespaces = [
        user_ns,
        product_ns,
        stock_movement_ns,
        requisition_ns,
        coffee_sale_ns,
        client_ns,
        order_ns,
        report_ns
    ]

    for ns in namespaces:
        try:
            api.add_namespace(ns)
        except Exception as e:
            current_app.logger.error(f"Failed to add API namespace {ns.name}: {str(e)}")

def create_default_users(app):
    """Create default users if they don't exist"""
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

