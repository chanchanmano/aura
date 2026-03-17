from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from aura_core.logstore.store import LokiLogStore
from aura_core.visualizer.dashboard import render_dashboard_html


def _build_query(
    *,
    service: str | None,
    ruleset: str | None,
    run_id: str | None,
    logql: str | None,
) -> str:
    if logql:
        return logql

    selectors = ['type="general"']
    if service:
        selectors.append(f'service="{service}"')
    if ruleset:
        selectors.append(f'ruleset="{ruleset}"')

    query = "{" + ",".join(selectors) + "} | json"
    if run_id:
        query += f' | run_id="{run_id}"'
    return query


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render an Aura HTML dashboard from logs stored in Loki."
    )
    parser.add_argument("--host", default="localhost", help="Loki host. Default: localhost")
    parser.add_argument("--port", type=int, default=3100, help="Loki port. Default: 3100")
    parser.add_argument(
        "--service",
        default="ai-travel-agent",
        help="Service label to query. Use empty string with --logql to override.",
    )
    parser.add_argument("--ruleset", default=None, help="Optional ruleset label filter.")
    parser.add_argument("--run-id", default=None, help="Optional run_id JSON field filter.")
    parser.add_argument("--logql", default=None, help="Custom LogQL query.")
    parser.add_argument(
        "--hours",
        type=float,
        default=24.0,
        help="Look back window in hours. Default: 24.",
    )
    parser.add_argument(
        "--max-logs",
        type=int,
        default=1000,
        help="Maximum number of logs to fetch. Default: 1000.",
    )
    parser.add_argument(
        "--output",
        default="runtime/visualizations/aura_dashboard.html",
        help="Output HTML path. Default: runtime/visualizations/aura_dashboard.html",
    )
    args = parser.parse_args()

    query = _build_query(
        service=args.service or None,
        ruleset=args.ruleset,
        run_id=args.run_id,
        logql=args.logql,
    )
    start_ns = int((datetime.now() - timedelta(hours=args.hours)).timestamp() * 1e9)

    store = LokiLogStore(
        {
            "host": args.host,
            "port": args.port,
            "service_name": args.service or "auracore",
        }
    )
    logs = store.query_logs(
        query,
        start_ns=start_ns,
        limit=args.max_logs,
        direction="backward",
    )

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_dashboard_html(
        logs,
        query=query,
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        max_logs=args.max_logs,
    )
    output_path.write_text(html, encoding="utf-8")

    print(f"Wrote Aura dashboard to {output_path}")
    print(f"Logs rendered: {len(logs)}")
    print(f"Query: {query}")


if __name__ == "__main__":
    main()
