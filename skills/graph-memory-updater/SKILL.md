---
name: graph-memory-updater
description: >
  Atualização em tempo real de grafos com atividades de agentes em simulação.
  Inspirado pelo GraphMemoryUpdater do MiroFish-Offline, monitora logs de
  ações de agentes (postar, curtir, comentar, seguir) e envia para o grafo
  em lotes com buffer por plataforma. Use quando precisar registrar atividades
  de simulação em um grafo de conhecimento em tempo real.
license: MIT
compatibility: opencode
allowed-tools: Read, Grep, Glob, Bash, Write, Sqlite
metadata:
  author: Reversa Engine (padrão MiroFish-Offline graph_memory_updater.py)
  version: "1.0.0"
  domain: pipeline
  triggers: memory, memória, update, atualizar, activity, atividade, agente, simulação
  role: pipeline
  scope: realtime
  output-format: json
  related-skills: graph-builder-pipeline, entity-ner-reader, code-graphrag, machine-states
  inspired-by: MiroFish-Offline GraphMemoryUpdater (graph_memory_updater.py)
---

# Graph Memory Updater — Atualização de Grafos em Tempo Real

Inspirado pelo **GraphMemoryUpdater** do MiroFish-Offline (`graph_memory_updater.py`).
Serviço que monitora ações de agentes em simulações sociais e as converte
em atualizações de grafo em tempo real, com buffer por plataforma e
processamento em lote.

## Arquitetura

```
Simulação → AgentActivity → Queue
  → Buffer por Plataforma (twitter/reddit)
    → Batch (5 atividades) → to_episode_text() → add_text() → Grafo
      → NER extrai entidades + relações da descrição textual
```

## Componentes

### AgentActivity
Dataclass representando uma ação de agente:
- `platform`: twitter / reddit
- `agent_id`, `agent_name`
- `action_type`: CREATE_POST, LIKE_POST, REPOST, FOLLOW, etc.
- `action_args` + `round_num` + `timestamp`

### to_episode_text()
Converte cada atividade em texto narrativo natural:
```
"Carlos: Posted a post: "A regulação de IA é necessária""
"Maria: Liked Carlos's post: "A regulação de IA é necessária""
"João: Followed user "Carlos""
```

### GraphMemoryUpdater
Serviço principal:
- Fila interna (`Queue`) + buffers por plataforma
- Worker thread com batch size configurável (padrão: 5)
- Retry com backoff (3 tentativas)
- Métricas: total_activities, batches_sent, failed_count, skipped_count
- Ações DO_NOTHING são automaticamente ignoradas

### GraphMemoryManager
Gerenciador de múltiplos updaters (um por simulação):
- `create_updater(simulation_id, graph_id, storage)`
- `stop_updater(simulation_id)`
- `stop_all()` — cleanup global
- `get_all_stats()` — métricas de todas as simulações

## Ações Suportadas

| Ação | Descrição | Template |
|------|-----------|----------|
| `CREATE_POST` | Publicar post | "Posted: {content}" |
| `LIKE_POST` | Curtir post | "Liked {author}'s post: {content}" |
| `DISLIKE_POST` | Rejeitar post | "Disliked {author}'s post: {content}" |
| `REPOST` | Repostar | "Reposted {author}'s post: {content}" |
| `QUOTE_POST` | Citar com comentário | "Quoted {author}'s post, commented: {comment}" |
| `FOLLOW` | Seguir usuário | "Followed user {name}" |
| `CREATE_COMMENT` | Comentar | "Commented on {author}'s post: {content}" |
| `LIKE_COMMENT` | Curtir comentário | "Liked {author}'s comment: {content}" |
| `SEARCH_POSTS` | Buscar posts | "Searched for {query}" |
| `SEARCH_USER` | Buscar usuário | "Searched for user {name}" |
| `MUTE` | Silenciar | "Muted user {name}" |
| `DO_NOTHING` | Ignorado | — |

## Quando Usar

| Cenário | Descrição |
|---------|-----------|
| Simulação ao vivo | "Registre as ações dos agentes em tempo real no grafo" |
| Log de atividades | "Converta logs de simulação em entidades do grafo" |
| Múltiplas plataformas | "Buffer por plataforma com processamento em lote" |
| Rastreabilidade | "Mantenha histórico de ações dos agentes" |
| Análise pós-simulação | "Consulte o grafo para entender interações" |

## Workflow

### Iniciar Monitoramento

```
python scripts/memory_updater.py start --graph <graph_id>
```

1. Cria GraphMemoryUpdater com buffer vazio
2. Inicia worker thread em background
3. Aceita atividades via add_activity()

### Adicionar Atividade

```python
activity = AgentActivity(
    platform="twitter",
    agent_id=1,
    agent_name="Carlos",
    action_type="CREATE_POST",
    action_args={"content": "A regulação de IA é necessária"},
    round_num=5,
    timestamp="2026-05-17T12:00:00Z"
)
updater.add_activity(activity)
```

### Parar e Flush

```
python scripts/memory_updater.py stop --simulation <sim_id>
```

- Envia atividades restantes na queue e buffers
- Para a worker thread
- Loga estatísticas finais

## Escala de Confiança

- 🟢 **CONFIRMADO** — Atividade registrada e enviada ao grafo com sucesso
- 🟡 **INFERIDO** — Descrição textual da ação (pode perder nuances)
- 🔴 **LACUNA** — Atividade que falhou após todas as retentativas

## Regras

### MUST DO
- Usar buffer por plataforma (twitter/reddit independentes)
- Batch size mínimo de 5 atividades antes de enviar
- Retry com backoff exponencial (até 3 tentativas)
- Ignorar DO_NOTHING (não poluir o grafo)
- Fornecer métricas detalhadas (enviados, falhas, ignorados)

### MUST NOT DO
- Enviar atividades uma a uma (ineficiente para o grafo)
- Bloquear a simulação enquanto envia (thread separada)
- Perder atividades ao parar (flush obrigatório)
- Ignorar falhas de rede sem retry
- Permitir que updaters órfãos consumam memória
