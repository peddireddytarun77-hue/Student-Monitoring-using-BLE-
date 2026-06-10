from flask import Flask
from flask_cors import CORS
from flasgger import Swagger
from .routes import api_bp

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
    
    app.register_blueprint(api_bp)
    return app

