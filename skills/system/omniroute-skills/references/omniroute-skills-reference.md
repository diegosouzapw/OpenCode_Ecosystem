# OmniRoute Skills — Full Reference

> Detailed reference for the `omniroute-skills` skill. Use this when the parent `SKILL.md` doesn't have enough detail.

## Overview

The OmniRoute gateway maintains a **Skills framework** independent from the OpenCode Ecosystem's 106 local skills. OmniRoute skills are:

- **Sandboxed** (run in isolated sub-process, no FS access to caller's repo).
- **Capability-restricted** (declared in skill manifest — network, FS read/write, etc.).
- **Audited** (each invocation logged in `mcp_audit` table with run_id, args hash, duration, exit status).
- **Public** (catalog is queryable; community can contribute via the OmniRoute repo).

Public catalog (verify current state via `skill_list`):

| Category | Examples |
|---|---|
| eval-suites | `eval-code-review`, `eval-factuality`, `eval-hallucination`, `eval-redteam` |
| guardrails | `pii-detect`, `prompt-injection-detect`, `vision-safety-check` |
| utility | `code-format`, `markdown-lint`, `regex-test` |
| benchmarks | `bench-throughput`, `bench-latency` |

## MCP tool: `skill_list`

Enumerate available OmniRoute skills.

### Request

```json
{
  "category": "eval-suites",    // optional filter
  "limit": 50,                  // optional, default 100
  "search": "factuality"        // optional substring match
}
```

### Response

```json
{
  "skills": [
    {
      "name": "eval-factuality",
      "category": "eval-suites",
      "description": "Score factual accuracy of an LLM response against a known answer.",
      "version": "1.4.2",
      "capabilities": ["network"],
      "timeout_ms": 30000,
      "input_schema": { "type": "object", "properties": { "claim": {...}, "ground_truth": {...} } }
    }
  ]
}
```

## MCP tool: `skill_run`

Execute a skill. Returns a `run_id` immediately; poll status via `skill_status`.

### Request

```json
{
  "skill": "eval-factuality",
  "args": {
    "claim": "The Eiffel Tower is in Paris, France.",
    "ground_truth": "The Eiffel Tower is located in Paris, France."
  },
  "timeout_ms": 30000    // optional, override skill default
}
```

### Response

```json
{
  "run_id": "skr_abc123",
  "status": "queued",        // queued | running | done | failed
  "started_at": null         // populated when status == "running"
}
```

## MCP tool: `skill_status`

Poll the status of a `run_id`.

### Request

```json
{ "run_id": "skr_abc123" }
```

### Response (running)

```json
{ "run_id": "skr_abc123", "status": "running", "started_at": "2026-05-25T14:32:01Z" }
```

### Response (done)

```json
{
  "run_id": "skr_abc123",
  "status": "done",
  "started_at": "2026-05-25T14:32:01Z",
  "finished_at": "2026-05-25T14:32:11Z",
  "duration_ms": 10142,
  "result": {
    "factuality_score": 0.97,
    "rationale": "Both statements agree on location and country."
  }
}
```

### Response (failed)

```json
{
  "run_id": "skr_abc123",
  "status": "failed",
  "error": {
    "code": "TIMEOUT",
    "message": "Skill exceeded timeout_ms (30000)"
  }
}
```

## MCP tool: `skill_cancel`

Abort a running skill.

### Request

```json
{ "run_id": "skr_abc123" }
```

### Response

```json
{ "run_id": "skr_abc123", "status": "cancelled" }
```

## Polling pattern (Python pseudocode)

```python
import time
import json

# 1. Start
resp = mcp.call("omniroute.skill_run", {
    "skill": "eval-factuality",
    "args": {"claim": "...", "ground_truth": "..."}
})
run_id = resp["run_id"]

# 2. Poll until terminal status
while True:
    status = mcp.call("omniroute.skill_status", {"run_id": run_id})
    if status["status"] in ("done", "failed", "cancelled"):
        break
    time.sleep(0.5)

# 3. Use result
if status["status"] == "done":
    print(json.dumps(status["result"], indent=2))
else:
    raise RuntimeError(f"Skill failed: {status['error']}")
```

## Error codes

| Code | Meaning | Recovery |
|---|---|---|
| `SKILL_NOT_FOUND` | Slug doesn't exist in catalog | `skill_list` to discover |
| `INVALID_ARGS` | Args don't match `input_schema` | Re-check schema, fix args |
| `TIMEOUT` | Exceeded `timeout_ms` | Reduce input size or increase timeout |
| `CAPABILITY_DENIED` | Skill needs capability not granted | Check OmniRoute admin / declare |
| `RATE_LIMITED` | Tenant quota exhausted | Wait or upgrade plan |
| `SANDBOX_CRASH` | Skill sub-process died | Report to OmniRoute maintainers |

## Common skills mapping (suggested usage)

| Need | OmniRoute skill | Local alternative |
|---|---|---|
| Check factual accuracy of MASWOS output | `eval-factuality` | none (use this) |
| Detect prompt injection in user input | `prompt-injection-detect` | none (use this) |
| Score code review quality | `eval-code-review` | `skills/system/code-review` (prefer local) |
| Lint markdown | `markdown-lint` | `markdownlint` MCP (prefer local) |
| Detect PII in academic abstract | `pii-detect` | none (use this) |
| Validate regex doesn't backtrack | `regex-test` | none (use this) |

## Audit trail

Every `skill_run` invocation creates a row in OmniRoute's `mcp_audit` table:

```sql
SELECT
  ts, tool_name, args_hash, duration_ms, exit_status, api_key_id
FROM mcp_audit
WHERE tool_name = 'omniroute.skill_run'
ORDER BY ts DESC
LIMIT 10;
```

Auditable fields: timestamp, tool name, args hash (not raw — hashed for privacy), duration, exit status, API key ID. Skill output is NOT stored (privacy).

## Security notes

- **Never pass secrets in `args`**: args hash is stored; raw args are logged at DEBUG level. Tokens, API keys, PII → use env vars or OmniRoute Secrets Store binding.
- **Sandboxed**: skills cannot read the caller's repo. To pass file content, base64-encode in args.
- **One-shot**: no state between calls. If you need stateful evaluation, use OmniRoute Memory (FTS5 + Qdrant) — separate MCP tool.
- **TLS required**: MCP transport must be over HTTPS or trusted Unix socket.

## References

- OmniRoute Skills framework docs: https://github.com/diegosouzapw/OmniRoute/blob/main/docs/frameworks/SKILLS.md
- MCP audit guarantees: https://github.com/diegosouzapw/OmniRoute/blob/main/docs/frameworks/MCP-SERVER.md
- Secrets handling: https://github.com/diegosouzapw/OmniRoute/blob/main/docs/security/PUBLIC_CREDS.md
