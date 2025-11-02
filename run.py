from flask_cors import CORS
from app import create_app
from app.models.curso import Curso
from app.routes.local_routes import local_bp
from app.routes.formatura_routes import formatura_bp
from app.routes.planilha_routes import planilha_bp

app = create_app()

# ===== CONFIGURAÇÃO CORS (PERMISSIVA PARA DEV) =====
CORS(app)

app.register_blueprint(local_bp)
app.register_blueprint(formatura_bp)
app.register_blueprint(planilha_bp)

if __name__ == "__main__":
    app.run(debug=True)