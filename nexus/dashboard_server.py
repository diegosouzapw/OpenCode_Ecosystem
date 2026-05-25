"""dashboard_server.py v3.0 — Dashboard web do ecossistema OpenCode.

Servidor HTTP auto-contido (stdlib apenas) que expoe dados do ecossistema
como API REST e serve interface web com graficos Chart.js.

Uso:
    python nexus/dashboard_server.py              # http://localhost:8081
    python nexus/dashboard_server.py --porta 9090
    python nexus/dashboard_server.py --gerar-only  # Gera HTML estatico

v3.0 (PR-6): Route dispatch, sidebar nav, asset pipeline, /api/* skeleton, /api/ping.
v2.0: Graficos de tendencia Chart.js, cards de dominio internacional,
      metricas do extrator de dados publicos e mcp-brasil.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler

WORKSPACE = Path(__file__).parent.parent.resolve()
CACHE_DIR = WORKSPACE / "cache"
EVALS_DIR = WORKSPACE / "evals"
EVOLVE_DIR = WORKSPACE / ".evolve"
HTML_PATH = Path(__file__).parent / "dashboard" / "index.html"

# === Route dispatch table (v3.0 — PR-6 foundation) ===
#
# Key:   URL path (exact for "/", exact for page routes)
# Value: relative path to HTML file (under nexus/)
#
# Add new routes here as PR-7..PR-10 land.

PAGE_ROUTES: dict[str, str] = {
    "/":           "dashboard/index.html",      # Overview (existing, v2.0)
    "/agents":     "dashboard/agents.html",     # PR-7 (currently 404)
    "/health":     "dashboard/health.html",     # PR-8 (currently 404)
    "/pipelines":  "dashboard/pipelines.html",  # PR-9 (currently 404)
    "/plugins":    "dashboard/plugins.html",    # PR-10 (currently 404)
}

# API handlers: key = path prefix, value = callable(self, method, parsed_path, body_or_none)
# Each entry returns a tuple (status_code: int, payload: dict|str|bytes, content_type: str)
API_HANDLERS: dict = {
    # Populated by api_register() from sub-modules.
    # Foundation only adds /api/ping (see task 6.4).
}


def api_register(prefix: str, handler) -> None:
    """Register an API handler. Called by sub-modules at import time."""
    API_HANDLERS[prefix] = handler


# === Robust module loader: works whether run as module or script ===
API_MODULE_DIR = Path(__file__).parent / "api"


def _load_api_module(name: str):
    p = API_MODULE_DIR / f"{name}.py"
    if not p.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"nexus.api.{name}", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# === Register API handlers from sub-modules ===
_ping = _load_api_module("ping")
if _ping:
    api_register("/api/ping", _ping.handle_ping)
else:
    print("[dashboard] Could not register /api/ping: module not found")

# === PR-7: Agents & Models screen ===
_agents_mod = _load_api_module("agents")
if _agents_mod:
    api_register("/api/agents", _agents_mod.handle_agents)

_omni = _load_api_module("omniroute_proxy")
if _omni:
    api_register("/api/models", _omni.handle_models)
    api_register("/api/combos", _omni.handle_combos)

_sess = _load_api_module("session_combo")
if _sess:
    api_register("/api/session/combo", _sess.handle_session_combo)

_changes = _load_api_module("agent_changes")
if _changes:
    # IMPORTANT: longest-prefix match means /api/agents/pending, /api/agents/diff,
    # /api/agents/apply must register BEFORE the /api/agents/ catchall.
    api_register("/api/agents/pending", _changes.handle_pending)
    api_register("/api/agents/diff", _changes.handle_diff)
    api_register("/api/agents/apply", _changes.handle_apply)

    def _route_agent_model(self, method, parsed, body):
        parts = parsed.path.strip("/").split("/")
        # /api/agents/<name>/model
        if len(parts) == 4 and parts[:2] == ["api", "agents"] and parts[3] == "model":
            return _changes.handle_agent_model_put(self, method, parsed, body, parts[2])
        # /api/agents/<name>/pending → DELETE
        if len(parts) == 4 and parts[:2] == ["api", "agents"] and parts[3] == "pending":
            return _changes.handle_agent_model_put(self, "DELETE", parsed, body, parts[2])
        return 404, {"error": "Bad agent route"}, "application/json"

    api_register("/api/agents/", _route_agent_model)

# === PR-8: Health screen (live monitoring with SSE) ===
_hp = _load_api_module("health_providers")
if _hp:
    api_register("/api/health/providers", _hp.handle_health_providers)

_hm = _load_api_module("health_mcp")
if _hm:
    api_register("/api/health/mcp", _hm.handle_health_mcp)

_hs = _load_api_module("health_stream")
if _hs and _hp and _hm:
    # Factory pattern: stream needs references to providers + mcp modules
    api_register("/api/health/stream", _hs.handle_health_stream_factory(_hp, _hm))

# === PR-9: Pipelines screen ===
_pl = _load_api_module("pipelines_list")
_pr = _load_api_module("pipelines_run")
_ps = _load_api_module("pipelines_stream")

if _pl:
    api_register("/api/pipelines", _pl.handle_pipelines)

if _pl or _ps:
    def _route_runs(self, method, parsed, body):
        parts = parsed.path.strip("/").split("/")
        # /api/pipelines/runs  (exact — list runs)
        if len(parts) == 3 and _pl:
            return _pl.handle_runs(self, method, parsed, body)
        # /api/pipelines/runs/<id>/output/stream
        if len(parts) == 6 and parts[:3] == ["api", "pipelines", "runs"] \
                and parts[4] == "output" and parts[5] == "stream" and _ps:
            return _ps.handle_output_stream(self, method, parsed, body, parts[3])
        # /api/pipelines/runs/<id>/cancel
        if len(parts) == 5 and parts[:3] == ["api", "pipelines", "runs"] \
                and parts[4] == "cancel" and _ps:
            return _ps.handle_cancel(self, method, parsed, body, parts[3])
        return 404, {"error": "Bad run route"}, "application/json"

    api_register("/api/pipelines/runs", _route_runs)

if _pr:
    api_register("/api/pipelines/run", _pr.handle_run)


def carregar_json(rel_path: str) -> dict | list | None:
    p = WORKSPACE / rel_path
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except: pass
    return None


def contar_scripts_python() -> dict:
    """Contagem rapida de scripts Python no workspace."""
    py_files = list(WORKSPACE.rglob("*.py"))
    total = len(py_files)
    total_lines = 0
    for f in py_files:
        try: total_lines += len(f.read_text(encoding="utf-8").splitlines())
        except: pass
    return {"total": total, "linhas": total_lines}


def coletar_dados() -> dict:
    manifest = carregar_json("cache/ecosystem_manifest.json") or {}
    history = carregar_json("cache/ecosystem_history.json") or {"snapshots": []}
    knowledge = carregar_json("cache/evolution_knowledge.json") or {}
    manus = carregar_json(".evolve/manus-state.json") or {}
    agentes_md = carregar_json("nexus/agentes.json") or {}

    # Metricas de saude
    health = {}
    if isinstance(manifest, dict):
        h = manifest.get("health", {})
        tots = manifest.get("totals", {})
        health = {
            "skills": tots.get("skills", 0),
            "scripts": tots.get("scripts", 0),
            "plugins": tots.get("plugins", 0),
            "agents": tots.get("agents", 0),
            "evals": tots.get("evals", 0),
            "total_lines_py": tots.get("total_lines_py", 0),
            "anomalies": len(manifest.get("anomalies", [])),
            "recommendations": len(manifest.get("recommendations", [])),
            "frontmatter_ok": h.get("frontmatter_ok", 0),
            "cjk_leaks": h.get("cjk_leaks", 0),
            "scripts_needing_entrypoint": h.get("scripts_needing_entrypoint", 0),
            "scripts_with_main": h.get("scripts_with_main", 0),
            "timestamp": manifest.get("timestamp", ""),
        }
    else:
        py = contar_scripts_python()
        health = {
            "skills": len(list(WORKSPACE.rglob("**/SKILL.md"))),
            "scripts": py["total"],
            "plugins": len(list(WORKSPACE.rglob("plugins/*.ts"))),
            "agents": 24,
            "evals": 5,
            "total_lines_py": py["linhas"],
            "anomalies": 0,
            "recommendations": 0,
            "frontmatter_ok": 0,
            "cjk_leaks": 0,
            "scripts_needing_entrypoint": 0,
            "scripts_with_main": 0,
            "timestamp": datetime.now().isoformat(),
        }

    # Rounds de evolucao
    rounds = []
    for r in manus.get("rounds", []):
        rounds.append({
            "round": r.get("round", 0), "score": r.get("score", 0),
            "actions": len(r.get("actions", [])),
            "skills": len(r.get("extractedSkills", [])),
            "learnings": len(r.get("learnings", [])),
            "timestamp": r.get("timestamp", ""),
        })

    nexus_reports = manus.get("nexusReports", [])
    snapshots = history.get("snapshots", [])

    # Recomendacoes
    recommendations = []
    if isinstance(manifest, dict):
        for r in manifest.get("recommendations", []):
            recommendations.append(r)

    # === DETALHAMENTO DOS COMPONENTES ===

    # Skills detalhadas
    skills_detalhes = []
    if isinstance(manifest, dict):
        for s in manifest.get("components", {}).get("skills", []):
            swot = gerar_swot_skill(s["name"])
            skills_detalhes.append({
                "nome": s["name"],
                "caminho": s["path"],
                "tamanho_bytes": s["bytes"],
                "tamanho_kb": round(s["bytes"] / 1024, 1),
                "linhas": s["lines"],
                "scripts": len(s["scripts"]),
                "frontmatter_ok": s["frontmatter"] and s.get("has_name", False) and s.get("has_description", False),
                "cjk_leak": s.get("cjk_leak", False),
                "scripts_lista": s.get("scripts", []),
                "swot": swot,
            })

    # Plugins detalhados
    plugins_detalhes = []
    if isinstance(manifest, dict):
        for p in manifest.get("components", {}).get("plugins", []):
            plugins_detalhes.append({
                "nome": p["name"],
                "caminho": p["path"],
                "bytes": p["bytes"],
                "linhas": p["lines"],
                "hash": p.get("hash", ""),
            })

    # Agentes (SEEKER) detalhados
    agentes_detalhes = []
    if isinstance(manifest, dict):
        for a in manifest.get("components", {}).get("agents", []):
            tipo = a.get("type", "desconhecido")
            funcoes_count = a.get("functions", 0)
            nome_agente = a["name"]
            # Determinar funcao do agente com base no nome
            funcao = _descrever_agente(nome_agente, tipo)
            agentes_detalhes.append({
                "nome": nome_agente,
                "tipo": tipo,
                "funcoes": funcoes_count,
                "caminho": a["path"],
                "funcao": funcao,
            })

    # MCPs (definidos no AGENTS.md)
    mcps = [
        {"categoria": "Busca", "mcps": [
            {"nome": "websearch", "descricao": "Busca na web via DuckDuckGo", "funcao": "Encontra informacoes atualizadas na internet"},
            {"nome": "gh_grep", "descricao": "Busca codigo no GitHub", "funcao": "Encontra exemplos de codigo reais em repositorios publicos"},
            {"nome": "context7", "descricao": "Documentacao de bibliotecas", "funcao": "Consulta documentacao oficial de frameworks e APIs"},
            {"nome": "scihub", "descricao": "Busca artigos academicos", "funcao": "Acessa papers cientificos por DOI, titulo ou palavra-chave"},
        ]},
        {"categoria": "Navegador", "mcps": [
            {"nome": "playwright", "descricao": "Automacao de navegador", "funcao": "Navega em sites, clica, preenche formularios, tira screenshots"},
            {"nome": "chrome-devtools", "descricao": "Ferramentas do Chrome", "funcao": "Inspeciona elementos, rede, console, desempenho de paginas web"},
        ]},
        {"categoria": "Codigo", "mcps": [
            {"nome": "eslint", "descricao": "Analise estatica de codigo", "funcao": "Verifica qualidade e padroes do codigo JavaScript/TypeScript"},
            {"nome": "diff", "descricao": "Comparacao de textos", "funcao": "Mostra diferencas entre versoes de arquivos"},
            {"nome": "code-runner", "descricao": "Execucao de codigo", "funcao": "Roda snippets em varias linguagens (Python, JS, etc)"},
        ]},
        {"categoria": "Dados", "mcps": [
            {"nome": "sqlite", "descricao": "Banco de dados SQLite", "funcao": "Executa consultas SQL em bancos de dados locais"},
            {"nome": "fetch", "descricao": "Requisicoes HTTP", "funcao": "Obtem conteudo de URLs (HTML, JSON, texto, PDFs, videos)"},
            {"nome": "pdf", "descricao": "Manipulacao de PDF", "funcao": "Le, extrai texto, adiciona marcas d'agua, conta paginas"},
            {"nome": "time", "descricao": "Data e hora", "funcao": "Obtem data/hora atual e informacoes de fuso horario"},
        ]},
        {"categoria": "Raciocinio", "mcps": [
            {"nome": "sequential-thinking", "descricao": "Raciocinio estruturado", "funcao": "Divide problemas complexos em etapas logicas e revisa hipoteses"},
            {"nome": "memory", "descricao": "Memoria persistente", "funcao": "Grafo de conhecimento para lembrar informacoes entre sessoes"},
        ]},
        {"categoria": "Infraestrutura", "mcps": [
            {"nome": "filesystem", "descricao": "Sistema de arquivos", "funcao": "Le, escreve, move e gerencia arquivos e diretorios"},
            {"nome": "github", "descricao": "API do GitHub", "funcao": "Gerencia repositorios, issues, PRs, commits e arquivos"},
        ]},
    ]

    # Legendas explicativas para leigos
    legendas = {
        "skill": {
            "titulo": "O que sao Skills?",
            "explicacao": "Skills sao manuais de instrucao que ensinam o assistente AI a realizar tarefas especificas. Cada skill contem um arquivo SKILL.md com regras, exemplos e fluxos de trabalho. Pense como um 'livro de receitas' para o AI: ele le a skill e sabe exatamente como executar aquela tarefa.",
            "como_funciona": "Quando voce pede algo relacionado a uma skill, o AI carrega automaticamente as instrucoes daquela skill e segue o passo-a-passo definido.",
        },
        "plugin": {
            "titulo": "O que sao Plugins?",
            "explicacao": "Plugins sao programas em TypeScript que adicionam capacidades especiais ao ecossistema. Eles automatizam fluxos complexos, como o ciclo de evolucao autonoma (Manus Evolve) ou a sincronizacao entre componentes.",
            "como_funciona": "Plugins sao executados automaticamente em segundo plano ou acionados por comandos como /evolve.",
        },
        "mcp": {
            "titulo": "O que sao MCPs?",
            "explicacao": "MCPs (Model Context Protocols) sao ferramentas que o assistente AI pode usar para interagir com o mundo externo: buscar informacoes na web, executar codigo, manipular arquivos, acessar bancos de dados e muito mais.",
            "como_funciona": "Cada MCP e como um 'aplicativo' que o AI pode chamar quando precisa. Por exemplo, o MCP websearch permite pesquisar no Google; o MCP sqlite permite consultar bancos de dados.",
        },
        "agente": {
            "titulo": "O que sao Agentes?",
            "explicacao": "Agentes sao sub-programas especializados que executam tarefas especificas dentro de um fluxo maior. Cada agente tem uma funcao unica: pesquisar (Social), analisar (Gaper), escrever (Scribe), verificar fatos (Rude), etc.",
            "como_funciona": "Os agentes trabalham em sequencia como uma linha de montagem: um agente passa o resultado para o proximo, cada um adicionando sua contribuicao ate o produto final ficar pronto.",
        },
        "swot": {
            "titulo": "O que e analise SWOT?",
            "explicacao": "SWOT e uma sigla para Forcas (Strengths), Fraquezas (Weaknesses), Oportunidades (Opportunities) e Ameacas (Threats). E como um 'raio-X' de cada componente: mostra o que ele faz bem, o que pode melhorar, onde pode crescer e quais riscos enfrenta.",
            "como_funciona": "Para cada componente do ecossistema, avaliamos esses 4 aspectos para entender seu valor e seus desafios.",
        },
        "limites": {
            "titulo": "Limites do Ecossistema",
            "explicacao": "Cada componente tem limites de capacidade, escopo ou disponibilidade. Conhecer esses limites ajuda a usar cada ferramenta de forma adequada e evitar frustracoes.",
            "como_funciona": "Os limites sao atualizados automaticamente pelo scanner do ecossistema e refletem o estado real de cada componente.",
        },
    }

    return {
        "health": health,
        "rounds": rounds,
        "nexus_reports": nexus_reports,
        "snapshots": snapshots,
        "recommendations": recommendations,
        "knowledge": {
            "ciclos_analisados": knowledge.get("ciclos_analisados", 0),
            "ultima_analise": knowledge.get("ultima_analise", ""),
        },
        "manus": {
            "total_skills": manus.get("totalSkillsGenerated", 0),
            "evolution_score": manus.get("evolutionScore", 0),
            "total_rounds": len(manus.get("rounds", [])),
            "version": manus.get("version", "?"),
        },
        "extrator": {
            "versao": "2.1",
            "fontes": 38,
            "dominios": 6,
            "tem_internacional": True,
            "fontes_internacionais": ["FMI", "ONU", "OCDE", "OMS", "BRICS", "UNCTAD", "FAO", "OIT", "UNESCO", "ADB"],
        },
        "skills_detalhes": skills_detalhes,
        "plugins_detalhes": plugins_detalhes,
        "agentes_detalhes": agentes_detalhes,
        "mcps": mcps,
        "legendas": legendas,
    }


def gerar_swot_skill(nome: str) -> dict:
    """Gera analise SWOT contextual para cada skill."""
    swots = {
        "editais-br": {
            "forcas": "Busca em 52 editais curados, 25 sub-dimensoes de classificacao, scoring 0-100 por perfil, cache versionado, fallback offline",
            "fraquezas": "SKILL.md proximo do limite de 2.5KB, DuckDuckGo bloqueia ~50% das requisicoes, CAPES/CNPq offline (404)",
            "oportunidades": "Integracao com CAPES e CNPq Lattes quando portais retornarem, expansao para 70+ fontes",
            "ameacas": "Portais governamentais mudam APIs sem aviso, bloqueios anti-bot",
        },
        "docling-pdf-extraction": {
            "forcas": "Extracao OCR avancada (IBM Docling), fallback pdfplumber rapido (<5s por documento), wrapper no nexus",
            "fraquezas": "Docling OCR lento (>10min), requer instalacao de dependencias pesadas",
            "oportunidades": "Suporte a mais formatos de documento, pipeline OCR em lote",
            "ameacas": "Dependencia de biblioteca externa pesada, possiveis mudancas de API",
        },
        "reasoning-orchestrator": {
            "forcas": "58 tipos de raciocinio mapeados, 6 niveis de profundidade (L1-L6), matriz de intersecao",
            "fraquezas": "Alta complexidade conceitual, requer entendimento profundo para usar",
            "oportunidades": "Integracao com mais agentes do ecossistema",
            "ameacas": "Pode ser preterido por abordagens mais simples",
        },
        "code-review": {
            "forcas": "Classificacao de gravidade, limites de confianca, metodologia abrangente",
            "fraquezas": "Revisao manual, nao automatizada",
            "oportunidades": "Integracao com CI/CD para revisao automatica",
            "ameacas": "Ferramentas de revisao automatizada podem substituir",
        },
        "plan-protocol": {
            "forcas": "Diretrizes claras para planos de implementacao com citacoes obrigatorias",
            "fraquezas": "Pode ser rigido demais para projetos pequenos",
            "oportunidades": "Template para geracao automatica de planos",
            "ameacas": "Times podem ignorar o protocolo se for muito burocratico",
        },
        "plan-review": {
            "forcas": "Criterios objetivos para revisao de planos contra padroes de qualidade",
            "fraquezas": "Requer planos bem formatados para funcionar",
            "oportunidades": "Integracao com plan-protocol para ciclo completo",
            "ameacas": "Planos mal escritos podem escapar da revisao",
        },
        "code-philosophy": {
            "forcas": "5 Leis da Defesa Elegante para codigo defensivo, principios solidos",
            "fraquezas": "Filosofia abstrata, dificil de aplicar mecanicamente",
            "oportunidades": "Exemplos praticos de aplicacao das 5 Leis",
            "ameacas": "Pode ser ignorada por devs focados em entrega rapida",
        },
        "frontend-philosophy": {
            "forcas": "5 Pilares da UI Intencional, foco em experiencia do usuario",
            "fraquezas": "Especifica para frontend, nao aplicavel a backend",
            "oportunidades": "Guia de componentes reais seguindo os pilares",
            "ameacas": "Tendencias de design podem mudar",
        },
        "token-efficiency": {
            "forcas": "Otimizacao de tokens usando chines para armazenamento (+40% densidade), saida PT-BR obrigatoria",
            "fraquezas": "Requer corretor CJK apos cada entrega, processo extra de qualidade",
            "oportunidades": "Reducao de custos com tokens, suporte a mais idiomas",
            "ameacas": "Modelos podem ter desempenho variavel com chines no contexto",
        },
    }
    return swots.get(nome, {
        "forcas": "Integrado ao ecossistema, segue padroes de qualidade",
        "fraquezas": "Documentacao limitada ou escopo restrito",
        "oportunidades": "Expansao de funcionalidades e integracoes",
        "ameacas": "Mudancas no ecossistema podem exigir adaptacao",
    })


def _descrever_agente(nome: str, tipo: str) -> str:
    """Descreve a funcao de cada agente de forma leiga."""
    descricoes = {
        "breaks": "Faz pausas estrategicas no pipeline para evitar erros e permitir revisao",
        "gaper": "Identifica lacunas no conhecimento, como um detetive procurando pistas faltantes",
        "grounder": "Busca as origens intelectuais do problema, encontrando livros e artigos fundamentais",
        "historian": "Cria uma linha do tempo do problema, mostrando como ele evoluiu",
        "rude": "Avalia se as propostas sao viaveis na pratica, como um 'pessimista realista'",
        "scribe": "Organiza e formata os resultados finais em documentos prontos para leitura",
        "social": "Pesquisa fontes academicas e da web, como um bibliotecario digital",
        "synthesizer": "Junta todas as pecas em uma narrativa coerente, como um editor de revista",
        "theorist": "Propoe abordagens e solucoes concretas, como um consultor tecnico",
        "thinker": "Abre novas direcoes a partir da sintese, pensando 'e se...?'",
        "vision": "Extrai consequencias logicas e implicacoes, como um futurista",
        "argument_tree": "Constroi uma arvore de argumentos que cresce a cada etapa da pesquisa",
        "concept_mapper": "Mapeia conceitos e suas conexoes, como um mapa mental",
        "context": "Monta o resumo do que ja foi descoberto para cada agente",
        "database": "Gerencia o banco de dados SQLite que armazena todo o progresso",
        "keys": "Gerencia chaves de API de forma segura",
        "llm": "Roteia requisicoes para modelos de linguagem (Claude, etc)",
        "rate_limiter": "Controla a velocidade das requisicoes para nao sobrecarregar servidores",
        "references": "Gera referencias bibliograficas no formato APA",
        "utils": "Funcoes uteis compartilhadas (logs, IDs, config)",
    }
    return descricoes.get(nome, f"Modulo de {tipo}: processamento auxiliar no ecossistema")


# =============================================================================
# HTTP HANDLER
# =============================================================================

class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse

        parsed = urlparse(self.path)
        path = parsed.path

        # === API routes (prefix match on /api/*) ===
        if path.startswith("/api/"):
            return self._dispatch_api("GET", path, parsed, body=None)

        # === Static assets (/assets/*) ===
        if path.startswith("/assets/"):
            return self._serve_asset(path)

        # === Page routes (exact path match) ===
        if path in PAGE_ROUTES:
            return self._serve_page(PAGE_ROUTES[path])

        # === Legacy data endpoint (preserved from v2.0) ===
        if path == "/dados.json":
            return self._serve_legacy_data()

        # === 404 ===
        self._send_json(404, {"error": "Not Found", "path": path})

    def do_HEAD(self):
        # Serve headers only (no body) for GET-able paths — supports curl -sI
        self._head_only = True
        try:
            self.do_GET()
        finally:
            self._head_only = False

    def do_PUT(self):
        return self._dispatch_with_body("PUT")

    def do_POST(self):
        return self._dispatch_with_body("POST")

    def _dispatch_with_body(self, method: str):
        from urllib.parse import urlparse

        parsed = urlparse(self.path)
        path = parsed.path

        if not path.startswith("/api/"):
            return self._send_json(405, {"error": "Method Not Allowed"})

        # Read body (max 1 MB to prevent abuse)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_048_576:
                return self._send_json(413, {"error": "Payload too large (max 1 MB)"})
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw) if raw else None
        except (json.JSONDecodeError, ValueError) as e:
            return self._send_json(400, {"error": f"Invalid JSON body: {e}"})

        return self._dispatch_api(method, path, parsed, body)

    def _dispatch_api(self, method: str, path: str, parsed, body):
        # Longest-prefix match
        match = None
        for prefix in sorted(API_HANDLERS.keys(), key=len, reverse=True):
            if path == prefix or path.startswith(prefix + "/"):
                match = (prefix, API_HANDLERS[prefix])
                break

        if not match:
            return self._send_json(404, {"error": "API endpoint not found", "path": path})

        try:
            status, payload, content_type = match[1](self, method, parsed, body)
            if status == -1:
                return  # handler already wrote the response (SSE, file download, etc.)
        except Exception as e:
            return self._send_json(500, {"error": str(e)})

        if isinstance(payload, (dict, list)):
            return self._send_json(status, payload)
        elif isinstance(payload, str):
            return self._send_text(status, payload, content_type)
        elif isinstance(payload, bytes):
            return self._send_bytes(status, payload, content_type)
        else:
            return self._send_json(500, {"error": "Handler returned unsupported payload type"})

    def _serve_page(self, rel_path: str):
        full = Path(__file__).parent / rel_path
        if not full.exists():
            # PR-7..PR-10 pages return 404 until those PRs land
            return self._send_json(404, {"error": f"Page not yet implemented: {rel_path}"})
        try:
            content = full.read_text(encoding="utf-8")
        except Exception as e:
            return self._send_json(500, {"error": str(e)})
        return self._send_text(200, content, "text/html; charset=utf-8")

    def _serve_asset(self, path: str):
        # Strip leading slash, prevent directory traversal
        safe = path.lstrip("/").replace("..", "")
        full = Path(__file__).parent / "dashboard" / safe
        if not full.is_file():
            return self._send_json(404, {"error": "Asset not found"})
        ext = full.suffix.lower()
        content_types = {
            ".js":   "application/javascript; charset=utf-8",
            ".css":  "text/css; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg":  "image/svg+xml",
            ".png":  "image/png",
        }
        ct = content_types.get(ext, "application/octet-stream")
        return self._send_bytes(200, full.read_bytes(), ct)

    def _send_json(self, status: int, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not getattr(self, "_head_only", False):
            self.wfile.write(body)

    def _send_text(self, status: int, payload: str, content_type: str):
        body = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not getattr(self, "_head_only", False):
            self.wfile.write(body)

    def _send_bytes(self, status: int, payload: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if not getattr(self, "_head_only", False):
            self.wfile.write(payload)

    def _serve_legacy_data(self):
        # Preserves the v2.0 contract for any external consumers of /dados.json
        return self._send_json(200, coletar_dados())

    def log_message(self, format, *args):
        # Suppress default access log noise; keep errors
        pass


def gerar_html_estatico():
    """Gera versao estatica do dashboard com dados inline."""
    dados = coletar_dados()
    content = HTML_PATH.read_text(encoding="utf-8") if HTML_PATH.exists() else ""
    if not content:
        print(f"[dashboard v3] Aviso: {HTML_PATH} nao encontrado, usando template embutido")
        return
    HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(content, encoding="utf-8")
    print(f"[dashboard v3] HTML estatico em {HTML_PATH}")
    print(f"[dashboard v3] Abra: file:///{HTML_PATH.as_posix()}")


def main():
    import argparse
    p = argparse.ArgumentParser(description="Dashboard do ecossistema v3.0")
    p.add_argument("--porta", type=int, default=8081, help="Porta HTTP")
    p.add_argument("--gerar-only", action="store_true", help="So gera HTML estatico")
    args = p.parse_args()

    if args.gerar_only:
        return gerar_html_estatico()

    server = ThreadingHTTPServer(("127.0.0.1", args.porta), DashboardHandler)
    print(f"Dashboard v3.0 (Foundation) em http://localhost:{args.porta}")
    print(f"  Pages registered: {', '.join(PAGE_ROUTES)}")
    print(f"  API handlers:     {', '.join(API_HANDLERS) or '(none yet — PR-6 foundation)'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] Servidor parado")


if __name__ == "__main__":
    main()
