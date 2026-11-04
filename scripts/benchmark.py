"""
Experimentos de desempenho do Ford-Fulkerson (DFS) x Edmonds-Karp (BFS).

Gera em docs/resultados/:
  escala.csv / escala.svg          tempo e iterações vs. tamanho da cidade sintética
  capacidade.csv / capacidade.svg  iterações vs. faixa de capacidades (mesmo grafo)
  reais.csv                        resultados nas instâncias do repositório

Uso:  python3 scripts/benchmark.py [--rapido]
"""

import csv
import os
import random
import statistics
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from fluxo.gerador import gerar_cidade  # noqa: E402
from fluxo.instancias import construir_rede, carregar_instancia, executar, listar_instancias  # noqa: E402
from fluxo.ford_fulkerson import ford_fulkerson  # noqa: E402

SAIDA = os.path.join(RAIZ, "docs", "resultados")
CORES = {"dfs": "#d95f02", "bfs": "#1b9e77"}


def medir(inst, estrategia, repeticoes=3):
    tempos, res = [], None
    for _ in range(repeticoes):
        rede, s, t, _ = construir_rede(inst, inst["cenario"]["origens"], inst["cenario"]["destinos"])
        ini = time.perf_counter()
        res = ford_fulkerson(rede, s, t, estrategia, registrar_caminhos=False)
        tempos.append((time.perf_counter() - ini) * 1000)
    return res, statistics.median(tempos), rede


def grafico_svg(caminho, titulo, rotulo_x, rotulo_y, series, log_x=False, log_y=False):
    """Gráfico de linhas simples em SVG (sem dependências)."""
    import math
    W, H, ml, mr, mt, mb = 640, 380, 70, 20, 40, 55
    xs = [x for _, pts in series for x, _ in pts]
    ys = [y for _, pts in series for _, y in pts]
    fx = (lambda v: math.log10(v)) if log_x else (lambda v: v)
    fy = (lambda v: math.log10(max(v, 1e-3))) if log_y else (lambda v: v)
    x0, x1 = fx(min(xs)), fx(max(xs))
    y0, y1 = (fy(min(ys)), fy(max(ys))) if log_y else (0, max(ys) * 1.08)
    if x1 == x0: x1 += 1
    if y1 == y0: y1 += 1
    px = lambda v: ml + (fx(v) - x0) / (x1 - x0) * (W - ml - mr)
    py = lambda v: H - mb - (fy(v) - y0) / (y1 - y0) * (H - mt - mb)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Helvetica,Arial,sans-serif" font-size="12">',
           f'<rect width="{W}" height="{H}" fill="white"/>',
           f'<text x="{W/2}" y="22" text-anchor="middle" font-size="14" font-weight="bold">{titulo}</text>']
    # grade e eixos
    for i in range(6):
        yv = y0 + (y1 - y0) * i / 5
        yy = H - mb - (yv - y0) / (y1 - y0) * (H - mt - mb)
        lab = f"{10 ** yv:,.0f}" if log_y else f"{yv:,.0f}"
        out.append(f'<line x1="{ml}" x2="{W-mr}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#e5e5e5"/>')
        out.append(f'<text x="{ml-6}" y="{yy+4:.1f}" text-anchor="end" fill="#555">{lab.replace(",", ".")}</text>')
    for x in sorted(set(xs)):
        xx = px(x)
        lab = f"{x:,.0f}".replace(",", ".")
        out.append(f'<text x="{xx:.1f}" y="{H-mb+16}" text-anchor="middle" fill="#555">{lab}</text>')
    out.append(f'<line x1="{ml}" x2="{W-mr}" y1="{H-mb}" y2="{H-mb}" stroke="#333"/>')
    out.append(f'<line x1="{ml}" x2="{ml}" y1="{mt}" y2="{H-mb}" stroke="#333"/>')
    out.append(f'<text x="{(ml+W-mr)/2}" y="{H-12}" text-anchor="middle">{rotulo_x}</text>')
    out.append(f'<text x="16" y="{(mt+H-mb)/2}" text-anchor="middle" transform="rotate(-90 16 {(mt+H-mb)/2})">{rotulo_y}</text>')
    for k, (nome, pts) in enumerate(series):
        cor = CORES.get(nome.split()[0].lower(), "#555")
        d = " ".join(f"{'M' if i == 0 else 'L'}{px(x):.1f},{py(y):.1f}" for i, (x, y) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="{cor}" stroke-width="2.2"/>')
        for x, y in pts:
            out.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="3.2" fill="{cor}"/>')
        out.append(f'<rect x="{ml+14}" y="{mt+8+k*18}" width="14" height="4" fill="{cor}"/>'
                   f'<text x="{ml+34}" y="{mt+13+k*18}">{nome}</text>')
    out.append("</svg>")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def experimento_escala(tamanhos):
    linhas = []
    for n in tamanhos:
        inst = gerar_cidade(n, n, semente=11, veiculos=10000)
        for est in ("dfs", "bfs"):
            res, ms, rede = medir(inst, est, 3 if n <= 60 else 1)
            linhas.append({"lado": n, "vertices": len(inst["vertices"]), "arestas": len(inst["arestas"]),
                           "estrategia": est, "fluxo": res.valor, "iteracoes": res.iteracoes, "tempo_ms": round(ms, 2)})
            print("escala", linhas[-1])
    return linhas


def experimento_capacidade(faixas, lado=15):
    base = gerar_cidade(lado, lado, semente=5)
    linhas = []
    for U in faixas:
        inst = dict(base, arestas=[dict(e) for e in base["arestas"]])
        rnd = random.Random(99)
        for e in inst["arestas"]:
            e["capacidade"] = rnd.randint(1, U)
        for est in ("dfs", "bfs"):
            res, ms, _ = medir(inst, est, 3)
            linhas.append({"cap_max": U, "estrategia": est, "fluxo": res.valor, "iteracoes": res.iteracoes,
                           "tempo_ms": round(ms, 2)})
            print("capacidade", linhas[-1])
    return linhas


def experimento_reais():
    linhas = []
    for item in listar_instancias():
        inst = carregar_instancia(item["arquivo"])
        for est in ("dfs", "bfs"):
            r = executar(inst, estrategia=est)
            linhas.append({"instancia": item["arquivo"], "vertices": item["n_vertices"], "arestas": item["n_arestas"],
                           "origens": len(inst["cenario"].get("origens", [])), "destinos": len(inst["cenario"].get("destinos", [])),
                           "estrategia": est, "fluxo": r["valor"], "iteracoes": r["iteracoes"], "tempo_ms": r["tempo_ms"],
                           "arestas_corte": len(r["corte"]), "tempo_evacuacao_min": r["tempo_evacuacao_min"]})
            print("real", linhas[-1])
    return linhas


def salvar_csv(nome, linhas):
    with open(os.path.join(SAIDA, nome), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)


def main():
    rapido = "--rapido" in sys.argv
    os.makedirs(SAIDA, exist_ok=True)
    tamanhos = [10, 20, 30, 40, 60] if rapido else [10, 20, 30, 40, 50, 60, 80, 100]
    esc = experimento_escala(tamanhos)
    salvar_csv("escala.csv", esc)
    serie = lambda chave, est: [(l["vertices"], l[chave]) for l in esc if l["estrategia"] == est]
    grafico_svg(os.path.join(SAIDA, "escala_tempo.svg"), "Tempo de execução vs. tamanho da rede",
                "número de vértices (cruzamentos)", "tempo (ms)",
                [("DFS (Ford-Fulkerson)", serie("tempo_ms", "dfs")), ("BFS (Edmonds-Karp)", serie("tempo_ms", "bfs"))])
    grafico_svg(os.path.join(SAIDA, "escala_iteracoes.svg"), "Caminhos aumentantes vs. tamanho da rede",
                "número de vértices (cruzamentos)", "iterações",
                [("DFS (Ford-Fulkerson)", serie("iteracoes", "dfs")), ("BFS (Edmonds-Karp)", serie("iteracoes", "bfs"))])

    cap = experimento_capacidade([10, 100, 1000, 10000, 100000])
    salvar_csv("capacidade.csv", cap)
    s2 = lambda est: [(l["cap_max"], l["iteracoes"]) for l in cap if l["estrategia"] == est]
    grafico_svg(os.path.join(SAIDA, "capacidade_iteracoes.svg"), "Iterações vs. faixa de capacidades (grade 15x15)",
                "capacidade máxima U (capacidades sorteadas em [1, U])", "iterações (escala log)",
                [("DFS (Ford-Fulkerson)", s2("dfs")), ("BFS (Edmonds-Karp)", s2("bfs"))], log_x=True, log_y=True)

    salvar_csv("reais.csv", experimento_reais())
    print("resultados em", SAIDA)


if __name__ == "__main__":
    main()
