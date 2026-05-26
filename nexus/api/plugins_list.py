"""
GET /api/plugins — list plugins from opencode.json with schema info.
"""

import json
import re
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent.parent.resolve()
CONFIG_PATH = WORKSPACE / "opencode.json"

# Hardcoded schemas — extend as new plugins gain config surface
PLUGIN_SCHEMAS = {
    "ecosystem-sync":      {"options": []},
    "manus-evolve":        {"options": []},
    "bernstein-sync":      {"options": []},
    "antigravity-bridge":  {"options": []},
    "@omniroute/opencode-plugin": {
        "options": [
            {"name": "providerId",    "type": "string",  "default": "omniroute"},
            {"name": "displayName",   "type": "string"},
            {"name": "baseURL",       "type": "string", "required": True},
            {"name": "modelCacheTtl", "type": "integer","default": 300000},
            {"name": "features.combos",              "type": "boolean", "default": True},
            {"name": "features.enrichment",          "type": "boolean", "default": True},
            {"name": "features.compressionMetadata", "type": "boolean", "default": False},
            {"name": "features.providerTag",         "type": "boolean", "default": True},
            {"name": "features.usableOnly",          "type": "boolean", "default": False},
            {"name": "features.diskCache",           "type": "boolean", "default": True},
            {"name": "features.geminiSanitization",  "type": "boolean", "default": True},
            {"name": "features.mcpAutoEmit",         "type": "boolean", "default": False},
        ],
    },
}


def _strip_comments(text: str) -> tuple[str, bool]:
    """
    Strip // line comments and /* */ block comments from JSONC source.
    Uses a state-machine that respects string literals.
    Returns (cleaned, had_comments).
    """
    had = False
    result = []
    i = 0
    length = len(text)
    in_string = False
    escape_next = False

    while i < length:
        ch = text[i]

        if escape_next:
            result.append(ch)
            escape_next = False
            i += 1
            continue

        if in_string:
            if ch == "\\":
                result.append(ch)
                escape_next = True
                i += 1
            elif ch == '"':
                result.append(ch)
                in_string = False
                i += 1
            else:
                result.append(ch)
                i += 1
            continue

        # Outside string
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue

        # Check for // line comment
        if ch == "/" and i + 1 < length and text[i + 1] == "/":
            had = True
            # Skip to end of line (preserve newline)
            i += 2
            while i < length and text[i] != "\n":
                i += 1
            continue

        # Check for /* block comment */
        if ch == "/" and i + 1 < length and text[i + 1] == "*":
            had = True
            i += 2
            while i < length:
                if text[i] == "*" and i + 1 < length and text[i + 1] == "/":
                    i += 2
                    break
                i += 1
            continue

        result.append(ch)
        i += 1

    cleaned = "".join(result)

    # Strip trailing commas (JSONC allows them)
    cleaned2, n = re.subn(r",(\s*[}\]])", r"\1", cleaned)
    if n > 0:
        had = True

    return cleaned2, had


def _infer_name(entry) -> str:
    """
    Extract friendly plugin name from entry.
    entry can be:
      - string  "plugins/ecosystem-sync.ts" -> "ecosystem-sync"
      - string  "@omniroute/opencode-plugin" -> "@omniroute/opencode-plugin"
      - tuple   [pkg, options] -> use pkg
    """
    if isinstance(entry, list) and entry:
        pkg = str(entry[0])
    elif isinstance(entry, str):
        pkg = entry
    else:
        return "(unknown)"

    if pkg.startswith("@"):
        return pkg

    # Strip path + extension
    m = re.match(r".*/([^/]+?)(\.ts|\.js|\.mjs)?$", pkg)
    if m:
        return m.group(1)
    return pkg


def _is_local_path(entry) -> bool:
    pkg = entry[0] if isinstance(entry, list) else entry
    if not isinstance(pkg, str):
        return False
    return pkg.startswith(".") or pkg.startswith("/") or ("/" in pkg and not pkg.startswith("@"))


def handle_plugins(self, method, parsed, body):
    if method != "GET":
        return 405, {"error": "Method Not Allowed"}, "application/json"

    if not CONFIG_PATH.exists():
        return 404, {"error": "opencode.json not found in workspace"}, "application/json"

    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8")
    except OSError as e:
        return 500, {"error": f"Cannot read opencode.json: {e}"}, "application/json"

    cleaned, has_comments = _strip_comments(raw)

    try:
        cfg = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return 500, {
            "error": f"opencode.json is not valid JSON/JSONC: {e}",
            "has_comments": has_comments,
        }, "application/json"

    plugin_entries = cfg.get("plugin") or cfg.get("plugins") or []
    if not isinstance(plugin_entries, list):
        return 500, {"error": "'plugin' key in opencode.json is not a list"}, "application/json"

    plugins = []
    for entry in plugin_entries:
        name = _infer_name(entry)
        options = entry[1] if isinstance(entry, list) and len(entry) > 1 and isinstance(entry[1], dict) else {}
        schema = PLUGIN_SCHEMAS.get(name)

        plugins.append({
            "id": entry[0] if isinstance(entry, list) else entry,
            "name": name,
            "type": "local" if _is_local_path(entry) else "npm",
            "version": _detect_version(entry),
            "enabled": True,
            "options": options,
            "schema": schema,
            "raw_entry": entry,
        })

    return 200, {
        "plugins": plugins,
        "config_path": str(CONFIG_PATH.relative_to(WORKSPACE)),
        "has_comments": has_comments,
        "config_warning": (
            "opencode.json contains comments or JSONC features; "
            "Apply will lose them. A backup is created automatically."
        ) if has_comments else None,
    }, "application/json"


def _detect_version(entry) -> str:
    """Best-effort version detection."""
    pkg = entry[0] if isinstance(entry, list) else entry
    if not isinstance(pkg, str):
        return "?"
    # Try plugins/<name>.ts: look for a comment "v3.5.0" or `version "3.5.0"`
    if pkg.endswith(".ts"):
        p = (WORKSPACE / pkg).resolve()
        try:
            p.relative_to(WORKSPACE)
        except ValueError:
            return "?"
        if not p.is_file():
            return "?"
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return "?"
        m = re.search(r"v(\d+\.\d+\.\d+)", text) or re.search(r"version\s*[:=]\s*['\"](\d+\.\d+\.\d+)['\"]", text)
        return m.group(1) if m else "?"
    # npm package: try node_modules/<pkg>/package.json
    if pkg.startswith("@") or "/" not in pkg:
        pj = WORKSPACE / "node_modules" / pkg / "package.json"
        if pj.is_file():
            try:
                return str(json.loads(pj.read_text(encoding="utf-8")).get("version", "?"))
            except (OSError, json.JSONDecodeError):
                return "?"
    return "?"
