from aura_core.evaluate.policy import Policy


class PolicyManager:

    def __init__(self, policy: Policy):
        self.policy = policy
        self.active_ruleset = "general"

    def evaluate(self, event: dict):
        """
        Evaluate rules in the active ruleset.
        Return triggered rule (after override resolution).
        """

        rules = self.policy.get_rules_for_ruleset(
            self.active_ruleset
        )

        triggered = []

        for rule in rules:
            if rule.evaluate(event):
                triggered.append(rule)

        if not triggered:
            return None

        return self._resolve_override(triggered)

    def _resolve_override(self, rules: list):
        """
        Override strategy:
        If multiple rules fire,
        prefer rule whose target ruleset has highest priority.
        """

        if len(rules) == 1:
            return rules[0]

        def priority(rule):
            target = getattr(rule.action, "target", None)
            if target:
                return self.policy.get_priority(target)
            return 0

        return max(rules, key=priority)

    def apply_action(self, rule):
        """
        Executes rule action (e.g. switch_ruleset).
        """

        if rule.action.type == "switch_ruleset":
            self._switch_ruleset(rule.action.target)

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
