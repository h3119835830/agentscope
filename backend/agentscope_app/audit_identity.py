"""Request-scoped credential provenance; shared credentials are not a person."""
from contextvars import ContextVar
from pydantic import BaseModel, model_validator

principal=ContextVar('control_principal',default=None)

class AuditModel(BaseModel):
    @model_validator(mode='after')
    def trusted_actor(self):
        actor=principal.get()
        if actor:
            for field in ('actor','reviewed_by'):
                if field in type(self).model_fields:setattr(self,field,actor)
        return self
