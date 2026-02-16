from aura_core.config.policy_schema import PolicyConfig
from aura_core.evaluate.condition import Condition
from aura_core.evaluate.rule import Rule


class Policy:

    def __init__(self, policy_config: PolicyConfig):
        self.name = policy_config.policy.name
        self.version = policy_config.policy.version
        self.collision_resolution = policy_config.policy.collision_resolution

        self.ruleset_priorities = {
            rs.name: rs.priority
            for rs in policy_config.rulesets
        }

        self.rules = self._build_rules(policy_config)

    def _build_rules(self, policy_config: PolicyConfig):
        rules_by_ruleset = {}

        for rc in policy_config.rules:

            conditions = [
                Condition(
                    field=c.field,
                    comparator=c.comparator,
                    value=c.value,
                )
                for c in rc.conditions
            ]

            rule = Rule(
                ruleset=rc.ruleset,
                tag=rc.tag,
                name=rc.name,
                action=rc.action,
                conditions=conditions,
                evaluation_on=rc.evaluation_on,
                log_fields=rc.log_fields,
            )

            rules_by_ruleset.setdefault(rc.ruleset, []).append(rule)

        return rules_by_ruleset

    def get_rules_for_ruleset(self, ruleset_name: str):
        return self.rules.get(ruleset_name, [])

    def get_priority(self, ruleset_name: str) -> int:
        return self.ruleset_priorities.get(ruleset_name, 0)
