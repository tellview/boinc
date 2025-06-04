import os

# Get the absolute path of the directory where config.py is located
# This will be /app/ai_game_show_project/
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    DEBUG = True
    # Define the SQLite database URI to be in 'ai_game_show_project/app.db'
    # (i.e., at the same level as config.py, run.py)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
