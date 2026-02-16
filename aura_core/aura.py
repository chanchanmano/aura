from pydantic import Json
from aura_core.config.policy_schema import PolicyConfig
from aura_core.evaluate.policy import Policy
from aura_core.engine.policy_manager import PolicyManager
from aura_core.logstore import store


class Aura:

    def __init__(self, store: store, policy_config:PolicyConfig):
        self.store = store
        self.policy_manager = PolicyManager(Policy(policy_config))
    
    def process_capture(self, data_dump:Json):
        pass

    def log(self, log_entry, labels: dict = {}, *args, **kwargs):
        return self.store.store_log(log_entry, labels, *args, **kwargs)

    def query(self, logql_query: str, start_ns: int = None, *args, **kwargs):
        if not logql_query:
            return

        return self.store.query(logql_query, start_ns, *args, **kwargs)

    def ingest_log_file(self):
        pass

    def escalate(self):
        pass

    def evaluate_logs(self):
        pass
