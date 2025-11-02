# import json
# from datetime import datetime
# from bson import ObjectId



# class ParaJson:
#     """
#     Classe utilitária para converter documentos em dicionários ou JSON.
#     Deve ser herdada por modelos que precisam de serialização customizada.
#     """

#     @property
#     def campos_bloqueados(self):
#         """
#         Define os campos que não devem aparecer na conversão para JSON.
#         :return: lista de nomes de campos a serem excluídos
#         """
#         raise NotImplementedError("Deve ser implementado na subclasse")

#     @property
#     def campos_especiais(self):
#         """
#         Define os campos que precisam de conversão especial.
#         Exemplo: DateTimeField -> field.isoformat()
#         :return: lista de nomes de campos especiais
#         """
#         raise NotImplementedError("Deve ser implementado na subclasse")

#     @property
#     def conversores_especiais(self):
#         """
#         Deve retornar um dicionário com funções para converter campos especiais.
#         Exemplo:
#             {
#                 "data": lambda valor: valor.isoformat() if valor else None,
#                 "id": lambda valor: str(valor)
#             }
#         :return: dicionário {campo: função conversora}
#         """
#         raise NotImplementedError("Deve ser implementado na subclasse")

#     def obter_valor_json(self, campo):
#         """
#         Retorna o valor de um atributo do modelo.
#         Se o campo estiver nos conversores especiais, aplica a função de conversão.
#         :return: valor do atributo convertido, se necessário
#         """
#         if campo not in self.conversores_especiais:
#             return getattr(self, campo, None)
#         return self.conversores_especiais[campo](getattr(self, campo))

#     def para_dict(self, *atributos, permitir_bloqueados=False, usar_camel_case=True):
#         """
#         Converte o objeto em um dicionário com os atributos especificados.

#         :param atributos: lista de campos desejados (por padrão, todos)
#         :param permitir_bloqueados: se True, inclui campos bloqueados
#         :param usar_camel_case: se True, converte nomes de campos para camelCase
#         :return: dicionário com os campos e valores serializáveis
#         """

#         # def extrair_chave(campo):
#         #     return to_camel_case(campo) if usar_camel_case else campo

#         atributos = atributos or set(self._fields)

#         def deve_incluir(campo):
#             return (campo not in self.campos_bloqueados) or permitir_bloqueados

#         convertido = {
#             extrair_chave(campo): self.obter_valor_json(campo)
#             for campo in atributos
#             if deve_incluir(campo)
#         }

#         return convertido

#     def para_json(self, *atributos):
#         """
#         Gera um JSON (string) a partir dos campos especificados do modelo.
#         Equivalente a json.dumps(self.para_dict()).
#         :return: string JSON
#         """
#         return json.dumps(self.para_dict(*atributos), ensure_ascii=False, indent=2)

#     def __init__(self, *args, **kwargs):
#         """
#         Construtor compatível com dataclasses e inicialização de modelos.
#         """
#         _apenas_campos = kwargs.get("__only_fields", [])
#         _kwargs = validar_kwargs_dataclass(self, **kwargs)
