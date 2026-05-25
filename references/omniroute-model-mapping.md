# OmniRoute — Model Mapping Reference

> Guia canônico de quais modelos OmniRoute usar para quais grupos de agentes do OpenCode Ecosystem. Consultado por novas PRs que especializam agentes adicionais.

## Convenções

- IDs no formato `omniroute/<model-id>` referem-se ao plugin `@omniroute/opencode-plugin` configurado conforme `opencode.omniroute.json.example`.
- IDs no formato `omniroute/<combo-slug>` (ex: `omniroute/auto`, `omniroute/claude-primary`) referem-se a **combos** — políticas de roteamento que escolhem o modelo em runtime.
- Se o cliente não tiver OmniRoute ativo, o OpenCode CLI cai no default global (`opencode/big-pickle`). Não há crash.

## Matriz canônica por grupo

| Grupo | Quant. estimada | Modelo recomendado | Justificativa | Status (2026-05-25) |
|---|:---:|---|---|:---:|
| **Core orchestrators** | 10 | `omniroute/auto` ou `omniroute/claude-primary` | Decisão complexa, vale combo com fallback | pendente |
| **Code/debug** | 12 | `omniroute/claude-sonnet-4-6` | Coding-grade balance de custo/qualidade | pendente |
| **Docs/writing** | 6 | `omniroute/gemini-2.5-pro` | Long-form, contexto 1M | pendente |
| **Reversa** | 9 | `omniroute/auto` | Pipeline sequencial, robustez > velocidade | pendente |
| **SEEKER** | 12 | `omniroute/gemini-2.5-flash` ou `omniroute/groq-llama-3.3` | Busca rápida e barata | pendente |
| **MASWOS criação** | 49 | `opencode/big-pickle` (preserva default) | Contexto 200K, gratuito, igual hoje | preservado |
| **Banca revisores** | 5 | `omniroute/claude-opus-4-7` | Rigor de revisão acadêmica | **PR-2 (este)** |
| **Orientadores doutores** | 4 | `omniroute/claude-opus-4-7` | Feedback PhD-grade | **PR-2 (este)** |
| **`linguistic-corrector`** | 1 | `omniroute/gemini-2.5-flash-lite` | Tarefa trivial (busca-e-substituição CJK) | pendente |
| **Quantum (VQC)** | 1 | `omniroute/o1` ou `omniroute/claude-opus-4-7-thinking` | Reasoning científico | pendente |
| **Antigravity bridge** | 1 | (default — gerenciado pelo plugin antigravity) | Plugin tem seu próprio modelo | preservado |

## Modelos em uso por PR-2 (escopo atual)

| Arquivo | Modelo atribuído | Papel |
|---|---|---|
| `agents/code-reviewer.md` | `omniroute/claude-opus-4-7` | reviewer |
| `agents/reviewer.md` | `omniroute/claude-opus-4-7` | reviewer |
| `agents/reversa-reviewer.md` | `omniroute/claude-opus-4-7` | reviewer |
| `agents/ws-reviewer.md` | `omniroute/claude-opus-4-7` | reviewer |
| `agents/security-auditor.md` | `omniroute/claude-opus-4-7` | reviewer |
| `agents/architect.md` | `omniroute/claude-opus-4-7` | orientador |
| `agents/architecture-analyzer.md` | `omniroute/claude-opus-4-7` | orientador |
| `agents/adr-manager.md` | `omniroute/claude-opus-4-7` | orientador |
| `agents/contract-manager.md` | `omniroute/claude-opus-4-7` | orientador |

> **Como alguém adiciona um agente novo nesta tabela:** abrir PR seguindo o mesmo padrão da PR-2 (frontmatter `model:` + entry nesta tabela). Não é necessário editar `opencode.json` raiz nem outros plugins.

## Fallback ladder (auto-resolve)

Quando o agente declara `omniroute/claude-opus-4-7` e a chamada falha (rate-limit, circuit breaker open, contexto excedido), o OmniRoute aplica a seguinte cascata automaticamente via Auto-Combo:

```
1.  claude-opus-4-7        (Anthropic, OAuth Pro)
 ↓ (rate-limit ou breaker open)
2.  claude-opus-4-7        (Anthropic, API-key)
 ↓
3.  claude-sonnet-4-6      (Anthropic, API-key)
 ↓
4.  gpt-5                  (OpenAI, OAuth Codex Pro)
 ↓
5.  gemini-2.5-pro         (Google AI Studio free tier)
 ↓
6.  opencode/big-pickle    (last-resort, mantém o ecossistema vivo)
```

O agente não precisa configurar nada — a cascata é interna ao gateway.

## Free-tier preservation

Se o usuário quer **garantir custo zero**, declarar combo `omniroute/auto-free` em vez de `omniroute/auto`. Este combo restringe a escolha aos provedores free-tier:

- Gemini AI Studio (free daily quota)
- GLM Free
- Groq
- Cerebras
- Pollinations AI
- Ollama Cloud
- OpenCode Zen (`big-pickle`)

Trade-off: latência maior nos picos (free-tier rate-limit mais agressivo), qualidade ligeiramente menor que combos pagos.

## Referências externas

- OmniRoute provider reference: https://github.com/diegosouzapw/OmniRoute/blob/main/docs/reference/PROVIDER_REFERENCE.md
- OmniRoute Auto-Combo scoring: https://github.com/diegosouzapw/OmniRoute/blob/main/docs/routing/AUTO-COMBO.md
- OmniRoute Resilience guide: https://github.com/diegosouzapw/OmniRoute/blob/main/docs/architecture/RESILIENCE_GUIDE.md
- `@omniroute/opencode-plugin`: https://github.com/diegosouzapw/OmniRoute/tree/main/@omniroute/opencode-plugin
