# aura

A project towards figuring out the observability metrics when evaluating agentic AI systems.

## Bootstrap

To set up the whole demo path from the Aura repo, run:

```bash
cd /Users/aryan/college_projects/aura
AI_TRAVEL_AGENT_DIR=/path/to/ai-travel-agent ./scripts/bootstrap_aura.sh
```

The bootstrap script in [bootstrap_aura.sh](/Users/aryan/college_projects/aura/scripts/bootstrap_aura.sh#L1):
- reuses the travel-agent checkout pointed to by `AI_TRAVEL_AGENT_DIR`
- if `AI_TRAVEL_AGENT_DIR` is not set, it clones `ai-travel-agent` into the Aura repo
- creates or reuses the `pyenv` env `ai-travel-agent-3.11`
- installs the travel-agent dependencies
- creates `ai-travel-agent/.env` if missing and enables Aura logging
- starts Loki and Grafana
- waits for both to become ready
- runs the end-to-end Aura smoke test automatically

If the existing `ai-travel-agent` checkout is dirty, the script intentionally does not change its branch.

## Loki / Grafana

Start the Aura logging stack:

```bash
cd /Users/aryan/college_projects/aura/aura_core
docker compose up -d
```

- Loki: `http://localhost:3100`
- Grafana: `http://localhost:3000` (`admin` / `admin`)

Grafana now auto-provisions a default Loki datasource named `Aura Loki`. That is the better option for live analysis while runs are still executing. Use Grafana Explore with LogQL such as:

```logql
{service="ai-travel-agent"} | json
```

```logql
{service="ai-travel-agent"} | json | run_id="mix-001"
```

```logql
{service="ai-travel-agent"} | json | event=~"llm_error|tool_error|node_error|failure_recorded"
```

Keep `run_id` as a JSON field rather than a Loki stream label. Grouping by `run_id` in the UI is the right tradeoff; making it a label would create high-cardinality streams and hurt Loki performance.

A provisioned dashboard is also included at:

```text
aura_core/grafana/provisioning/dashboards/json/aura-run-analytics.json
```

If Grafana was already running before this was added, reload it once:

```bash
cd /Users/aryan/college_projects/aura/aura_core
docker compose up -d --force-recreate grafana
```

The dashboard focuses on metrics that exist in the current Aura-shipped logs:
- event volume over time by `event_group`
- ruleset activity over time
- average per-event `latency_ms` grouped by `run_id`
- p95 latency across visible runs
- failure signal volume grouped by `run_id`
- terminal `failure_count_run_so_far` grouped by `run_id`
- failing nodes, failure categories, and run outcomes
- run-end and failure drilldown logs

Useful Explore queries behind the dashboard:

```logql
sum by (event_group) (
  count_over_time({service="ai-travel-agent"} | json | __error__="" [5m])
)
```

```logql
avg by (run_id) (
  avg_over_time({service="ai-travel-agent"} | json | __error__="" | run_id=~"mix-.*" | latency_ms != "" | unwrap latency_ms [5m])
)
```

```logql
quantile_over_time(0.95,
  {service="ai-travel-agent"} | json | __error__="" | latency_ms != "" | unwrap latency_ms [5m]
)
```

```logql
sum by (run_id) (
  count_over_time({service="ai-travel-agent"} | json | __error__="" | event=~"llm_error|tool_error|node_error|failure_recorded" [5m])
)
```

```logql
max by (run_id) (
  max_over_time({service="ai-travel-agent"} | json | __error__="" | event=~"run_end|mixed_run_end" | failure_count_run_so_far != "" | unwrap failure_count_run_so_far [24h])
)
```

```logql
topk(10,
  sum by (node) (
    count_over_time({service="ai-travel-agent"} | json | __error__="" | event=~"llm_error|tool_error|node_error|failure_recorded" [24h])
  )
)
```

## Smoke Test

Run the bridge-level Aura smoke test from the Aura repo:

```bash
cd /Users/aryan/college_projects/aura
AI_TRAVEL_AGENT_DIR=/path/to/ai-travel-agent /Users/aryan/.pyenv/versions/ai-travel-agent-3.11/bin/python aura_test.py
```

This does not require Loki. It drives the real travel-agent logging path:

```text
log_event(...) -> aura_bridge.capture_event(...) -> Aura.capture(...)
```

The script asserts the full policy transition sequence:
- starts in `general`
- a `tool_error` escalates Aura to `maximal_logging`
- the next event is logged under `maximal_logging`
- a healthy `mixed_run_end` resets Aura back to `general`
- the next event is logged under `general` again

It also checks that `span_payload.data` only appears once maximal logging is active, so the test proves both the ruleset switch and the logging-shape change.

## Aura Visualizer

Render a local HTML dashboard from the logs Aura has stored in Loki:

```bash
cd /Users/aryan/college_projects/aura
python aura_visualizer.py --service ai-travel-agent
```

This writes:

```text
runtime/visualizations/aura_dashboard.html
```

You can also change the query window or output path:

```bash
python aura_visualizer.py --service ai-travel-agent --hours 6 --max-logs 500
```

The HTML dashboard now groups logs by `run_id` first and keeps raw logs in a collapsible section. You can also narrow the snapshot to a single run:

```bash
python aura_visualizer.py --service ai-travel-agent --run-id mix-001
```
