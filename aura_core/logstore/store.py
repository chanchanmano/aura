import requests
import json
import time


class LokiLogStore:

    standard_labels = {"type":"general"}

    def __init__(self, config):
        """
        config: dict with keys:
          - host: URL of Loki, e.g., http://localhost:3100
          - service_name: e.g., 'auracore'
        """
        self.config = config
        self.host = config.get("host", "localhost")
        self.port = config.get("port",3100)
        self.host_url = f"http://{self.host}:{self.port}"
        self.service_name = config.get("service_name", "auracore")
        print(f"Connected to Loki at {self.host_url}!")

    def store_log(self, log_entry: dict, labels: dict = None):
        if labels is None:
            labels = {}

        loki_labels = {
            "type": "general",
            "service": self.service_name
        }

        loki_labels.update(labels)

        payload = {
            "streams": [
                {
                    "stream": loki_labels,
                    "values": [
                        [
                            str(int(time.time() * 1e9)),
                            json.dumps(log_entry)
                        ]
                    ]
                }
            ]
        }

        # print("PAYLOAD:", json.dumps(payload, indent=2))
        resp = requests.post(f"{self.host_url}/loki/api/v1/push", json=payload)
        # print("STATUS:", resp.status_code)
        # print("BODY:", resp.text)
        if resp.status_code != 204:
            print(f"Failed to push log to Loki: {resp.text}")
        
        print("Logged successfully")

    def query_logs(self, logql_query: str, start_ns: int = None, end_ns: int = None):
        """
        Query Loki using LogQL.
        - logql_query: string like '{service="auracore",agent="planner"} | json | confidence_score<0.5'
        - start_ns, end_ns: timestamps in nanoseconds (optional)
        """
        params = {"query": logql_query}
        if start_ns:
            params["start"] = str(start_ns)
        if end_ns:
            params["end"] = str(end_ns)

        resp = requests.get(f"{self.host_url}/loki/api/v1/query_range", params=params)
        if resp.status_code != 200:
            print(f"Query failed: {resp.text}")
            return []

        data = resp.json().get("data", {}).get("result", [])
        logs = []
        for stream in data:
            for entry in stream.get("values", []):
                ts, line = entry
                logs.append({"timestamp": int(ts), "line": json.loads(line)})

        return logs
