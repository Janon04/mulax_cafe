import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap5 import Bootstrap
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config
from app.extensions import db, migrate
from app.models import Shift



# Initialize core extensions
db = SQLAlchemy()
bootstrap = Bootstrap()
login_manager = LoginManager()


def create_app(config_class=Config):
    """Application factory"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    configure_logging(app)
    initialize_extensions(app)
    register_blueprints(app)
    setup_database(app)

    return app


def configure_logging(app):
    """Configure app-level logging to file"""
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, 'mulax_cafe.log')
    handler = RotatingFileHandler(log_path, maxBytes=10240, backupCount=10)
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)

    if not app.logger.handlers:
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)

    app.logger.info('Mulax Cafe app startup')


def initialize_extensions(app):
    """Initialize Flask extensions"""
    db.init_app(app)
    migrate.init_app(app, db)
    bootstrap.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    login_manager.needs_refresh_message_category = 'info'


def register_blueprints(app):
    """Register blueprints for route organization"""
    from app.routes import (
        main_bp,
        auth_bp,
        requisitions_bp,
        product_bp,
        coffee_bp,
        kitchen_bp,
        orders_bp,
        shifts_bp
    )

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(requisitions_bp, url_prefix='/requisitions')
    app.register_blueprint(product_bp, url_prefix='/products')
    app.register_blueprint(coffee_bp, url_prefix='/coffee')
    app.register_blueprint(kitchen_bp, url_prefix='/kitchen')
    app.register_blueprint(orders_bp, url_prefix='/orders')
    app.register_blueprint(shifts_bp, url_prefix='/shifts')


def create_default_users(app):
    """Create default users from config"""
    from app.models import User

    try:
        for role_key, user_data in app.config.get('DEFAULT_USERS', {}).items():
            user = User.query.filter_by(username=user_data['username']).first()
            if not user:
                new_user = User(
                    username=user_data['username'],
                    role=user_data['role'],
                    is_admin=user_data.get('is_admin', False),
                    must_change_password=user_data.get('must_change_password', True),
                    active=True
                )
                new_user.set_password(user_data['password'])
                db.session.add(new_user)
                app.logger.info(f"Created default user: {new_user.username} ({new_user.role})")

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error creating default users: {str(e)}")


def setup_database(app):
    """Setup database and optionally create default users"""
    with app.app_context():
        db.create_all()
        if app.config.get('CREATE_DEFAULT_USERS'):
            create_default_users(app)

        # Log existing users
        from app.models import User
        for role_key, user_data in app.config.get('DEFAULT_USERS', {}).items():
            user = User.query.filter_by(username=user_data['username']).first()
            if user:
                app.logger.info(f"Verified user: {user.username} ({user.role})")
            else:
                app.logger.warning(f"Default user creation failed: {user_data['username']}")
