from __future__ import annotations

import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml


WORKSPACE_ROOT = Path(__file__).resolve().parent
TRAVEL_AGENT_ROOT = Path(
    os.getenv("AI_TRAVEL_AGENT_DIR", str(WORKSPACE_ROOT / "ai-travel-agent"))
).expanduser().resolve()
POLICY_PATH = TRAVEL_AGENT_ROOT / "aura_policy.yml"

for path in (WORKSPACE_ROOT, TRAVEL_AGENT_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from aura_core.aura import Aura
from aura_core.config.config import validate_policy_config
from aura_core.config.policy_schema import PolicyConfig
from ai_travel_agent.observability.aura_bridge import _STATE, configure_aura, get_aura_status
from ai_travel_agent.observability.logger import LogContext, get_logger, log_event, setup_logging


@dataclass
class RecordedEntry:
    payload: dict
    labels: dict


class RecordingStore:
    def __init__(self, service_name: str = "ai-travel-agent-smoke") -> None:
        self.service_name = service_name
        self.entries: list[RecordedEntry] = []

    def store_log(self, log_entry: dict, labels: dict | None = None) -> bool:
        self.entries.append(
            RecordedEntry(payload=dict(log_entry), labels=dict(labels or {}))
        )
        return True


def _load_policy_config(path: Path) -> PolicyConfig:
    with path.open("r", encoding="utf-8") as f:
        raw_policy = yaml.safe_load(f)
    policy_config = PolicyConfig(**raw_policy)
    validate_policy_config(policy_config)
    return policy_config


def _install_in_memory_aura() -> tuple[RecordingStore, Aura]:
    configure_aura(
        enabled=True,
        policy_path=POLICY_PATH,
        host="localhost",
        port=3100,
        service_name="ai-travel-agent-smoke",
        timeout_s=0.25,
    )
    store = RecordingStore()
    client = Aura(store, _load_policy_config(POLICY_PATH))
    _STATE.client = client
    _STATE.init_error = None
    return store, client


def _reset_aura_bridge() -> None:
    _STATE.client = None
    _STATE.init_error = None
    configure_aura(enabled=False, policy_path=POLICY_PATH)


def _emit(
    *,
    logger: logging.Logger,
    store: RecordingStore,
    client: Aura,
    level: int,
    message: str,
    event: str,
    context: LogContext,
    data: dict,
) -> dict:
    before = len(store.entries)
    log_event(
        logger,
        level=level,
        message=message,
        event=event,
        context=context,
        data=data,
    )
    assert len(store.entries) == before + 1, f"Expected Aura to ingest event '{event}'"
    entry = store.entries[-1]
    return {
        "event": event,
        "logged_ruleset": entry.labels.get("ruleset"),
        "active_ruleset_after": client.policy_manager.active_ruleset,
        "has_span_payload_data": "span_payload.data" in entry.payload,
        "entry": entry,
    }


def run_aura_integration_smoke_test() -> list[dict]:
    if not POLICY_PATH.exists():
        raise FileNotFoundError(f"Missing travel-agent Aura policy: {POLICY_PATH}")

    with tempfile.TemporaryDirectory(prefix="aura-smoke-") as runtime_dir:
        os.environ.setdefault("CONSOLE_LOG_LEVEL", "CRITICAL")
        setup_logging(runtime_dir=Path(runtime_dir), level="INFO")
        logger = get_logger("aura.smoke")
        store, client = _install_in_memory_aura()

        status = get_aura_status()
        assert status["enabled"] is True
        assert status["init_error"] is None
        assert client.policy_manager.active_ruleset == "general"

        base_context = LogContext(
            run_id="smoke-run-001",
            user_id="smoke-user",
            graph_node="orchestrator",
            step_type="PLAN",
            step_id="step-1",
            step_title="Smoke test run",
            step_index=1,
        )

        try:
            snapshots = [
                _emit(
                    logger=logger,
                    store=store,
                    client=client,
                    level=logging.INFO,
                    message="Smoke run started",
                    event="mixed_run_start",
                    context=base_context,
                    data={
                        "run_mode": "smoke",
                        "scenario": "policy_switch",
                        "overall_status": "starting",
                    },
                ),
                _emit(
                    logger=logger,
                    store=store,
                    client=client,
                    level=logging.ERROR,
                    message="Forced tool failure",
                    event="tool_error",
                    context=LogContext(
                        run_id="smoke-run-001",
                        user_id="smoke-user",
                        graph_node="executor",
                        step_type="TOOL_CALL",
                        step_id="step-2",
                        step_title="Trigger escalation",
                        step_index=2,
                    ),
                    data={
                        "run_mode": "smoke",
                        "scenario": "policy_switch",
                        "tool_name": "flight_search",
                        "latency_ms": 3210,
                        "error": "timeout waiting for provider",
                    },
                ),
                _emit(
                    logger=logger,
                    store=store,
                    client=client,
                    level=logging.INFO,
                    message="Follow-up event under maximal logging",
                    event="tool_retry_scheduled",
                    context=LogContext(
                        run_id="smoke-run-001",
                        user_id="smoke-user",
                        graph_node="executor",
                        step_type="TOOL_CALL",
                        step_id="step-3",
                        step_title="Inspect maximal logging",
                        step_index=3,
                    ),
                    data={
                        "run_mode": "smoke",
                        "scenario": "policy_switch",
                        "tool_name": "flight_search",
                        "tool_attempt": 2,
                        "latency_ms": 850,
                        "debug_payload": {
                            "provider": "fallback",
                            "retryable": True,
                        },
                    },
                ),
                _emit(
                    logger=logger,
                    store=store,
                    client=client,
                    level=logging.INFO,
                    message="Healthy mixed run ended",
                    event="mixed_run_end",
                    context=LogContext(
                        run_id="smoke-run-001",
                        user_id="smoke-user",
                        graph_node="orchestrator",
                        step_type="RUN",
                        step_id="step-4",
                        step_title="Reset to general",
                        step_index=4,
                    ),
                    data={
                        "run_mode": "smoke",
                        "scenario": "policy_switch",
                        "overall_status": "good",
                        "termination_reason": "finalized",
                        "task_completion_rate": 1.0,
                        "goal_completion_rate": 1.0,
                        "tokens_total": 42,
                    },
                ),
                _emit(
                    logger=logger,
                    store=store,
                    client=client,
                    level=logging.INFO,
                    message="Post-reset heartbeat",
                    event="heartbeat",
                    context=LogContext(
                        run_id="smoke-run-001",
                        user_id="smoke-user",
                        graph_node="orchestrator",
                        step_type="RUN",
                        step_id="step-5",
                        step_title="Verify reset",
                        step_index=5,
                    ),
                    data={
                        "run_mode": "smoke",
                        "scenario": "policy_switch",
                        "overall_status": "steady",
                    },
                ),
            ]

            assert snapshots[0]["logged_ruleset"] == "general"
            assert snapshots[0]["active_ruleset_after"] == "general"
            assert snapshots[0]["has_span_payload_data"] is False

            assert snapshots[1]["logged_ruleset"] == "general"
            assert snapshots[1]["active_ruleset_after"] == "maximal_logging"

            assert snapshots[2]["logged_ruleset"] == "maximal_logging"
            assert snapshots[2]["active_ruleset_after"] == "maximal_logging"
            assert snapshots[2]["has_span_payload_data"] is True
            assert (
                snapshots[2]["entry"].payload["span_payload.data"]["debug_payload"]["provider"]
                == "fallback"
            )

            assert snapshots[3]["logged_ruleset"] == "maximal_logging"
            assert snapshots[3]["active_ruleset_after"] == "general"
            assert snapshots[3]["has_span_payload_data"] is True

            assert snapshots[4]["logged_ruleset"] == "general"
            assert snapshots[4]["active_ruleset_after"] == "general"
            assert snapshots[4]["has_span_payload_data"] is False

            return snapshots
        finally:
            _reset_aura_bridge()


if __name__ == "__main__":
    print("Running Aura integration smoke test")
    snapshots = run_aura_integration_smoke_test()
    for snapshot in snapshots:
        print(
            f"- {snapshot['event']}: logged as {snapshot['logged_ruleset']}, "
            f"active after capture={snapshot['active_ruleset_after']}, "
            f"span_payload.data={snapshot['has_span_payload_data']}"
        )
    print("Smoke test passed")
