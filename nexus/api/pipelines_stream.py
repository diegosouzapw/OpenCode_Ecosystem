"""
GET  /api/pipelines/runs/<run_id>/output/stream  — SSE tail of output.log
POST /api/pipelines/runs/<run_id>/cancel         — kill the process group
"""

import json
import os
import re
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

WORKSPACE = Path(__file__).parent.parent.parent.resolve()
RUNS_DIR = WORKSPACE / ".evolve" / "pipeline-runs"

POLL_INTERVAL_S = 1.0
MAX_STREAM_DURATION_S = 7200   # 2h — same cap as the long-pipeline runtime ceiling
CHUNK_SIZE = 4096
SIGKILL_GRACE_S = 5


def _safe_run_id(raw: str):
    """Allow only the format produced by _run_id() in pipelines_run.py."""
    if not isinstance(raw, str):
        return None
    raw = unquote(raw).strip()
    if not re.fullmatch(r"run_\d{8}T\d{6}Z_[a-f0-9]{6}", raw):
        return None
    return raw


def _read_meta(run_id: str):
    f = RUNS_DIR / run_id / "meta.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ===== Stream =====

def handle_output_stream(self, method, parsed, body, run_id: str):
    if method != "GET":
        return 405, {"error": "Method Not Allowed"}, "application/json"

    safe_id = _safe_run_id(run_id)
    if not safe_id:
        return 400, {"error": "Invalid run_id format"}, "application/json"

    log_file = RUNS_DIR / safe_id / "output.log"
    if not log_file.exists():
        return 404, {"error": "run not found or no output yet"}, "application/json"

    # Send SSE headers
    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream")
    self.send_header("Cache-Control", "no-cache, no-transform")
    self.send_header("X-Accel-Buffering", "no")
    self.send_header("Connection", "keep-alive")
    self.end_headers()

    start_ts = time.time()
    offset = 0

    try:
        with log_file.open("rb") as f:
            while True:
                # Read available
                f.seek(offset)
                chunk = f.read(CHUNK_SIZE)
                if chunk:
                    offset += len(chunk)
                    text = chunk.decode("utf-8", errors="replace")
                    # SSE: data: <each line>\n, finalized with \n\n
                    for line in text.splitlines():
                        evt = "data: " + json.dumps({"line": line}) + "\n\n"
                        self.wfile.write(evt.encode("utf-8"))
                        self.wfile.flush()
                    continue  # check for more

                # Check run status: if terminal, send close + exit
                meta = _read_meta(safe_id) or {}
                status = meta.get("status")
                if status in ("ok", "failed", "cancelled", "timeout", "orphan"):
                    final = "event: close\ndata: " + json.dumps({
                        "run_id": safe_id,
                        "status": status,
                        "exit_code": meta.get("exit_code"),
                    }) + "\n\n"
                    self.wfile.write(final.encode("utf-8"))
                    self.wfile.flush()
                    break

                # Cap stream lifetime
                if (time.time() - start_ts) > MAX_STREAM_DURATION_S:
                    self.wfile.write(b"event: close\ndata: {\"reason\":\"stream-cap\"}\n\n")
                    self.wfile.flush()
                    break

                time.sleep(POLL_INTERVAL_S)
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass

    return -1, None, None


# ===== Cancel =====

def handle_cancel(self, method, parsed, body, run_id: str):
    if method != "POST":
        return 405, {"error": "Method Not Allowed"}, "application/json"

    safe_id = _safe_run_id(run_id)
    if not safe_id:
        return 400, {"error": "Invalid run_id"}, "application/json"

    meta = _read_meta(safe_id)
    if not meta:
        return 404, {"error": "Run not found"}, "application/json"

    status = meta.get("status")
    if status != "running":
        return 409, {"error": f"Run is already terminal: {status}"}, "application/json"

    pid = int(meta.get("pid") or 0)
    if pid <= 0:
        return 500, {"error": "Run has no PID recorded"}, "application/json"

    # SIGTERM the process group, wait, then SIGKILL
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError) as e:
        return 500, {"error": f"SIGTERM failed: {e}"}, "application/json"

    # Background grace-then-kill (don't block the handler)
    def _grace_kill():
        time.sleep(SIGKILL_GRACE_S)
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    threading.Thread(target=_grace_kill, daemon=True).start()

    # Mark cancelled
    meta["status"] = "cancelled"
    meta["finished_at"] = datetime.now(timezone.utc).isoformat()
    meta["exit_code"] = -2
    (RUNS_DIR / safe_id / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return 200, {"run_id": safe_id, "status": "cancelled", "signal": "SIGTERM"}, "application/json"
