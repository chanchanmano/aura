from aura_core.logstore.store import LokiLogStore
from aura_core.config.config import AuraConfig
from aura_core.aura import Aura


def create_aura():
    log_config = AuraConfig.get_log_config()
    aura_config = AuraConfig.get_config()
    policy_config = AuraConfig.load_policy(aura_config.get("policy_path"))
    store = LokiLogStore(log_config)
    return Aura(store, policy_config)