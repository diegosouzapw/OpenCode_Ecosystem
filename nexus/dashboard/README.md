# Nexus Dashboard — Architecture v3.0

> HTTP server stdlib-only servindo múltiplas telas de gestão do ecossistema, sem deps externas, sem build step, loopback-only.

## TL;DR

```bash
python nexus/dashboard_server.py              # http://localhost:8081
python nexus/dashboard_server.py --porta 9090
python nexus/dashboard_server.py --gerar-only # gera HTML estático
```

## File layout

```
nexus/
├── dashboard_server.py          ← roteador HTTP + main()
├── dashboard/
│   ├── index.html               ← Overview (v2.0 preserved, v3.0 layout-wrapped)
│   ├── agents.html              ← PR-7 (Agents & Models — Layout A)
│   ├── health.html              ← PR-8 (Provider & MCP Health)
│   ├── pipelines.html           ← PR-9 (Pipeline Runner)
│   ├── plugins.html             ← PR-10 (Plugin Configuration)
│   ├── README.md                ← este arquivo
│   └── assets/
│       ├── nav.js               ← sidebar render (renderNav("activeKey"))
│       ├── styles.css           ← design tokens
│       ├── api.js               ← cliente fetch (window.api.{get,put,post})
│       ├── agents.js            ← PR-7 (lógica da tela)
│       ├── health.js            ← PR-8
│       ├── pipelines.js         ← PR-9
│       └── plugins.js           ← PR-10
└── api/
    ├── __init__.py
    ├── ping.py                  ← /api/ping (foundation)
    ├── agents.py                ← /api/agents/* (PR-7)
    ├── health.py                ← /api/health/* (PR-8)
    ├── pipelines.py             ← /api/pipelines/* (PR-9)
    └── plugins.py               ← /api/plugins/* (PR-10)
```

## Routing

### Pages

| Path | File | Owner |
|---|---|---|
| `/` | `dashboard/index.html` | v2.0 (preserved) |
| `/agents` | `dashboard/agents.html` | PR-7 |
| `/health` | `dashboard/health.html` | PR-8 |
| `/pipelines` | `dashboard/pipelines.html` | PR-9 |
| `/plugins` | `dashboard/plugins.html` | PR-10 |

Defined in `PAGE_ROUTES` dict at the top of `dashboard_server.py`.

### Assets

`/assets/*` → `nexus/dashboard/assets/*` (directory-traversal-guarded).

### API

`/api/*` dispatched via `API_HANDLERS` dict. Handlers register themselves via `api_register(prefix, handler)` at import time.

Each handler signature:

```python
def handle_xxx(self, method: str, parsed: ParseResult, body: dict | None) -> tuple[int, dict | str | bytes, str]:
    # Returns (status_code, payload, content_type)
    ...
```

Longest-prefix match for dispatch (e.g., `/api/agents/reviewer-1/model` matches `/api/agents/` then `/api/agents` if both exist — uses the longer).

### Legacy

`/dados.json` — preserved from v2.0 for any external consumers.

## Design principles

1. **CLI is source of truth.** UI reads/writes the same files the CLI uses (agent frontmatter, `opencode.json`, `.evolve/*`). No parallel state.
2. **Loopback only.** No auth. Document the contract: do not expose port 8081 publicly. Use SSH port-forward for remote access.
3. **Pending changes pattern.** Mutations stage in `.evolve/pending-*.json` files; UI shows diff; user explicitly Applies.
4. **Stdlib only.** No Flask, FastAPI, Next.js, npm.
5. **Reversible.** Every PR can be `git revert` cleanly. No DB migrations.

## Security model

| Vector | Mitigation |
|---|---|
| Network exposure | Bind to `127.0.0.1` only (default of `HTTPServer`); document do-not-expose policy |
| Path traversal | `_serve_asset` strips `..` and resolves under fixed prefix |
| JSON body bomb | `Content-Length` cap at 1 MB before reading |
| Shell injection in pipeline runner (PR-9) | No `shell=True`; args allow-list from `command/*.md` schemas |
| Frontmatter write race | Atomic write (`tempfile.NamedTemporaryFile` + `os.replace`) |
| Cross-session env contamination | `OMNIROUTE_COMBO` written to `.evolve/session-env.json`, NOT to user's shell rc |

## How to add a new page (PR-N)

1. Add path to `PAGE_ROUTES` in `dashboard_server.py`.
2. Create `nexus/dashboard/<name>.html` using the standard template:

   ```html
   <!DOCTYPE html>
   <html lang="pt-BR">
   <head>
     <meta charset="UTF-8">
     <title>Nexus › My Page</title>
     <link rel="stylesheet" href="/assets/styles.css">
   </head>
   <body>
     <div class="layout">
       <div id="nav"></div>
       <main class="main">
         <h1>My Page</h1>
         <!-- content -->
       </main>
     </div>
     <script src="/assets/api.js"></script>
     <script src="/assets/nav.js"></script>
     <script src="/assets/mypage.js"></script>
     <script>renderNav("mykey");</script>
   </body>
   </html>
   ```

3. Add the key to `nav.js` `items` array (with `since: "PR-N"` until merged, then remove).
4. Create `nexus/api/<name>.py` if the page needs API endpoints, call `api_register(...)`.
5. Document in the PR description.

## How to test

```bash
# Boot
python3 nexus/dashboard_server.py --porta 8088 &

# Foundation check
curl -s http://localhost:8088/api/ping | python3 -m json.tool

# Page renders
curl -s http://localhost:8088/ | head -c 200
curl -sI http://localhost:8088/agents   # 404 until PR-7
curl -sI http://localhost:8088/health   # 404 until PR-8

# Asset served
curl -sI http://localhost:8088/assets/nav.js
```

## Version history

| Version | PR | Highlights |
|:--:|:--:|---|
| v1.0 | (pre-existing) | Single-page Chart.js dashboard |
| v2.0 | (pre-existing) | + trend charts, domínio internacional cards, mcp-brasil metrics |
| **v3.0** | **PR-6** | **Route dispatch, sidebar nav, asset pipeline, /api/* skeleton, /api/ping** |
| v3.1 | PR-7 | + Agents & Models screen (Layout A) |
| v3.2 | PR-8 | + Provider & MCP Health screen |
| v3.3 | PR-9 | + Pipeline Runner screen |
| v3.4 | PR-10 | + Plugin Configuration screen |
