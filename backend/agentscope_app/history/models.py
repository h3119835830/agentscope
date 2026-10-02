from typing import Literal, TypedDict
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Origin(StrictModel):
    document_id: str
    repository: str
    commit: str
    path: str
    content_hash: str
    url: str = ""

class MarkdownDocument(StrictModel):
    text: str
    origin: Origin

class Statement(StrictModel):
    source_quote: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    text_original: str = Field(min_length=1)
    text_zh: str = ""
    text_en: str = ""
    language: str = "en"
    content_type: Literal["description", "policy", "mixed", "uncertain"]
    policy_kind: Literal["instruction", "constraint", "preference", "none"] = "none"
    topics: list[str]
    enforcement_level: Literal["semantic_only", "content", "per_event", "cross_event", "not_applicable"]
    context_requirement: Literal["self_contained", "project", "task", "not_applicable"]
    uncertainties: list[str] = []
    evidence_state: str = "pending"
    char_start: int | None = None
    char_end: int | None = None

    @model_validator(mode="after")
    def english_original(self):
        if self.language.lower().startswith("en") and not self.text_en:
            self.text_en=self.text_original
        return self

class StrategyStatementVersion(StrictModel):
    id: str
    strategy_id: str
    version: int
    origin: Origin
    statement: Statement
    scope_path: str = ""
    resolved_context: dict = {}
    review_status: str = "pending_review"

class ExtractionResult(StrictModel):
    statements: list[Statement]
    coverage: dict
    llm_runs: list[dict]

class CandidateRule(StrictModel):
    source: str
    target: str
    effect: Literal["block", "notify", "kill", "none"]
    gate: str = "none"
    reason: str

    @field_validator("gate",mode="before")
    @classmethod
    def canonical_gate(cls,value):
        return "none" if value is None else value

class Translation(StrictModel):
    candidate_rule: CandidateRule
    actplane_dsl: str | None
    required_context: list[str] = Field(default_factory=list,description="Names of missing context parameters ONLY. Empty when VERIFIED_CONTEXT supplies all needed values.")
    context_used: list[str] = Field(default_factory=list,description="Already supplied context values used by the translation; these are NOT missing parameters.")
    required_hooks: list[str] = []
    unresolved: list[str] = Field(default_factory=list,description="Remaining semantic or capability gaps ONLY; resolved assumptions are not gaps.")
    semantic_notes: list[str] = []

    @field_validator("semantic_notes",mode="before")
    @classmethod
    def canonical_notes(cls,value):
        return [value] if isinstance(value,str) and value else ([] if value is None or value=="" else value)

class PolicyArtifactCandidate(StrictModel):
    statement_version_id: str
    policy_record: dict
    pseudo_code: str
    actplane_dsl: str | None
    state: str
    llm_runs: list[dict]


class LoadReceipt(TypedDict):
    task_id: str
    deployment_id: str
    bundle_hash: str
    domain_id: int
    runner_pid: int
    binding_confirmed: bool
    artifact_version_ids: list[str]
