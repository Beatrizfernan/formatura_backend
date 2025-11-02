from flask import Blueprint, jsonify, request
from mongoengine import ValidationError

from app.models.local import Local

local_bp = Blueprint("local", __name__)

@local_bp.route("/listar_locais/", methods=["GET"])
def listar_locais():
    listar_locais = Local.objects(ativo=True)
    dict_local = [locais.to_dict() for locais in listar_locais]
    return jsonify(dict_local)


@local_bp.route("/criar_local", methods=["POST"])
def criar_local():
    try:
        data = request.get_json()
        
        # Validação básica
        if not data:
            return jsonify({"error": "Dados não fornecidos"}), 400
        
        if not data.get("nome"):
            return jsonify({"error": "Nome é obrigatório"}), 400
        
        if not data.get("filas") or len(data.get("filas", [])) == 0:
            return jsonify({"error": "Pelo menos uma fila deve ser fornecida"}), 400
        
        # Cria o local
        local = Local(
            nome=data["nome"],
            descricao=data.get("descricao", "")
        )
        
        # Adiciona as filas
        for fila_data in data["filas"]:
            local.adicionar_fila(
                nome=fila_data["nome"],
                quantidade_assentos=fila_data["quantidade_assentos"],
                ordem=fila_data.get("ordem")
            )
        
        # Salva o local
        local.save()
        
        return jsonify({
            "message": "Local criado com sucesso",
            "local": local.to_dict()
        }), 201
        
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Erro ao criar local: {str(e)}"}), 500


@local_bp.route("/buscar_local/<local_id>", methods=["GET"])
def buscar_local(local_id):
    try:
        local = Local.objects(id=local_id, ativo=True).first()
        
        if not local:
            return jsonify({"error": "Local não encontrado"}), 404
        
        return jsonify(local.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500