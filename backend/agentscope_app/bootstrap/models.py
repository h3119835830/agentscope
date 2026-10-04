from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Atom(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["reuse", "parameterize", "new_candidate"]
    statement: str = Field(min_length=3, max_length=2000)
    evidence_ids: list[str] = Field(min_length=1, max_length=20, description="Actual opaque source IDs returned by list/read tools; never role names or invented IDs")
    history_id: str | None = None
    history_hash: str | None = None
    operations: list[Literal["write", "unlink"]] = Field(min_length=1, max_length=2)
    paths: list[str] = Field(min_length=1, max_length=30)
    reason: str = Field(min_length=3, max_length=1000)


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context_hash: str
    summary: str = Field(min_length=3, max_length=2000)
    atoms: list[Atom] = Field(default_factory=list, max_length=20)
    guidance: list[str] = Field(default_factory=list, max_length=20)
    unresolved: list[str] = Field(default_factory=list, max_length=20, description="Unresolved necessary execution constraints only. Semantic requirements go in guidance. Do not invent gaps for assets or task requirements absent from evidence.")
    no_op: bool = False


class GenerateRequest(BaseModel):
    condition: Literal["A", "B"] = "B"


class FixtureTaskRequest(BaseModel):
    condition: Literal["A", "B"] = "B"


class VersionRequest(BaseModel):
    condition: Literal["A", "B"] = "B"
