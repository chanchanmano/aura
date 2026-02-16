

from aura_core.evaluate.condition import Condition


class Rule:

    def __init__(
        self,
        ruleset: str,
        tag: str,
        name: str,
        action,
        conditions: list[Condition],
        evaluation_on: str = "AND",
        log_fields: list[str] | None = None,
    ):
        self.ruleset = ruleset
        self.tag = tag
        self.name = name
        self.action = action
        self.conditions = conditions
        self.evaluation_on = evaluation_on
        self.log_fields = log_fields or []

    def evaluate(self, event: dict) -> bool:
        results = [c.evaluate(event) for c in self.conditions]

        if self.evaluation_on == "AND":
            return all(results)

        if self.evaluation_on == "OR":
            return any(results)

        raise ValueError(f"Invalid evaluation mode {self.evaluation_on}")
