"""
PUT    /api/plugins/<id>          — stage enabled/options change
DELETE /api/plugins/<id>/pending   — unstage
GET    /api/plugins/pending        — list staged
GET    /api/plugins/diff           — preview diff
POST   /api/plugins/apply          — atomic rewrite + backup + restore-on-failure
"""

import copy
import difflib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

WORKSPACE = Path(__file__).parent.parent.parent.resolve()
CONFIG_PATH = WORKSPACE / "opencode.json"
STAGING_FILE = WORKSPACE / ".evolve" / "pending-plugin-changes.json"

# Plugin id allows letters, digits, @ _ . / - but rejects '..' sequences
# (defense-in-depth even though id is only used as a dict key, not a path).
PLUGIN_ID_RE = re.compile(r"^(?!.*\.\.)[A-Za-z0-9@_./-]{1,200}$")


# ===== Storage =====

def _read_staging() -> dict:
    if not STAGING_FILE.exists():
        return {}
    try:
        return json.loads(STAGING_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_staging(data: dict):
    STAGING_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                      dir=STAGING_FILE.parent, delete=False, suffix=".tmp")
    try:
        json.dump(data, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp.close()
        os.replace(tmp.name, STAGING_FILE)
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


# ===== Read current config (delegates to plugins_list._strip_comments) =====

def _read_config() -> tuple[dict, str]:
    """Returns (parsed_config, raw_text). Raises on read/parse fail."""
    from importlib import util
    ppath = Path(__file__).parent / "plugins_list.py"
    spec = util.spec_from_file_location("plugins_list_local", str(ppath))
    mod = util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    raw = CONFIG_PATH.read_text(encoding="utf-8")
    cleaned, _ = mod._strip_comments(raw)
    return json.loads(cleaned), raw


# ===== Apply staging in-memory =====

def _apply_to_config(cfg: dict, staging: dict) -> dict:
    """
    Returns a NEW config dict with staging applied.
    - enabled=False  -> remove from plugin array
    - enabled=True + options=null -> leave as bare string entry
    - enabled=True + options dict -> ensure tuple form [pkg, options]
    """
    cfg = copy.deepcopy(cfg)
    arr = cfg.get("plugin") or cfg.get("plugins") or []
    new_arr = []

    for entry in arr:
        pkg = entry[0] if isinstance(entry, list) else entry
        if not isinstance(pkg, str):
            new_arr.append(entry)
            continue
        if pkg not in staging:
            new_arr.append(entry)
            continue

        change = staging[pkg]
        if change.get("enabled") is False:
            # Remove (don't append)
            continue

        options = change.get("options")
        if options is None:
            # Bare string entry
            new_arr.append(pkg)
        else:
            new_arr.append([pkg, options])

    cfg["plugin"] = new_arr
    return cfg


# ===== Handlers =====

def handle_plugin_put(self, method, parsed, body, plugin_id: str):
    plugin_id = unquote(plugin_id)
    if not PLUGIN_ID_RE.match(plugin_id):
        return 400, {"error": "Invalid plugin id"}, "application/json"

    if method == "PUT":
        if not isinstance(body, dict):
            return 400, {"error": "Body must be JSON object"}, "application/json"

        # Validate body shape
        if "enabled" not in body and "options" not in body:
            return 400, {"error": "Body must contain 'enabled' and/or 'options'"}, "application/json"

        enabled = body.get("enabled", True)
        options = body.get("options")

        if not isinstance(enabled, bool):
            return 400, {"error": "'enabled' must be boolean"}, "application/json"
        if options is not None and not isinstance(options, dict):
            return 400, {"error": "'options' must be dict or null"}, "application/json"

        staging = _read_staging()
        staging[plugin_id] = {
            "enabled": enabled,
            "options": options,
            "staged_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_staging(staging)
        return 200, {"staged": True, "id": plugin_id}, "application/json"

    if method == "DELETE":
        staging = _read_staging()
        if plugin_id in staging:
            del staging[plugin_id]
            _write_staging(staging)
            return 200, {"removed": True, "id": plugin_id}, "application/json"
        return 404, {"error": "Not staged"}, "application/json"

    return 405, {"error": "Method Not Allowed"}, "application/json"


def handle_pending(self, method, parsed, body):
    if method != "GET":
        return 405, {"error": "Method Not Allowed"}, "application/json"
    staging = _read_staging()
    return 200, {"total": len(staging), "items": staging}, "application/json"


def handle_diff(self, method, parsed, body):
    if method != "GET":
        return 405, {"error": "Method Not Allowed"}, "application/json"

    try:
        cfg, raw = _read_config()
    except (OSError, json.JSONDecodeError) as e:
        return 500, f"Cannot read opencode.json: {e}", "text/plain"

    staging = _read_staging()
    if not staging:
        return 200, "(no pending changes)", "text/plain"

    new_cfg = _apply_to_config(cfg, staging)

    # Re-serialize old (from parsed) and new for proper diff
    old_text = json.dumps(cfg, indent=2, sort_keys=False)
    new_text = json.dumps(new_cfg, indent=2, sort_keys=False)

    diff = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile="a/opencode.json",
        tofile="b/opencode.json",
        lineterm="",
    )
    return 200, "".join(diff), "text/plain; charset=utf-8"


# ===== Apply =====

def handle_apply(self, method, parsed, body):
    if method != "POST":
        return 405, {"error": "Method Not Allowed"}, "application/json"

    staging = _read_staging()
    if not staging:
        return 200, {"applied": 0, "message": "No pending changes"}, "application/json"

    # 1. Read current config
    try:
        cfg, raw = _read_config()
    except (OSError, json.JSONDecodeError) as e:
        return 500, {"error": f"Cannot read opencode.json: {e}"}, "application/json"

    # 2. Pre-validate: each staged plugin must exist in current config
    arr = cfg.get("plugin") or cfg.get("plugins") or []
    existing_ids = set()
    for entry in arr:
        pkg = entry[0] if isinstance(entry, list) else entry
        if isinstance(pkg, str):
            existing_ids.add(pkg)

    missing = [pid for pid in staging if pid not in existing_ids]
    if missing:
        return 400, {
            "error": "Some staged plugins do not exist in opencode.json",
            "missing": missing,
            "hint": "Discard those staged changes or add the plugin manually first.",
        }, "application/json"

    # 3. Validate options against schemas (best-effort — unknown plugins pass through)
    from importlib import util
    ppath = Path(__file__).parent / "plugins_list.py"
    spec = util.spec_from_file_location("plugins_list_local", str(ppath))
    mod = util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    for pid, change in staging.items():
        opts = change.get("options")
        if not opts:
            continue
        name = mod._infer_name(pid)
        schema = mod.PLUGIN_SCHEMAS.get(name)
        if not schema:
            continue  # unknown plugin — accept user's options as-is
        err = _validate_options(opts, schema["options"])
        if err:
            return 400, {
                "error": f"Options validation failed for {pid}",
                "details": err,
            }, "application/json"

    # 4. Compute new config
    new_cfg = _apply_to_config(cfg, staging)

    # 5. Backup current opencode.json
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = CONFIG_PATH.with_suffix(f".json.bak.{ts}")
    try:
        backup_path.write_bytes(CONFIG_PATH.read_bytes())
    except OSError as e:
        return 500, {"error": f"Backup failed: {e}"}, "application/json"

    # 6. Write new config atomically
    new_text = json.dumps(new_cfg, indent=2, sort_keys=False) + "\n"
    tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                      dir=CONFIG_PATH.parent, delete=False, suffix=".tmp")
    try:
        tmp.write(new_text)
        tmp.close()
        os.replace(tmp.name, CONFIG_PATH)
    except Exception as e:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        # Restore from backup
        try:
            CONFIG_PATH.write_bytes(backup_path.read_bytes())
        except OSError:
            pass
        return 500, {"error": f"Write failed (restored from backup): {e}"}, "application/json"

    # 7. Clear staging
    _write_staging({})

    return 200, {
        "applied": len(staging),
        "items": list(staging.keys()),
        "backup": str(backup_path.relative_to(WORKSPACE)),
        "restart_required": True,
        "restart_hint": "Run `opencode` (or restart your OpenCode session) for changes to take effect.",
    }, "application/json"


def _validate_options(opts: dict, schema: list) -> str | None:
    """Returns error message or None."""
    declared = {s["name"] for s in schema}

    # Flatten nested keys (features.combos)
    def _flat(d, prefix=""):
        out = {}
        for k, v in d.items():
            key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
            if isinstance(v, dict):
                out.update(_flat(v, key))
            else:
                out[key] = v
        return out

    flat_opts = _flat(opts)
    for k in flat_opts:
        if k not in declared:
            return f"Unknown option: {k}"

    for s in schema:
        name = s["name"]
        if s.get("required") and name not in flat_opts:
            return f"Required option missing: {name}"
        atype = s.get("type", "string")
        if name in flat_opts:
            val = flat_opts[name]
            if atype == "string" and not isinstance(val, str):
                return f"Option {name} must be string"
            if atype == "integer" and not isinstance(val, int):
                return f"Option {name} must be integer"
            if atype == "boolean" and not isinstance(val, bool):
                return f"Option {name} must be boolean"
    return None
