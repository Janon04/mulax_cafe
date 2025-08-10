import os
from dotenv import load_dotenv
from datetime import timedelta
import secrets

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration class with sensible defaults."""

    # ============ CORE CONFIGURATION ============
    SECRET_KEY = os.getenv('SECRET_KEY', secrets.token_hex(32))
    APP_NAME = "Mulax Cafe"
    APP_URL = os.getenv('APP_URL', 'http://localhost:5050')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development').lower()
    SERVER_NAME = os.getenv('SERVER_NAME')
    APPLICATION_ROOT = os.getenv('APPLICATION_ROOT', '/')
    PREFERRED_URL_SCHEME = os.getenv('PREFERRED_URL_SCHEME', 'http')

    # ============ DATABASE CONFIGURATION ============
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///mulax_cafe.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 20,
        'max_overflow': 30
    }
    SQLALCHEMY_RECORD_QUERIES = os.getenv('SQLALCHEMY_RECORD_QUERIES', 'False').lower() == 'true'

    # ============ SECURITY CONFIGURATION ============
    SESSION_COOKIE_NAME = 'mulax_cafe_session'
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    PASSWORD_RESET_EXPIRE = timedelta(hours=24)
    SECURITY_PASSWORD_SALT = os.getenv('SECURITY_PASSWORD_SALT', secrets.token_hex(16))
    SECURITY_PASSWORD_HASH = 'bcrypt'
    SECURITY_PASSWORD_COMPLEXITY = 3  # Requires at least 3 character categories

    # ============ EMAIL CONFIGURATION ============
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@mulaxcafe.com')
    MAIL_DEBUG = os.getenv('MAIL_DEBUG', 'False').lower() == 'true'
    MAIL_SUPPRESS_SEND = os.getenv('MAIL_SUPPRESS_SEND', 'False').lower() == 'true'
    MAIL_TIMEOUT = int(os.getenv('MAIL_TIMEOUT', 10))  # seconds

    # ============ NOTIFICATION SETTINGS ============
    NOTIFICATION_COOLDOWN_HOURS = int(os.getenv('NOTIFICATION_COOLDOWN_HOURS', '24'))
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@mulaxcafe.com')
    EMAIL_NOTIFICATIONS_ENABLED = os.getenv('EMAIL_NOTIFICATIONS_ENABLED', 'True').lower() == 'true'
    ADMIN_EMAILS = [email.strip() for email in os.getenv('ADMIN_EMAILS', 'admin@mulaxcafe.com').split(',')]

    # ============ RATE LIMITING ============
    RATELIMIT_STORAGE_URI = os.getenv('RATELIMIT_STORAGE_URI', 'memory://')
    DEFAULT_LIMITS = ["200 per day", "50 per hour"]
    API_RATE_LIMIT = "100 per hour"

    # ============ APPLICATION BEHAVIOR ============
    BEHIND_PROXY = os.getenv('BEHIND_PROXY', 'False').lower() == 'true'
    BOOTSTRAP_SERVE_LOCAL = True
    REQUISITION_EDIT_WINDOW = int(os.getenv('REQUISITION_EDIT_WINDOW', 120))  # minutes
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB upload limit

    # ============ DEFAULT USERS ============
    CREATE_DEFAULT_USERS = os.getenv('CREATE_DEFAULT_USERS', 'True').lower() == 'true'
    DEFAULT_USERS = {
        'admin': {
            'username': os.getenv('DEFAULT_ADMIN_USER', 'admin'),
            'password': os.getenv('DEFAULT_ADMIN_PASSWORD', 'admin1'),  
            'email': os.getenv('DEFAULT_ADMIN_EMAIL', 'admin@mulaxcafe.com'),
            'role': 'system_control', 
            'is_admin': True,
            'must_change_password': True,
            'active': True
        },
        'manager': {
            'username': os.getenv('DEFAULT_MANAGER_USER', 'manager'),
            'password': os.getenv('DEFAULT_MANAGER_PASSWORD', 'manager2'),  
            'email': os.getenv('DEFAULT_MANAGER_EMAIL', 'manager@mulaxcafe.com'),
            'role': 'manager',
            'is_admin': False,
            'must_change_password': True,
            'active': True
        }
    }

    # ============ PASSWORD POLICY ============
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_MAX_LENGTH = 128
    PASSWORD_REQUIRE_UPPERCASE = True
    PASSWORD_REQUIRE_LOWERCASE = True
    PASSWORD_REQUIRE_NUMBERS = True
    PASSWORD_REQUIRE_SPECIAL = True
    PASSWORD_RESET_EXPIRATION = timedelta(hours=24)  # Password reset links expire after 24 hours

    # ============ BUSINESS CONFIGURATION ============
    @property
    def DAILY_REVENUE_GOAL(self):
        """Get daily revenue goal in RWF"""
        return float(os.getenv('DAILY_REVENUE_GOAL', 500000))  # Default 500,000 RWF

    BUSINESS_HOURS = {
        'open': os.getenv('BUSINESS_HOURS_OPEN', '08:00'),
        'close': os.getenv('BUSINESS_HOURS_CLOSE', '20:00')
    }

    # ============ THEME ============
    THEME_COLORS = {
        'primary': '#7B3F00',  # Coffee brown
        'secondary': '#FFD700',  # Gold
        'success': '#28A745',
        'danger': '#DC3545',
        'warning': '#FFC107',
        'info': '#17A2B8'
    }

    # ============ FEATURE TOGGLES ============
    ENABLE_REGISTRATION = os.getenv('ENABLE_REGISTRATION', 'False').lower() == 'true'
    ENABLE_PASSWORD_RESET = os.getenv('ENABLE_PASSWORD_RESET', 'True').lower() == 'true'
    ENABLE_API = os.getenv('ENABLE_API', 'False').lower() == 'true'
    DEBUG_TB_ENABLED = os.getenv('DEBUG_TB_ENABLED', 'False').lower() == 'true'

    # ============ LOGGING ============
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
    LOG_FILE = os.getenv('LOG_FILE', 'logs/mulax_cafe.log')
    LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', 102400))  # 100KB
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', 5))
    LOG_FORMAT = os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class ProductionConfig(Config):
    FLASK_ENV = 'production'
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = 'https'
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')  # Must be set in production
    MAIL_SUPPRESS_SEND = False
    DEBUG_TB_ENABLED = False
    ENABLE_REGISTRATION = False
    # Override default passwords in production for security
    DEFAULT_USERS = {
        'admin': {
            'username': os.getenv('DEFAULT_ADMIN_USER', 'admin'),
            'password': os.getenv('DEFAULT_ADMIN_PASSWORD'),  # Must be set in production
            'email': os.getenv('DEFAULT_ADMIN_EMAIL', 'admin@mulaxcafe.com'),
            'role': 'system_control',
            'is_admin': True,
            'must_change_password': True,
            'active': True
        },
        'manager': {
            'username': os.getenv('DEFAULT_MANAGER_USER', 'manager'),
            'password': os.getenv('DEFAULT_MANAGER_PASSWORD'),  # Must be set in production
            'email': os.getenv('DEFAULT_MANAGER_EMAIL', 'manager@mulaxcafe.com'),
            'role': 'manager',
            'is_admin': False,
            'must_change_password': True,
            'active': True
        }
    }


class DevelopmentConfig(Config):
    FLASK_ENV = 'development'
    DEBUG = True
    TESTING = False
    SQLALCHEMY_ECHO = os.getenv('SQLALCHEMY_ECHO', 'True').lower() == 'true'
    SESSION_COOKIE_SECURE = False
    DEBUG_TB_ENABLED = True
    ENABLE_REGISTRATION = True


class TestingConfig(Config):
    FLASK_ENV = 'testing'
    DEBUG = False
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ECHO = False
    WTF_CSRF_ENABLED = False
    CREATE_DEFAULT_USERS = False
    MAIL_SUPPRESS_SEND = True
    ENABLE_REGISTRATION = False


def get_config():
    """Get the appropriate config class based on FLASK_ENV"""
    env = os.getenv('FLASK_ENV', 'development').lower()
    return {
        'production': ProductionConfig,
        'testing': TestingConfig
    }.get(env, DevelopmentConfig)