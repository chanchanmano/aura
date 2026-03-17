import json
import time
from urllib import error, parse, request


class LokiNotReadyError(RuntimeError):
    pass


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
        self.port = config.get("port", 3100)
        self.timeout_s = float(config.get("timeout_s", 2.0))
        self.host_url = f"http://{self.host}:{self.port}"
        self.service_name = config.get("service_name", "auracore")
        print(f"Connected to Loki at {self.host_url}!")

    def _request(self, *, method: str, path: str, payload=None, params=None):
        url = f"{self.host_url}{path}"
        if params:
            url = f"{url}?{parse.urlencode(params)}"

        headers = {}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")

        req = request.Request(url, data=body, headers=headers, method=method)
        with request.urlopen(req, timeout=self.timeout_s) as resp:
            return resp.status, resp.read().decode("utf-8")

    def is_ready(self) -> bool:
        try:
            status_code, response_text = self._request(
                method="GET",
                path="/ready",
            )
        except (error.URLError, TimeoutError, OSError):
            return False

        return status_code == 200 and response_text.strip().lower() == "ready"

    def require_ready(self) -> None:
        if not self.is_ready():
            raise LokiNotReadyError(f"Loki is not ready at {self.host_url}")

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

        try:
            status_code, response_text = self._request(
                method="POST",
                path="/loki/api/v1/push",
                payload=payload,
            )
        except (error.URLError, TimeoutError, OSError) as exc:
            print(f"Failed to push log to Loki: {exc}")
            return False

        if status_code != 204:
            print(f"Failed to push log to Loki: {response_text}")
            return False

        print("Logged successfully")
        return True

    def query_logs(
        self,
        logql_query: str,
        start_ns: int = None,
        end_ns: int = None,
        limit: int = None,
        direction: str = None,
    ):
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
        if limit:
            params["limit"] = str(limit)
        if direction:
            params["direction"] = direction

        try:
            status_code, response_text = self._request(
                method="GET",
                path="/loki/api/v1/query_range",
                params=params,
            )
        except (error.URLError, TimeoutError, OSError) as exc:
            print(f"Query failed: {exc}")
            return []

        if status_code != 200:
            print(f"Query failed: {response_text}")
            return []

        data = json.loads(response_text).get("data", {}).get("result", [])
        logs = []
        for stream in data:
            labels = stream.get("stream", {})
            for entry in stream.get("values", []):
                ts, line = entry
                logs.append(
                    {
                        "timestamp": int(ts),
                        "line": json.loads(line),
                        "labels": labels,
                    }
                )

        return logs
