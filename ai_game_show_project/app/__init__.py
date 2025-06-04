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
    with app.app_context():
        from . import models

    # Logging Setup
    import logging
    from logging.handlers import RotatingFileHandler
    import os

    # Create logs directory if it doesn't exist - place it in project root for simplicity for now
    log_dir = os.path.join(app.root_path, '..', 'logs') # app.root_path is .../app, so .. gets to project root
    if not os.path.exists(log_dir):
        try:
            os.mkdir(log_dir)
        except OSError as e:
            # Log this failure to stderr, as app.logger might not be fully set up
            print(f"Error creating log directory {log_dir}: {e}", file=sys.stderr)


    # Configure logging only if not in debug or testing mode,
    # or if specifically enabled (for this exercise, let's enable it more broadly but be mindful)
    # For simplicity of this task, we'll set it up regardless of app.debug for now to ensure it's active.
    # In production, you'd likely use if not app.debug:

    log_file = os.path.join(log_dir, 'ai_game_show.log')
    try:
        file_handler = RotatingFileHandler(log_file, maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
        file_handler.setLevel(logging.INFO) # Set level for the handler

        # Forcefully add the handler, even if Flask in debug mode added its own.
        # In debug, logs might go to both console and file.
        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO) # Set level for the app logger itself
        app.logger.info('AI Game Show application startup')
    except Exception as e:
        # Log this failure to stderr
        print(f"Error setting up file logger at {log_file}: {e}", file=sys.stderr)


    return app
