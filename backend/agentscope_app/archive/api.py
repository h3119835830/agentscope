"""Admin-protected read API; shared app middleware owns authentication."""
from typing import Literal
from fastapi import APIRouter, Query
from . import projection

router=APIRouter()

@router.get("/api/tasks/{task_id}/archive")
def task_archive(task_id: str, before: str|None=None, limit: int=Query(50,ge=1,le=200)):
    return projection.archive(task_id,before,limit)

@router.get("/api/tasks/{task_id}/archive/events")
def task_archive_events(task_id: str, category: Literal["timeline","tools","kernel","audit"]="timeline", before: str|None=None, limit: int=Query(50,ge=1,le=200), stage: Literal["preparation","execution","closure"]|None=None):
    return projection.events(task_id,category,before,limit,stage)

@router.get("/api/tasks/{task_id}/archive/events/{event_id}")
def task_archive_event(task_id: str, event_id: str):
    return projection.event_detail(task_id,event_id)


@router.get("/api/task-archives")
def task_archive_index(q: str=Query("",max_length=500), status: Literal["ended","active","all"]="all", page: int=Query(0,ge=0), limit: int=Query(12,ge=1,le=50)):
    return projection.archive_index(q,status,page,limit)


@router.get("/api/tasks/{task_id}/archive/domains")
def archive_domains(task_id: str, version: int|None=Query(None,ge=1)):
    from .historical import graph
    return graph(task_id,version)


@router.get("/api/tasks/{task_id}/archive/domains/{key}")
def archive_domain_detail(task_id: str, key: str):
    from .historical import domain_detail
    return domain_detail(task_id,key)
