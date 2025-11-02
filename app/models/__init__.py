
from mongoengine import Document, EmbeddedDocument
from mongoengine import StringField, IntField, DateTimeField, BooleanField, DateField
from mongoengine import ListField, EmbeddedDocumentField, ReferenceField, ObjectIdField
from mongoengine import ValidationError, DoesNotExist, NotUniqueError
from datetime import datetime
from typing import Dict, Any, Optional, List
import json

class BaseModel(Document):
    """Classe base para todos os modelos do sistema"""
    
    
    meta = {
        'abstract': True, 
        'ordering': ['-created_at'],
        'indexes': [
            'created_at',
            'updated_at'
        ]
    }
    

    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    
    def save(self, *args, **kwargs):
        """Override do save para atualizar updated_at"""
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)
    
    def to_dict(self, exclude_fields: List[str] = None) -> Dict[str, Any]:
        """Converte o documento para dicionário"""
        exclude_fields = exclude_fields or []
        exclude_fields.extend(['created_at', 'updated_at'])
        
        data = self.to_mongo().to_dict()
        
       
        for field in exclude_fields:
            data.pop(field, None)
        
        
        if '_id' in data:
            data['id'] = str(data['_id'])
            del data['_id']
        
      
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
        
        return data
    
    def to_json(self, exclude_fields: List[str] = None) -> str:
        """Converte o documento para JSON"""
        return json.dumps(self.to_dict(exclude_fields), default=str, ensure_ascii=False)
    
    @classmethod
    def get_by_id(cls, doc_id: str):
        """Busca documento por ID"""
        try:
            return cls.objects(id=doc_id).first()
        except (ValidationError, DoesNotExist):
            return None
    
    @classmethod
    def get_or_404(cls, doc_id: str):
        """Busca documento por ID ou lança exceção"""
        doc = cls.get_by_id(doc_id)
        if not doc:
            raise DoesNotExist(f"{cls.__name__} com ID {doc_id} não encontrado")
        return doc
    
    def update_fields(self, **kwargs):
        """Atualiza campos do documento"""
        for field, value in kwargs.items():
            if hasattr(self, field):
                setattr(self, field, value)
        return self.save()
    
    @property
    def id_str(self) -> str:
        """Retorna o ID como string"""
        return str(self.id)


class SoftDeleteMixin:
    """Mixin para implementar soft delete"""
    
    ativo = BooleanField(default=True)
    deleted_at = DateTimeField()
    
    def delete(self, hard_delete: bool = False):
        """Soft delete ou hard delete"""
        if hard_delete:
            return super().delete()
        else:
            self.ativo = False
            self.deleted_at = datetime.utcnow()
            return self.save()
    
    def restore(self):
        """Restaura um documento soft-deleted"""
        self.ativo = True
        self.deleted_at = None
        return self.save()
    
    @classmethod
    def get_active(cls):
        """Retorna apenas documentos ativos"""
        return cls.objects(ativo=True)
    
    @classmethod
    def get_deleted(cls):
        """Retorna apenas documentos deletados"""
        return cls.objects(ativo=False)