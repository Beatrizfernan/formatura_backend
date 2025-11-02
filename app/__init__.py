from flask import Flask
from mongoengine import connect

from config import MONGO_URI



def create_app():
    app = Flask(__name__)
    connect(host=MONGO_URI)  
    @app.route("/")
    def home():
        return "Backend rodando no Render! 🚀"
    
    return app
