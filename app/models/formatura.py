from mongoengine import EmbeddedDocument, StringField, IntField
from mongoengine import ValidationError
from mongoengine import StringField, DateField, ListField, EmbeddedDocumentField, ReferenceField
from mongoengine import BooleanField, ValidationError, queryset_manager
from datetime import date
from app.models.local import Local
from . import BaseModel, SoftDeleteMixin

class FormaturaCurso(EmbeddedDocument):
    """Embedded document para representar um curso em uma formatura específica"""
    
    curso_id = StringField(required=True) 
    qtd_formandos = IntField(required=True, min_value=1)
    
    def clean(self):
        """Validação do embedded document"""
        errors = {}
        
        if not self.curso_id:
            errors['curso_id'] = 'ID do curso é obrigatório'
        
        if not self.qtd_formandos or self.qtd_formandos <= 0:
            errors['qtd_formandos'] = 'Quantidade de formandos deve ser maior que zero'
        
        if errors:
            raise ValidationError(errors)
    
    @property
    def qtd_assentos(self) -> int:
        """Calcula quantidade de assentos (formando + acompanhante)"""
        return self.qtd_formandos * 2
    
    def to_dict(self):
        """Converte para dicionário incluindo campos calculados"""
        return {
            'curso_id': self.curso_id,
            'qtd_formandos': self.qtd_formandos,
            'qtd_assentos': self.qtd_assentos
        }
    
    def __str__(self):
        return f"FormaturaCurso(curso={self.curso_id}, formandos={self.qtd_formandos}, assentos={self.qtd_assentos})"
    

class Formatura(BaseModel,SoftDeleteMixin):
    """Modelo para representar uma formatura"""
    
    meta = {
        'collection': 'formaturas',
        'indexes': [
            'nome',
            'data',
            'local',
            'status',
            [('data', 1), ('status', 1)]
        ]
    }
    
    # Status possíveis para uma formatura
    STATUS_CHOICES = (
        ('planejamento', 'Planejamento'),
        ('confirmada', 'Confirmada'),
        ('realizada', 'Realizada'),
        ('cancelada', 'Cancelada')
    )
    
    nome = StringField(required=True, max_length=150)
    data = DateField(required=True)
    local = ReferenceField(Local, required=True)
    cursos = ListField(EmbeddedDocumentField(FormaturaCurso))
    observacoes = StringField(max_length=1000)
    status = StringField(choices=STATUS_CHOICES, default='planejamento')
    alocacao_gerada = BooleanField(default=False)
    
    def clean(self):
        """Validação customizada do modelo"""
        # Normaliza campos
        if self.nome:
            self.nome = self.nome.strip()
        if self.observacoes:
            self.observacoes = self.observacoes.strip()
        
        errors = {}
        
        # Valida nome
        if self.nome and len(self.nome) < 3:
            errors['nome'] = 'Nome deve ter pelo menos 3 caracteres'
        
        # Valida cursos
        if not self.cursos or len(self.cursos) == 0:
            errors['cursos'] = 'Formatura deve ter pelo menos um curso'
        
        # Verifica duplicatas de cursos
        if self.cursos:
            cursos_ids = [curso.curso_id for curso in self.cursos]
            if len(cursos_ids) != len(set(cursos_ids)):
                errors['cursos'] = 'Não pode haver cursos duplicados na formatura'
        
        if errors:
            raise ValidationError(errors)
    
    @queryset_manager
    def ativas(cls, queryset):
        """Manager para formaturas ativas (não canceladas)"""
        return queryset.filter(status__ne='cancelada')
    
    @queryset_manager
    def proximas(cls, queryset):
        """Manager para formaturas próximas (futuras)"""
        return queryset.filter(
            data__gte=date.today(),
            status__ne='cancelada'
        ).order_by('data')
    
    def adicionar_curso(self, curso_id: str, qtd_formandos: int):
        """Adiciona um curso à formatura"""
        # Verifica se o curso já foi adicionado
        if any(curso.curso_id == curso_id for curso in self.cursos):
            raise ValidationError('Este curso já foi adicionado à formatura')
        
        formatura_curso = FormaturaCurso(
            curso_id=curso_id,
            qtd_formandos=qtd_formandos
        )
        
        # Validação será feita no clean() do FormaturaCurso
        formatura_curso.clean()
        
        self.cursos.append(formatura_curso)
        return self
    
    def remover_curso(self, curso_id: str):
        """Remove um curso da formatura"""
        self.cursos = [curso for curso in self.cursos if curso.curso_id != curso_id]
        return self
    
    def atualizar_curso(self, curso_id: str, qtd_formandos: int):
        """Atualiza a quantidade de formandos de um curso"""
        for curso in self.cursos:
            if curso.curso_id == curso_id:
                curso.qtd_formandos = qtd_formandos
                curso.clean()  # Revalida
                return self
        
        raise ValidationError('Curso não encontrado na formatura')
    
    def get_curso_formatura(self, curso_id: str):
        """Busca um curso específico na formatura"""
        for curso in self.cursos:
            if curso.curso_id == curso_id:
                return curso
        return None
    
    @property
    def total_formandos(self) -> int:
        """Retorna o total de formandos da formatura"""
        return sum(curso.qtd_formandos for curso in self.cursos)
    
    @property
    def total_assentos_necessarios(self) -> int:
        """Retorna o total de assentos necessários"""
        return sum(curso.qtd_assentos for curso in self.cursos)
    
    @property
    def pode_gerar_alocacao(self) -> bool:
        """Verifica se pode gerar alocação"""
        return (
            len(self.cursos) > 0 and
            self.local is not None and
            self.status in ['planejamento', 'confirmada']
        )
    
    @property
    def capacidade_suficiente(self) -> bool:
        """Verifica se o local tem capacidade suficiente"""
        if not self.local:
            return False
        return self.local.total_assentos >= self.total_assentos_necessarios
    
    def confirmar(self):
        """Confirma a formatura"""
        if self.status == 'planejamento':
            self.status = 'confirmada'
        return self
    
    def cancelar(self):
        """Cancela a formatura"""
        if self.status in ['planejamento', 'confirmada']:
            self.status = 'cancelada'
            self.alocacao_gerada = False
        return self
    
    def marcar_como_realizada(self):
        """Marca a formatura como realizada"""
        if self.status == 'confirmada':
            self.status = 'realizada'
        return self
    
    def marcar_alocacao_gerada(self):
        """Marca que a alocação foi gerada"""
        self.alocacao_gerada = True
        return self
    
    def to_dict(self, exclude_fields=None, include_stats=True) -> dict:
        """Converte para dicionário com opções de incluir estatísticas"""
        data = super().to_dict(exclude_fields)
        data["id"] = str(self.id)
        # Converte data para string
        if self.data:
            data['data'] = self.data.isoformat()
        
        # Converte local
        if self.local:
           data['local'] = self.local.to_dict()

        
        # Converte cursos
        data['cursos'] = [curso.to_dict() for curso in self.cursos]
        
        if include_stats:
            data['total_formandos'] = self.total_formandos
            data['total_assentos_necessarios'] = self.total_assentos_necessarios
            data['pode_gerar_alocacao'] = self.pode_gerar_alocacao
            data['capacidade_suficiente'] = self.capacidade_suficiente
        
        return data
    
    @classmethod
    def buscar_por_nome(cls, nome: str):
        """Busca formatura por nome"""
        return cls.ativas(nome__iexact=nome).first()
    
    @classmethod
    def buscar_por_local(cls, local):
        """Busca formaturas por local"""
        return cls.ativas(local=local)
    
    @classmethod
    def buscar_por_periodo(cls, data_inicio: date, data_fim: date):
        """Busca formaturas em um período"""
        return cls.ativas(
            data__gte=data_inicio,
            data__lte=data_fim
        ).order_by('data')
    
    @classmethod
    def listar_proximas(cls, dias: int = 30):
        """Lista formaturas nos próximos X dias"""
        from datetime import timedelta
        data_limite = date.today() + timedelta(days=dias)
        
        return cls.ativas(
            data__gte=date.today(),
            data__lte=data_limite
        ).order_by('data')
    
    def __str__(self):
        return f"{self.nome} - {self.data.strftime('%d/%m/%Y')}"
    
    def __repr__(self):
        return f"Formatura(nome='{self.nome}', data='{self.data}', status='{self.status}')"