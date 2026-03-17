import yaml
from enum import Enum

from aura_core.config.policy_schema import PolicyConfig


def validate_policy_config(policy_config: PolicyConfig) -> None:
    rulesets = policy_config.rulesets
    ruleset_names = [r.name for r in rulesets]

    if "general" not in ruleset_names:
        raise ValueError("A default 'general' ruleset is required.")

    if len(set(ruleset_names)) != len(ruleset_names):
        raise ValueError("Duplicate ruleset names detected.")

    priorities = [r.priority for r in rulesets]
    if len(set(priorities)) != len(priorities):
        raise ValueError("Duplicate ruleset priorities detected.")

    for rule in policy_config.rules:
        if rule.action.type == "switch_ruleset":
            if rule.action.target not in ruleset_names:
                raise ValueError(
                    f"Rule '{rule.name}' targets unknown ruleset "
                    f"'{rule.action.target}'."
                )

    if policy_config.policy.collision_resolution != "override":
        raise ValueError("Only 'override' collision resolution is supported.")


class RunMode(str, Enum):
    EMBEDDED = "embedded"
    SERVICE = "service"


class AuraConfig:

    mode: RunMode = RunMode.EMBEDDED

    log_host = "localhost"
    log_port = 3100

    policy_config: PolicyConfig = None

    @classmethod
    def get_log_config(cls):
        return {"host": cls.log_host, "port": cls.log_port}

    @classmethod
    def get_config(cls):
        return {
            "policy_path": "/Users/aryan/college_projects/aura/aura_sample.yml"
        }

    @classmethod
    def load_policy(cls, path: str):
        with open(path, "r") as f:
            raw_yaml = yaml.safe_load(f)

        cls.policy_config = PolicyConfig(**raw_yaml)
        validate_policy_config(cls.policy_config)
        return cls.policy_config

    @classmethod
    def _validate_policy(cls):
        validate_policy_config(cls.policy_config)
