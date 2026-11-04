"""
Gerador de cidades sintéticas para testes de escala.

Gera uma malha urbana (grade) com:
  * avenidas a cada `espaco_avenidas` linhas/colunas (2 faixas por sentido);
  * ruas locais com capacidade menor, parte delas em mão única (sentido aleatório);
  * quarteirões removidos ao acaso (praças, rios, obstáculos);
  * zona de risco circular no centro (origens) e saídas nas bordas sobre avenidas (destinos).

As capacidades seguem a mesma tabela das instâncias reais (fluxo/osm.py).
Com a mesma semente, a instância gerada é sempre a mesma (reprodutível).
"""

import math
import random

from .osm import CAPACIDADE_POR_FAIXA


def gerar_cidade(linhas=20, colunas=20, semente=42, prob_mao_unica=0.3,
                 prob_remocao=0.08, espaco_avenidas=5, raio_zona=0.2, veiculos=5000):
    if linhas < 2 or colunas < 2:
        raise ValueError("a grade precisa de pelo menos 2x2 cruzamentos")
    if linhas * colunas > 40000:
        raise ValueError("instância grande demais para a interface (máx. 40 000 vértices)")
    rnd = random.Random(semente)
    vid = lambda i, j: f"c{i}_{j}"
    vertices = []
    for i in range(linhas):
        for j in range(colunas):
            vertices.append({"id": vid(i, j),
                             "x": j * 100 + rnd.uniform(-15, 15),
                             "y": -(i * 100 + rnd.uniform(-15, 15))})
    arestas = []
    k = 0

    def adicionar(a, b, cap, nome, tipo):
        nonlocal k
        arestas.append({"id": f"e{k}", "u": a, "v": b, "capacidade": cap,
                        "nome": nome, "tipo": tipo, "comprimento_m": 100.0})
        k += 1

    for i in range(linhas):
        for j in range(colunas):
            for di, dj in ((0, 1), (1, 0)):
                i2, j2 = i + di, j + dj
                if i2 >= linhas or j2 >= colunas:
                    continue
                avenida = (i % espaco_avenidas == 0) if di == 0 else (j % espaco_avenidas == 0)
                a, b = vid(i, j), vid(i2, j2)
                if avenida:
                    cap = 2 * CAPACIDADE_POR_FAIXA["secondary"]
                    nome = f"Av. {'L' if di == 0 else 'C'}{i if di == 0 else j}"
                    adicionar(a, b, cap, nome, "secondary")
                    adicionar(b, a, cap, nome, "secondary")
                    continue
                if rnd.random() < prob_remocao:
                    continue
                cap = CAPACIDADE_POR_FAIXA["residential"] * rnd.choice((1, 1, 2))
                nome = f"Rua {i}-{j}"
                if rnd.random() < prob_mao_unica:
                    if rnd.random() < 0.5:
                        a, b = b, a
                    adicionar(a, b, cap, nome, "residential")
                else:
                    adicionar(a, b, cap, nome, "residential")
                    adicionar(b, a, cap, nome, "residential")

    # cenário: zona de risco central e saídas nas bordas sobre avenidas
    ci, cj = (linhas - 1) / 2, (colunas - 1) / 2
    r = raio_zona * min(linhas, colunas)
    origens, destinos = [], []
    for i in range(linhas):
        for j in range(colunas):
            if math.hypot(i - ci, j - cj) <= r:
                origens.append(vid(i, j))
            borda = i in (0, linhas - 1) or j in (0, colunas - 1)
            sobre_avenida = i % espaco_avenidas == 0 or j % espaco_avenidas == 0
            if borda and sobre_avenida:
                destinos.append(vid(i, j))
    destinos = [d for d in destinos if d not in set(origens)]
    if not origens:
        origens = [vid(int(ci), int(cj))]
    for v in vertices:
        if v["id"] in destinos:
            v["saida"] = True
    return {
        "nome": f"Cidade sintética {linhas}x{colunas} (semente {semente})",
        "descricao": "Malha urbana gerada aleatoriamente para testes de escala.",
        "fonte": "Gerador sintético (fluxo/gerador.py)",
        "geo": False,
        "unidade": "veículos/h",
        "vertices": vertices,
        "arestas": arestas,
        "cenario": {"origens": origens, "destinos": destinos, "veiculos": veiculos,
                    "zona": {"x": cj * 100, "y": -ci * 100, "raio_m": r * 100}},
    }
