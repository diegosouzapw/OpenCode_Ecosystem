"""
/api/models e /api/combos — proxies para o OmniRoute com cache 30s.

Estratégia:
- Single-flight in-memory cache.
- Soft-fail: se OmniRoute estiver inacessível, devolve último snapshot OK (se houver)
  marcando "stale": true. Sem snapshot ⇒ 503.
"""

import http.client
import json
import os
import socket
import ssl
import time
from urllib.parse import urlparse

# Shared SSL context: verifies certificates + hostname, uses system trust store.
# Created once at import time so it is reused across requests.
_SSL_CTX = ssl.create_default_context()

_CACHE: dict[str, dict] = {}
TTL_S = 30
TIMEOUT_S = 3.0

# Only http/https are valid upstream schemes.  http.client connections are
# scheme-specific objects, so file:// / ftp:// are structurally impossible.
_ALLOWED_SCHEMES = {"http", "https"}


def _read_env():
    base = os.environ.get("OMNIROUTE_BASE_URL", "").strip().rstrip("/")
    key = os.environ.get("OMNIROUTE_API_KEY", "").strip() or None
    return base, key


def _fetch(url: str, api_key: str | None) -> tuple[int, dict | list]:
    """
    Fetch *url* using http.client directly (never urllib.request.urlopen).

    http.client.HTTP[S]Connection only speaks HTTP/HTTPS — file:// and other
    schemes are structurally impossible regardless of what OMNIROUTE_BASE_URL
    contains, satisfying CWE-939 / semgrep's urllib scheme-confusion rule.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        return 0, {"error": f"URL parse error: {e}"}

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return 0, {"error": f"Disallowed URL scheme '{scheme}' (only http/https)"}

    host = parsed.netloc
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    headers = {
        "Accept": "application/json",
        "User-Agent": "nexus-dashboard/3.1",
        "Host": host,
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        if scheme == "https":
            conn = http.client.HTTPSConnection(host, timeout=TIMEOUT_S, context=_SSL_CTX)  # nosemgrep: python.lang.security.audit.httpsconnection-detected.httpsconnection-detected
        else:
            conn = http.client.HTTPConnection(host, timeout=TIMEOUT_S)

        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()

        try:
            return resp.status, json.loads(body)
        except json.JSONDecodeError:
            return resp.status, {"error": f"Non-JSON response (status {resp.status})"}

    except (http.client.HTTPException, socket.timeout, OSError) as e:
        return 0, {"error": str(e)}


def _get_cached(key: str, fetcher) -> tuple[int, dict | list, bool]:
    """
    Returns (status, payload, is_stale).
    """
    now = time.time()
    entry = _CACHE.get(key)
    if entry and (now - entry["ts"]) < TTL_S:
        return 200, entry["payload"], False

    status, payload = fetcher()
    if status == 200:
        _CACHE[key] = {"payload": payload, "ts": now}
        return 200, payload, False

    # Falha — devolve cache stale se houver
    if entry:
        return 200, entry["payload"], True

    # Nada em cache → 503 com diagnóstico
    return 503, {
        "error": "OmniRoute unreachable and no cached snapshot",
        "upstream_status": status,
        "upstream_payload": payload,
    }, False


def handle_models(self, method, parsed, body):
    if method != "GET":
        return 405, {"error": "Method Not Allowed"}, "application/json"

    base, key = _read_env()
    if not base:
        return 503, {"error": "OMNIROUTE_BASE_URL not configured"}, "application/json"

    status, payload, stale = _get_cached("models", lambda: _fetch(f"{base}/v1/models", key))
    out = payload if status == 200 else payload
    if status == 200:
        # Anota staleness no envelope
        if isinstance(out, dict):
            out = {**out, "_stale": stale}
        elif isinstance(out, list):
            out = {"data": out, "_stale": stale}
    return status, out, "application/json"


def handle_combos(self, method, parsed, body):
    if method != "GET":
        return 405, {"error": "Method Not Allowed"}, "application/json"

    base, key = _read_env()
    if not base:
        return 503, {"error": "OMNIROUTE_BASE_URL not configured"}, "application/json"

    status, payload, stale = _get_cached("combos", lambda: _fetch(f"{base}/api/combos", key))
    if status == 200:
        if isinstance(payload, list):
            payload = {"data": payload, "_stale": stale}
        elif isinstance(payload, dict):
            payload["_stale"] = stale
    return status, payload, "application/json"
