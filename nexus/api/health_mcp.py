"""
/api/health/mcp — read MCP health from .evolve/ecosystem-state.json.

The ecosystem-sync.ts plugin maintains this file; we only read it.
File is checked on every request (no cache — mtime-based read is cheap).
"""

import json
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path(__file__).parent.parent.parent.resolve()
STATE_FILE = WORKSPACE / ".evolve" / "ecosystem-state.json"


def _classify(score: int, status_raw: str) -> str:
    if status_raw == "offline" or score <= 0:
        return "off"
    if score < 70:
        return "crit"
    if score < 85:
        return "warn"
    return "ok"


def _fmt_latency(ms) -> str:
    if ms is None:
        return "lat —"
    try:
        ms = int(ms)
    except (ValueError, TypeError):
        return "lat —"
    if ms < 1000:
        return f"lat {ms}ms"
    return f"lat {ms/1000:.1f}s"


def _normalize_mcp(name: str, h: dict) -> dict:
    score = int(h.get("score") or 0)
    status_raw = str(h.get("status") or "unknown")
    err = int(h.get("errorCount") or 0)
    lat = h.get("latency")
    last_check = h.get("lastCheck") or datetime.now(timezone.utc).isoformat()

    details_parts = [_fmt_latency(lat), f"{err} err"]
    if status_raw == "offline":
        details_parts = [f"{err} errors · offline"]

    return {
        "type": "mcp",
        "name": name,
        "status": _classify(score, status_raw),
        "score": score,
        "details": " · ".join(details_parts),
        "extra": {
            "score_raw": score,
            "latency_ms": lat,
            "error_count": err,
            "status_raw": status_raw,
        },
        "last_check": last_check,
    }


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def handle_health_mcp(self, method, parsed, body):
    if method != "GET":
        return 405, {"error": "Method Not Allowed"}, "application/json"

    state = _load_state()
    mcps = state.get("mcps", {}) if isinstance(state, dict) else {}

    items = []
    for name, h in mcps.items():
        if not isinstance(h, dict):
            continue
        items.append(_normalize_mcp(name, h))

    return 200, {
        "items": items,
        "source": str(STATE_FILE.relative_to(WORKSPACE)),
        "available": STATE_FILE.exists(),
        "ecosystem_health": state.get("overallHealth"),
        "last_sync": state.get("lastSync"),
    }, "application/json"
