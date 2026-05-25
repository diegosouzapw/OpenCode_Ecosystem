#!/usr/bin/env bash
# apply-omniroute-config.sh
# Merges the JSONC opencode.omniroute.json.example with the current
# opencode.json (preserving its `mcp` section), then writes the merged
# result to opencode.json. A backup of the original is saved with a
# UTC timestamp suffix.
#
# Usage:
#   bash scripts/apply-omniroute-config.sh [example_path] [target_path]
#
# Defaults:
#   example_path = opencode.omniroute.json.example
#   target_path  = opencode.json
#
# Exit codes:
#   0  — merged successfully
#   1  — invalid args / files missing
#   2  — example file is not valid JSONC
#   3  — target file is not valid JSON
#   4  — backup or write failed
#   5  — missing dependency (node)

set -euo pipefail

EXAMPLE_PATH="${1:-opencode.omniroute.json.example}"
TARGET_PATH="${2:-opencode.json}"

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node is required (used to parse JSONC)." >&2
  exit 5
fi

if [ ! -f "$EXAMPLE_PATH" ]; then
  echo "ERROR: example file not found: $EXAMPLE_PATH" >&2
  exit 1
fi

if [ ! -f "$TARGET_PATH" ]; then
  echo "ERROR: target file not found: $TARGET_PATH" >&2
  exit 1
fi

TS=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_PATH="${TARGET_PATH}.bak.${TS}"

if ! cp -- "$TARGET_PATH" "$BACKUP_PATH"; then
  echo "ERROR: backup failed: $BACKUP_PATH" >&2
  exit 4
fi

# Inline Node script. String-state-aware JSONC stripper handles:
#   - block comments  /* ... */
#   - line comments   // ... (outside of string literals — URLs like
#     https:// in values are preserved)
#   - trailing commas before } or ]
NODE_SCRIPT='
const fs = require("fs");

function stripJsonc(src) {
  // Remove block comments first (they cannot span string boundaries in
  // well-formed JSONC; simple regex is safe here).
  src = src.replace(/\/\*[\s\S]*?\*\//g, "");
  // Remove line comments outside string literals.
  const out = [];
  let inStr = false;
  let esc = false;
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (inStr) {
      out.push(c);
      if (esc) esc = false;
      else if (c === "\\") esc = true;
      else if (c === "\"") inStr = false;
      continue;
    }
    if (c === "\"") { inStr = true; out.push(c); continue; }
    if (c === "/" && src[i + 1] === "/") {
      while (i < src.length && src[i] !== "\n") i++;
      out.push("\n");
      continue;
    }
    out.push(c);
  }
  // Remove trailing commas in objects and arrays.
  return out.join("").replace(/,(\s*[}\]])/g, "$1");
}

const [examplePath, targetPath, mergedPath] = process.argv.slice(-3);

let example;
try {
  example = JSON.parse(stripJsonc(fs.readFileSync(examplePath, "utf8")));
} catch (err) {
  console.error("Example file is not valid JSONC: " + err.message);
  process.exit(2);
}

let target;
try {
  target = JSON.parse(fs.readFileSync(targetPath, "utf8"));
} catch (err) {
  console.error("Target file is not valid JSON: " + err.message);
  process.exit(3);
}

const merged = { ...example, mcp: target.mcp };
fs.writeFileSync(mergedPath, JSON.stringify(merged, null, 2) + "\n");
console.log("Merged. Plugins: " + (merged.plugin || []).length + ", MCP keys: " + Object.keys(merged.mcp || {}).length);
'

MERGED_PATH="${TARGET_PATH}.merged.tmp"
# Note: must capture $? BEFORE evaluating an `if !` block — bash resets $?
# to 0 inside the then-branch of a negated condition.
set +e
node -e "$NODE_SCRIPT" -- "$EXAMPLE_PATH" "$TARGET_PATH" "$MERGED_PATH"
NODE_EXIT=$?
set -e
if [ "$NODE_EXIT" -ne 0 ]; then
  rm -f -- "$MERGED_PATH"
  exit "$NODE_EXIT"
fi

mv -- "$MERGED_PATH" "$TARGET_PATH"

echo ""
echo "✓ Config applied. Backup at: $BACKUP_PATH"
echo "  Original is recoverable via: cp \"$BACKUP_PATH\" \"$TARGET_PATH\""
