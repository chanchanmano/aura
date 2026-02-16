class Condition:

    def __init__(self, field: str, comparator: str, value):
        self.field = field
        self.comparator = comparator
        self.value = value

    def evaluate(self, event: dict) -> bool:
        actual = self._extract_field(event)

        if actual is None:
            return False

        if self.comparator == ">":
            return actual > self.value
        elif self.comparator == "<":
            return actual < self.value
        elif self.comparator == "==":
            return actual == self.value
        elif self.comparator == "<=":
            return actual <= self.value
        elif self.comparator == ">=":
            return actual >= self.value
        else:
            raise ValueError(f"Unsupported comparator {self.comparator}")

    def _extract_field(self, event: dict):
        """
        Supports dot-path extraction:
        controller.latency.time
        """
        value = event
        for part in self.field.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
            if value is None:
                return None
        return value
