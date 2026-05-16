"""
MASWOS V5 NEXUS — Servidor MCP Juridico (porta 3001)
60 agentes para documentacao juridica brasileira.
Uso: python juridico_server.py [--sse] [--port 3001]
"""

import sys, json, asyncio
from mcp.server import FastMCP

app = FastMCP("maswos-juridico", debug=False, log_level="INFO")


@app.tool()
def consultar_legislacao(termo: str, tipo: str = "federal") -> str:
    """Consulta base legislativa brasileira por termo. Dados simulados."""
    return json.dumps({
        "termo": termo,
        "tipo": tipo,
        "resultados": [
            {"lei": f"Lei {hash(termo) % 10000}/{(hash(tipo) % 50) + 1990}",
             "artigos": [f"Art. {i}" for i in range(1, 6)]}
        ],
        "nivel_confianca": "INFERIDO"
    }, ensure_ascii=False, indent=2)


@app.tool()
def validar_documento_juridico(texto: str, tipo_documento: str = "peticao") -> str:
    """Valida documento juridico quanto a estrutura e conformidade."""
    sections = [s.strip() for s in texto.replace("\r", "").split("\n\n") if s.strip()]
    return json.dumps({
        "tipo": tipo_documento,
        "secoes_encontradas": len(sections),
        "estrutura_ok": len(sections) >= 3,
        "sugestoes": [
            "Incluir fundamentacao legal" if len(sections) < 4 else "Estrutura adequada"
        ],
        "nivel_confianca": "INFERIDO"
    }, ensure_ascii=False, indent=2)


@app.tool()
def listar_modelos_juridicos(categoria: str = "trabalhista") -> str:
    """Lista modelos de documentos juridicos disponiveis."""
    modelos = {
        "trabalhista": ["Reclamacao Trabalhista", "Contestacao", "Recurso Ordinario"],
        "civil": ["Peticao Inicial", "Contestacao", "Apelacao"],
        "tributario": ["Embargos a Execucao Fiscal", "Mandado de Seguranca"],
    }
    return json.dumps({
        "categoria": categoria,
        "modelos": modelos.get(categoria, modelos["civil"]),
        "total": len(modelos.get(categoria, modelos["civil"]))
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    port = 3001
    for i, a in enumerate(sys.argv):
        if a == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    if "--sse" in sys.argv:
        srv = FastMCP("maswos-juridico-sse", port=port)
        srv._tool_manager = app._tool_manager
        print(f"Iniciando servidor SSE na porta {port}...", file=sys.stderr)
        asyncio.run(srv.run_sse_async())
    else:
        app.run()
