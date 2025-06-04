from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()

def create_app():
    # Ensure static and template folders are correctly specified relative to the app root path
    app = Flask(__name__,
                instance_relative_config=True,
                static_folder='static',
                template_folder='templates')

    # Load configuration from config.Config
    # Assumes config.py is in ai_game_show_project directory and has a class Config
    app.config.from_object('config.Config')

    # Ensure the instance folder exists if config expects it (e.g. for SQLite)
    # Flask creates it automatically if instance_path is used by SQLAlchemy & instance_relative_config=True
    # For SQLite, db path in config.py is 'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
    # where basedir is ai_game_show_project. Flask's app.instance_path will resolve to
    # ai_game_show_project/instance if instance_relative_config=True.
    # So, this should align.

    # Initialize Flask extensions here
    db.init_app(app)
    migrate.init_app(app, db)

    # Import and register blueprints
    from .routes import bp as api_bp
    from .routes import main_bp as main_routes_bp
    app.register_blueprint(api_bp, url_prefix='/api') # Corrected here
    app.register_blueprint(main_routes_bp) # No prefix for main UI routes

    # Import models here, after db is initialized and associated with app
    # This makes `db` available for models when they are defined.
    # (Alternatively, models.py could import `db` from this file,
    # but that might lead to circular imports if not handled carefully.
    # This explicit import within create_app is safer for discovery)
    with app.app_context():
        from . import models

    return app
