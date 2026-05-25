"""
POST /api/pipelines/run — securely spawn a slash-command pipeline as a subprocess.

Security:
- command MUST exist in command/*.md (allow-list).
- args MUST validate against the arguments: schema in frontmatter.
- subprocess uses shell=False, list-form args.
- subprocess runs as the dashboard user, no privilege change.
- Each spawn creates .evolve/pipeline-runs/<run_id>/ with meta.json + output.log.
- One concurrent run per command (configurable per command).
"""

import json
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent.parent.resolve()
COMMAND_DIR = WORKSPACE / "command"
RUNS_DIR = WORKSPACE / ".evolve" / "pipeline-runs"

# Hard cap on concurrent runs (defensive)
MAX_GLOBAL_CONCURRENT = 8

# Max value sizes
MAX_ARG_VALUE_LEN = 4096
MAX_ARGS_TOTAL_LEN = 16384

# Hard timeout (8h)
MAX_DURATION_S = 8 * 3600


# ===== Validation =====

NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
COMMAND_TOKEN_RE = re.compile(r"^/?[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def _normalize_command(raw: str):
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not COMMAND_TOKEN_RE.match(raw):
        return None
    return raw.lstrip("/")


def _load_command_spec(name: str):
    """Load command/<name>.md frontmatter spec. Returns None if not found."""
    from importlib import util
    # Reuse parsing from pipelines_list.py
    parser_path = Path(__file__).parent / "pipelines_list.py"
    spec = util.spec_from_file_location("pipelines_list_local", str(parser_path))
    mod = util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    f = COMMAND_DIR / f"{name}.md"
    if not f.is_file():
        return None
    try:
        text = f.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    fm = mod._parse_frontmatter(text)
    if not fm:
        return None
    args = fm.get("arguments", []) if isinstance(fm.get("arguments"), list) else []
    return {
        "name": fm.get("name", name),
        "arguments": [a for a in args if isinstance(a, dict)],
        "pipeline": fm.get("pipeline", ""),
        "allow_concurrent": str(fm.get("allow_concurrent", "false")).lower() == "true",
    }


def _validate_args(user_args: dict, schema_args: list):
    """
    Validates user_args against schema. Returns (ok, error_msg, sanitized_args).
    """
    if not isinstance(user_args, dict):
        return False, "args must be a JSON object", {}

    sanitized = {}
    total_len = 0
    declared_names = {a.get("name") for a in schema_args}

    # 1) Check unknown args
    for k in user_args:
        if k not in declared_names:
            return False, f"Unknown arg: {k}", {}

    # 2) For each declared arg: check required + type + pattern + length
    for a in schema_args:
        name = a.get("name")
        required = str(a.get("required", "false")).lower() == "true"
        atype = str(a.get("type", "string"))
        pattern = a.get("pattern")
        val = user_args.get(name)

        if val is None or val == "":
            if required:
                return False, f"Required arg missing: {name}", {}
            continue

        # Length cap
        sval = str(val)
        if len(sval) > MAX_ARG_VALUE_LEN:
            return False, f"Arg {name} too long (max {MAX_ARG_VALUE_LEN})", {}
        total_len += len(sval)
        if total_len > MAX_ARGS_TOTAL_LEN:
            return False, "Total args size exceeds limit", {}

        # Type check
        if atype == "integer":
            try:
                sanitized[name] = int(sval)
            except ValueError:
                return False, f"Arg {name} must be integer", {}
        elif atype == "boolean":
            sanitized[name] = sval.lower() in ("true", "1", "yes")
        else:  # string default
            sanitized[name] = sval

        # Pattern check (only for strings)
        if pattern and atype == "string":
            try:
                if not re.fullmatch(pattern, sval):
                    return False, f"Arg {name} doesn't match pattern {pattern}", {}
            except re.error:
                # Malformed pattern in spec — refuse, don't bypass
                return False, f"Invalid pattern in spec for {name}", {}

    return True, "", sanitized


# ===== Concurrency check =====

def _active_runs():
    if not RUNS_DIR.is_dir():
        return []
    out = []
    for d in RUNS_DIR.iterdir():
        if not d.is_dir():
            continue
        meta_f = d / "meta.json"
        if not meta_f.exists():
            continue
        try:
            meta = json.loads(meta_f.read_text(encoding="utf-8"))
            if meta.get("status") == "running":
                pid = meta.get("pid", 0)
                try:
                    os.kill(pid, 0)
                    out.append(d)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
        except (OSError, json.JSONDecodeError):
            pass
    return out


# ===== Spawning =====

def _resolve_handler(spec: dict):
    """
    Map command name → actual executable + args.
    For now, we ASSUME the command's `pipeline:` field is a Python module path
    OR a script path under nexus/scripts/. Extend as ecosystem grows.

    Returns argv list for subprocess.Popen, or None if no resolver available.

    SECURITY: argv elements are constructed from CODE (not user input).
    User-provided args are appended only via the args dict passed as JSON env var.
    """
    name = spec["name"]
    pipeline = spec.get("pipeline", "")

    # Convention: pipeline starts with "script:" → run python script
    if pipeline.startswith("script:"):
        script_rel = pipeline[7:].strip()
        script_path = (WORKSPACE / script_rel).resolve()
        # Must be under WORKSPACE (no traversal)
        try:
            script_path.relative_to(WORKSPACE)
        except ValueError:
            return None
        if not script_path.is_file():
            return None
        return ["python3", str(script_path)]

    # Convention: pipeline starts with "module:" → python -m
    if pipeline.startswith("module:"):
        mod = pipeline[7:].strip()
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.]*", mod):
            return None
        return ["python3", "-m", mod]

    # Fallback: assume the command is dispatched via a single entry point at nexus/scripts/run_command.py
    entry = WORKSPACE / "nexus" / "scripts" / "run_command.py"
    if entry.is_file():
        return ["python3", str(entry), name]

    return None


def _run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{ts}_{uuid.uuid4().hex[:6]}"


def _spawn(run_dir: Path, argv: list, args_dict: dict):
    """
    Spawn subprocess with stdout+stderr redirected to output.log.
    Returns (pid, error). On success, error is None.
    """
    out_log = run_dir / "output.log"
    try:
        f = out_log.open("ab")  # append-only binary
    except OSError as e:
        return None, f"cannot open log: {e}"

    # Pass args via env var (no shell quoting issues)
    env = os.environ.copy()
    env["PIPELINE_ARGS_JSON"] = json.dumps(args_dict)
    env["PIPELINE_RUN_ID"] = run_dir.name

    try:
        proc = subprocess.Popen(
            argv,
            stdout=f,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            cwd=str(WORKSPACE),
            env=env,
            shell=False,             # CRITICAL: never True
            start_new_session=True,  # for clean SIGTERM of process group
        )
        # Don't wait — store PID and return
    except (OSError, FileNotFoundError) as e:
        try:
            f.close()
        except OSError:
            pass
        return None, f"spawn failed: {e}"

    f.close()  # the subprocess holds its own FD; we close ours

    # Write PID file
    pid_file = run_dir / "pid"
    try:
        pid_file.write_text(str(proc.pid), encoding="utf-8")
    except OSError:
        pass  # not fatal

    # Background watcher: when proc exits, update meta.json
    def _watcher():
        try:
            exit_code = proc.wait(timeout=MAX_DURATION_S)
            status = "ok" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), 15)  # SIGTERM
                time.sleep(5)
                os.killpg(os.getpgid(proc.pid), 9)   # SIGKILL
            except (ProcessLookupError, PermissionError, OSError):
                pass
            exit_code = -1
            status = "timeout"
        except (OSError, ProcessLookupError):
            exit_code = -1
            status = "failed"

        # Update meta.json
        meta_f = run_dir / "meta.json"
        try:
            meta = json.loads(meta_f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        meta["status"] = status
        meta["exit_code"] = exit_code
        meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        try:
            meta_f.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except OSError:
            pass
        # Remove pid file
        try:
            (run_dir / "pid").unlink()
        except OSError:
            pass

    threading.Thread(target=_watcher, daemon=True).start()
    return proc.pid, None


# ===== Handler =====

def handle_run(self, method, parsed, body):
    if method != "POST":
        return 405, {"error": "Method Not Allowed"}, "application/json"

    if not isinstance(body, dict):
        return 400, {"error": "Body must be JSON object"}, "application/json"

    # 1) Validate command
    raw_cmd = body.get("command")
    cmd = _normalize_command(raw_cmd or "")
    if not cmd:
        return 400, {"error": "Invalid or missing 'command'"}, "application/json"

    spec = _load_command_spec(cmd)
    if not spec:
        return 404, {"error": f"Unknown command: /{cmd}"}, "application/json"

    # 2) Validate args
    ok, err, args = _validate_args(body.get("args") or {}, spec["arguments"])
    if not ok:
        return 400, {"error": err}, "application/json"

    # 3) Concurrency
    active = _active_runs()
    if len(active) >= MAX_GLOBAL_CONCURRENT:
        return 429, {"error": f"Too many active runs ({MAX_GLOBAL_CONCURRENT} max)"}, "application/json"

    if not spec.get("allow_concurrent"):
        for d in active:
            try:
                meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
                if meta.get("command") == f"/{cmd}":
                    return 409, {
                        "error": f"Another run of /{cmd} is active (run_id={d.name}). Cancel or wait.",
                    }, "application/json"
            except Exception:
                pass

    # 4) Resolve handler argv
    argv = _resolve_handler(spec)
    if not argv:
        return 501, {
            "error": f"No resolver for /{cmd}. Add 'pipeline: script:...' or 'pipeline: module:...' to command frontmatter, or create nexus/scripts/run_command.py as fallback.",
        }, "application/json"

    # 5) Create run dir
    run_id = _run_id()
    run_dir = RUNS_DIR / run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return 500, {"error": "run_id collision"}, "application/json"

    started_at = datetime.now(timezone.utc).isoformat()
    meta = {
        "run_id": run_id,
        "command": f"/{cmd}",
        "args": args,
        "status": "running",
        "pid": None,
        "started_at": started_at,
        "argv": argv,
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # 6) Spawn
    pid, err = _spawn(run_dir, argv, args)
    if err:
        meta["status"] = "failed"
        meta["error"] = err
        meta["finished_at"] = datetime.now(timezone.utc).isoformat()
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return 500, {"error": err, "run_id": run_id}, "application/json"

    meta["pid"] = pid
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return 200, {
        "run_id": run_id,
        "command": f"/{cmd}",
        "args": args,
        "status": "running",
        "pid": pid,
        "started_at": started_at,
        "log_path": str((run_dir / "output.log").relative_to(WORKSPACE)),
    }, "application/json"
