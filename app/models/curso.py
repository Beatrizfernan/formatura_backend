from mongoengine import StringField, ValidationError, queryset_manager
from . import BaseModel, SoftDeleteMixin
import re

class Curso(BaseModel, SoftDeleteMixin):
    """Modelo para representar um curso"""
    
    meta = {
        'collection': 'cursos',
        'indexes': [
            {'fields': ['nome'], 'unique': True, 'partialFilterExpression': {'ativo': True}},
            {'fields': ['abreviacao'], 'unique': True, 'sparse': True},
            'ativo',
            'created_at',
            'updated_at'
        ]
    }
    
    nome = StringField(required=True, max_length=100)
    abreviacao = StringField(required=False, max_length=20, min_length=2)  # ✅ ALTERADO: max_length=20
    cor = StringField(required=False, max_length=7)
    
    def clean(self):
        """Validação customizada do modelo"""
        # Normaliza campos
        if self.nome:
            self.nome = self.nome.strip()
        if self.abreviacao:
            self.abreviacao = self.abreviacao.strip()  # ✅ REMOVIDO .upper() para manter "Farm" com F maiúsculo
        if self.cor:
            self.cor = self.cor.strip()
        
        errors = {}
        
        # Valida nome
        if self.nome and len(self.nome) < 3:
            errors['nome'] = 'Nome deve ter pelo menos 3 caracteres'
        
        # Valida abreviação (apenas se fornecida)
        if self.abreviacao:
            if len(self.abreviacao) < 2:
                errors['abreviacao'] = 'Abreviação deve ter pelo menos 2 caracteres'
            if len(self.abreviacao) > 20:
                errors['abreviacao'] = 'Abreviação deve ter no máximo 20 caracteres'
        
        # Valida cor hexadecimal (apenas se fornecida)
        if self.cor and not re.match(r'^#[0-9A-Fa-f]{6}$', self.cor):
            errors['cor'] = 'Cor deve ser um código hexadecimal válido (ex: #ffcc00)'
        
        if errors:
            raise ValidationError(errors)
    
    @queryset_manager
    def ativos(cls, queryset):
        """Manager para cursos ativos"""
        return queryset.filter(ativo=True)
    
    @classmethod
    def buscar_por_nome(cls, nome: str):
        """Busca curso por nome (case insensitive)"""
        return cls.ativos(nome__iexact=nome).first()
    
    @classmethod
    def buscar_por_abreviacao(cls, abreviacao: str):
        """Busca curso por abreviação (case insensitive)"""
        if not abreviacao:
            return None
        return cls.ativos(abreviacao__iexact=abreviacao).first()
    
    @classmethod
    def listar_ativos(cls):
        """Lista todos os cursos ativos ordenados por nome"""
        return cls.ativos().order_by('nome')
    
    def to_dict(self, exclude_fields=None):
        """Override para incluir campos específicos"""
        data = super().to_dict(exclude_fields)
        return data
    
    def __str__(self):
        if self.abreviacao:
            return f"{self.nome} ({self.abreviacao})"
        return self.nome
    
    def __repr__(self):
        return f"Curso(nome='{self.nome}', abreviacao='{self.abreviacao}')"