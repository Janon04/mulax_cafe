from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_restx import Api
from flask_mail import Mail

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
api = Api()
mail = Mail()
limiter = Limiter(key_func=lambda: 'global')