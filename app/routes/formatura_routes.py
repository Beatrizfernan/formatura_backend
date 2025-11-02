from flask import Blueprint,jsonify

from app.models.formatura import Formatura


formatura_bp = Blueprint("formatura" , __name__)

@formatura_bp.route("/listar_formaturas/", methods=["GET"])
def listar_formaturas():
    formaturas = Formatura.objects()

    formatura_to_dict = [formatura.to_dict() for formatura in formaturas]
    return jsonify(formatura_to_dict)
    