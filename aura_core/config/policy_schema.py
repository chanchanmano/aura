from pydantic import BaseModel
from typing import Union, List, Literal


class ConditionConfig(BaseModel):
    field: str
    comparator: str
    value: Union[int, float, str]


class ActionConfig(BaseModel):
    type: str
    target: str | None = None


class RuleConfig(BaseModel):
    ruleset: str
    tag: str
    name: str
    action: ActionConfig
    log_fields: List[str] = []
    evaluation_on: str = "AND"
    conditions: List[ConditionConfig]


class RulesetConfig(BaseModel):
    name: str
    priority: int = 0


class PolicyMetadata(BaseModel):
    name: str
    version: float
    author: str
    collision_resolution: Literal["override"] = "override"


class PolicyConfig(BaseModel):
    policy: PolicyMetadata
    rulesets: List[RulesetConfig]
    rules: List[RuleConfig]
