from aura_core.evaluate.policy import Policy
from aura_core.evaluate.rule import Rule


class PolicyManager:

    def __init__(self, policy: Policy):
        self.policy = policy
        self.active_ruleset = "general"

    def evaluate(self, event: dict) -> tuple[list[Rule], str | None]:

        rules = self.policy.get_rules_for_ruleset(self.active_ruleset)
        triggered = [rule for rule in rules if rule.evaluate(event)]

        if not triggered:
            return [], None

        winning_ruleset = self._resolve_override(triggered)
        return triggered, winning_ruleset

    def get_relevant_logs(self, rules: list[Rule]) -> list[str]:
        """
        Returns the logs that belongs to rules passed as parameters
        """

        logs = set()
        for rule in rules:
            [logs.add(log) for log in rule.log_fields]

        return logs

    def get_active_log_fields(self) -> set[str]:
        rules = self.policy.get_rules_for_ruleset(self.active_ruleset)

        fields = set()
        for rule in rules:
            fields.update(rule.log_fields)

        return fields

    def _resolve_override(self, rules: list[Rule]) -> str | None:
        """
        Override strategy:
        If multiple rules fire,
        return the target ruleset with highest priority.
        """

        winning_ruleset = None
        max_priority = -1

        for rule in rules:
            target = getattr(rule.action, "target", None)
            if not target:
                continue

            priority = self.policy.get_priority(target)
            if priority > max_priority:
                max_priority = priority
                winning_ruleset = target

        return winning_ruleset

    def apply_action(self, target_ruleset: str | None):
        if target_ruleset:
            self._switch_ruleset(target_ruleset)

    def _switch_ruleset(self, target: str):
        if target not in self.policy.ruleset_priorities:
            raise ValueError(f"Unknown ruleset {target}")

        self.active_ruleset = target

    def build_log_payload(self, event: dict, rule):
        payload = {}

        for field in rule.log_fields:
            payload[field] = self._extract_field(event, field)

        return payload

    def _extract_field(self, event: dict, path: str):
        value = event
        for part in path.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
            if value is None:
                return None
        return value
