from aura_core.logstore.store import LokiLogStore
from aura_core.config import AuraConfig
from aura_core.aura import Aura


def create_aura():
    log_config = AuraConfig.get_log_config()
    aura_config = AuraConfig.get_config()
    store = LokiLogStore(log_config)
    return Aura(store, **aura_config)