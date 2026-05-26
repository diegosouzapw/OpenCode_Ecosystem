"""
core/command_registry.py — Bridge Python para o sistema de Comandos TypeScript.

Lê metadados dos comandos em command/*.md e registra no Container DI.
Serve como ponte entre o ecossistema TypeScript (OpenCode) e Python (core).
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Allowlist for command names derived from filesystem stems.
# Prevents path-traversal-shaped strings from ever appearing in trigger lists.
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


@dataclass
class CommandMeta:
    """Metadados de um comando OpenCode."""
    name: str
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    source_file: str = ""
    requires_new_session: bool = False


# Mapa de triggers espelhado do dispatcher.ts
TRIGGER_MAP: dict[str, list[str]] = {
    "auto": ["/auto", "auto", "autonomous"],
    "commit": ["/commit", "commit"],
    "devcontainer": ["/devcontainer", "devcontainer"],
    "evolve": ["/evolve", "evolve", "evolution"],
    "execute": ["/execute", "execute"],
    "plan": ["/plan", "plan"],
    "quantum": ["/quantum", "quantum"],
    "research": ["/research", "research"],
    "reversa": ["/reversa", "reversa", "reverse engineering", "iniciar análise", "engenharia reversa"],
    "route": ["/route", "/r", "/combo", "route", "combo"],
    "review": ["/review", "review"],
    "ticket": ["/ticket", "ticket"],
    "workspaces": ["/workspaces", "workspaces"],
    "worktree": ["/worktree", "worktree"],
    "ws-review": ["/ws-review", "ws-review", "ws review"],
}

NEW_SESSION_COMMANDS = {"plan", "research", "execute"}


class CommandRegistry:
    """Registry de comandos lidos de command/*.md.

    Pode ser resolvido via Container DI:
        container = Container.instance()
        registry = container.resolve('command_registry')
        cmd = registry.find('reversa')
    """

    def __init__(self, command_dir: Optional[str | Path] = None, container: Any = None) -> None:
        self._commands: dict[str, CommandMeta] = {}
        self._trigger_index: dict[str, str] = {}
        self._loaded = False
        self._container = container

        # Auto-registro no Container DI
        if container is not None and not container.is_registered('command_registry'):
            container.register('command_registry', self)

        # Se command_dir for fornecido, carrega imediatamente
        if command_dir:
            self.load(command_dir)

    @classmethod
    def from_container(cls, container: Any, command_dir: Optional[str | Path] = None) -> 'CommandRegistry':
        """Factory para criar CommandRegistry a partir do Container."""
        return cls(command_dir=command_dir, container=container)

    def load(self, command_dir: str | Path) -> list[CommandMeta]:
        """Carrega comandos do diretório command/.

        Lê arquivos .md e extrai frontmatter (description).
        """
        cmd_path = Path(command_dir)
        if not cmd_path.exists() or not cmd_path.is_dir():
            logger.warning("Command directory not found: %s", cmd_path)
            return []

        md_files = sorted(cmd_path.glob("*.md"))
        loaded: list[CommandMeta] = []

        for md_file in md_files:
            name = md_file.stem
            if not _SAFE_NAME_RE.match(name):
                logger.warning("Skipping command file with unsafe name: %s", md_file.name)
                continue
            description = self._parse_frontmatter_description(md_file)
            triggers = TRIGGER_MAP.get(name, [f"/{name}", name])

            meta = CommandMeta(
                name=name,
                description=description or f"Comando /{name}",
                triggers=triggers,
                source_file=str(md_file),
                requires_new_session=name in NEW_SESSION_COMMANDS,
            )
            self._commands[name] = meta
            for trigger in triggers:
                self._trigger_index[trigger.lower()] = name
            loaded.append(meta)

        self._loaded = True
        logger.info("Loaded %d commands from %s", len(loaded), cmd_path)
        return loaded

    def find(self, input_text: str) -> Optional[CommandMeta]:
        """Encontra comando por nome ou trigger."""
        if not self._loaded:
            return None

        normalized = input_text.lower().strip()

        # Trigger exato
        cmd_name = self._trigger_index.get(normalized)
        if cmd_name:
            return self._commands.get(cmd_name)

        # Fuzzy: input contém trigger ou vice-versa
        for trigger, name in self._trigger_index.items():
            if normalized in trigger or trigger in normalized:
                return self._commands.get(name)

        return None

    def get(self, name: str) -> Optional[CommandMeta]:
        """Obtém comando pelo nome."""
        return self._commands.get(name)

    def list(self) -> list[CommandMeta]:
        """Lista todos os comandos."""
        return list(self._commands.values())

    @property
    def count(self) -> int:
        return len(self._commands)

    @property
    def names(self) -> list[str]:
        return sorted(self._commands.keys())

    def summary(self) -> dict[str, Any]:
        """Resumo para reports de sincronia."""
        return {
            "total": self.count,
            "names": self.names,
            "loaded": self._loaded,
            "triggers_count": len(self._trigger_index),
            "new_session": list(NEW_SESSION_COMMANDS & set(self.names)),
        }

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _parse_frontmatter_description(md_file: Path) -> str:
        """Extrai 'description' do frontmatter YAML do .md."""
        try:
            content = md_file.read_text(encoding="utf-8", errors="ignore")
            # Frontmatter: ---\n...\n---
            match = re.search(r'^---\n([\s\S]*?)\n---', content)
            if not match:
                return ""
            for line in match.group(1).split("\n"):
                idx = line.index(": ") if ": " in line else -1
                if idx > 0 and line[:idx].strip() == "description":
                    return line[idx + 2:].strip()
        except Exception as e:
            logger.debug("Error parsing frontmatter from %s: %s", md_file, e)
        return ""


def route_command_handler(args: list[str]) -> dict[str, Any]:
    """
    /route slash command handler.

    Sets OMNIROUTE_COMBO env var for the current OpenCode session,
    selecting the routing strategy for subsequent pipeline calls.

    Args:
        args: list of CLI args.
            - empty / ["--list"]: print current + available combos
            - ["none"]: clear OMNIROUTE_COMBO
            - [<slug>]: activate combo if slug is in
              ECOSYSTEM_OMNIROUTE_COMBO_SLUGS (CSV from ecosystem-sync v3.6)
              or in built-in slugs.

    Returns:
        dict with:
            - success: bool
            - message: str (user-facing)
            - env_updates: dict[str, str | None] (None to unset)
    """
    base_url = os.environ.get("OMNIROUTE_BASE_URL", "").strip()
    if not base_url:
        return {
            "success": False,
            "message": (
                "OmniRoute not active. Set OMNIROUTE_BASE_URL and apply "
                "opencode.omniroute.json.example (see GETTING_STARTED.md §5)."
            ),
            "env_updates": {},
        }

    known_csv = os.environ.get("ECOSYSTEM_OMNIROUTE_COMBO_SLUGS", "").strip()
    known_slugs = [s.strip() for s in known_csv.split(",") if s.strip()]
    builtin_slugs = ["auto", "auto-free", "none"]
    valid_slugs = sorted(set(known_slugs) | set(builtin_slugs))

    current = os.environ.get("OMNIROUTE_COMBO", "").strip() or "(not set)"

    if not args or args[0] == "--list":
        lines = [
            f"Current combo: {current}",
            f"OmniRoute tenant: {base_url}",
            "",
            "Available combos:",
            *[f"  - {s}" for s in valid_slugs],
            "",
            "Usage: /route <slug>  |  /route none  |  /route --list",
        ]
        return {
            "success": True,
            "message": "\n".join(lines),
            "env_updates": {},
        }

    slug = args[0].strip()

    if slug == "none":
        return {
            "success": True,
            "message": "OMNIROUTE_COMBO cleared. Subsequent calls use direct model routing.",
            "env_updates": {"OMNIROUTE_COMBO": None},  # None = unset
        }

    if slug not in valid_slugs:
        return {
            "success": False,
            "message": (
                f"Unknown combo '{slug}'.\n"
                f"Available: {', '.join(valid_slugs)}\n"
                f"Run /route --list for details."
            ),
            "env_updates": {},
        }

    return {
        "success": True,
        "message": f"Active combo: {slug}\n(applies to subsequent /artigo, /reversa, /quantum, etc.)",
        "env_updates": {"OMNIROUTE_COMBO": slug},
    }


def discover_command_dir(base_dir: Optional[str | Path] = None) -> Path:
    """Descobre o diretório command/ a partir de um base_dir."""
    base = Path(base_dir) if base_dir else Path.cwd()
    candidates = [
        base / "command",
        base / "commands",
        Path.cwd() / "command",
        Path.cwd() / "commands",
    ]
    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    return base / "command"
