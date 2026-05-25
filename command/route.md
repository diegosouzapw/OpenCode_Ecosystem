---
name: route
trigger: ["/route", "/r", "/combo"]
description: Choose the OmniRoute combo (routing strategy) for subsequent pipeline calls
arguments:
  - name: combo_slug
    type: string
    required: false
    description: Combo slug to activate (e.g., "auto", "auto-free", "claude-primary"). Pass "--list" to enumerate available combos.
env_required:
  - OMNIROUTE_BASE_URL
env_exported:
  - OMNIROUTE_COMBO
pipeline: route_command_handler
since: v4.3.0
---

# /route — OmniRoute Combo Selector

> **Mission**: Set the active OmniRoute routing strategy (combo) for the current OpenCode session, controlling which LLM(s) the 125 agents call.

## What it does

Sets the env var `OMNIROUTE_COMBO=<slug>`, which the `@omniroute/opencode-plugin` reads on each `/v1/chat/completions` call and forwards via the `X-OmniRoute-Combo:` header. The OmniRoute gateway then applies the corresponding routing strategy (priority list, weighted, P2C, cost-optimized, etc.).

## Usage

```
/route                      # show current combo + list available
/route --list               # list available combos with descriptions
/route auto                 # use Auto-Combo (9-factor scoring)
/route auto-free            # use Auto-Combo restricted to free-tier providers
/route claude-primary       # force Claude family (Opus + Sonnet fallback)
/route cost-optimized       # always pick cheapest available
/route none                 # clear OMNIROUTE_COMBO (revert to direct model)
```

## Validation

The command reads `ECOSYSTEM_OMNIROUTE_COMBO_SLUGS` (exported by `ecosystem-sync v3.6` in PR-3) — a CSV of combo slugs known to the OmniRoute tenant. If the requested slug is not in this list:

- Print error showing available slugs.
- Do NOT export `OMNIROUTE_COMBO`.

If `OMNIROUTE_BASE_URL` is unset (OmniRoute not configured):

- Print message: "OmniRoute not active. Run setup per GETTING_STARTED.md section 5."
- Do NOT export anything.

## Examples

### Example 1: economic run of `/artigo`

```
/route cost-optimized
/artigo "Impact of LLM-based peer review"
```

The 49 MASWOS agents and 9 review/orientador agents all dispatch through the cost-optimized combo, selecting the cheapest healthy provider per call.

### Example 2: quality run with Claude Opus

```
/route claude-primary
/artigo "Quantum noise mitigation strategies"
```

Forces the Claude family for the entire pipeline, including the 9 reviewer/orientador agents that already have `model: omniroute/claude-opus-4-7` in frontmatter (PR-2). The combo guarantees Claude even if a single connection rate-limits.

### Example 3: free-tier only (zero cost preserved)

```
/route auto-free
/artigo "Brazilian higher education trends 2020-2026"
```

Restricts to Gemini Free, GLM Free, Groq, Cerebras, Pollinations, OpenCode Zen (big-pickle). Latency may vary, but cost is guaranteed zero.

### Example 4: revert to direct model

```
/route none
```

Clears `OMNIROUTE_COMBO`. Subsequent calls use the model directly (e.g., the agent's `model: omniroute/claude-opus-4-7` frontmatter bypass the combo layer).

## Rules

<rule id="env_required">
  REQUIRE `OMNIROUTE_BASE_URL` to be set. Without it, the OmniRoute plugin is not active and combos have no meaning.
</rule>
<rule id="slug_validation">
  VALIDATE the slug against `ECOSYSTEM_OMNIROUTE_COMBO_SLUGS` (CSV from ecosystem-sync v3.6). If not in list, error out without changing state.
</rule>
<rule id="session_scope">
  EXPORT `OMNIROUTE_COMBO` to the current OpenCode session env. Subsequent commands inherit it. Does NOT persist across sessions.
</rule>
<rule id="no_side_effects">
  This command MUST NOT call OmniRoute or any external endpoint. It only reads ECOSYSTEM_OMNIROUTE_COMBO_SLUGS (already populated by ecosystem-sync) and writes one env var.
</rule>

## Implementation

The pipeline `route_command_handler` is implemented in `core/command_registry.py` (see task 4.2). Reads args, validates against env, exports `OMNIROUTE_COMBO`, prints confirmation.

## See also

- `_tasks/00-PLAN-OMNIROUTE-INTEGRATION.md` — full integration plan
- `references/omniroute-model-mapping.md` — per-agent model mapping (PR-2)
- `https://github.com/diegosouzapw/OmniRoute/blob/main/docs/routing/AUTO-COMBO.md` — Auto-Combo scoring details
