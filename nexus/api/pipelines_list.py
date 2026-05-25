"""
/api/pipelines        — list commands from command/*.md
/api/pipelines/runs   — list runs from .evolve/pipeline-runs/*/meta.json
"""

import json
import os
import re
import signal
from pathlib import Path
from urllib.parse import parse_qs

WORKSPACE = Path(__file__).parent.parent.parent.resolve()
COMMAND_DIR = WORKSPACE / "command"
RUNS_DIR = WORKSPACE / ".evolve" / "pipeline-runs"


# ===== Frontmatter parsing =====

def _parse_frontmatter(text: str) -> dict:
    """Minimal YAML-ish parser for the frontmatter we control."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    # Use json fallback or simple key:value parser — but command/*.md may have nested
    # `arguments:` lists. Use a minimal indent-based parser.
    out = {}
    current_key = None
    current_list = None
    for line in block.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        # Top-level key:value
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if m and not line.startswith(" "):
            key, val = m.group(1), m.group(2).strip()
            current_key = key
            if val == "" or val == "[]":
                current_list = []
                out[key] = current_list
            elif val.startswith("["):
                # inline list (best effort)
                try:
                    out[key] = json.loads(val)
                except Exception:
                    out[key] = val
                current_list = None
            else:
                out[key] = val.strip('"\'')
                current_list = None
            continue
        # List item under current_key
        if line.startswith("  - ") and current_list is not None:
            item_str = line[4:]
            # Inline object?
            if item_str.startswith("{") or ":" in item_str:
                # Multi-line object: collect subsequent indented lines into a dict
                item = {}
                k, _, v = item_str.partition(":")
                if k and v:
                    item[k.strip()] = v.strip().strip('"\'')
                current_list.append(item)
            else:
                current_list.append(item_str.strip('"\''))
            continue
        # Sub-properties of last list item
        if line.startswith("    ") and current_list and isinstance(current_list[-1], dict):
            sub = line.strip()
            k, _, v = sub.partition(":")
            if k:
                current_list[-1][k.strip()] = v.strip().strip('"\'')
            continue
    return out


def _list_commands() -> list:
    if not COMMAND_DIR.is_dir():
        return []
    items = []
    for f in sorted(COMMAND_DIR.glob("*.md")):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm = _parse_frontmatter(text)
        name = fm.get("name", f.stem)
        args = fm.get("arguments", []) if isinstance(fm.get("arguments"), list) else []
        # Normalize each arg
        norm_args = []
        for a in args:
            if not isinstance(a, dict):
                continue
            norm_args.append({
                "name": str(a.get("name", "")),
                "type": str(a.get("type", "string")),
                "required": str(a.get("required", "false")).lower() == "true",
                "description": str(a.get("description", "")),
                "pattern": str(a.get("pattern", "")) or None,
            })
        items.append({
            "name": name,
            "description": str(fm.get("description", "")),
            "category": str(fm.get("category", "")),
            "trigger": fm.get("trigger", [f"/{name}"]),
            "arguments": norm_args,
            "pipeline": str(fm.get("pipeline", "")),  # internal handler name
            "since": str(fm.get("since", "")),
            "path": str(f.relative_to(WORKSPACE)),
        })
    return items


# ===== Runs listing =====

def _pid_alive(pid: int) -> bool:
    """Best-effort PID liveness check (Unix only)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def _list_runs(limit: int = 200) -> list:
    if not RUNS_DIR.is_dir():
        return []
    items = []
    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta_f = d / "meta.json"
        if not meta_f.exists():
            continue
        try:
            meta = json.loads(meta_f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        # Reconcile: if status=running but PID dead → orphan
        if meta.get("status") == "running":
            pid = meta.get("pid", 0)
            if not _pid_alive(pid):
                meta["status"] = "orphan"
                try:
                    meta_f.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                except OSError:
                    pass
                # Remove pid file
                pid_file = d / "pid"
                try:
                    pid_file.unlink()
                except OSError:
                    pass
        items.append(meta)
        if len(items) >= limit:
            break
    return items


# ===== Handlers =====

def handle_pipelines(self, method, parsed, body):
    """GET /api/pipelines — list commands."""
    if method != "GET":
        return 405, {"error": "Method Not Allowed"}, "application/json"
    items = _list_commands()
    cats = sorted(set(i["category"] or "uncategorized" for i in items))
    return 200, {"total": len(items), "items": items, "categories": cats}, "application/json"


def handle_runs(self, method, parsed, body):
    """GET /api/pipelines/runs — list runs."""
    if method != "GET":
        return 405, {"error": "Method Not Allowed"}, "application/json"
    qs = parse_qs(parsed.query or "")
    status_filter = qs.get("status", [None])[0]
    items = _list_runs()
    if status_filter:
        items = [i for i in items if i.get("status") == status_filter]
    # Summary
    summary = {
        "total": len(items),
        "running": sum(1 for i in items if i.get("status") == "running"),
        "ok": sum(1 for i in items if i.get("status") == "ok"),
        "failed": sum(1 for i in items if i.get("status") in ("failed", "timeout", "orphan")),
        "cancelled": sum(1 for i in items if i.get("status") == "cancelled"),
    }
    return 200, {"items": items, "summary": summary}, "application/json"
