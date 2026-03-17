from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from typing import Any


def _format_timestamp(timestamp_ns: int) -> str:
    dt = datetime.fromtimestamp(timestamp_ns / 1e9, tz=timezone.utc).astimezone()
    return dt.isoformat(timespec="seconds")


def _safe_get(mapping: dict[str, Any] | None, *path: str) -> Any:
    value: Any = mapping or {}
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
        if value is None:
            return None
    return value


def _normalize_log(entry: dict[str, Any]) -> dict[str, Any]:
    payload = entry.get("line") or {}
    labels = entry.get("labels") or {}
    aura_meta = _safe_get(payload, "_aura") or {}
    span_payload = _safe_get(payload, "span_payload") or {}

    level = str(payload.get("level") or "INFO")
    status = str(
        payload.get("status")
        or ("failed" if level.upper() == "ERROR" or payload.get("error_message") else "ok")
    )
    event = str(payload.get("event") or payload.get("event_type") or "unknown")
    ruleset = str(labels.get("ruleset") or aura_meta.get("active_ruleset") or "unknown")
    service = str(labels.get("service") or "unknown")
    policy = str(labels.get("policy") or aura_meta.get("policy") or "unknown")
    run_id = payload.get("run_id") or "-"
    run_mode = payload.get("run_mode") or ""
    scenario = payload.get("scenario") or ""
    overall_status = payload.get("overall_status") or ""
    termination_reason = payload.get("termination_reason") or ""
    node = payload.get("node") or "-"
    message = (
        _safe_get(span_payload, "message")
        or payload.get("error_message")
        or payload.get("termination_reason")
        or event
    )

    searchable_parts = [
        service,
        ruleset,
        policy,
        event,
        level,
        status,
        str(run_id),
        str(run_mode),
        str(scenario),
        str(overall_status),
        str(termination_reason),
        str(node),
        str(message),
        json.dumps(payload, sort_keys=True),
    ]

    return {
        "timestamp": entry.get("timestamp"),
        "timestamp_iso": _format_timestamp(entry.get("timestamp")),
        "timeline_bucket": datetime.fromtimestamp(entry.get("timestamp") / 1e9, tz=timezone.utc)
        .astimezone()
        .replace(minute=0, second=0, microsecond=0)
        .isoformat(timespec="minutes"),
        "service": service,
        "ruleset": ruleset,
        "policy": policy,
        "event": event,
        "level": level,
        "status": status,
        "run_id": str(run_id),
        "run_mode": str(run_mode),
        "scenario": str(scenario),
        "overall_status": str(overall_status),
        "termination_reason": str(termination_reason),
        "node": str(node),
        "message": str(message),
        "payload": payload,
        "labels": labels,
        "_search": " ".join(searchable_parts).lower(),
    }


def _bucket_counts(records: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for record in records:
        key = str(record.get(field) or "unknown")
        counts[key] = counts.get(key, 0) + 1

    items = [{"label": key, "count": value} for key, value in counts.items()]
    items.sort(key=lambda item: (-item["count"], item["label"]))
    return items


def _timeline_buckets(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for record in records:
        ts = datetime.fromtimestamp(record["timestamp"] / 1e9, tz=timezone.utc).astimezone()
        bucket = ts.replace(minute=0, second=0, microsecond=0).isoformat(timespec="minutes")
        counts[bucket] = counts.get(bucket, 0) + 1

    items = [{"label": key, "count": value} for key, value in counts.items()]
    items.sort(key=lambda item: item["label"])
    return items


def _build_dashboard_data(
    logs: list[dict[str, Any]],
    *,
    query: str,
    generated_at: str,
    max_logs: int | None,
) -> dict[str, Any]:
    records = [_normalize_log(entry) for entry in logs]
    records.sort(key=lambda item: item["timestamp"], reverse=True)

    failed_logs = [
        record
        for record in records
        if record["status"].lower() == "failed" or record["level"].upper() == "ERROR"
    ]
    unique_runs = {record["run_id"] for record in records if record["run_id"] != "-"}
    unique_services = {record["service"] for record in records}
    unique_rulesets = {record["ruleset"] for record in records}

    return {
        "query": query,
        "generated_at": generated_at,
        "max_logs": max_logs,
        "summary": {
            "total_logs": len(records),
            "failed_logs": len(failed_logs),
            "run_count": len(unique_runs),
            "service_count": len(unique_services),
            "ruleset_count": len(unique_rulesets),
        },
        "events": _bucket_counts(records, "event"),
        "rulesets": _bucket_counts(records, "ruleset"),
        "levels": _bucket_counts(records, "level"),
        "services": _bucket_counts(records, "service"),
        "timeline": _timeline_buckets(records),
        "records": records,
    }


def render_dashboard_html(
    logs: list[dict[str, Any]],
    *,
    query: str,
    generated_at: str | None = None,
    max_logs: int | None = None,
) -> str:
    data = _build_dashboard_data(
        logs,
        query=query,
        generated_at=generated_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        max_logs=max_logs,
    )
    data_json = json.dumps(data, ensure_ascii=True).replace("</script>", "<\\/script>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aura Log Dashboard</title>
  <style>
    :root {{
      --bg: #f5f1e8;
      --panel: #fffaf0;
      --ink: #172126;
      --muted: #63717a;
      --accent: #0d6b5f;
      --accent-soft: #d9efe9;
      --danger: #b63f2f;
      --warn: #d2872c;
      --border: #d8d0c2;
      --shadow: 0 14px 40px rgba(23, 33, 38, 0.08);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Avenir Next", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(13, 107, 95, 0.12), transparent 28%),
        radial-gradient(circle at right, rgba(210, 135, 44, 0.14), transparent 24%),
        var(--bg);
      color: var(--ink);
    }}

    .page {{
      width: min(1360px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }}

    .hero {{
      display: grid;
      gap: 10px;
      padding: 24px;
      border: 1px solid var(--border);
      border-radius: 24px;
      background: linear-gradient(135deg, rgba(255,250,240,0.96), rgba(240,246,242,0.96));
      box-shadow: var(--shadow);
    }}

    .eyebrow {{
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--accent);
      font-weight: 700;
    }}

    h1 {{
      margin: 0;
      font-size: clamp(32px, 5vw, 54px);
      line-height: 0.96;
      letter-spacing: -0.04em;
    }}

    .hero p {{
      margin: 0;
      color: var(--muted);
      max-width: 82ch;
    }}

    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      font-size: 14px;
      color: var(--muted);
    }}

    .meta code {{
      background: rgba(23, 33, 38, 0.06);
      padding: 3px 7px;
      border-radius: 999px;
      color: var(--ink);
    }}

    .grid {{
      display: grid;
      gap: 18px;
      margin-top: 18px;
    }}

    .stats {{
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    }}

    .panels {{
      grid-template-columns: 1.2fr 1fr;
      align-items: start;
    }}

    .panel {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 18px;
      box-shadow: var(--shadow);
    }}

    .stat-value {{
      font-size: 34px;
      font-weight: 700;
      letter-spacing: -0.05em;
      margin: 10px 0 6px;
    }}

    .stat-label, .panel h2 {{
      margin: 0;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--muted);
    }}

    .panel h2 {{
      margin-bottom: 14px;
    }}

    .bars {{
      display: grid;
      gap: 10px;
    }}

    .bar-row {{
      display: grid;
      gap: 6px;
    }}

    .bar-top {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      font-size: 14px;
    }}

    .bar-track {{
      height: 10px;
      border-radius: 999px;
      background: rgba(23, 33, 38, 0.08);
      overflow: hidden;
    }}

    .bar-fill {{
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent), #2ea387);
    }}

    .filters {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      margin-top: 18px;
    }}

    label {{
      display: grid;
      gap: 6px;
      font-size: 13px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}

    input, select {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px 12px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }}

    .table-panel {{
      margin-top: 18px;
    }}

    .table-meta {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
      font-size: 14px;
      color: var(--muted);
      flex-wrap: wrap;
    }}

    .table-wrap {{
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 16px;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1080px;
      background: #fff;
    }}

    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid rgba(23, 33, 38, 0.08);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}

    th {{
      position: sticky;
      top: 0;
      background: #f8f4eb;
      z-index: 1;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
    }}

    td code {{
      font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
      font-size: 12px;
      background: rgba(23, 33, 38, 0.05);
      border-radius: 8px;
      padding: 2px 6px;
    }}

    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      background: rgba(13, 107, 95, 0.12);
      color: var(--accent);
    }}

    .pill.error, .pill.failed {{
      background: rgba(182, 63, 47, 0.12);
      color: var(--danger);
    }}

    .pill.warning, .pill.degraded {{
      background: rgba(210, 135, 44, 0.15);
      color: var(--warn);
    }}

    details {{
      max-width: 360px;
    }}

    details summary {{
      cursor: pointer;
      color: var(--accent);
      font-weight: 600;
    }}

    .details-block > summary {{
      list-style: none;
      font-size: 14px;
    }}

    .details-block > summary::-webkit-details-marker {{
      display: none;
    }}

    .pill-group {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}

    pre {{
      margin: 8px 0 0;
      max-height: 240px;
      overflow: auto;
      padding: 12px;
      border-radius: 12px;
      background: #112027;
      color: #ebf7f4;
      font-size: 12px;
      line-height: 1.45;
    }}

    .empty {{
      padding: 28px;
      text-align: center;
      color: var(--muted);
    }}

    @media (max-width: 980px) {{
      .panels {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="eyebrow">Aura Visualizer</div>
      <h1>Policy-Gated Log Dashboard</h1>
      <p>Inspect the logs Aura has persisted to Loki, track failures and ruleset transitions, and filter down to the runs that matter.</p>
      <div class="meta">
        <span>Generated <code>{escape(data["generated_at"])}</code></span>
        <span>Query <code>{escape(data["query"])}</code></span>
        <span>Showing latest <code>{escape(str(data["max_logs"] or "all"))}</code> logs</span>
      </div>
    </section>

    <section id="stats" class="grid stats"></section>

    <section class="grid panels">
      <div class="panel">
        <h2>Timeline</h2>
        <div id="timelineBars" class="bars"></div>
      </div>
      <div class="grid">
        <div class="panel">
          <h2>Events</h2>
          <div id="eventBars" class="bars"></div>
        </div>
        <div class="panel">
          <h2>Rulesets</h2>
          <div id="rulesetBars" class="bars"></div>
        </div>
      </div>
    </section>

    <section class="panel table-panel">
      <h2>Filters</h2>
      <div class="filters">
        <label>Search
          <input id="searchInput" type="search" placeholder="run id, message, event, node">
        </label>
        <label>Run ID
          <input id="runFilter" type="search" placeholder="mix-001">
        </label>
        <label>Service
          <select id="serviceFilter"></select>
        </label>
        <label>Ruleset
          <select id="rulesetFilter"></select>
        </label>
        <label>Level
          <select id="levelFilter"></select>
        </label>
        <label>Status
          <select id="statusFilter"></select>
        </label>
        <label>Event
          <select id="eventFilter"></select>
        </label>
      </div>
    </section>

    <section class="panel table-panel">
      <div class="table-meta">
        <div id="runResultsSummary"></div>
        <div>Grouped by <code>run_id</code></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Last Seen</th>
              <th>Run</th>
              <th>Service</th>
              <th>Mode</th>
              <th>Scenario</th>
              <th>Overall</th>
              <th>Termination</th>
              <th>Rulesets</th>
              <th>Logs</th>
              <th>Errors</th>
              <th>Nodes</th>
              <th>Duration</th>
              <th>Timeline</th>
            </tr>
          </thead>
          <tbody id="runTableBody"></tbody>
        </table>
      </div>
      <div id="runEmptyState" class="empty" hidden>No runs matched the current filters.</div>
    </section>

    <section class="panel table-panel">
      <div class="table-meta">
        <div id="resultsSummary"></div>
        <div>Newest logs first</div>
      </div>
      <details class="details-block">
        <summary>Raw logs</summary>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Service</th>
                <th>Ruleset</th>
                <th>Level</th>
                <th>Status</th>
                <th>Event</th>
                <th>Run</th>
                <th>Node</th>
                <th>Message</th>
                <th>Payload</th>
              </tr>
            </thead>
            <tbody id="tableBody"></tbody>
          </table>
        </div>
        <div id="emptyState" class="empty" hidden>No logs matched the current filters.</div>
      </details>
    </section>
  </div>

  <script id="dashboard-data" type="application/json">{data_json}</script>
  <script>
    const dashboardData = JSON.parse(document.getElementById("dashboard-data").textContent);
    const entries = dashboardData.records;

    const filters = {{
      search: document.getElementById("searchInput"),
      run: document.getElementById("runFilter"),
      service: document.getElementById("serviceFilter"),
      ruleset: document.getElementById("rulesetFilter"),
      level: document.getElementById("levelFilter"),
      status: document.getElementById("statusFilter"),
      event: document.getElementById("eventFilter"),
    }};

    function uniqueValues(field) {{
      return Array.from(new Set(entries.map((entry) => entry[field]).filter(Boolean))).sort();
    }}

    function populateSelect(select, values) {{
      select.innerHTML = "";
      const allOption = document.createElement("option");
      allOption.value = "";
      allOption.textContent = "All";
      select.appendChild(allOption);
      values.forEach((value) => {{
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      }});
    }}

    function countBy(records, field) {{
      const counts = new Map();
      records.forEach((record) => {{
        const key = record[field] || "unknown";
        counts.set(key, (counts.get(key) || 0) + 1);
      }});
      return Array.from(counts.entries())
        .map(([label, count]) => ({{ label, count }}))
        .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
    }}

    function renderBars(containerId, items, maxItems = 8) {{
      const container = document.getElementById(containerId);
      container.innerHTML = "";
      const visibleItems = items.slice(0, maxItems);
      const maxCount = visibleItems.length ? Math.max(...visibleItems.map((item) => item.count)) : 1;
      visibleItems.forEach((item) => {{
        const row = document.createElement("div");
        row.className = "bar-row";
        row.innerHTML = `
          <div class="bar-top"><span>${{escapeHtml(item.label)}}</span><strong>${{item.count}}</strong></div>
          <div class="bar-track"><div class="bar-fill" style="width:${{(item.count / maxCount) * 100}}%"></div></div>
        `;
        container.appendChild(row);
      }});
      if (!visibleItems.length) {{
        container.innerHTML = '<div class="empty">No data</div>';
      }}
    }}

    function escapeHtml(value) {{
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }}

    function isFailedRecord(record) {{
      return record.status.toLowerCase() === "failed" || record.level.toUpperCase() === "ERROR";
    }}

    function formatDuration(durationMs) {{
      if (!durationMs) {{
        return "0 ms";
      }}
      if (durationMs < 1000) {{
        return `${{durationMs}} ms`;
      }}
      return `${{(durationMs / 1000).toFixed(1)}} s`;
    }}

    function summarizeRuns(records) {{
      const runMap = new Map();

      records.forEach((record) => {{
        if (!record.run_id || record.run_id === "-") {{
          return;
        }}

        if (!runMap.has(record.run_id)) {{
          runMap.set(record.run_id, {{
            run_id: record.run_id,
            service: record.service,
            first_timestamp: record.timestamp,
            first_timestamp_iso: record.timestamp_iso,
            last_timestamp: record.timestamp,
            last_timestamp_iso: record.timestamp_iso,
            run_modes: new Set(),
            scenarios: new Set(),
            rulesets: [],
            nodes: new Set(),
            log_count: 0,
            error_count: 0,
            overall_status: "",
            termination_reason: "",
            records: [],
          }});
        }}

        const summary = runMap.get(record.run_id);
        summary.records.push(record);
        summary.log_count += 1;
        if (isFailedRecord(record)) {{
          summary.error_count += 1;
        }}
        if (!summary.service || summary.service === "unknown") {{
          summary.service = record.service;
        }}
        if (record.timestamp < summary.first_timestamp) {{
          summary.first_timestamp = record.timestamp;
          summary.first_timestamp_iso = record.timestamp_iso;
        }}
        if (record.timestamp > summary.last_timestamp) {{
          summary.last_timestamp = record.timestamp;
          summary.last_timestamp_iso = record.timestamp_iso;
        }}
        if (record.run_mode) {{
          summary.run_modes.add(record.run_mode);
        }}
        if (record.scenario && record.scenario !== "none") {{
          summary.scenarios.add(record.scenario);
        }}
        if (record.node && record.node !== "-") {{
          summary.nodes.add(record.node);
        }}
        if (record.ruleset && !summary.rulesets.includes(record.ruleset)) {{
          summary.rulesets.push(record.ruleset);
        }}
        if (record.overall_status) {{
          summary.overall_status = record.overall_status;
        }}
        if (record.termination_reason) {{
          summary.termination_reason = record.termination_reason;
        }}
      }});

      return Array.from(runMap.values())
        .map((summary) => {{
          summary.records.sort((a, b) => a.timestamp - b.timestamp);
          return {{
            run_id: summary.run_id,
            service: summary.service || "unknown",
            run_mode: Array.from(summary.run_modes).join(", ") || "-",
            scenario: Array.from(summary.scenarios).join(", ") || "-",
            overall_status: summary.overall_status || (summary.error_count ? "error" : "ok"),
            termination_reason: summary.termination_reason || "-",
            rulesets: summary.rulesets.length ? summary.rulesets : ["unknown"],
            log_count: summary.log_count,
            error_count: summary.error_count,
            node_count: summary.nodes.size,
            duration_ms: Math.max(0, Math.round((summary.last_timestamp - summary.first_timestamp) / 1e6)),
            last_timestamp: summary.last_timestamp,
            last_timestamp_iso: summary.last_timestamp_iso,
            records: summary.records.slice(),
          }};
        }})
        .sort((a, b) => b.last_timestamp - a.last_timestamp || a.run_id.localeCompare(b.run_id));
    }}

    function renderStats(records) {{
      const failedLogs = records.filter((record) => isFailedRecord(record)).length;
      const runs = summarizeRuns(records);
      const services = new Set(records.map((record) => record.service));
      const rulesets = new Set(records.map((record) => record.ruleset));

      const stats = [
        {{ label: "Visible logs", value: records.length }},
        {{ label: "Failed / error logs", value: failedLogs }},
        {{ label: "Runs", value: runs.length }},
        {{ label: "Services", value: services.size }},
        {{ label: "Rulesets", value: rulesets.size }},
      ];

      const statsContainer = document.getElementById("stats");
      statsContainer.innerHTML = "";
      stats.forEach((stat) => {{
        const card = document.createElement("article");
        card.className = "panel";
        card.innerHTML = `
          <div class="stat-label">${{escapeHtml(stat.label)}}</div>
          <div class="stat-value">${{stat.value}}</div>
        `;
        statsContainer.appendChild(card);
      }});
    }}

    function pillClass(value) {{
      const normalized = String(value).toLowerCase();
      if (["error", "failed"].includes(normalized)) {{
        return "pill error";
      }}
      if (["warning", "degraded"].includes(normalized)) {{
        return "pill warning";
      }}
      return "pill";
    }}

    function renderRunTable(runSummaries) {{
      const tbody = document.getElementById("runTableBody");
      const emptyState = document.getElementById("runEmptyState");
      tbody.innerHTML = "";
      if (!runSummaries.length) {{
        emptyState.hidden = false;
        return;
      }}
      emptyState.hidden = true;

      runSummaries.forEach((summary) => {{
        const tr = document.createElement("tr");
        const timeline = summary.records
          .map((record) => `${{record.timestamp_iso}}  [${{record.level}}]  ${{record.event}}  node=${{record.node}}  ${{record.message}}`)
          .join("\\n");
        const rulesetHtml = summary.rulesets
          .map((ruleset) => `<span class="pill">${{escapeHtml(ruleset)}}</span>`)
          .join("");
        tr.innerHTML = `
          <td><code>${{escapeHtml(summary.last_timestamp_iso)}}</code></td>
          <td><code>${{escapeHtml(summary.run_id)}}</code></td>
          <td>${{escapeHtml(summary.service)}}</td>
          <td>${{escapeHtml(summary.run_mode)}}</td>
          <td>${{escapeHtml(summary.scenario)}}</td>
          <td><span class="${{pillClass(summary.overall_status)}}">${{escapeHtml(summary.overall_status)}}</span></td>
          <td>${{escapeHtml(summary.termination_reason)}}</td>
          <td><div class="pill-group">${{rulesetHtml}}</div></td>
          <td>${{summary.log_count}}</td>
          <td>${{summary.error_count}}</td>
          <td>${{summary.node_count}}</td>
          <td>${{escapeHtml(formatDuration(summary.duration_ms))}}</td>
          <td>
            <details>
              <summary>View</summary>
              <pre>${{escapeHtml(timeline)}}</pre>
            </details>
          </td>
        `;
        tbody.appendChild(tr);
      }});
    }}

    function renderTable(records) {{
      const tbody = document.getElementById("tableBody");
      const emptyState = document.getElementById("emptyState");
      tbody.innerHTML = "";
      if (!records.length) {{
        emptyState.hidden = false;
        return;
      }}
      emptyState.hidden = true;

      records.forEach((record) => {{
        const tr = document.createElement("tr");
        const payload = JSON.stringify(record.payload, null, 2);
        tr.innerHTML = `
          <td><code>${{escapeHtml(record.timestamp_iso)}}</code></td>
          <td>${{escapeHtml(record.service)}}</td>
          <td><span class="pill">${{escapeHtml(record.ruleset)}}</span></td>
          <td><span class="${{pillClass(record.level)}}">${{escapeHtml(record.level)}}</span></td>
          <td><span class="${{pillClass(record.status)}}">${{escapeHtml(record.status)}}</span></td>
          <td>${{escapeHtml(record.event)}}</td>
          <td><code>${{escapeHtml(record.run_id)}}</code></td>
          <td>${{escapeHtml(record.node)}}</td>
          <td>${{escapeHtml(record.message)}}</td>
          <td>
            <details>
              <summary>View</summary>
              <pre>${{escapeHtml(payload)}}</pre>
            </details>
          </td>
        `;
        tbody.appendChild(tr);
      }});
    }}

    function applyFilters() {{
      const searchTerm = filters.search.value.trim().toLowerCase();
      const runTerm = filters.run.value.trim().toLowerCase();
      const filtered = entries.filter((entry) => {{
        if (searchTerm && !entry._search.includes(searchTerm)) {{
          return false;
        }}
        if (runTerm && !entry.run_id.toLowerCase().includes(runTerm)) {{
          return false;
        }}
        if (filters.service.value && entry.service !== filters.service.value) {{
          return false;
        }}
        if (filters.ruleset.value && entry.ruleset !== filters.ruleset.value) {{
          return false;
        }}
        if (filters.level.value && entry.level !== filters.level.value) {{
          return false;
        }}
        if (filters.status.value && entry.status !== filters.status.value) {{
          return false;
        }}
        if (filters.event.value && entry.event !== filters.event.value) {{
          return false;
        }}
        return true;
      }});
      const runSummaries = summarizeRuns(filtered);

      document.getElementById("runResultsSummary").textContent = `${{runSummaries.length}} runs grouped from ${{filtered.length}} visible logs`;
      document.getElementById("resultsSummary").textContent = `${{filtered.length}} of ${{entries.length}} logs visible across ${{runSummaries.length}} runs`;
      renderStats(filtered);
      renderBars("timelineBars", countBy(filtered, "timeline_bucket").sort((a, b) => a.label.localeCompare(b.label)), 10);
      renderBars("eventBars", countBy(filtered, "event"), 8);
      renderBars("rulesetBars", countBy(filtered, "ruleset"), 8);
      renderRunTable(runSummaries);
      renderTable(filtered);
    }}

    populateSelect(filters.service, uniqueValues("service"));
    populateSelect(filters.ruleset, uniqueValues("ruleset"));
    populateSelect(filters.level, uniqueValues("level"));
    populateSelect(filters.status, uniqueValues("status"));
    populateSelect(filters.event, uniqueValues("event"));

    Object.values(filters).forEach((element) => {{
      element.addEventListener("input", applyFilters);
      element.addEventListener("change", applyFilters);
    }});

    renderBars("timelineBars", dashboardData.timeline, 10);
    renderBars("eventBars", dashboardData.events, 8);
    renderBars("rulesetBars", dashboardData.rulesets, 8);
    applyFilters();
  </script>
</body>
</html>
"""
