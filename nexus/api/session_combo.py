"""
/api/session/combo — read & persist OMNIROUTE_COMBO selection.

Persistence: .evolve/session-env.json
{
  "OMNIROUTE_COMBO": "auto",
  "OMNIROUTE_COMBO_SET_AT": "2026-05-25T12:34:56Z",
  "OMNIROUTE_COMBO_SET_BY": "dashboard"
}

Plugin reads this file on startup and on demand (the file mtime is
checked between calls — no need for restart).
"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent.parent.resolve()
SESSION_FILE = WORKSPACE / ".evolve" / "session-env.json"

# Slugs aceitos sem consultar OmniRoute (validação client + builtin)
BUILTIN_SLUGS = {"auto", "auto-free", "none"}

# Slug pattern: kebab-case, 1-64 chars
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _read_session() -> dict:
    if not SESSION_FILE.exists():
        return {}
    try:
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_session(data: dict):
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8",
        dir=SESSION_FILE.parent, delete=False, suffix=".tmp"
    )
    try:
        json.dump(data, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp.close()
        os.replace(tmp.name, SESSION_FILE)
    except Exception:
        try: os.unlink(tmp.name)
        except OSError: pass
        raise


def handle_session_combo(self, method, parsed, body):
    if method == "GET":
        data = _read_session()
        return 200, {
            "combo": data.get("OMNIROUTE_COMBO") or None,
            "set_at": data.get("OMNIROUTE_COMBO_SET_AT") or None,
            "set_by": data.get("OMNIROUTE_COMBO_SET_BY") or None,
        }, "application/json"

    if method == "PUT":
        if not isinstance(body, dict):
            return 400, {"error": "Body must be a JSON object"}, "application/json"

        slug = body.get("combo")
        if slug is None or slug == "":
            # Clear
            data = _read_session()
            data.pop("OMNIROUTE_COMBO", None)
            data.pop("OMNIROUTE_COMBO_SET_AT", None)
            data.pop("OMNIROUTE_COMBO_SET_BY", None)
            _write_session(data)
            return 200, {"combo": None, "message": "Combo cleared"}, "application/json"

        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            return 400, {"error": "Invalid combo slug (kebab-case, 1-64 chars)"}, "application/json"

        # Persistir
        data = _read_session()
        data["OMNIROUTE_COMBO"] = slug
        data["OMNIROUTE_COMBO_SET_AT"] = datetime.now(timezone.utc).isoformat()
        data["OMNIROUTE_COMBO_SET_BY"] = "dashboard"
        _write_session(data)

        return 200, {
            "combo": slug,
            "set_at": data["OMNIROUTE_COMBO_SET_AT"],
            "set_by": data["OMNIROUTE_COMBO_SET_BY"],
            "message": "Combo persisted to .evolve/session-env.json",
        }, "application/json"

    return 405, {"error": "Method Not Allowed", "allowed": ["GET", "PUT"]}, "application/json"
