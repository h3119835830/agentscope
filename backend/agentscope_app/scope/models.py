from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChangeRequest(Strict):
    kind: Literal["task_grant", "restrict", "expand", "guidance"]
    text: str = Field(min_length=4, max_length=2000)
    request_key: str = Field(min_length=1, max_length=100)
    expected_snapshot: str | None = None


class Proposal(Strict):
    decision: Literal["task_grant", "restrict", "expand", "guidance_only", "no_change"]
    allowed_write_dirs: list[Literal["backend", "frontend"]] = Field(default_factory=list)
    allow_output: bool = False
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    explanation: str = Field(min_length=4, max_length=2000)


class Review(Strict):
    decision: Literal["approve", "reject"]
    expected_proposal_hash: str
    reviewed_by: str = Field(default="研究者", min_length=1, max_length=80)


class ToolCall(Strict):
    args: dict = Field(default_factory=dict)
