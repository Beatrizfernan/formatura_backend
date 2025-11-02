
from typing import List
from mongoengine import EmbeddedDocument, StringField, ListField, IntField, DateTimeField
from mongoengine import ReferenceField, EmbeddedDocumentField, ValidationError, queryset_manager
from datetime import datetime
from . import BaseModel
from .formatura import Formatura
from .local import Local

class AlocacaoFila(EmbeddedDocument):
    """Embedded document para representar a alocação de um curso em uma fila"""
    
    curso_id = StringField(required=True)
    fila_nome = StringField(required=True)
    assentos = ListField(IntField(min_value=1), required=True)
    
    def clean(self):
        """Validação do embedded document"""
        if not self.assentos or len(self.assentos) == 0:
            raise ValidationError('Lista de assentos não pode estar vazia')
        
        # Remove duplicatas e ordena
        self.assentos = sorted(list(set(self.assentos)))
    
    @property
    def quantidade_assentos(self) -> int:
        """Retorna a quantidade de assentos ocupados"""
        return len(self.assentos)
    
    @property
    def primeiro_assento(self) -> int:
        """Retorna o número do primeiro assento"""
        return min(self.assentos) if self.assentos else 0
    
    @property
    def ultimo_assento(self) -> int:
        """Retorna o número do último assento"""
        return max(self.assentos) if self.assentos else 0
    
    @property
    def range_assentos(self) -> str:
        """Retorna o range de assentos formatado"""
        if not self.assentos:
            return ""
        if len(self.assentos) == 1:
            return str(self.assentos[0])
        
        # Se são sequenciais, mostra como range
        if self.ultimo_assento - self.primeiro_assento == len(self.assentos) - 1:
            return f"{self.primeiro_assento}-{self.ultimo_assento}"
        else:
            # Se não são sequenciais, mostra lista
            return ", ".join(map(str, self.assentos))
    
    def to_dict(self):
        """Converte para dicionário"""
        return {
            'curso_id': self.curso_id,
            'fila_nome': self.fila_nome,
            'assentos': self.assentos,
            'quantidade_assentos': self.quantidade_assentos,
            'primeiro_assento': self.primeiro_assento,
            'ultimo_assento': self.ultimo_assento,
            'range_assentos': self.range_assentos
        }
    
    def __str__(self):
        return f"AlocacaoFila({self.curso_id} em {self.fila_nome}: {self.quantidade_assentos} assentos)"


class Alocacao(BaseModel):
    """Modelo para representar a alocação de assentos de uma formatura"""
    
    meta = {
        'collection': 'alocacoes',
        'indexes': [
            {'fields': ['formatura'], 'unique': True},
            'local',
            'data_geracao'
        ]
    }
    
    formatura = ReferenceField(Formatura, required=True, unique=True)
    local = ReferenceField(Local, required=True)
    alocacoes = ListField(EmbeddedDocumentField(AlocacaoFila))
    data_geracao = DateTimeField(default=datetime.utcnow)
    observacoes = StringField(max_length=1000)
    
    def clean(self):
        """Validação customizada do modelo"""
        if self.observacoes:
            self.observacoes = self.observacoes.strip()
        
        errors = {}
        
        # Valida se há alocações
        if not self.alocacoes or len(self.alocacoes) == 0:
            errors['alocacoes'] = 'Deve haver pelo menos uma alocação'
        
        # Verifica conflitos de assentos (mesmo assento alocado para cursos diferentes)
        if self.alocacoes:
            mapa_assentos = {}
            for alocacao in self.alocacoes:
                for assento in alocacao.assentos:
                    chave = f"{alocacao.fila_nome}_{assento}"
                    if chave in mapa_assentos and mapa_assentos[chave] != alocacao.curso_id:
                        if 'conflitos' not in errors:
                            errors['conflitos'] = []
                        errors['conflitos'].append(
                            f"Assento {assento} na fila {alocacao.fila_nome} está alocado para múltiplos cursos"
                        )
                    mapa_assentos[chave] = alocacao.curso_id
        
        if errors:
            raise ValidationError(errors)
    
    def adicionar_alocacao_fila(self, curso_id: str, fila_nome: str, assentos: List[int]):
        """Adiciona uma alocação de curso em fila"""
        if not assentos:
            raise ValidationError('Lista de assentos não pode estar vazia')
        
        alocacao_fila = AlocacaoFila(
            curso_id=curso_id,
            fila_nome=fila_nome,
            assentos=assentos
        )
        
        alocacao_fila.clean()
        self.alocacoes.append(alocacao_fila)
        return self
    
    def remover_alocacao_curso(self, curso_id: str):
        """Remove todas as alocações de um curso"""
        self.alocacoes = [a for a in self.alocacoes if a.curso_id != curso_id]
        return self
    
    def get_alocacoes_por_curso(self, curso_id: str):
        """Retorna todas as alocações de um curso específico"""
        return [a for a in self.alocacoes if a.curso_id == curso_id]
    
    def get_alocacoes_por_fila(self, fila_nome: str):
        """Retorna todas as alocações de uma fila específica"""
        return [a for a in self.alocacoes if a.fila_nome == fila_nome]
    
    def get_cursos_alocados(self):
        """Retorna lista de IDs dos cursos alocados"""
        return list(set(a.curso_id for a in self.alocacoes))
    
    def get_filas_utilizadas(self):
        """Retorna lista de nomes das filas utilizadas"""
        return list(set(a.fila_nome for a in self.alocacoes))
    
    def get_assentos_ocupados_fila(self, fila_nome: str):
        """Retorna todos os assentos ocupados em uma fila específica"""
        assentos = []
        for alocacao in self.get_alocacoes_por_fila(fila_nome):
            assentos.extend(alocacao.assentos)
        return sorted(list(set(assentos)))
    
    def get_resumo_por_curso(self):
        """Retorna resumo de alocação por curso"""
        resumo = {}
        
        for curso_id in self.get_cursos_alocados():
            alocacoes_curso = self.get_alocacoes_por_curso(curso_id)
            total_assentos = sum(a.quantidade_assentos for a in alocacoes_curso)
            filas_ocupadas = [a.fila_nome for a in alocacoes_curso]
            
            resumo[curso_id] = {
                'total_assentos': total_assentos,
                'filas_ocupadas': filas_ocupadas,
                'quantidade_filas': len(filas_ocupadas),
                'detalhes_filas': [
                    {
                        'fila': a.fila_nome,
                        'assentos': a.quantidade_assentos,
                        'range': a.range_assentos
                    }
                    for a in alocacoes_curso
                ]
            }
        
        return resumo
    
    def get_mapa_assentos(self):
        """Retorna mapa de assentos: {fila_nome: {assento_numero: curso_id}}"""
        mapa = {}
        
        for alocacao in self.alocacoes:
            if alocacao.fila_nome not in mapa:
                mapa[alocacao.fila_nome] = {}
            
            for assento in alocacao.assentos:
                mapa[alocacao.fila_nome][assento] = alocacao.curso_id
        
        return mapa
    
    @property
    def total_assentos_alocados(self) -> int:
        """Retorna o total de assentos alocados"""
        return sum(a.quantidade_assentos for a in self.alocacoes)
    
    @property
    def taxa_ocupacao(self) -> float:
        """Retorna a taxa de ocupação do local"""
        if not self.local or self.local.total_assentos == 0:
            return 0.0
        return (self.total_assentos_alocados / self.local.total_assentos) * 100
    
    def limpar_alocacoes(self):
        """Remove todas as alocações"""
        self.alocacoes = []
        return self
    
    def to_dict(self, exclude_fields=None, populate_refs=False):
        """Converte para dicionário com dados calculados"""
        data = super().to_dict(exclude_fields)
        
        # Converte referências
        if self.formatura:
            if populate_refs:
                data['formatura'] = self.formatura.to_dict(include_stats=False)
            else:
                data['formatura_id'] = str(self.formatura.id)
                data['formatura_nome'] = self.formatura.nome
        
        if self.local:
            if populate_refs:
                data['local'] = self.local.to_dict(include_stats=False)
            else:
                data['local_id'] = str(self.local.id)
                data['local_nome'] = self.local.nome
        
        # Converte alocações
        data['alocacoes'] = [a.to_dict() for a in self.alocacoes]
        
        # Adiciona dados calculados
        data['resumo_por_curso'] = self.get_resumo_por_curso()
        data['cursos_alocados'] = self.get_cursos_alocados()
        data['filas_utilizadas'] = self.get_filas_utilizadas()
        data['mapa_assentos'] = self.get_mapa_assentos()
        data['total_assentos_alocados'] = self.total_assentos_alocados
        data['taxa_ocupacao'] = round(self.taxa_ocupacao, 2)
        
        return data
    
    @classmethod
    def buscar_por_formatura(cls, formatura):
        """Busca alocação por formatura"""
        return cls.objects(formatura=formatura).first()
    
    @classmethod
    def buscar_por_local(cls, local):
        """Busca alocações por local"""
        return cls.objects(local=local)
    
    
    def __str__(self):
        return f"Alocacao({self.formatura.nome if self.formatura else 'N/A'}, {len(self.alocacoes)} alocações)"
    
    def __repr__(self):
        return f"Alocacao(formatura='{self.formatura}', alocacoes={len(self.alocacoes)})"