
from enum import Enum
from pydantic import BaseModel


class RunMode(str, Enum):
    EMBEDDED = "embedded"
    SERVICE = "service"

class AuraConfig():

    mode: RunMode = RunMode.EMBEDDED

    log_host = "localhost"
    log_port = 3100

    @classmethod
    def get_log_config(cls):
        return {
            "host":cls.log_host,
            "port":cls.log_port
        }

    @classmethod
    def get_config(self):
        return {}