"""
/api/ping — foundation validation endpoint.

Returns minimal status info:
- ok: bool
- version: dashboard version
- omniroute_enabled: whether OMNIROUTE_BASE_URL is set
- omniroute_base_url: redacted (without scheme/host details? — full URL for now,
  since this is loopback-only)
- timestamp: current ISO 8601
"""

import os
from datetime import datetime, timezone


def handle_ping(self, method, parsed, body):
    """
    Handler signature: (self, method, parsed_path, body) -> (status, payload, content_type)
    """
    if method != "GET":
        return 405, {"error": "Method Not Allowed", "allowed": ["GET"]}, "application/json"

    payload = {
        "ok": True,
        "version": "3.0",
        "omniroute_enabled": bool(os.environ.get("OMNIROUTE_BASE_URL", "").strip()),
        "omniroute_base_url": os.environ.get("OMNIROUTE_BASE_URL", "").strip() or None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return 200, payload, "application/json"
