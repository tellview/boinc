from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler
from app import create_app # Assuming your create_app is in app/__init__.py
import logging # For capturing app.logger if needed before server runs

app = create_app()

if __name__ == '__main__':
    # Capture the app's logger instance if needed for pre-server messages
    # However, app.logger itself will work once app is created.
    # Using current_app.logger directly in routes is better.
    # For run.py, direct print or basic logging can be used if app.logger is not ready.

    app.logger.info("Attempting to start server with gevent-pywsgi for WebSocket support.")
    try:
        server = pywsgi.WSGIServer(('', 5000), app, handler_class=WebSocketHandler)
        app.logger.info("Server listening on port 5000 with WebSocket support...")
        server.serve_forever()
    except Exception as e:
        # Use app.logger if available, otherwise print
        log_message = f"Failed to start gevent-pywsgi server: {e}"
        if hasattr(app, 'logger'):
            app.logger.error(log_message)
            app.logger.info("Falling back to standard Flask dev server (WebSockets will NOT work).")
        else: # Fallback if app.logger itself is the problem or not configured yet
            print(log_message)
            print("Falling back to standard Flask dev server (WebSockets will NOT work).")

        # Fallback to Flask's built-in server if gevent fails (WebSockets won't work)
        app.run(debug=True, host='0.0.0.0', port=5000)
