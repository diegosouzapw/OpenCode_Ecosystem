<div align="center">

# OpenCode Ecosystem v4.0.0

**Arquitetura multiagente evolutiva integrada ao OpenCode (OpenAI Codex CLI)**

[![Agentes](https://img.shields.io/badge/Agentes-118-6366f1?style=for-the-badge&logo=robot&logoColor=white)](agents/)
[![MCPs](https://img.shields.io/badge/MCPs-38_servidores-0ea5e9?style=for-the-badge&logo=server&logoColor=white)](opencode.json)
[![Skills](https://img.shields.io/badge/Skills-45-10b981?style=for-the-badge&logo=book&logoColor=white)](skills/)
[![Python](https://img.shields.io/badge/Python-109.180_linhas-f59e0b?style=for-the-badge&logo=python&logoColor=white)](nexus/)
[![Qualis](https://img.shields.io/badge/Qualis-A1_%E2%89%A595%2F100-ef4444?style=for-the-badge&logo=graduation-cap&logoColor=white)](criador-artigo/)
[![Modelo](https://img.shields.io/badge/Modelo-big--pickle_200K_ctx-8b5cf6?style=for-the-badge)](opencode.json)

</div>

---

O **OpenCode Ecosystem** é uma arquitetura multiagente evolutiva composta por **118 agentes**, **38 servidores MCP**, **45 skills especializadas** e aproximadamente **109.180 linhas de código Python**. O ecossistema operacionaliza produção acadêmica Qualis A1, pesquisa científica autônoma, documentação jurídica, análise de dados quânticos e engenharia reversa de sistemas legados.

> Repositório: `C:\Users\marce\.config\opencode`  
> Modelo base: `opencode/big-pickle` (OpenCode Zen, 200K ctx, 128K out)

---

## Visão Geral da Arquitetura

<img src="diagrams/architecture-overview.svg" alt="Arquitetura do Ecossistema OpenCode" width="100%" style="max-width:900px; border-radius:8px; margin:16px 0;">

| Camada | Função | Componentes | Tecnologia |
|--------|--------|-------------|------------|
| **L6 — Orquestração** | Coordenação meta-granular | Nexus NMA v6.2, Reversa, Evo Loop | Python, JSON-RPC |
| **L5 — Agentes** | Execução especializada | 118 agentes em 4 categorias | OpenCode Subagents |
| **L4 — MCP** | Protocolo ferramenta-agente | 38 servidores (36 local, 2 remote) | MCP SDK, stdio |
| **L3 — Skills** | Diretrizes de domínio | 45 SKILL.md (progressive disclosure) | YAML, Markdown |
| **L2 — Dados** | Armazenamento e memória | SQLite, Mem0, Quantum, DOCLing | SQLite, Ollama |
| **L1 — Infra** | Runtime e sistema de arquivos | Node.js 25, Bun 1.3, Python 3.12 | Win32 |

---

## Orquestração Multiagente (Nexus NMA v6.2)

<img src="diagrams/agent-orchestration.svg" alt="Orquestração Multiagente Nexus" width="100%" style="max-width:900px; border-radius:8px; margin:16px 0;">

O **Nexus-Multiagents-v6** (NMA) sincroniza operações atômicas entre agentes com **120+ sync barriers** e **500+ constraints de validação** em 6 camadas (L0–L5):

```
L0 — Meta-Coordenação      (orquestração entre barreiras de sincronização)
L1 — Sincronização Micro   (validação atômica de cada operação)
L2 — Execução Paralela     (dispatcher de tarefas independentes)
L3 — Consolidação          (merge de resultados parciais)
L4 — Auditoria             (validação cruzada Qualis A1)
L5 — Evolução              (ciclo de auto-aprimoramento)
```

| Métrica NMA | Valor |
|-------------|:-----:|
| Sync Barriers | 120+ |
| Constraints de validação | 500+ |
| Sub-tipos de raciocínio | 38 |
| Scripts Python | 63 |
| Sessões context offload | 55 |
| Health score | 96/100 |

---

## MCP Servers (38 configurados)

<img src="diagrams/mcp-architecture.svg" alt="Arquitetura MCP Client-Host-Server" width="100%" style="max-width:900px; border-radius:8px; margin:16px 0;">

O protocolo MCP opera em três zonas: **Host** (OpenCode), **sessões Client** (ferramentas) e **servidores** locais/remotos.

| Categoria | Servidores | Exemplos |
|-----------|:----------:|---------|
| Core / Infraestrutura | 12 | `filesystem`, `sqlite`, `github`, `playwright` |
| Busca e Pesquisa | 6 | `websearch`, `context7`, `gh_grep`, `wikipedia` |
| Execução e Análise | 6 | `code-runner`, `sequential-thinking`, `mermaid` |
| Memória e Decisões | 3 | `mem0-mcp`, `decisionnode`, `self-healer` |
| Domínio Jurídico/Acadêmico | 6 | `maswos-juridico`, `maswos-rag`, `scihub`, `biomcp` |
| Outros | 5 | `hacker-news`, `youtube-transcript`, ... |

### Estratégias RAG (9 estratégias)

<img src="diagrams/rag-strategies.svg" alt="9 Estratégias RAG do MASWOS" width="100%" style="max-width:900px; border-radius:8px; margin:16px 0;">

O servidor `maswos-rag` expõe 9 estratégias de Retrieval-Augmented Generation aplicadas ao pipeline acadêmico e jurídico.

---

## Pipeline Acadêmico Qualis A1

<img src="diagrams/academic-pipeline.svg" alt="Pipeline Acadêmico Qualis A1" width="100%" style="max-width:900px; border-radius:8px; margin:16px 0;">

Pipeline multiagente de 8 estágios para produção acadêmica Qualis A1 (score ≥ 95/100):

**SEEKER** → Estrutura → Escrita → Formatação → Revisão (5 revisores) → Correção (4 orientadores) → Score (≥ 95/100) → Export LaTeX/PDF

| Métrica | Valor |
|---------|:-----:|
| Agentes especialistas | 49 (A00–A45 + scheduler) |
| Templates de artigo | 24 |
| Referências acadêmicas (Qualis A1, ABNT) | 14 |
| Board Score inicial → final | 86,5 → 92,7/100 (+7,1%) |
| Auto Score Qualis inicial → final | 74 → 95/100 (+28,4%) |
| Limiar Qualis A1 | ≥ 95/100 |

### Ciclos de Evolução AutoEvolve (8 gerações)

| Ciclo | Skill Gerada | Score |
|:-----:|-------------|:-----:|
| evo-1 | Cross-validation + World Bank API | 85/100 |
| evo-2 | Artigo 35 páginas + ABNT + setores | 90/100 |
| evo-3 | TSAC citations + notas de rodapé auditáveis | 95/100 |
| evo-4 | Sci-Hub MCP + arXiv + multi-source | 88/100 |
| evo-5 | Pearson cross-validation + 27 indicadores | 92/100 |
| evo-6 | Iterative Correction Loop + SEEKER | 95/100 |
| evo-7 | Sync v3.5 + CJK corrector + token efficiency | 96/100 |
| evo-8 | Progressive disclosure + observability | 98/100 |
| **Média** | Progressão: **85 → 98** (+15,3%) | **91,1** |

---

## Ciclo de Autocura (Self-Healing)

<img src="diagrams/self-healing.svg" alt="Ciclo de Autocura do Ecossistema" width="100%" style="max-width:900px; border-radius:8px; margin:16px 0;">

O ciclo **Monitorar → Detectar → Diagnosticar → Reparar → Verificar** opera continuamente pelo MCP `self-healer` e script `nexus/scripts/self_healer.py`, mantendo **95,6% das skills** dentro do limite de 2.500B e **100% dos MCPs ativos**.

---

## Saúde do Ecossistema

| Indicador | Valor | Status |
|-----------|:-----:|:------:|
| Skills dentro do limite (≤ 2.500B) | 43/45 | 🟢 95,6% |
| MCPs ativos | 38/38 | 🟢 100% |
| Agentes registrados | 118 | 🟢 |
| Reversa confidence score | 100% | 🟢 |
| AutoEvolve gerações concluídas | 9 | 🟢 |
| Gaps de engenharia reversa abertos | 0 | 🟢 |
| Health score Nexus | 96/100 | 🟢 |

---

## Módulos Principais

| Módulo | Arquivos `.py` | Linhas | Descrição |
|--------|:--------------:|:------:|-----------|
| DOCLing | 100+ | ~39.910 | Pipeline PDF → OCR → RAG Index |
| Nexus | 63 | ~22.286 | Orquestrador NMA v6.2 |
| Basis Research (SEEKER) | 33 | ~13.659 | Pesquisa autônoma multi-fonte |
| Quantum | 40 | ~10.088 | VQC 50-qubit, QML HAM10000 (89,52%) |
| Editais-BR | 73 | ~5.797 | Busca inteligente de editais de fomento |
| Artigo MIT-IA | 46 | ~5.678 | Artigo acadêmico referência |
| **Total** | **~427+** | **~109.180** | |

### Quantum — Resultados Validados

| Experimento | Resultado |
|------------|:---------:|
| QML HAM10000 (7 classes) | Acurácia: **89,52%** |
| VQC 50-qubit MPS (CV 5-fold) | Mean accuracy: **90,54% ± 0,58%** |
| AUC-ROC | **99,98%** |
| ZNE noise recovery | E = 0,771 |
| Redução MPS vs Statevector | ~**10¹¹×** |

---

## Skills Registry (45 skills)

Todas as skills seguem **progressive disclosure**: SKILL.md ≤ 2.500B com referências a `references/*.md`.

| Categoria | Skills | Exemplos |
|-----------|:------:|---------|
| system | 6 | `code-review`, `reasoning-orchestrator`, `token-efficiency` |
| juridico | 7 | `edicao-cirurgica`, `pecas-juridicas-html`, `gerador-contratos` |
| research | 3 | `academic-export-abnt`, `academic-ml-pipeline`, `editais-br` |
| tooling | 18 | `mcp-builder`, `agentic-mcp` |
| superpowers | 10 | `writing-plans`, `test-driven-dev` |
| Outras | 1 | `frontend-philosophy`, `plan-protocol`, ... |

---

## Comandos Rápidos

| Comando | Pipeline Acionado |
|---------|-------------------|
| `/artigo` | SEEKER + criador-artigo (49 agentes) + manus-evolve → Qualis A1 |
| `/evolve` | AutoEvolve pipeline (6 estágios: PLAN→ACT→REFLECT→EXTRACT→EVOLVE) |
| `/reversa` | reversa-* (9 agentes: scout → design-system) |
| `/quantum` | quantum-nexus-phd + code-runner + pdf |
| `/plan` | writing-plans + sequential-thinking MCP |
| `/auto` | openagent + todos os MCPs |

---

## Notas Técnicas

1. **Token Efficiency** — Contexto armazenado em formato compacto (+40% densidade); output sempre em PT-BR formal. Correção por `ptbr_corrector.py` com detecção CJK.
2. **Progressive Disclosure** — Skills com SKILL.md ≤ 2.500B; conteúdo detalhado em `references/*.md`.
3. **MCP Lazy Init** — Servidores `local` auto-iniciam na primeira chamada, sem overhead.
4. **Manus Evolve** — Engine autônoma PLAN→ACT→REFLECT→EXTRACT→EVOLVE gerando novas skills em `evolution/`.
5. **Auditoria Qualis A1** — 10 critérios com pesos, 5 revisores + 4 orientadores até score ≥ 95/100.
6. **DecisionNode** — Registro de decisões arquiteturais com busca semântica via embeddings Ollama.

---

> **OpenCode Ecosystem v4.0.0** — 118 agentes · 38 MCPs · 45 skills · ~109.180 linhas Python  
> Documentação gerada pelo Reversa Framework v1.2.22 em 2026-05-16  
> Repositório: `C:\Users\marce\.config\opencode` | Modelo: `opencode/big-pickle`
