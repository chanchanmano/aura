import yaml
from enum import Enum
from pydantic import BaseModel

from aura_core.config.policy_schema import PolicyConfig


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
        cls._validate_policy()
        return cls.policy_config

    @classmethod
    def _validate_policy(cls):
        rulesets = cls.policy_config.rulesets
        ruleset_names = [r.name for r in rulesets]

        # Must contain general
        if "general" not in ruleset_names:
            raise ValueError("A default 'general' ruleset is required.")

        # No duplicate names
        if len(set(ruleset_names)) != len(ruleset_names):
            raise ValueError("Duplicate ruleset names detected.")

        # No duplicate priorities
        priorities = [r.priority for r in rulesets]
        if len(set(priorities)) != len(priorities):
            raise ValueError("Duplicate ruleset priorities detected.")

        # Validate switch targets
        for rule in cls.policy_config.rules:
            if rule.action.type == "switch_ruleset":
                if rule.action.target not in ruleset_names:
                    raise ValueError(
                        f"Rule '{rule.name}' targets unknown ruleset "
                        f"'{rule.action.target}'."
                    )

        # Validate collision mode
        if cls.policy_config.policy.collision_resolution != "override":
            raise ValueError("Only 'override' collision resolution is supported.")
