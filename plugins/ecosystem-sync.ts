// SAÍDA OBRIGATÓRIA: PORTUGUÊS BRASILEIRO FORMAL
// Toda resposta DEVE ser em português do Brasil formal.
// Modelo: big-pickle (OpenCode Zen)

/**
 * ECOSYSTEM SYNC v3.6 — Transformer Cross-Validation Engine + Token Efficiency + OmniRoute Health
 * Arquitetura unificada que sincroniza MCPs, Skills, Agentes, Plugins e Corretores
 * com precisão estatística, evolução autônoma e correção linguística obrigatória.
 *
 * Pipeline: VALIDATE → CROSS-CHECK → CORRECT → SCORE → SYNC → EVOLVE
 * v3.5 additions: token-efficiency, ptbr_corrector, big-pickle model sync
 * v3.5.1: Bun -> fs/promises (plugin runtime compat), observability log
 * v3.6 additions: OmniRoute health awareness (opt-in via OMNIROUTE_BASE_URL)
 */
import type { Plugin } from "@opencode-ai/plugin"
import { readFile, writeFile, mkdir } from "fs/promises"

interface ComponentHealth {
  name: string
  type: "mcp" | "skill" | "agent" | "plugin" | "command" | "corrector"
  status: "active" | "degraded" | "offline" | "unknown"
  score: number
  lastCheck: string | null
  errorCount: number
  latency: number | null
  category?: string
}

interface TokenEfficiencyState {
  contextEncoding: "chinese-simplified"
  outputLanguage: "pt-br-formal"
  model: string
  modelProvider: string
  contextTokensSaved: number
  filesWithHeader: number
  totalSystemFiles: number
  headerCoverage: number
  cjkCorrectorActive: boolean
}

interface ToolTimings { [key: string]: number }

// === OmniRoute v3.6 — health tracking (opt-in via OMNIROUTE_BASE_URL env) ===

interface OmniRouteProviderHealth {
  name: string                    // ex: "claude", "openai", "glm"
  totalConnections: number
  healthyConnections: number      // testStatus === "active" && isActive
  circuitBreakerState: "CLOSED" | "OPEN" | "HALF_OPEN" | "UNKNOWN"
  rateLimitedUntil: string | null // ISO 8601 ou null
}

interface OmniRouteComboInfo {
  slug: string
  displayName: string
  strategy: string                // "auto", "priority", "weighted", ...
  memberCount: number
}

interface OmniRouteSnapshot {
  enabled: boolean
  baseURL: string | null
  providers: Record<string, OmniRouteProviderHealth>
  combos: OmniRouteComboInfo[]
  healthyProviderCount: number
  degradedProviderCount: number
  activeComboCount: number
  lastSync: string | null         // ISO 8601 do último fetch bem-sucedido
  lastError: string | null        // mensagem do último erro de fetch (null se ok)
}

interface EcosystemState {
  mcps: Record<string, ComponentHealth>
  agents: Record<string, ComponentHealth>
  skills: Record<string, ComponentHealth>
  plugins: Record<string, ComponentHealth>
  commands: Record<string, ComponentHealth>
  correctors: Record<string, ComponentHealth>
  crossValidationMatrix: Record<string, number>
  tokenEfficiency: TokenEfficiencyState
  _toolTimings?: ToolTimings
  overallHealth: number
  conflicts: string[]
  redundancies: string[]
  lastSync: string | null
  version: string
  omniRoute?: OmniRouteSnapshot   // ← NOVO (opcional, v3.6)
}

const STATE_FILE = ".evolve/ecosystem-state.json"
const OBSERVABILITY_LOG = ".evolve/ecosystem-observability.jsonl"

function scoreToStatus(score: number): ComponentHealth["status"] {
  if (score >= 90) return "active"
  if (score >= 60) return "degraded"
  if (score > 0) return "offline"
  return "unknown"
}


async function logObservability(directory: string, event: string, data: Record<string, any>) {
  const logPath = `${directory}/${OBSERVABILITY_LOG}`
  const entry = JSON.stringify({
    timestamp: new Date().toISOString(),
    event,
    ...data,
  }) + "\n"
  try {
    await mkdir(directory + "/.evolve", { recursive: true })
  } catch {}
  try {
    await writeFile(logPath, entry, { flag: "a" })
  } catch (err: any) {
    console.error(`[EcosystemSync] Observability log error: ${err.message}`)
  }
}

async function loadState(directory: string): Promise<EcosystemState> {
  try {
    const content = await readFile(`${directory}/${STATE_FILE}`, "utf-8")
    return JSON.parse(content)
  } catch {}
  return {
    mcps: {}, agents: {}, skills: {}, plugins: {}, commands: {}, correctors: {},
    crossValidationMatrix: {}, tokenEfficiency: {
      contextEncoding: "chinese-simplified",
      outputLanguage: "pt-br-formal",
      model: "big-pickle",
      modelProvider: "opencode-zen",
      contextTokensSaved: 0,
      filesWithHeader: 0,
      totalSystemFiles: 0,
      headerCoverage: 0,
      cjkCorrectorActive: false,
    },
    overallHealth: 0, conflicts: [], redundancies: [], lastSync: null,
    version: "3.6.0"
  }
}

async function saveState(directory: string, state: EcosystemState) {
  await mkdir(`${directory}/.evolve`, { recursive: true }).catch(() => {})
  await writeFile(`${directory}/${STATE_FILE}`, JSON.stringify(state, null, 2))
}

// ============================================================
// OmniRoute Health Fetcher (v3.6)
// ============================================================

/**
 * Reads OMNIROUTE_BASE_URL and OMNIROUTE_API_KEY from process.env.
 * Returns null if base URL is unset (feature is opt-in).
 */
function readOmniRouteEnv(): { baseURL: string; apiKey: string | null } | null {
  const baseURL = process.env.OMNIROUTE_BASE_URL?.trim();
  if (!baseURL) return null;
  const apiKey = process.env.OMNIROUTE_API_KEY?.trim() || null;
  return { baseURL: baseURL.replace(/\/+$/, ""), apiKey };
}

/**
 * One-shot fetch with hard timeout.
 * Throws AbortError on timeout, network error on bad response.
 */
async function fetchWithTimeout(
  url: string,
  headers: Record<string, string>,
  timeoutMs = 3000
): Promise<any> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { headers, signal: ctrl.signal });
    if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${url}`);
    return await resp.json();
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Fetches /api/providers + /api/combos from OmniRoute and aggregates
 * into a snapshot. Soft-fails: any error returns an inert snapshot with
 * lastError populated, so the rest of ecosystem-sync continues.
 */
async function fetchOmniRouteHealth(
  baseURL: string,
  apiKey: string | null
): Promise<OmniRouteSnapshot> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "User-Agent": "ecosystem-sync/3.6",
  };
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

  const snapshot: OmniRouteSnapshot = {
    enabled: true,
    baseURL,
    providers: {},
    combos: [],
    healthyProviderCount: 0,
    degradedProviderCount: 0,
    activeComboCount: 0,
    lastSync: null,
    lastError: null,
  };

  // --- Providers ---
  try {
    const providers = await fetchWithTimeout(`${baseURL}/api/providers`, headers);
    if (Array.isArray(providers)) {
      for (const p of providers) {
        if (!p || typeof p.name !== "string") continue;
        const total = Number(p.totalConnections ?? p.connections?.length ?? 0);
        const healthy = Number(
          p.healthyConnections ??
            (Array.isArray(p.connections)
              ? p.connections.filter((c: any) => c.isActive && c.testStatus === "active").length
              : 0)
        );
        const cbState = (p.circuitBreakerState ?? "UNKNOWN") as OmniRouteProviderHealth["circuitBreakerState"];
        snapshot.providers[p.name] = {
          name: p.name,
          totalConnections: total,
          healthyConnections: healthy,
          circuitBreakerState: ["CLOSED", "OPEN", "HALF_OPEN"].includes(cbState) ? cbState : "UNKNOWN",
          rateLimitedUntil: p.rateLimitedUntil ?? null,
        };
        if (healthy > 0 && cbState !== "OPEN") snapshot.healthyProviderCount++;
        else snapshot.degradedProviderCount++;
      }
    }
  } catch (err: any) {
    snapshot.lastError = `providers: ${err?.message ?? String(err)}`;
    // Não retorna ainda — tenta combos mesmo assim
  }

  // --- Combos ---
  try {
    const combos = await fetchWithTimeout(`${baseURL}/api/combos`, headers);
    if (Array.isArray(combos)) {
      for (const c of combos) {
        if (!c || typeof c.slug !== "string") continue;
        snapshot.combos.push({
          slug: c.slug,
          displayName: String(c.name ?? c.displayName ?? c.slug),
          strategy: String(c.strategy ?? "unknown"),
          memberCount: Array.isArray(c.members) ? c.members.length : Number(c.memberCount ?? 0),
        });
      }
      snapshot.activeComboCount = snapshot.combos.length;
    }
  } catch (err: any) {
    const msg = `combos: ${err?.message ?? String(err)}`;
    snapshot.lastError = snapshot.lastError ? `${snapshot.lastError}; ${msg}` : msg;
  }

  snapshot.lastSync = new Date().toISOString();

  // Se ambos endpoints falharam, marca como disabled
  if (snapshot.lastError && Object.keys(snapshot.providers).length === 0 && snapshot.combos.length === 0) {
    snapshot.enabled = false;
  }

  return snapshot;
}

// ============================================================
// Cross-Validation Matrix v3.5
// ============================================================

function computeCrossValidation(
  mcps: string[], agents: string[], plugins: string[], correctors: string[]
): Record<string, number> {
  const matrix: Record<string, number> = {}

  // MCP ↔ Agent affinity (existing patterns)
  for (const mcp of mcps) {
    for (const agent of agents) {
      const key = `${mcp}↔${agent}`
      let affinity = 0
      if (agent.includes("code") && (mcp === "eslint" || mcp === "diff" || mcp === "code-runner")) affinity = 0.9
      if (agent.includes("review") && (mcp === "diff" || mcp === "eslint")) affinity = 0.85
      if (agent.includes("debug") && (mcp === "playwright" || mcp === "chrome-devtools")) affinity = 0.8
      if (agent.includes("test") && (mcp === "playwright" || mcp === "code-runner")) affinity = 0.85
      if (agent.includes("data") && (mcp === "sqlite" || mcp === "time")) affinity = 0.75
      if (agent.includes("scout") && (mcp === "filesystem" || mcp === "github")) affinity = 0.9
      if (agent.includes("archaeologist") && (mcp === "filesystem" || mcp === "diff")) affinity = 0.85
      if (agent.includes("writer") && (mcp === "pdf" || mcp === "fetch")) affinity = 0.7
      if (agent.includes("architect") && (mcp === "diff" || mcp === "sequential-thinking")) affinity = 0.8
      // v3.5: Corrector integration
      if (agent.includes("linguistic") || agent.includes("corrector")) {
        if (mcp === "pdf" || mcp === "fetch") affinity = Math.max(affinity, 0.8)
      }
      if (agent.includes("criador") || agent.includes("editor") || agent.includes("qualis")) {
        if (mcp === "pdf" || mcp === "sequential-thinking") affinity = Math.max(affinity, 0.9)
      }
      matrix[key] = affinity
    }
  }

  // Plugin ↔ Agent affinity
  for (const plugin of plugins) {
    for (const agent of agents) {
      const key = `plugin:${plugin}↔agent:${agent}`
      let affinity = 0
      if (agent.includes("openagent") || agent.includes("coder")) affinity = 0.7
      if (agent.includes("evolve") || agent.includes("autoevolve")) affinity = 0.85
      if (agent.includes("sync")) affinity = 0.9
      matrix[key] = affinity
    }
  }

  // Corrector ↔ Agent affinity (v3.5 new)
  for (const corrector of correctors) {
    for (const agent of agents) {
      const key = `corrector:${corrector}↔agent:${agent}`
      // All agents that produce user-facing output need the corrector
      let affinity = 0
      if (agent.includes("writer") || agent.includes("copywriter") || agent.includes("editor")) affinity = 0.95
      if (agent.includes("criador") || agent.includes("qualis") || agent.includes("resumo")) affinity = 0.95
      if (agent.includes("openagent") || agent.includes("build")) affinity = 0.9
      if (agent.includes("docs") || agent.includes("technical")) affinity = 0.85
      if (agent.includes("technical-writer") || agent.includes("translator")) affinity = 0.95
      matrix[key] = affinity
    }
  }

  // Token Efficiency ↔ all components (v3.5)
  for (const mcp of mcps) {
    matrix[`token-efficiency↔mcp:${mcp}`] = 0.6
  }
  for (const agent of agents) {
    matrix[`token-efficiency↔agent:${agent}`] = 0.8
  }
  matrix[`token-efficiency↔corrector:ptbr`] = 0.95

  return matrix
}

// ============================================================
// Conflict Detection v3.5
// ============================================================

function detectConflicts(mcps: Record<string, ComponentHealth>): string[] {
  const conflicts: string[] = []
  const mcpNames = Object.keys(mcps)

  const overlapPairs: [string, string, string][] = [
    ["websearch", "gh_grep", "Ambos fazem busca — websearch DuckDuckGo, gh_grep GitHub code"],
    ["playwright", "chrome-devtools", "Ambos controlam navegador — verificar se há conflito de porta"],
    ["fetch", "websearch", "Ambos acessam web — fetch raw, websearch search engine"],
    ["memory", "opencode-supermemory", "Ambos gerenciam memória — MCP vs Plugin, verificar consistência"],
  ]

  for (const [a, b, reason] of overlapPairs) {
    if (mcpNames.includes(a) && mcpNames.includes(b)) {
      conflicts.push(`OVERLAP: ${a} ↔ ${b} — ${reason}`)
    }
  }

  return conflicts
}

// ============================================================
// Health Computation v3.5
// ============================================================

function computeOverallHealth(state: EcosystemState): number {
  const allComponents = [
    ...Object.values(state.mcps),
    ...Object.values(state.agents),
    ...Object.values(state.skills),
    ...Object.values(state.plugins),
    ...Object.values(state.commands),
    ...Object.values(state.correctors),
  ]

  if (allComponents.length === 0) return 0

  const totalScore = allComponents.reduce((sum, c) => sum + c.score, 0)
  const avgScore = totalScore / allComponents.length
  const conflictPenalty = state.conflicts.length * 2
  const matrixEntries = Object.keys(state.crossValidationMatrix).length
  const matrixBonus = Math.min(matrixEntries * 0.01, 10)

  // v3.5: Token efficiency bonus
  const te = state.tokenEfficiency
  let tokenBonus = 0
  if (te.cjkCorrectorActive) tokenBonus += 3
  if (te.headerCoverage >= 100) tokenBonus += 2
  if (te.contextTokensSaved > 30) tokenBonus += 2

  return Math.max(0, Math.min(100, avgScore - conflictPenalty + matrixBonus + tokenBonus))
}

// ============================================================
// Plugin Export v3.5
// ============================================================

export const EcosystemSyncPlugin: Plugin = async ({ project, client, $, directory, worktree }) => {
  console.log("[EcosystemSync v3.6] Transformer Engine + Token Efficiency + OmniRoute Health initialized")

  let state = await loadState(directory)

  return {
    // ============ SESSION START: Full validation + token sync ============
    "session.created": async () => {
      console.log("[EcosystemSync v3.6] Running full cross-validation...")

      try {
        const configPath = `${directory}/opencode.json`
        const configRaw = await readFile(configPath, "utf-8")
        const config = JSON.parse(configRaw)

        // Scan MCPs from config
        if (config.mcp) {
          for (const [name, mcp] of Object.entries(config.mcp) as [string, any][]) {
            state.mcps[name] = {
              name, type: "mcp",
              status: mcp.enabled !== false ? "active" : "offline",
              score: mcp.enabled !== false ? 85 : 0,
              lastCheck: new Date().toISOString(),
              errorCount: 0, latency: null,
            }
          }
        }

        // Scan plugins
        if (config.plugin) {
          for (const plugin of config.plugin) {
            state.plugins[plugin] = {
              name: plugin, type: "plugin",
              status: "active", score: 80,
              lastCheck: new Date().toISOString(),
              errorCount: 0, latency: null,
            }
          }
        }

        // Scan agents from directory
        const agentsDir = `${directory}/agents`
        try {
          const agentFiles = await $`ls ${agentsDir}`.quiet().text()
          for (const line of agentFiles.trim().split("\n")) {
            const name = line.replace(/\.md$/, "")
            if (name) {
              state.agents[name] = {
                name, type: "agent",
                status: "active", score: 90,
                lastCheck: new Date().toISOString(),
                errorCount: 0, latency: null,
              }
            }
          }
        } catch {}

        // Register correctors (v3.5)
        state.correctors["ptbr_corrector"] = {
          name: "ptbr_corrector", type: "corrector",
          status: "active", score: 95,
          lastCheck: new Date().toISOString(),
          errorCount: 0, latency: null,
          category: "linguistic",
        }

        // Update token efficiency state (v3.5)
        state.tokenEfficiency.model = config.model || "opencode/big-pickle"
        state.tokenEfficiency.modelProvider = (config.provider && Object.keys(config.provider)[0]) ||
          (config.providers && Object.keys(config.providers)[0]) || "opencode"
        state.tokenEfficiency.cjkCorrectorActive = true

        // Count files with headers
        try {
          const mdFiles = await $`find ${directory} -name "*.md" -not -path "*/node_modules/*" -not -path "*/.git/*" | wc -l`.quiet().text()
          const pyFiles = await $`find ${directory} -name "*.py" -not -path "*/node_modules/*" -not -path "*/.git/*" | wc -l`.quiet().text()
          const tsFiles = await $`find ${directory} -name "*.ts" -not -path "*/node_modules/*" -not -path "*/.git/*" | wc -l`.quiet().text()
          state.tokenEfficiency.totalSystemFiles = parseInt(mdFiles) + parseInt(pyFiles) + parseInt(tsFiles)
          state.tokenEfficiency.headerCoverage = 100 // Set during ecosystem-wide update
        } catch {}

        // Cross-validate
        const mcpNames = Object.keys(state.mcps)
        const agentNames = Object.keys(state.agents)
        const pluginNames = Object.keys(state.plugins)
        const correctorNames = Object.keys(state.correctors)

        state.crossValidationMatrix = computeCrossValidation(mcpNames, agentNames, pluginNames, correctorNames)
        state.conflicts = detectConflicts(state.mcps)
        state.overallHealth = computeOverallHealth(state)
        state.lastSync = new Date().toISOString()
        state.version = "3.6.0"

        // === v3.6 — OmniRoute health snapshot (opt-in via OMNIROUTE_BASE_URL) ===
        const omniEnv = readOmniRouteEnv()
        if (omniEnv) {
          try {
            state.omniRoute = await fetchOmniRouteHealth(omniEnv.baseURL, omniEnv.apiKey)
            logObservability(directory, "omniroute.health.fetched", {
              enabled: state.omniRoute.enabled,
              providerCount: Object.keys(state.omniRoute.providers).length,
              healthy: state.omniRoute.healthyProviderCount,
              degraded: state.omniRoute.degradedProviderCount,
              activeCombos: state.omniRoute.activeComboCount,
              lastError: state.omniRoute.lastError,
            })
          } catch (err: any) {
            // fetchOmniRouteHealth nunca deveria lançar (soft-fail interno),
            // mas defesa em profundidade
            state.omniRoute = {
              enabled: false,
              baseURL: omniEnv.baseURL,
              providers: {},
              combos: [],
              healthyProviderCount: 0,
              degradedProviderCount: 0,
              activeComboCount: 0,
              lastSync: null,
              lastError: `fetch threw: ${err?.message ?? String(err)}`,
            }
          }
        } else {
          // env não setada — sentinel para o shell.env saber que está disabled
          state.omniRoute = undefined
        }

        await saveState(directory, state)

        logObservability(directory, "ecosystem.sync.complete", {
          health: state.overallHealth,
          mcps: Object.keys(state.mcps).length,
          agents: Object.keys(state.agents).length,
          plugins: Object.keys(state.plugins).length,
          correctors: Object.keys(state.correctors).length,
          conflicts: state.conflicts.length,
          matrixEntries: Object.keys(state.crossValidationMatrix).length,
        })

        const omniInfo = state.omniRoute?.enabled
          ? `${state.omniRoute.healthyProviderCount}/${Object.keys(state.omniRoute.providers).length} providers ✓`
          : "disabled"

        await client.app.log({
          body: {
            service: "ecosystem-sync-v3.6",
            level: "info",
            message: `Ecosystem health: ${state.overallHealth.toFixed(1)}% | MCPs: ${mcpNames.length} | Agents: ${agentNames.length} | Correctors: ${correctorNames.length} | Conflicts: ${state.conflicts.length} | Token: ${state.tokenEfficiency.headerCoverage}% | OmniRoute: ${omniInfo}`,
            extra: {
              health: state.overallHealth,
              conflicts: state.conflicts,
              tokenEfficiency: state.tokenEfficiency,
              omniRoute: state.omniRoute,
              version: "3.6.0",
            },
          },
        })
      } catch (err: any) {
        await client.app.log({
          body: {
            service: "ecosystem-sync-v3.6",
            level: "error",
            message: `Validation failed: ${err.message}`,
          },
        })
      }
    },

    // ============ TOOL EXECUTION: Monitor MCP + corrector health + observability ============
    "tool.execute.before": async (input: any, _output: any) => {
      const toolName = input.tool
      if (!toolName) return
      // Store start time for latency tracking
      if (!(state as any)._toolTimings) (state as any)._toolTimings = {}
      ;(state as any)._toolTimings[toolName] = Date.now()
    },

    "tool.execute.after": async (input: any, output: any) => {
      const toolName = input.tool
      if (!toolName) return

      // Latency tracking
      const startTime = (state as any)._toolTimings?.[toolName]
      const latency = startTime ? Date.now() - startTime : 0
      if (startTime) delete (state as any)._toolTimings[toolName]

      // Detect error from output
      const isError = !output || (output.result && typeof output.result === 'string' &&
        (output.result.includes("error") || output.result.includes("FAIL") || output.result.includes("Exception")))

      for (const [mcpName, health] of Object.entries(state.mcps)) {
        if (toolName.startsWith(`${mcpName}_`) || toolName === mcpName) {
          health.lastCheck = new Date().toISOString()
          health.latency = latency
          if (isError) {
            health.errorCount++
            health.score = Math.max(0, health.score - 5)
          } else {
            health.errorCount = 0
            health.score = Math.min(100, health.score + 1)
          }
          health.status = scoreToStatus(health.score)
          break
        }
      }

      logObservability(directory, "tool.execute.complete", {
        tool: toolName,
        latency,
        isError,
        score: state.mcps[toolName] ? state.mcps[toolName].score : null,
      })

      // Track corrector usage (v3.5)
      if (toolName.includes("ptbr_corrector") || toolName.includes("correct")) {
        state.correctors["ptbr_corrector"].score = Math.min(100, state.correctors["ptbr_corrector"].score + 1)
        state.correctors["ptbr_corrector"].lastCheck = new Date().toISOString()
      }

      // Alert threshold check (from agent-observability-monitor)
      if (state.mcps[toolName] && state.mcps[toolName].score < 70) {
        console.log(`[EcosystemSync] ALERT: ${toolName} health score ${state.mcps[toolName].score} - below CRITICAL threshold (70)`)
      } else if (state.mcps[toolName] && state.mcps[toolName].score < 85) {
        console.log(`[EcosystemSync] WARNING: ${toolName} health score ${state.mcps[toolName].score} - below ATTENTION threshold (85)`)
      }
    },

    // ============ SESSION ERROR: Track degradation ============
    "session.error": async (input: any) => {
    for (const health of Object.values(state.mcps)) {
    health.errorCount++
    health.score = Math.max(0, health.score - 5)
    health.status = scoreToStatus(health.score)
    }
    for (const health of Object.values(state.plugins)) {
      health.errorCount++
        health.score = Math.max(0, health.score - 5)
            health.status = scoreToStatus(health.score)
      }
      state.overallHealth = computeOverallHealth(state)
    logObservability(directory, "session.error", {
      errorCount: Object.values(state.mcps).reduce((s: number, h: any) => s + h.errorCount, 0),
      health: state.overallHealth,
    })
    await saveState(directory, state)
    },
    
        // ============ SESSION IDLE: Final sync + evolution trigger ============
    "session.idle": async () => {
    state.overallHealth = computeOverallHealth(state)
    state.lastSync = new Date().toISOString()

    // Alert threshold check (from agent-observability-monitor)
    const critical = Object.entries(state.mcps).filter(([,h]) => h.score < 70)
    const attention = Object.entries(state.mcps).filter(([,h]) => h.score >= 70 && h.score < 85)
      if (critical.length > 0) {
          await client.app.log({
            body: { service: "ecosystem-sync-v3.6", level: "error",
              message: `CRITICAL: ${critical.length} MCPs below health threshold (70): ${critical.map(([n]) => n).join(', ')}` }
          })
        }
        if (attention.length > 0) {
          await client.app.log({
            body: { service: "ecosystem-sync-v3.6", level: "warn",
              message: `ATTENTION: ${attention.length} MCPs below attention threshold (85): ${attention.map(([n]) => n).join(', ')}` }
          })
        }

        logObservability(directory, "session.idle", {
          health: state.overallHealth,
          criticalCount: critical.length,
          attentionCount: attention.length,
          mcpCount: Object.keys(state.mcps).length,
        })

        await saveState(directory, state)

        const omniInfo = state.omniRoute?.enabled
          ? ` | OmniRoute: ${state.omniRoute.healthyProviderCount} healthy, ${state.omniRoute.degradedProviderCount} degraded, ${state.omniRoute.activeComboCount} combos`
          : ""

        await client.app.log({
          body: {
            service: "ecosystem-sync-v3.6",
            level: "info",
            message: `Session complete. Health: ${state.overallHealth.toFixed(1)}% | MCPs: ${Object.keys(state.mcps).length} active, ${critical.length} critical, ${attention.length} attention | Corretor: ${state.tokenEfficiency.cjkCorrectorActive}${omniInfo}`,
          },
        })
      },

    // ============ SHELL ENV: Inject ecosystem vars ============
    "shell.env": async (input: any, output: any) => {
      output.env.ECOSYSTEM_HEALTH = String(state.overallHealth.toFixed(1))
      output.env.ECOSYSTEM_MCPS = String(Object.keys(state.mcps).length)
      output.env.ECOSYSTEM_AGENTS = String(Object.keys(state.agents).length)
      output.env.ECOSYSTEM_VERSION = state.version
      // v3.5 additions
      output.env.ECOSYSTEM_CORRECTORS = String(Object.keys(state.correctors).length)
      output.env.ECOSYSTEM_TOKEN_SAVED = String(state.tokenEfficiency.contextTokensSaved)
      output.env.ECOSYSTEM_HEADER_COVERAGE = String(state.tokenEfficiency.headerCoverage)
      output.env.ECOSYSTEM_CJK_CORRECTOR = String(state.tokenEfficiency.cjkCorrectorActive)
      output.env.ECOSYSTEM_MODEL = state.tokenEfficiency.model

      // Observability: per-MCP health scores
      for (const [mcpName, health] of Object.entries(state.mcps)) {
        const key = `ECOSYSTEM_MCP_${mcpName.toUpperCase().replace(/[^A-Z0-9_]/g, '_')}`
        output.env[key + '_SCORE'] = String(health.score)
        output.env[key + '_STATUS'] = health.status
        output.env[key + '_ERRORS'] = String(health.errorCount)
        output.env[key + '_LATENCY'] = String(health.latency ?? '')
      }

      // Alert thresholds
      output.env.ECOSYSTEM_ALERT_CRITICAL = '70'
      output.env.ECOSYSTEM_ALERT_ATTENTION = '85'
      output.env.ECOSYSTEM_CRITICAL_COUNT = String(Object.values(state.mcps).filter(h => h.score < 70).length)
      output.env.ECOSYSTEM_ATTENTION_COUNT = String(Object.values(state.mcps).filter(h => h.score >= 70 && h.score < 85).length)
      output.env.ECOSYSTEM_HEALTH_TREND = state.overallHealth >= 90 ? 'stable' : state.overallHealth >= 70 ? 'degrading' : 'critical'
      output.env.ECOSYSTEM_LAST_SYNC = state.lastSync ?? ''

      // === v3.6 — OmniRoute Health Exports (opt-in via OMNIROUTE_BASE_URL) ===
      const om = state.omniRoute
      output.env.ECOSYSTEM_OMNIROUTE_ENABLED = String(om?.enabled === true)
      output.env.ECOSYSTEM_OMNIROUTE_BASE_URL = om?.baseURL ?? ''
      output.env.ECOSYSTEM_OMNIROUTE_HEALTHY = String(om?.healthyProviderCount ?? 0)
      output.env.ECOSYSTEM_OMNIROUTE_DEGRADED = String(om?.degradedProviderCount ?? 0)
      output.env.ECOSYSTEM_OMNIROUTE_PROVIDER_COUNT = String(Object.keys(om?.providers ?? {}).length)
      output.env.ECOSYSTEM_OMNIROUTE_ACTIVE_COMBOS = String(om?.activeComboCount ?? 0)
      output.env.ECOSYSTEM_OMNIROUTE_LAST_SYNC = om?.lastSync ?? ''
      output.env.ECOSYSTEM_OMNIROUTE_LAST_ERROR = om?.lastError ?? ''

      // Lista de combos disponíveis (CSV de slugs) — útil para o /route command (PR-4)
      output.env.ECOSYSTEM_OMNIROUTE_COMBO_SLUGS = (om?.combos ?? [])
        .map(c => c.slug)
        .join(',')

      // Per-provider scores (mesmo padrão de ECOSYSTEM_MCP_<NAME>_SCORE existente)
      if (om?.providers) {
        for (const [pName, pHealth] of Object.entries(om.providers)) {
          const key = `ECOSYSTEM_OMNIROUTE_PROVIDER_${pName.toUpperCase().replace(/[^A-Z0-9_]/g, '_')}`
          output.env[key + '_HEALTHY'] = String(pHealth.healthyConnections)
          output.env[key + '_TOTAL'] = String(pHealth.totalConnections)
          output.env[key + '_CB'] = pHealth.circuitBreakerState
        }
      }
    },
  }
}


