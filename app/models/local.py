from mongoengine import EmbeddedDocument, StringField, IntField, ListField, EmbeddedDocumentField
from mongoengine import ValidationError, queryset_manager
from . import BaseModel, SoftDeleteMixin
import re

class Fila(EmbeddedDocument):
    """Embedded document para representar uma fila de assentos"""
    
    nome = StringField(required=True, max_length=10)
    quantidade_assentos = IntField(required=True, min_value=1, max_value=100)
    ordem = IntField(min_value=1)
    
    def clean(self):
        """Validação do embedded document"""
        # Normaliza nome
        if self.nome:
            self.nome = self.nome.strip().upper()
        
        errors = {}
        
        # Valida padrão do nome (número + letra)
        if self.nome and not re.match(r'^[0-9]+[A-Z]$', self.nome):
            errors['nome'] = 'Nome da fila deve seguir o padrão número+letra (ex: 1A, 2B)'
        
        # Valida quantidade de assentos
        if self.quantidade_assentos and (self.quantidade_assentos < 1 or self.quantidade_assentos > 100):
            errors['quantidade_assentos'] = 'Quantidade de assentos deve estar entre 1 e 100'
        
        if errors:
            raise ValidationError(errors)
        
        # Calcula ordem automaticamente se não fornecida
        if not self.ordem and self.nome:
            self.ordem = self._calcular_ordem()
    
    def _calcular_ordem(self) -> int:
        """Calcula a ordem baseada no nome da fila"""
        match = re.match(r'^(\d+)([A-Z])$', self.nome)
        if match:
            numero = int(match.group(1))
            letra_index = ord(match.group(2)) - ord('A') + 1
            return (numero - 1) * 26 + letra_index
        return 999 
    
    def to_dict(self):
        """Converte para dicionário"""
        return {
            'nome': self.nome,
            'quantidade_assentos': self.quantidade_assentos,
            'ordem': self.ordem or self._calcular_ordem()
        }
    
    def __str__(self):
        return f"Fila {self.nome}: {self.quantidade_assentos} assentos"

class Local(BaseModel, SoftDeleteMixin):
    """Modelo para representar um local de formatura"""
    
    meta = {
        'collection': 'locais',
        'indexes': [
            {'fields': ['nome'], 'unique': True, 'partialFilterExpression': {'ativo': True}},
            'ativo',
            'created_at',
            'updated_at'
        ]
    }
    
    nome = StringField(required=True, max_length=100)
    descricao = StringField(max_length=500)
    filas = ListField(EmbeddedDocumentField(Fila))
    
    def clean(self):
        """Validação customizada do modelo"""
        # Normaliza campos
        if self.nome:
            self.nome = self.nome.strip()
        if self.descricao:
            self.descricao = self.descricao.strip()
        
        errors = {}
        
        # Valida nome
        if self.nome and len(self.nome) < 3:
            errors['nome'] = 'Nome deve ter pelo menos 3 caracteres'
        
        # Valida filas
        if not self.filas or len(self.filas) == 0:
            errors['filas'] = 'Local deve ter pelo menos uma fila'
        
        # Verifica nomes únicos de filas
        if self.filas:
            nomes_filas = [fila.nome for fila in self.filas]
            if len(nomes_filas) != len(set(nomes_filas)):
                errors['filas'] = 'Nomes das filas devem ser únicos'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Override save para ordenar filas e atualizar updated_at"""
        if self.filas:
            # Ordena filas pela ordem
            self.filas.sort(key=lambda f: f.ordem or f._calcular_ordem())
        
        return super().save(*args, **kwargs)
    
    @queryset_manager
    def ativos(cls, queryset):
        """Manager para locais ativos"""
        return queryset.filter(ativo=True)
    
    def adicionar_fila(self, nome: str, quantidade_assentos: int, ordem: int = None):
        """Adiciona uma fila ao local"""
        # Verifica se já existe fila com mesmo nome
        if any(fila.nome.upper() == nome.upper() for fila in self.filas):
            raise ValidationError({'fila': f'Já existe uma fila com o nome "{nome}"'})
        
        fila = Fila(
            nome=nome,
            quantidade_assentos=quantidade_assentos,
            ordem=ordem
        )
        

        fila.clean()
        
        self.filas.append(fila)
        return self
    
    def remover_fila(self, nome_fila: str):
        """Remove uma fila do local"""
        self.filas = [fila for fila in self.filas if fila.nome.upper() != nome_fila.upper()]
        return self
    
    def atualizar_fila(self, nome_fila: str, quantidade_assentos: int = None, ordem: int = None):
        """Atualiza uma fila existente"""
        for fila in self.filas:
            if fila.nome.upper() == nome_fila.upper():
                if quantidade_assentos is not None:
                    fila.quantidade_assentos = quantidade_assentos
                if ordem is not None:
                    fila.ordem = ordem
                fila.clean() 
                return self
        
        raise ValidationError({'fila': f'Fila "{nome_fila}" não encontrada'})
    
    def get_fila_por_nome(self, nome: str):
        """Busca uma fila pelo nome"""
        for fila in self.filas:
            if fila.nome.upper() == nome.upper():
                return fila
        return None
    
    @property
    def total_assentos(self) -> int:
        """Retorna o total de assentos do local"""
        return sum(fila.quantidade_assentos for fila in self.filas)
    
    @property
    def total_filas(self) -> int:
        """Retorna o total de filas do local"""
        return len(self.filas)
    
    @property
    def filas_ordenadas(self):
        """Retorna as filas ordenadas por ordem"""
        return sorted(self.filas, key=lambda f: f.ordem or f._calcular_ordem())
    
    def to_dict(self, exclude_fields=None, include_stats=True):
        """Override para incluir dados das filas e estatísticas"""
        data = super().to_dict(exclude_fields)
        
        # Converte filas para dict
        data['filas'] = [fila.to_dict() for fila in self.filas_ordenadas]
        
        if include_stats:
            data['total_assentos'] = self.total_assentos
            data['total_filas'] = self.total_filas
        
        return data
    
    @classmethod
    def buscar_por_nome(cls, nome: str):
        """Busca local por nome (case insensitive)"""
        return cls.ativos(nome__iexact=nome).first()
    
    @classmethod
    def listar_ativos(cls):
        """Lista todos os locais ativos ordenados por nome"""
        return cls.ativos().order_by('nome')
    
    @classmethod
    def buscar_por_capacidade_minima(cls, assentos_minimos: int):
        """Busca locais com capacidade mínima de assentos"""

        locais_adequados = []
        for local in cls.listar_ativos():
            if local.total_assentos >= assentos_minimos:
                locais_adequados.append(local)
        return locais_adequados
    
    def verificar_capacidade_suficiente(self, assentos_necessarios: int) -> bool:
        """Verifica se o local tem capacidade suficiente"""
        return self.total_assentos >= assentos_necessarios
    
    def get_distribuicao_filas(self):
        """Retorna estatísticas de distribuição das filas"""
        if not self.filas:
            return {}
        
        assentos_por_fila = [fila.quantidade_assentos for fila in self.filas]
        
        return {
            'total_filas': len(self.filas),
            'total_assentos': sum(assentos_por_fila),
            'media_assentos_por_fila': sum(assentos_por_fila) / len(assentos_por_fila),
            'menor_fila': min(assentos_por_fila),
            'maior_fila': max(assentos_por_fila),
            'filas_por_tamanho': {
                fila.nome: fila.quantidade_assentos 
                for fila in sorted(self.filas, key=lambda f: f.quantidade_assentos, reverse=True)
            }
        }
    
    def __str__(self):
        return f"{self.nome} ({self.total_filas} filas, {self.total_assentos} assentos)"
    
    def __repr__(self):
        return f"Local(nome='{self.nome}', filas={self.total_filas}, assentos={self.total_assentos})"
