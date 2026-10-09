"""Shared, tool-independent policy contract and deterministic ActPlane renderer."""
import json
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


# ActPlane stores patterns in a 64-byte C buffer, including the final NUL.
PATTERN_MAX_UTF8_BYTES = 63


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LabelExpression(Strict):
    kind: Literal["label", "true", "not", "all", "any"] = "label"
    label: str = "AGENT"
    operands: list["LabelExpression"] = Field(default_factory=list)


class Event(Strict):
    operation: Literal["exec", "open", "read", "write", "unlink", "connect"]
    pattern: str = Field(min_length=1)
    argument: str | None = None


class Gate(Strict):
    kind: Literal["target", "lineage", "after"]
    pattern: str
    argument: str | None = None
    exits_zero: bool = False
    since: list[Event] = Field(default_factory=list)


class Clause(Event):
    effect: Literal["block", "notify", "kill"] = "block"
    when: LabelExpression = Field(default_factory=LabelExpression)
    unless: Gate | None = None


class Rule(Strict):
    name: str
    reason: str = Field(min_length=1)
    clauses: list[Clause] = Field(min_length=1)


class Source(Strict):
    name: str
    kind: Literal["exec", "file", "endpoint"]
    pattern: str


class PolicyIR(Strict):
    version: Literal["PolicyIR/v1"] = "PolicyIR/v1"
    sources: list[Source] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


def identifier(value):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", value) or value == "AGENT":
        raise ValueError("IR 私有名称无效或重定义 AGENT")
    return value


def pattern(value, *, file=False):
    if any(c in value for c in '\n\r\0"\\') or len(value.encode("utf-8")) > PATTERN_MAX_UTF8_BYTES:
        raise ValueError(f"IR pattern 超过 {PATTERN_MAX_UTF8_BYTES} UTF-8 bytes 或包含控制字符")
    if file and (not value.startswith("/") or ".." in value.split("/") or "${" in value):
        raise ValueError("文件 pattern 必须为已绑定的规范绝对路径")
    return json.dumps(value, ensure_ascii=False)


def render(ir: PolicyIR, prefix: str) -> str | None:
    if ir.required_context or ir.unresolved or not ir.rules:
        return None
    names = {s.name for s in ir.sources}
    if len(names) != len(ir.sources) or len({r.name for r in ir.rules}) != len(ir.rules):
        raise ValueError("IR 名称重复")
    def expressions(e, negate=False):
        if e.kind == "true": return [] if negate else [[]]
        if e.kind == "label":
            if e.label != "AGENT" and e.label not in names: raise ValueError("IR 引用了未登记 label")
            label = "AGENT" if e.label == "AGENT" else prefix + identifier(e.label)
            return [[("not " if negate else "") + label]]
        if e.kind == "not":
            if len(e.operands) != 1: raise ValueError("not 必须有一个操作数")
            return expressions(e.operands[0], not negate)
        if len(e.operands) < 2: raise ValueError("复合 label 表达式至少两个操作数")
        is_all = (e.kind == "all") != negate
        result = [[]] if is_all else []
        for child in e.operands:
            terms = expressions(child, negate)
            result = [a+b for a in result for b in terms] if is_all else result+terms
            if len(result)>64: raise ValueError("label 表达式展开超过 64 个分支")
        return result
    def event(e, *, since=False):
        if since and e.operation != "write": raise ValueError("since 仅支持 write")
        if e.argument is not None and e.operation != "exec": raise ValueError("argument 仅适用于 exec")
        kind = "file " if e.operation in ("open", "read", "write", "unlink") and not since else "endpoint " if e.operation == "connect" else ""
        return e.operation + " " + kind + pattern(e.pattern, file=e.operation in ("open", "read", "write", "unlink")) + (" " + pattern(e.argument) if e.argument is not None else "")
    def gate(g):
        if g.kind == "target":
            if g.argument or g.since or g.exits_zero: raise ValueError("target gate 字段无效")
            return "target " + pattern(g.pattern)
        if g.kind == "lineage":
            if g.argument or g.since or g.exits_zero: raise ValueError("lineage gate 字段无效")
            return "lineage-includes exec " + pattern(g.pattern)
        return "after exec " + pattern(g.pattern) + (" " + pattern(g.argument) if g.argument is not None else "") + (" exits 0" if g.exits_zero else "") + (" since " + " or ".join(event(x, since=True) for x in g.since) if g.since else "")
    lines = ["source " + prefix + identifier(s.name) + " = " + s.kind + " " + pattern(s.pattern, file=s.kind == "file") for s in ir.sources]
    for rule in ir.rules:
        lines.append("rule " + prefix + identifier(rule.name) + ":")
        for clause in rule.clauses:
            if clause.argument is not None and clause.effect != "kill":
                raise ValueError("argv 敏感 exec 必须使用 kill")
            alternatives = expressions(clause.when)
            if not alternatives: raise ValueError("恒假规则需明确保留为非执行指导项")
            for terms in alternatives:
                lines.append("  " + clause.effect + " " + event(clause) + " if " + (" and ".join(terms) or "true") + (" unless " + gate(clause.unless) if clause.unless else ""))
        reason = rule.reason.replace('"', "'").replace("\\", "/").replace("\n", " ").replace("\r", " ")
        lines.append('  because "' + reason + '"')
    return "\n".join(lines)


def file_protection(paths, operations, reason, name="protected"):
    return PolicyIR(rules=[Rule(name=name, reason=reason,
        clauses=[Clause(operation=op, pattern=path) for path in paths for op in operations])])
