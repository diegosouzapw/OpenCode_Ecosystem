---
name: omniroute-skills
description: Invoke OmniRoute sandbox skills (eval suites, guardrails, code-review) via MCP. Use when you need isolated/audited skill execution or want to leverage OmniRoute's public skill catalog beyond the 106 local skills.
trigger:
  - "omniroute skill"
  - "run eval"
  - "sandbox skill"
  - "guardrail check"
category: system
since: v4.3.0
mcp_dependency: mcp__omniroute__skill_run
size_budget: 2500
references:
  - references/omniroute-skills-reference.md
---

# omniroute-skills

> **Mission**: Bridge the OpenCode Ecosystem to the OmniRoute Skills framework via MCP, enabling sandboxed/audited execution of public skill catalog beyond the 106 local skills.

## When to use

- Need **sandboxed execution** (untrusted code, eval suites)
- Need **audit trail** (`mcp_audit` table)
- Need a skill the OmniRoute catalog has and local does not (eval-* suites, guardrails)
- Want **parallel runs** with isolation between calls

## When NOT to use

- Local skill suffices (always prefer local — lower latency)
- Need direct file I/O on local FS (sandboxed skills cannot read repo files)
- Need stateful execution across calls (sandbox is one-shot)

## How to invoke

The skill exposes 4 MCP tools (full schema in `references/omniroute-skills-reference.md`):

| Tool | Use |
|---|---|
| `skill_list` | enumerate OmniRoute skills |
| `skill_run` | execute a skill (returns run_id) |
| `skill_status` | poll status by run_id |
| `skill_cancel` | abort a long-running skill |

Typical flow:

1. `skill_list` → find skill matching task
2. `skill_run` with payload → get `run_id`
3. Poll `skill_status` until `done` or `failed`
4. Use result

## Rules

<rule id="prefer_local">Always check the 106 local skills first. Only invoke OmniRoute if no local match.</rule>
<rule id="timeout_aware">OmniRoute skills have hard timeout (default 60s). Don't wrap in long agent loops.</rule>
<rule id="audit_required">Every invocation is logged in `mcp_audit`. Don't bypass via direct HTTP to OmniRoute.</rule>
<rule id="no_secrets">Never pass tokens/keys in skill payloads — they get logged.</rule>

## See

`references/omniroute-skills-reference.md` — full MCP schemas, examples, error handling.
