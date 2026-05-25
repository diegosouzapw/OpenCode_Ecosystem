"""
/api/health/providers — proxy OmniRoute /api/providers, normalize to unified schema.

Cache: 5s in-memory (shorter than the 30s used by /api/models since this is for
the live health screen).
"""

import http.client
import json
import os
import ssl
import time
import urllib.parse
from datetime import datetime, timezone

_CACHE: dict = {"ts": 0, "payload": []}
TTL_S = 5
TIMEOUT_S = 3.0


def _read_env():
    base = os.environ.get("OMNIROUTE_BASE_URL", "").strip().rstrip("/")
    key = os.environ.get("OMNIROUTE_API_KEY", "").strip() or None
    return base, key


def _classify(score: int, cb_state: str) -> str:
    """Map score + CB state → status enum."""
    if cb_state == "OPEN":
        return "crit"
    if score <= 0:
        return "crit"
    if cb_state == "HALF_OPEN" or score < 70:
        return "crit"
    if score < 85:
        return "warn"
    return "ok"


def _normalize_provider(p: dict) -> dict:
    name = str(p.get("name", "?"))
    total = int(p.get("totalConnections") or len(p.get("connections", [])) or 0)
    healthy = int(p.get("healthyConnections") or sum(
        1 for c in p.get("connections", [])
        if c.get("isActive") and c.get("testStatus") == "active"
    ))
    cb = str(p.get("circuitBreakerState", "UNKNOWN"))
    rl = p.get("rateLimitedUntil")
    cooldown_count = sum(
        1 for c in p.get("connections", [])
        if c.get("rateLimitedUntil") and c["rateLimitedUntil"] > datetime.now(timezone.utc).isoformat()
    ) if isinstance(p.get("connections"), list) else 0

    score = int(100 * healthy / total) if total > 0 else 0
    if cb == "OPEN":
        score = 0
    elif cb == "HALF_OPEN":
        score = min(score, 40)

    details_parts = [f"{healthy}/{total} conn", f"CB {cb}"]
    if cooldown_count > 0:
        details_parts.append(f"{cooldown_count} cooldown")
    if rl:
        details_parts.append(f"RL until {rl[:16]}")

    return {
        "type": "prov",
        "name": name,
        "status": _classify(score, cb),
        "score": score,
        "details": " · ".join(details_parts),
        "extra": {
            "totalConnections": total,
            "healthyConnections": healthy,
            "circuitBreakerState": cb,
            "rateLimitedUntil": rl,
            "cooldownCount": cooldown_count,
        },
        "last_check": datetime.now(timezone.utc).isoformat(),
    }


def _fetch() -> tuple:
    base, key = _read_env()
    if not base:
        return False, [], "OMNIROUTE_BASE_URL not configured"

    # Use http.client directly (not urllib) — http.client has no file:// scheme
    # support, making CWE-939 structurally impossible regardless of env var content.
    parsed = urllib.parse.urlparse(base)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return False, [], "OMNIROUTE_BASE_URL must use http:// or https://"

    host = parsed.netloc
    path = (parsed.path or "") + "/api/providers"

    headers = {
        "Accept": "application/json",
        "User-Agent": "nexus-dashboard/3.2",
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"

    try:
        if scheme == "https":
            # context=ssl.create_default_context() enforces cert validation on all Python 3.x.
            conn = http.client.HTTPSConnection(host, timeout=TIMEOUT_S, context=ssl.create_default_context())  # nosemgrep: python.lang.security.audit.httpsconnection-detected.httpsconnection-detected
        else:
            conn = http.client.HTTPConnection(host, timeout=TIMEOUT_S)
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        conn.close()
        data = json.loads(raw)
    except (http.client.HTTPException, OSError, TimeoutError, json.JSONDecodeError) as e:
        return False, [], f"upstream fetch failed: {e}"

    if not isinstance(data, list):
        return False, [], "upstream returned non-list payload"

    return True, [_normalize_provider(p) for p in data if isinstance(p, dict)], None


def handle_health_providers(self, method, parsed, body):
    if method != "GET":
        return 405, {"error": "Method Not Allowed"}, "application/json"

    now = time.time()
    if (now - _CACHE["ts"]) < TTL_S and _CACHE.get("payload"):
        return 200, {"items": _CACHE["payload"], "cached": True}, "application/json"

    ok, items, err = _fetch()
    if ok:
        _CACHE["ts"] = now
        _CACHE["payload"] = items
        return 200, {"items": items, "cached": False}, "application/json"

    # Soft-fail: stale snapshot if available
    if _CACHE.get("payload"):
        return 200, {"items": _CACHE["payload"], "cached": True, "stale": True, "error": err}, "application/json"

    return 503, {"items": [], "error": err}, "application/json"
