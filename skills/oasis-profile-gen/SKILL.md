---
name: oasis-profile-gen
description: >
  Gera perfis de agente IA (personas) a partir de entidades de um grafo de
  conhecimento. Inspirado pelo OASIS Profile Generator do MiroFish-Offline
  (oasis_profile_generator.py, simulation_config_generator.py).
  Converte nós do grafo (pessoas, organizações, conceitos) em personas
  estruturadas com bio, persona, interesses, MBTI, tópicos e estilo de fala.
  Use quando precisar criar agentes simulados realistas a partir de dados
  reais extraídos de documentos ou bases de conhecimento.
license: MIT
compatibility: opencode
allowed-tools: Read, Grep, Glob, Bash, Write
metadata:
  author: Reversa Engine (padrão MiroFish-Offline OASIS)
  version: "1.0.0"
  domain: simulation
  triggers: perfil, persona, profile, oasis, agente simulado, simulação
  role: generator
  scope: simulation
  output-format: json
  related-skills: code-graphrag, hybrid-graph-retrieval
  inspired-by: MiroFish-Offline oasis_profile_generator.py, simulation_config_generator.py
---

# OASIS Profile Generator — Personas de Agente a partir de Grafos

Inspirado pelo **OASIS (Opinion Agent Simulation Immersion System)** do
MiroFish-Offline. Converte entidades de um grafo de conhecimento em perfis
detalhados de agente para simulações multi-plataforma (Twitter, Reddit).

## Arquitetura (Padrão OASIS Profile)

```
MiroFish-Offline:  EntityReader → OasisProfileGenerator → Profile Files (JSON/CSV)
                          ↓                    ↓
                   GraphStorage (Neo4j)    LLM Prompt Templates

OpenCode:         GraphRAG Query → Profile Builder → Profile Output (JSON)
                          ↓                    ↓
                   code-graph.db (SQLite)   Ollama/OpenAI API
```

### Estrutura do Perfil

Cada perfil gerado contém:

| Campo | Tipo | Descrição | Origem |
|-------|------|-----------|--------|
| `name` | string | Nome do agente | Nó do grafo |
| `bio` | string | Biografia resumida | LLM + atributos do nó |
| `persona` | string | Personalidade em primeira pessoa | LLM |
| `interests` | string[] | Lista de interesses | LLM + arestas |
| `mbti` | string | Tipo Myers-Briggs | LLM inferido |
| `topics` | string[] | Tópicos de especialidade | Arestas + LLM |
| `speaking_style` | string | Estilo de fala característico | LLM |
| `twitter_behavior` | object | Comportamento no Twitter | Config + LLM |
| `reddit_behavior` | object | Comportamento no Reddit | Config + LLM |

## Quando Usar

| Cenário | Descrição |
|---------|-----------|
| Simulação de agentes | Criar agentes realistas para simular opiniões em rede social |
| Geração de NPCs | Personagens para jogos ou cenários de teste |
| Role-playing | Personas para teste de chatbots ou sistemas de diálogo |
| Análise de stakeholders | Perfis de atores a partir de documentos de análise |
| Onboarding | Personas de usuário para design centrado no humano |

## Workflow

### Fase 1: EXTRAIR — Obter Entidades do Grafo

1. **Consulte o grafo** — use GraphRAG ou consulta direta ao SQLite
2. **Filtre por tipo** — selecione entidades com labels significativos (excluindo `Entity`, `Node`)
3. **Enriqueça com arestas** — obtenha arestas de entrada/saída e nós relacionados

### Fase 2: GERAR — Produzir Perfis via LLM

1. **Para cada entidade**, monte um prompt com:
   - Nome, summary, atributos
   - Relações (outgoing + incoming)
   - Nós relacionados com seus atributos

2. **Template de Prompt** (melhorado do original):
```
Gere um perfil de agente para simulação baseado na entidade abaixo:

== DADOS DA ENTIDADE ==
Nome: {name}
Resumo: {summary}
Atributos: {attributes}

== RELAÇÕES ==
{related_edges}

== CONTEXTO DO GRAFO ==
{related_nodes}

== PERFIL REQUERIDO ==
Gere um JSON com os campos:
- bio: biografia de 2-3 frases
- persona: voz em primeira pessoa (1 parágrafo)
- interests: lista de 3-5 interesses
- mbti: um dos 16 tipos MBTI mais adequado
- topics: lista de 3-5 tópicos de especialidade
- speaking_style: descrição do estilo de fala (formal, casual, técnico, etc.)
- twitter_behavior: {
    post_frequency: "alta"|"media"|"baixa",
    content_types: ["opiniao", "compartilhamento", "pergunta", ...],
    interaction_style: "engajador"|"observador"|"influenciador"
  }
- reddit_behavior: {
    post_frequency: "alta"|"media"|"baixa",
    subreddits_preference: ["topicos relacionados"],
    comment_style: "analitico"|"humoristico"|"informativo"
  }
```

3. **Gere em paralelo** — use `parallel_count` para gerar múltiplos perfis simultaneamente
4. **Valide o JSON** — verifique se todos os campos obrigatórios estão presentes

### Fase 3: SALVAR — Exportar Perfis

| Formato | Uso | Estrutura |
|---------|-----|-----------|
| JSON | Reddit / uso geral | Lista de objetos completos |
| CSV | Twitter (requerido pelo OASIS) | Campos achatados |

## Melhorias em Relação ao Original

| Aspecto | Original (MiroFish-Offline) | Melhoria (OpenCode) |
|---------|----------------------------|---------------------|
| Fonte de dados | Neo4j graph_storage | SQLite code-graph.db + qualquer JSON |
| Paralelismo | Implementado | Usa Task Agent para paralelismo real |
| Validação | Básica (try/except) | Schema validation pós-geração |
| Extensibilidade | Apenas OASIS | Templates customizáveis por domínio |
| Fallback | Sem LLM → perfil vazio | Fallback com regras heurísticas |
| Rastreabilidade | Nenhuma | 🟡 INFERIDO / 🟢 CONFIRMADO por campo |

## Prompt Templates Customizáveis

Para domínios específicos, crie templates em `references/prompts/`:

- `default.md` — Template genérico (usado por padrão)
- `academic.md` — Para perfis acadêmicos/pesquisadores
- `corporate.md` — Para perfis corporativos/executivos
- `healthcare.md` — Para profissionais de saúde

## Exemplo de Uso

```bash
# Gerar perfis a partir de uma consulta GraphRAG
/oasis-profile --graph mirofish_abc123 --entities tipos:Person,Organization --parallel 5

# Gerar a partir de arquivo JSON
/oasis-profile --input entities.json --output profiles.json

# Gerar com template específico
/oasis-profile --graph mirofish_abc123 --template academic
```

## Referências

- Código original: `oasis_profile_generator.py` (MiroFish-Offline)
- Código original: `simulation_config_generator.py` (MiroFish-Offline)
- Estruturas de dados: `EntityNode`, `FilteredEntities` em `entity_reader.py`
- SKILL relacionada: `code-graphrag` (fonte de dados do grafo)
