from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    db.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    from .routes import bp as api_bp
    from .admin_routes import bp as admin_api_bp

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(admin_api_bp, url_prefix="/api/admin")

    return app