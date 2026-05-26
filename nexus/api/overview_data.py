"""
GET /api/dados — overview data endpoint restored after PR-6 refactor.

Delegates to coletar_dados() from dashboard_server.py to return live
ecosystem metrics. Compatible with the shape that index.html line ~183
(fetch('/api/dados')) expects, so the Overview page refreshes live.
"""

import importlib.util
from pathlib import Path

_WORKSPACE = Path(__file__).parent.parent.parent.resolve()


def _load_coletar_dados():
    """Lazy-load coletar_dados() from dashboard_server.py via importlib.

    Avoids circular import — dashboard_server.py loads this module at
    registration time; this module needs coletar_dados() defined there.
    """
    server_path = _WORKSPACE / "nexus" / "dashboard_server.py"
    spec = importlib.util.spec_from_file_location("dashboard_server_local", str(server_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.coletar_dados


def handle_dados(self, method, parsed, body):
    if method != "GET":
        return 405, {"error": "Method Not Allowed", "allowed": ["GET"]}, "application/json"

    try:
        coletar = _load_coletar_dados()
        data = coletar()
    except Exception as e:
        return 500, {"error": f"Failed to collect overview data: {e}"}, "application/json"

    return 200, data, "application/json"
