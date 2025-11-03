from flask import Flask
from mongoengine import connect
from flask_cors import CORS
from config import MONGO_URI

from app.routes.local_routes import local_bp
from app.routes.formatura_routes import formatura_bp
from app.routes.planilha_routes import planilha_bp

def create_app():
    app = Flask(__name__)
    connect(host=MONGO_URI)  
    @app.route("/")
    def home():
        return "Backend rodando no Render! 🚀"
    CORS(app)

    app.register_blueprint(local_bp)
    app.register_blueprint(formatura_bp)
    app.register_blueprint(planilha_bp)


    
    return app
