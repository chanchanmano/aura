import json
from aura_core.config.policy_schema import PolicyConfig
from aura_core.evaluate.policy import Policy
from aura_core.engine.policy_manager import PolicyManager
from aura_core.logstore.store import LokiLogStore


class Aura:

    def __init__(self, store: LokiLogStore, policy_config: PolicyConfig):
        self.store = store
        self.policy_manager = PolicyManager(Policy(policy_config))

    def capture(self, json_payload: str):
        """
        Public entrypoint.
        Accepts JSON string, logs it, evaluates policy, updates state.
        """
        try:
            data_dump = json.loads(json_payload)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON passed to aura.capture()")

        self.process_capture(data_dump)

    def process_capture(self, data_dump: dict):

        payload = self.prepare_log(data_dump)
        labels = self.prepare_labels()
        self.log(payload, labels)
        triggered, winning_ruleset = self.policy_manager.evaluate(data_dump)
        if winning_ruleset:
            self.policy_manager.apply_action(winning_ruleset)

    def prepare_log(self, data_dump: dict) -> dict:
        fields = self.policy_manager.get_active_log_fields()

        payload = {
            field: self.policy_manager._extract_field(data_dump, field)
            for field in fields
        }

        payload["_aura"] = {
            "active_ruleset": self.policy_manager.active_ruleset,
            "policy": self.policy_manager.policy.name,
            "policy_version": self.policy_manager.policy.version,
        }

        return payload

    def prepare_labels(self) -> dict:
        return {
            "ruleset": self.policy_manager.active_ruleset,
            "policy": self.policy_manager.policy.name,
        }

    def log(self, log_entry: dict, labels: dict = None):
        return self.store.store_log(log_entry, labels)

    def query(self, logql_query: str, start_ns: int = None, *args, **kwargs):
        if not logql_query:
            return
        return self.store.query_logs(logql_query, start_ns, *args, **kwargs)
