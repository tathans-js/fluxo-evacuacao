"""
Servidor HTTP da aplicação (somente biblioteca padrão do Python).

Serve a interface web (pasta web/) e uma API JSON:

  GET  /api/instancias               -> lista instâncias disponíveis
  GET  /api/instancias/<arquivo>     -> conteúdo de uma instância
  POST /api/gerar      {linhas, colunas, semente, ...}          -> instância sintética
  POST /api/importar   {formato: "json"|"csv", texto}           -> instância validada
  POST /api/executar   {instancia, origens, destinos, estrategia} -> resultado do Ford-Fulkerson
  POST /api/comparar   {instancia, origens, destinos}           -> DFS x BFS lado a lado

O algoritmo roda no servidor (Python, fluxo/ford_fulkerson.py);
a interface apenas desenha a rede e os resultados.
"""

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .gerador import gerar_cidade
from .instancias import (ErroInstancia, carregar_instancia, executar,
                         instancia_de_texto, listar_instancias)

PASTA_WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
LIMITE_CORPO = 30 * 1024 * 1024


class Manipulador(BaseHTTPRequestHandler):
    server_version = "FluxoEvacuacao/1.0"

    def log_message(self, fmt, *args):  # log enxuto no terminal
        print("[http]", self.address_string(), fmt % args)

    # ---------------- respostas ----------------
    def _json(self, obj, status=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _erro(self, msg, status=400):
        self._json({"erro": msg}, status)

    def _ler_json(self):
        tam = int(self.headers.get("Content-Length", 0))
        if tam > LIMITE_CORPO:
            raise ErroInstancia("requisição grande demais")
        try:
            return json.loads(self.rfile.read(tam) or b"{}")
        except json.JSONDecodeError:
            raise ErroInstancia("corpo da requisição não é JSON válido")

    # ---------------- GET ----------------
    def do_GET(self):
        caminho = self.path.split("?", 1)[0]
        try:
            if caminho == "/api/instancias":
                return self._json(listar_instancias())
            if caminho.startswith("/api/instancias/"):
                return self._json(carregar_instancia(caminho[len("/api/instancias/"):]))
        except ErroInstancia as ex:
            return self._erro(str(ex), 404)
        return self._arquivo_estatico(caminho)

    def _arquivo_estatico(self, caminho):
        if caminho == "/":
            caminho = "/index.html"
        alvo = os.path.normpath(os.path.join(PASTA_WEB, caminho.lstrip("/")))
        if not alvo.startswith(PASTA_WEB) or not os.path.isfile(alvo):
            return self._erro("não encontrado", 404)
        tipo = mimetypes.guess_type(alvo)[0] or "application/octet-stream"
        with open(alvo, "rb") as f:
            corpo = f.read()
        self.send_response(200)
        self.send_header("Content-Type", tipo + ("; charset=utf-8" if tipo.startswith("text") or tipo.endswith("javascript") else ""))
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(corpo)

    # ---------------- POST ----------------
    def do_POST(self):
        try:
            corpo = self._ler_json()
            if self.path == "/api/gerar":
                return self._json(gerar_cidade(
                    linhas=int(corpo.get("linhas", 20)), colunas=int(corpo.get("colunas", 20)),
                    semente=int(corpo.get("semente", 42)),
                    prob_mao_unica=float(corpo.get("prob_mao_unica", 0.3)),
                    prob_remocao=float(corpo.get("prob_remocao", 0.08)),
                    raio_zona=float(corpo.get("raio_zona", 0.2)),
                    veiculos=int(corpo.get("veiculos", 5000))))
            if self.path == "/api/importar":
                return self._json(instancia_de_texto(corpo.get("texto", ""), corpo.get("formato")))
            if self.path == "/api/executar":
                return self._json(executar(corpo["instancia"], corpo.get("origens"),
                                           corpo.get("destinos"), corpo.get("estrategia", "dfs")))
            if self.path == "/api/comparar":
                saida = {}
                for est in ("dfs", "bfs"):
                    r = executar(corpo["instancia"], corpo.get("origens"), corpo.get("destinos"), est)
                    comp = [len(c["arcos"]) for c in r["caminhos"]]
                    saida[est] = {"valor": r["valor"], "iteracoes": r["iteracoes"], "tempo_ms": r["tempo_ms"],
                                  "comprimento_medio": round(sum(comp) / len(comp), 1) if comp else 0,
                                  "maior_gargalo": max((c["gargalo"] for c in r["caminhos"]), default=0),
                                  "menor_gargalo": min((c["gargalo"] for c in r["caminhos"]), default=0)}
                return self._json(saida)
            return self._erro("rota inexistente", 404)
        except (ErroInstancia, ValueError, KeyError, TypeError) as ex:
            return self._erro(str(ex))


def iniciar(porta=8000, host="127.0.0.1"):
    servidor = ThreadingHTTPServer((host, porta), Manipulador)
    return servidor
