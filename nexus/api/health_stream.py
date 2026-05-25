"""
/api/health/stream — Server-Sent Events emitting unified health snapshot every 5s.

Format (per event):
  data: {"providers": [...], "mcps": [...], "summary": {...}, "ts": "..."}
  \n\n

Cleanly handles client disconnect (BrokenPipeError, ConnectionResetError).
"""

import json
import time
from datetime import datetime, timezone

INTERVAL_S = 5
MAX_DURATION_S = 600  # auto-close stream after 10 min (client should reconnect)


def _collect_snapshot(ping_module, prov_module, mcp_module) -> dict:
    """Build a unified snapshot dict."""
    # Reuse the handler logic (they're cheap to invoke directly)
    # NOTE: handlers here return tuples; we just want the payload.
    _, prov_payload, _ = prov_module.handle_health_providers(None, "GET", None, None)
    _, mcp_payload, _ = mcp_module.handle_health_mcp(None, "GET", None, None)

    prov_items = prov_payload.get("items", []) if isinstance(prov_payload, dict) else []
    mcp_items = mcp_payload.get("items", []) if isinstance(mcp_payload, dict) else []

    # Summary
    all_items = list(prov_items) + list(mcp_items)
    summary = {
        "total": len(all_items),
        "ok": sum(1 for x in all_items if x["status"] == "ok"),
        "warn": sum(1 for x in all_items if x["status"] == "warn"),
        "crit": sum(1 for x in all_items if x["status"] == "crit"),
        "off": sum(1 for x in all_items if x["status"] == "off"),
    }
    return {
        "providers": prov_items,
        "mcps": mcp_items,
        "summary": summary,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def handle_health_stream_factory(prov_module, mcp_module):
    """
    Returns a handler bound to the provider/mcp modules.
    Called once from dashboard_server.py at registration time.
    """
    def handle(self, method, parsed, body):
        if method != "GET":
            return 405, {"error": "Method Not Allowed"}, "application/json"

        # Send headers manually (we return None to signal "already handled")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Accel-Buffering", "no")  # nginx hint (defensive)
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        start_ts = time.time()

        try:
            # Emit immediately, then every INTERVAL_S
            while True:
                snapshot = _collect_snapshot(None, prov_module, mcp_module)
                payload = "data: " + json.dumps(snapshot) + "\n\n"
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.flush()

                # Cap stream lifetime (client reconnects)
                if (time.time() - start_ts) > MAX_DURATION_S:
                    self.wfile.write(b"event: close\ndata: {}\n\n")
                    self.wfile.flush()
                    break

                time.sleep(INTERVAL_S)
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Client disconnected — clean exit
            pass
        except Exception as e:
            try:
                err_payload = "event: error\ndata: " + json.dumps({"error": str(e)}) + "\n\n"
                self.wfile.write(err_payload.encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

        # Signal handled (None == "already wrote response")
        # But our framework expects (status, payload, ct). Return (-1, None, None) as sentinel.
        return -1, None, None
    return handle
