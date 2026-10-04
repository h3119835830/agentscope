from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, ConfigDict
from . import catalog
from .api import invoke
from typing import Literal

router=APIRouter(tags=["history-records"])

class Draft(BaseModel):
    model_config=ConfigDict(extra="forbid")
    text: str=Field(min_length=5,max_length=12000)
    category: str="semantic"
    context_scope: str="self-contained"
    execution_layer: str="repository_instruction"
    source_url: str|None=None
    actor: str="研究者"

class Revision(BaseModel):
    model_config=ConfigDict(extra="forbid")
    text: str|None=Field(default=None,min_length=5,max_length=12000)
    category: str|None=None
    context_scope: str|None=None
    execution_layer: str|None=None
    actor: str="研究者"
    reason: str=Field(default="",max_length=2000)

@router.get("/api/history/records")
def records(q:str="",status:str="",category:str="",context_scope:str="",source_repo:str="",archived:str="active",
        limit:int=Query(default=20,ge=1,le=100),offset:int=Query(default=0,ge=0),source_kind:str="",execution_layer:str="",completeness:str="",adaptation:str="",loadable:str=""):
    return invoke(catalog.page,q,status,category,context_scope,source_repo,archived,limit,offset,source_kind,execution_layer,completeness,adaptation,loadable)

class InputLabels(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enforcement_level:Literal['semantic_only','content','per_event','cross_event','not_applicable']='semantic_only'
    context_requirement:Literal['self_contained','project','task','not_applicable']='self_contained'
    text_zh:str=Field(default='',max_length=12000)
    text_en:str=Field(default='',max_length=12000)
    actor:str='研究者'
    task_id:str|None=None

class PolicyInput(InputLabels):
    text:str=Field(min_length=5,max_length=12000)

@router.post('/api/history/inputs')
def create_input(body:PolicyInput):
    from .inputs import create_input
    return invoke(create_input,body.model_dump(exclude={'actor'}),body.actor)

@router.post('/api/history/records/{ident}/statement-input')
def prepare_input(ident:str,body:InputLabels):
    from .inputs import prepare_record
    return invoke(prepare_record,ident,body.model_dump(exclude={'actor'}),body.actor)

@router.get("/api/history/records/{ident}")
def record(ident:str):
    return invoke(catalog.detail,ident)

@router.post("/api/strategies")
def create(body:Draft):
    return invoke(catalog.create,body.model_dump(exclude={"actor"}),body.actor)

@router.patch("/api/strategies/{ident}")
def revise(ident:str,body:Revision):
    values=body.model_dump(exclude={"actor","reason"},exclude_none=True,exclude_unset=True)
    return invoke(catalog.revise,ident,values,body.actor,body.reason)

@router.delete("/api/strategies/{ident}")
def archive(ident:str,actor:str="研究者"):
    return invoke(catalog.archive,ident,True,actor)

@router.post("/api/strategies/{ident}/restore")
def restore(ident:str,actor:str="研究者"):
    return invoke(catalog.archive,ident,False,actor)
