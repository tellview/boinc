import os
import sys

# Add the directory containing run.py (ai_game_show_project) to sys.path
# to ensure 'app' package within this directory is discoverable.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
