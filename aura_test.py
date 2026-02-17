import json

from aura_core.bootstrap.bootstrap import create_aura
from datetime import datetime, timedelta
import time


def run_aura_pipeline_test():
    """
    End-to-end escalation test for Aura.
    Validates ruleset transitions based on policy conditions.
    """

    aura = create_aura()
    assert aura.policy_manager.active_ruleset == "general", \
        "Aura should start in 'general' ruleset"

    print("✓ Initial ruleset is general")
    event_escalate = json.dumps({
        "risk_score": 0.92,
        "tool_used": "external_api",

        # extra fields (logged, not evaluated)
        "controller.latency.time": 1200,
        "controller.sensitivity": "high",
        "model.temperature": 0.8
    })

    aura.capture(event_escalate)

    print("Active ruleset after escalation attempt:",
          aura.policy_manager.active_ruleset)

    assert aura.policy_manager.active_ruleset == "maximal_logging", \
        "Expected escalation to 'maximal_logging'"

    print("✓ Step 1 passed (general → maximal_logging)")
    event_deescalate = json.dumps({
        "agent_latency": 80,
        "risk_score": 0.4
    })

    aura.capture(event_deescalate)
    print("Active ruleset after de-escalation attempt:",
          aura.policy_manager.active_ruleset)
    assert aura.policy_manager.active_ruleset == "minimal_logging", \
        "Expected de-escalation to 'minimal_logging'"

    print("✓ Step 2 passed (maximal_logging → minimal_logging)")
    event_reset = json.dumps({
        "event_type": "heartbeat",
        "risk_score": 0.3
    })

    aura.capture(event_reset)

    print("Active ruleset after reset attempt:",
          aura.policy_manager.active_ruleset)

    assert aura.policy_manager.active_ruleset == "general", \
        "Expected return to 'general' ruleset"

    print("✓ Step 3 passed (minimal_logging → general)")
    return aura


if __name__ == "__main__":
    print("\n🔥 Running Aura end-to-end escalation test 🔥\n")

    aura = run_aura_pipeline_test()

    print("\n🎉 Aura escalation test completed successfully 🎉\n")
    service_name = aura.store.service_name
    logql_query = f'{{service="{service_name}"}} | json'

    # Optional: limit to last 5 minutes4
    end_ts = int(time.time() * 1e9)
    start_ts = int((time.time() - 9000) * 1e9) 

    logs = aura.store.query_logs(logql_query, start_ns=start_ts, end_ns=end_ts)

    print(f"Fetched {len(logs)} logs from Loki:\n")
    for entry in logs:
        ts = datetime.fromtimestamp(entry["timestamp"] / 1e9)
        print(f"[{ts}] {entry['line']}")