"""
/api/agents — list agents with their current model assignment.

Reads frontmatter from agents/*.md (and other configured directories).
Returns JSON list with: name, category, model, is_default, path.

Filters via query params:
  ?category=<cat>    — exact match on category
  ?model=<model>     — exact match on declared model (use "default" for none)
  ?overridden=true   — only agents with declared model
  ?q=<substring>     — case-insensitive substring match on name
"""

import re
from pathlib import Path
from urllib.parse import parse_qs
from typing import Iterable

WORKSPACE = Path(__file__).parent.parent.parent.resolve()

# Diretórios que contêm agentes. Adicionar conforme o ecossistema crescer.
AGENT_DIRS = [
    WORKSPACE / "agents",
    # WORKSPACE / "criador-artigo" / "agents",   # descomentar se houver agentes aqui
]


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extracts simple key: value pairs from YAML frontmatter."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end].strip()
    out = {}
    for line in block.splitlines():
        line = line.rstrip()
        # Ignora linhas que começam com espaço (subkeys YAML) e comentários
        if not line or line.startswith(" ") or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"\'')
    return out


def _infer_category(file_path: Path, fm: dict) -> str:
    """
    Determines category. Priority:
    1. frontmatter 'category' field
    2. parent directory name (if not 'agents')
    3. heuristic from filename
    """
    if "category" in fm:
        return fm["category"]
    parent = file_path.parent.name
    if parent != "agents":
        return parent
    name = file_path.stem.lower()
    if "reversa" in name:
        return "reversa"
    if "review" in name or "revisor" in name:
        return "review"
    if "orientad" in name:
        return "orientador"
    if "seek" in name:
        return "seeker"
    if "code" in name or "debug" in name:
        return "code"
    if "doc" in name or "writer" in name:
        return "docs"
    if "linguist" in name or "corretor" in name:
        return "corrector"
    if "quantum" in name:
        return "quantum"
    if "antigravity" in name:
        return "antigravity"
    return "core"


def _list_agents() -> Iterable[dict]:
    for adir in AGENT_DIRS:
        if not adir.is_dir():
            continue
        for f in sorted(adir.glob("*.md")):
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            fm = _parse_frontmatter(text)
            name = fm.get("name", f.stem)
            model = fm.get("model", "").strip() or None
            yield {
                "name": name,
                "category": _infer_category(f, fm),
                "model": model,                          # None when not declared
                "is_default": model is None,             # True if uses opencode.json global
                "path": str(f.relative_to(WORKSPACE)),
                "description": fm.get("description", "")[:200],
            }


def handle_agents(self, method, parsed, body):
    if method != "GET":
        return 405, {"error": "Method Not Allowed", "allowed": ["GET"]}, "application/json"

    # Parse query string
    qs = parse_qs(parsed.query or "")
    category = qs.get("category", [None])[0]
    model_filter = qs.get("model", [None])[0]
    overridden = qs.get("overridden", [None])[0] == "true"
    q = (qs.get("q", [""])[0] or "").lower().strip()

    items = list(_list_agents())

    if category:
        items = [i for i in items if i["category"] == category]
    if model_filter:
        if model_filter == "default":
            items = [i for i in items if i["is_default"]]
        else:
            items = [i for i in items if i["model"] == model_filter]
    if overridden:
        items = [i for i in items if not i["is_default"]]
    if q:
        items = [i for i in items if q in i["name"].lower()]

    # Categories distribuídas (para popular o filtro do frontend sem 2ª chamada)
    cats = sorted(set(_infer_category(Path(i["path"]), {"category": i["category"]}) for i in _list_agents()))

    return 200, {
        "total": len(items),
        "items": items,
        "facets": {
            "categories": cats,
        },
    }, "application/json"
