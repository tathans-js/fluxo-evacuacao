"""
Leitura, validação e execução de instâncias do problema de evacuação.

Formato de instância (JSON):

{
  "nome": "...", "descricao": "...", "fonte": "...",
  "geo": true,                      # true -> x = longitude, y = latitude
  "unidade": "veículos/h",
  "vertices": [ {"id": "n1", "x": -44.2, "y": -20.1, "rotulo": "...", "saida": false}, ... ],
  "arestas":  [ {"id": "e1", "u": "n1", "v": "n2", "capacidade": 1500,
                 "nome": "Rua X", "tipo": "secondary", "comprimento_m": 120.5,
                 "bloqueada": false}, ... ],
  "cenario": {"origens": ["n1", ...], "destinos": ["n9", ...],
              "veiculos": 3000, "zona": {"x": -44.2, "y": -20.1, "raio_m": 700}}
}

As arestas são DIRECIONADAS (uma rua de mão dupla aparece como duas arestas,
uma em cada sentido, cada uma com a capacidade daquele sentido).

Formato CSV aceito para importação rápida (uma aresta por linha):
    u,v,capacidade[,nome][,mao_dupla]
"""

import csv
import io
import json
import math
import os
import random

from .rede import RedeFluxo
from .ford_fulkerson import ford_fulkerson, verificar_fluxo, ESTRATEGIAS

PASTA_INSTANCIAS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "data", "instancias")

SUPER_ORIGEM = "S*"
SUPER_DESTINO = "T*"


class ErroInstancia(ValueError):
    pass


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------

def validar_instancia(inst):
    if not isinstance(inst, dict):
        raise ErroInstancia("a instância deve ser um objeto JSON")
    vertices = inst.get("vertices")
    arestas = inst.get("arestas")
    if not isinstance(vertices, list) or not vertices:
        raise ErroInstancia("a instância precisa de uma lista não vazia de 'vertices'")
    if not isinstance(arestas, list):
        raise ErroInstancia("a instância precisa de uma lista de 'arestas'")
    ids = set()
    for v in vertices:
        vid = str(v.get("id", ""))
        if not vid:
            raise ErroInstancia("vértice sem 'id'")
        if vid in ids:
            raise ErroInstancia(f"vértice duplicado: {vid}")
        if vid in (SUPER_ORIGEM, SUPER_DESTINO):
            raise ErroInstancia(f"'{vid}' é um id reservado")
        ids.add(vid)
        v["id"] = vid
        v.setdefault("x", 0.0)
        v.setdefault("y", 0.0)
    ids_arestas = set()
    for i, e in enumerate(arestas):
        e.setdefault("id", f"e{i}")
        e["id"] = str(e["id"])
        if e["id"] in ids_arestas:
            raise ErroInstancia(f"aresta duplicada: {e['id']}")
        ids_arestas.add(e["id"])
        e["u"], e["v"] = str(e.get("u")), str(e.get("v"))
        if e["u"] not in ids or e["v"] not in ids:
            raise ErroInstancia(f"aresta {e['id']} referencia vértice inexistente")
        try:
            cap = float(e.get("capacidade", 0))
        except (TypeError, ValueError):
            raise ErroInstancia(f"capacidade inválida na aresta {e['id']}")
        if cap < 0 or not math.isfinite(cap):
            raise ErroInstancia(f"capacidade negativa/inválida na aresta {e['id']}")
        if cap != int(cap):
            raise ErroInstancia(f"capacidade não inteira na aresta {e['id']} (use veículos/h inteiros)")
        e["capacidade"] = int(cap)
    inst.setdefault("cenario", {})
    inst.setdefault("nome", "sem nome")
    inst.setdefault("geo", False)
    inst.setdefault("unidade", "veículos/h")
    return inst


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------

def listar_instancias():
    itens = []
    for arq in sorted(os.listdir(PASTA_INSTANCIAS)):
        if arq.endswith(".json"):
            with open(os.path.join(PASTA_INSTANCIAS, arq), encoding="utf-8") as f:
                inst = json.load(f)
            itens.append({
                "arquivo": arq,
                "nome": inst.get("nome", arq),
                "descricao": inst.get("descricao", ""),
                "n_vertices": len(inst.get("vertices", [])),
                "n_arestas": len(inst.get("arestas", [])),
            })
    return itens


def carregar_instancia(arquivo):
    nome = os.path.basename(arquivo)            # evita acesso fora da pasta
    caminho = os.path.join(PASTA_INSTANCIAS, nome)
    if not os.path.isfile(caminho):
        raise ErroInstancia(f"instância não encontrada: {nome}")
    with open(caminho, encoding="utf-8") as f:
        return validar_instancia(json.load(f))


def instancia_de_texto(texto, formato):
    formato = (formato or "").lower()
    if formato == "json":
        try:
            return validar_instancia(json.loads(texto))
        except json.JSONDecodeError as ex:
            raise ErroInstancia(f"JSON inválido: {ex}")
    if formato == "csv":
        return instancia_de_csv(texto)
    raise ErroInstancia("formato deve ser 'json' ou 'csv'")


def instancia_de_csv(texto):
    leitor = csv.DictReader(io.StringIO(texto.strip()))
    if not leitor.fieldnames or not {"u", "v", "capacidade"} <= {c.strip() for c in leitor.fieldnames}:
        raise ErroInstancia("CSV precisa das colunas u,v,capacidade")
    vertices, arestas = {}, []
    for i, linha in enumerate(leitor):
        linha = {k.strip(): (val or "").strip() for k, val in linha.items() if k}
        u, v = linha["u"], linha["v"]
        for x in (u, v):
            vertices.setdefault(x, {"id": x})
        base = {"capacidade": linha["capacidade"], "nome": linha.get("nome", "")}
        arestas.append(dict(base, id=f"e{i}", u=u, v=v))
        if linha.get("mao_dupla", "").lower() in ("sim", "s", "1", "true", "yes"):
            arestas.append(dict(base, id=f"e{i}r", u=v, v=u))
    inst = {"nome": "Importada (CSV)", "geo": False,
            "vertices": list(vertices.values()), "arestas": arestas}
    layout_forca(inst)
    return validar_instancia(inst)


def layout_forca(inst, iteracoes=250, semente=1):
    """Layout de força (Fruchterman-Reingold simplificado) para instâncias sem coordenadas."""
    rnd = random.Random(semente)
    vs = inst["vertices"]
    n = len(vs)
    pos = {v["id"]: [rnd.random(), rnd.random()] for v in vs}
    if n > 400:                                  # grande demais: círculo
        for i, v in enumerate(vs):
            ang = 2 * math.pi * i / n
            v["x"], v["y"] = math.cos(ang), math.sin(ang)
        return
    k = math.sqrt(1.0 / max(n, 1))
    viz = [(e["u"], e["v"]) for e in inst["arestas"]]
    temp = 0.1
    for _ in range(iteracoes):
        desl = {i: [0.0, 0.0] for i in pos}
        ids = list(pos)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = ids[i], ids[j]
                dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
                d = math.hypot(dx, dy) or 1e-6
                f = k * k / d
                desl[a][0] += dx / d * f; desl[a][1] += dy / d * f
                desl[b][0] -= dx / d * f; desl[b][1] -= dy / d * f
        for a, b in viz:
            if a == b:
                continue
            dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
            d = math.hypot(dx, dy) or 1e-6
            f = d * d / k
            desl[a][0] -= dx / d * f; desl[a][1] -= dy / d * f
            desl[b][0] += dx / d * f; desl[b][1] += dy / d * f
        for i in pos:
            dx, dy = desl[i]
            d = math.hypot(dx, dy) or 1e-6
            pos[i][0] += dx / d * min(d, temp)
            pos[i][1] += dy / d * min(d, temp)
        temp *= 0.98
    for v in vs:
        v["x"], v["y"] = pos[v["id"]]


# ---------------------------------------------------------------------------
# Construção da rede e execução do algoritmo
# ---------------------------------------------------------------------------

def construir_rede(inst, origens, destinos):
    """
    Converte a instância em RedeFluxo. Com várias origens (todas as
    interseções da zona de risco) ou vários destinos (todas as saídas/abrigos),
    cria-se uma SUPER-ORIGEM S* ligada a cada origem e um SUPER-DESTINO T*
    ligado a cada destino, com capacidade "infinita" (maior que a soma de
    todas as capacidades). Isso reduz o problema multi-origem/multi-destino
    ao problema clássico de uma origem e um destino.
    """
    ids = [v["id"] for v in inst["vertices"]]
    indice = {vid: i for i, vid in enumerate(ids)}
    origens = [str(o) for o in origens]
    destinos = [str(d) for d in destinos]
    if not origens or not destinos:
        raise ErroInstancia("selecione ao menos uma origem e um destino")
    for x in origens + destinos:
        if x not in indice:
            raise ErroInstancia(f"vértice inexistente: {x}")
    comuns = set(origens) & set(destinos)
    if comuns:
        raise ErroInstancia(f"vértice não pode ser origem e destino ao mesmo tempo: {sorted(comuns)[:5]}")

    rede = RedeFluxo(len(ids))
    for e in inst["arestas"]:
        if e.get("bloqueada") or e["capacidade"] <= 0 or e["u"] == e["v"]:
            continue
        rede.adicionar_aresta(indice[e["u"]], indice[e["v"]], e["capacidade"], rotulo=e["id"])

    infinito = sum(e["capacidade"] for e in inst["arestas"]) + 1
    if len(origens) == 1:
        s = indice[origens[0]]
    else:
        s = rede.adicionar_vertice()
        for o in origens:
            rede.adicionar_aresta(s, indice[o], infinito, rotulo=None)
    if len(destinos) == 1:
        t = indice[destinos[0]]
    else:
        t = rede.adicionar_vertice()
        for d in destinos:
            rede.adicionar_aresta(indice[d], t, infinito, rotulo=None)

    nomes = ids + ([SUPER_ORIGEM] if len(origens) > 1 else []) + ([SUPER_DESTINO] if len(destinos) > 1 else [])
    return rede, s, t, nomes


def executar(inst, origens=None, destinos=None, estrategia="dfs", max_caminhos=5000):
    """Executa Ford-Fulkerson na instância e devolve um dicionário serializável em JSON."""
    validar_instancia(inst)
    cen = inst.get("cenario", {})
    origens = origens if origens is not None else cen.get("origens", [])
    destinos = destinos if destinos is not None else cen.get("destinos", [])
    if estrategia not in ESTRATEGIAS:
        raise ErroInstancia(f"estratégia deve ser uma de {ESTRATEGIAS}")

    rede, s, t, nomes = construir_rede(inst, origens, destinos)
    res = ford_fulkerson(rede, s, t, estrategia=estrategia)
    verif = verificar_fluxo(rede, s, t, res.valor)
    verif["corte_igual_fluxo"] = (res.capacidade_corte == res.valor)

    fluxo_arestas = {}
    for a, u, v, c, f in rede.arestas_diretas():
        rot = rede.rotulo_arco[a]
        if rot is not None and f > 0:
            fluxo_arestas[rot] = f

    caminhos = []
    for arcos, gargalo in res.caminhos[:max_caminhos]:
        passos = []
        vertices_cam = [nomes[rede.origem_arco[arcos[0]]]]
        for a in arcos:
            # sentido +1: usa a rua no sentido dela; -1: cancela fluxo (arco reverso residual)
            passos.append([rede.rotulo_arco[a], 1 if a % 2 == 0 else -1])
            vertices_cam.append(nomes[rede.destino_arco[a]])
        caminhos.append({"gargalo": gargalo, "arcos": passos, "vertices": vertices_cam})

    veiculos = cen.get("veiculos")
    tempo_evac = None
    if veiculos and res.valor > 0:
        tempo_evac = veiculos / res.valor * 60.0        # minutos (cota inferior teórica)

    return {
        "valor": res.valor,
        "estrategia": estrategia,
        "iteracoes": res.iteracoes,
        "tempo_ms": round(res.tempo_ms, 3),
        "n_vertices": rede.n,
        "n_arcos": rede.n_arestas,
        "super_origem": len(origens) > 1,
        "super_destino": len(destinos) > 1,
        "fluxo_arestas": fluxo_arestas,
        "caminhos": caminhos,
        "caminhos_omitidos": max(0, len(res.caminhos) - max_caminhos),
        "corte": [rede.rotulo_arco[a] for a in res.arcos_corte if rede.rotulo_arco[a] is not None],
        "capacidade_corte": res.capacidade_corte,
        "lado_s": [nomes[v] for v in res.lado_s if v < len(inst["vertices"])],
        "verificacao": verif,
        "veiculos": veiculos,
        "tempo_evacuacao_min": round(tempo_evac, 1) if tempo_evac else None,
    }
