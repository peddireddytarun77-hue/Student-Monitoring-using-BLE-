from flask import Flask
from flask_cors import CORS
from flasgger import Swagger
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from .routes import api_bp

# ── GLOBALS ──
socketio = SocketIO(cors_allowed_origins="*")
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])

def create_app():
    app = Flask(__name__)
    CORS(app)
    
    # Initialize Swagger
    Swagger(app, template={
        "info": {
            "title": "NEXUS Smart Attendance API",
            "description": "API for Student Monitoring and Attendance using BLE & Face Recognition",
            "version": "2.0.0"
        }
    })
    
    # Initialize Extensions
    socketio.init_app(app)
    limiter.init_app(app)
    
    app.register_blueprint(api_bp)
    return app


