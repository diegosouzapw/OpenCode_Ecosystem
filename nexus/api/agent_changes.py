"""
/api/agents/* — pending changes machinery for agent model assignments.

Workflow:
  1. UI edits a row's "→ NEW" dropdown      →  PUT /api/agents/<name>/model
                                              → stages in .evolve/pending-agent-changes.json
  2. UI calls GET /api/agents/diff           → returns plain-text diff (preview)
  3. User clicks Apply                       → POST /api/agents/apply
                                              → atomic write to each agent file
                                              → clears the staging file

Atomic write: tempfile + os.replace per file. If any file fails, transaction
aborts with detailed error and leaves staging intact.
"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

WORKSPACE = Path(__file__).parent.parent.parent.resolve()
STAGING_FILE = WORKSPACE / ".evolve" / "pending-agent-changes.json"

AGENT_DIRS = [WORKSPACE / "agents"]
SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")  # agent name
MODEL_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_./:-]{0,127}$")  # model id or combo


# ===== Storage =====

def _read_staging() -> dict[str, dict]:
    if not STAGING_FILE.exists():
        return {}
    try:
        return json.loads(STAGING_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_staging(data: dict[str, dict]):
    STAGING_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                       dir=STAGING_FILE.parent, delete=False, suffix=".tmp")
    try:
        json.dump(data, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp.close()
        os.replace(tmp.name, STAGING_FILE)
    except Exception:
        try: os.unlink(tmp.name)
        except OSError: pass
        raise


# ===== Frontmatter manipulation =====

def _find_agent_file(name: str) -> Path | None:
    if not SLUG_RE.match(name):
        return None
    for adir in AGENT_DIRS:
        cand = adir / f"{name}.md"
        if cand.is_file():
            return cand
    return None


def _read_current_model(file_path: Path) -> str | None:
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end]
    for line in block.splitlines():
        m = re.match(r"^model:\s*(.+?)\s*$", line)
        if m:
            return m.group(1).strip().strip('"\'')
    return None


def _apply_model_to_file(file_path: Path, new_model: str | None) -> str:
    """
    Apply a model change to one agent file. Returns the new file contents
    (without writing). Caller does the atomic write.

    Behavior:
      - If new_model is None / "" / "default": REMOVE the model: line (revert to inherit).
      - Else: replace if present; insert after `name:` if absent.
    """
    text = file_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{file_path}: missing frontmatter")

    end = text.find("\n---", 3)
    if end == -1:
        raise ValueError(f"{file_path}: malformed frontmatter (no closing ---)")

    block = text[3:end]
    body_after = text[end:]

    lines = block.splitlines()
    out_lines = []
    found = False
    name_idx = -1

    for i, ln in enumerate(lines):
        if ln.strip().startswith("name:"):
            name_idx = len(out_lines)
        if re.match(r"^model:\s*", ln):
            found = True
            if new_model and new_model != "default":
                out_lines.append(f"model: {new_model}")
            # else: drop the line (revert to inherit)
        else:
            out_lines.append(ln)

    if not found and new_model and new_model != "default":
        # insert after name:
        if name_idx >= 0:
            out_lines.insert(name_idx + 1, f"model: {new_model}")
        else:
            out_lines.append(f"model: {new_model}")

    new_block = "\n".join(out_lines)
    return "---" + ("\n" if not new_block.startswith("\n") else "") + new_block + body_after


# ===== Diff generator =====

def _diff_preview(staging: dict[str, dict]) -> str:
    """Render a git-diff-like preview of all staged changes."""
    out_lines = []
    for name, entry in sorted(staging.items()):
        file_path = _find_agent_file(name)
        if not file_path:
            out_lines.append(f"--- a/agents/{name}.md\n+++ /dev/null\nERROR: agent file not found\n")
            continue
        current = _read_current_model(file_path)
        new = entry["new_model"]
        rel = file_path.relative_to(WORKSPACE)
        out_lines.append(f"--- a/{rel}")
        out_lines.append(f"+++ b/{rel}")
        if current and (new is None or new == "" or new == "default"):
            out_lines.append(f"-model: {current}")
            out_lines.append(f"  (reverts to global default)")
        elif current and new and new != "default":
            out_lines.append(f"-model: {current}")
            out_lines.append(f"+model: {new}")
        elif not current and new and new != "default":
            out_lines.append(f"+model: {new}")
        out_lines.append("")
    return "\n".join(out_lines) or "(no pending changes)"


# ===== Handlers =====

def handle_agent_model_put(self, method, parsed, body, agent_name: str):
    """PUT /api/agents/<name>/model {model: '...' | null | 'default'}"""
    if method == "PUT":
        if not isinstance(body, dict):
            return 400, {"error": "Body must be JSON object {model: ...}"}, "application/json"

        if not _find_agent_file(agent_name):
            return 404, {"error": f"Agent not found: {agent_name}"}, "application/json"

        new_model = body.get("model")
        if new_model is not None and new_model not in ("", "default"):
            if not isinstance(new_model, str) or not MODEL_RE.match(new_model):
                return 400, {"error": "Invalid model id (chars: a-z 0-9 _.-/:)"}, "application/json"

        staging = _read_staging()
        staging[agent_name] = {
            "new_model": new_model if new_model not in ("", None) else None,
            "staged_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_staging(staging)
        return 200, {"staged": True, "agent": agent_name, "new_model": new_model}, "application/json"

    if method == "DELETE":
        staging = _read_staging()
        if agent_name in staging:
            del staging[agent_name]
            _write_staging(staging)
            return 200, {"removed": True, "agent": agent_name}, "application/json"
        return 404, {"error": "Not staged"}, "application/json"

    return 405, {"error": "Method Not Allowed"}, "application/json"


def handle_pending(self, method, parsed, body):
    """GET /api/agents/pending — list staged changes."""
    if method != "GET":
        return 405, {"error": "Method Not Allowed"}, "application/json"
    staging = _read_staging()
    items = []
    for name, entry in sorted(staging.items()):
        file_path = _find_agent_file(name)
        items.append({
            "agent": name,
            "current_model": _read_current_model(file_path) if file_path else None,
            "new_model": entry["new_model"],
            "staged_at": entry["staged_at"],
            "exists": file_path is not None,
        })
    return 200, {"total": len(items), "items": items}, "application/json"


def handle_diff(self, method, parsed, body):
    """GET /api/agents/diff — plain text diff."""
    if method != "GET":
        return 405, {"error": "Method Not Allowed"}, "application/json"
    staging = _read_staging()
    return 200, _diff_preview(staging), "text/plain; charset=utf-8"


def handle_apply(self, method, parsed, body):
    """POST /api/agents/apply — atomic apply of all staged changes."""
    if method != "POST":
        return 405, {"error": "Method Not Allowed"}, "application/json"

    staging = _read_staging()
    if not staging:
        return 200, {"applied": 0, "message": "No pending changes"}, "application/json"

    # Pre-validate all + compute new contents in memory
    plan = []
    errors = []
    for name, entry in staging.items():
        file_path = _find_agent_file(name)
        if not file_path:
            errors.append({"agent": name, "error": "file not found"})
            continue
        try:
            new_contents = _apply_model_to_file(file_path, entry["new_model"])
            plan.append((file_path, new_contents))
        except Exception as e:
            errors.append({"agent": name, "error": str(e)})

    if errors:
        return 400, {
            "error": "Pre-validation failed, no changes applied",
            "details": errors,
        }, "application/json"

    # Apply (atomic per file)
    applied = []
    for file_path, new_contents in plan:
        tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                           dir=file_path.parent, delete=False, suffix=".tmp")
        try:
            tmp.write(new_contents)
            tmp.close()
            os.replace(tmp.name, file_path)
            applied.append(str(file_path.relative_to(WORKSPACE)))
        except Exception as e:
            try: os.unlink(tmp.name)
            except OSError: pass
            # Best-effort rollback would require backups — out of scope for now.
            return 500, {
                "error": f"Failed mid-apply: {e}",
                "applied_before_failure": applied,
            }, "application/json"

    # Clear staging
    _write_staging({})

    return 200, {"applied": len(applied), "files": applied}, "application/json"
