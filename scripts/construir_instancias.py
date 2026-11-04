"""
Gera os arquivos de data/instancias/ a partir dos dados brutos em data/raw/
(OpenStreetMap) e das instâncias pequenas de verificação.

Uso:  python3 scripts/construir_instancias.py
"""

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from fluxo.osm import converter_osm, aplicar_zona_de_risco  # noqa: E402
from fluxo.gerador import gerar_cidade  # noqa: E402

RAW = os.path.join(RAIZ, "data", "raw")
SAIDA = os.path.join(RAIZ, "data", "instancias")

# Cenários das cidades reais. A REDE VIÁRIA é real (OSM); a zona de risco e o
# número de veículos são HIPÓTESES de planejamento, documentadas no relatório
# e alteráveis pela interface.
CIDADES = {
    "brumadinho": {
        "nome": "Brumadinho (MG) — evacuação do centro",
        "descricao": ("Rede viária real de Brumadinho/MG (OSM). Cenário hipotético inspirado no "
                      "rompimento da barragem B1 (2019): evacuar a área central, próxima ao rio "
                      "Paraopeba, até as saídas da cidade."),
        "bbox": (-20.205, -44.222, -20.123, -44.162),
        "zona": (-20.1430, -44.2000, 800),
        "veiculos": 4000,
    },
    "petropolis": {
        "nome": "Petrópolis (RJ) — evacuação do Centro Histórico",
        "descricao": ("Rede viária real do centro de Petrópolis/RJ (OSM). Cenário hipotético "
                      "inspirado nas chuvas de fevereiro/2022: evacuar o Centro Histórico "
                      "(vale do rio Quitandinha) até as saídas da área de estudo."),
        "bbox": (-22.535, -43.208, -22.484, -43.153),
        "zona": (-22.5070, -43.1790, 900),
        "veiculos": 8000,
    },
}


def didatica():
    """Rede clássica (Cormen et al., fig. 26.1) com capacidades x100. Fluxo máximo conhecido: 2300."""
    pos = {"Escola": (0, 0), "A": (1, 1), "B": (1, -1), "C": (2, 1), "D": (2, -1), "Abrigo": (3, 0)}
    arestas = [("Escola", "A", 1600), ("Escola", "B", 1300), ("A", "B", 1000), ("B", "A", 400),
               ("A", "C", 1200), ("C", "B", 900), ("B", "D", 1400), ("D", "C", 700),
               ("C", "Abrigo", 2000), ("D", "Abrigo", 400)]
    return {
        "nome": "Bairro didático (resultado verificável: 2300)",
        "descricao": ("Rede pequena com resposta conhecida (Cormen et al., Fig. 26.1, capacidades x100). "
                      "Serve para conferir o algoritmo à mão e acompanhar passo a passo."),
        "fonte": "Cormen, Leiserson, Rivest, Stein — Introduction to Algorithms, cap. 26",
        "geo": False, "unidade": "veículos/h",
        "vertices": [{"id": k, "x": x, "y": y, "rotulo": k} for k, (x, y) in pos.items()],
        "arestas": [{"id": f"e{i}", "u": u, "v": v, "capacidade": c, "nome": f"{u}→{v}"}
                    for i, (u, v, c) in enumerate(arestas)],
        "cenario": {"origens": ["Escola"], "destinos": ["Abrigo"], "veiculos": 1000},
    }


def sem_caminho():
    """Bairro numa ilha cuja única ponte está bloqueada: fluxo máximo = 0."""
    pos = {"Bairro": (0, 0), "R1": (1, 0.6), "R2": (1, -0.6), "Cabeceira": (2, 0),
           "Ponte": (3, 0), "Abrigo": (4, 0)}
    arestas = [("Bairro", "R1", 800, False), ("Bairro", "R2", 800, False), ("R1", "Cabeceira", 600, False),
               ("R2", "Cabeceira", 600, False), ("Cabeceira", "Ponte", 1500, True),
               ("Ponte", "Abrigo", 1500, False), ("R1", "R2", 300, False)]
    return {
        "nome": "Ilha com ponte interditada (sem solução)",
        "descricao": ("Caso sem caminho: a única ponte até o abrigo está bloqueada (alagada). "
                      "O fluxo máximo é 0. Desbloqueie a ponte na interface para ver o fluxo voltar."),
        "fonte": "Construída pelo grupo (caso de fronteira)",
        "geo": False, "unidade": "veículos/h",
        "vertices": [{"id": k, "x": x, "y": y, "rotulo": k} for k, (x, y) in pos.items()],
        "arestas": [{"id": f"e{i}", "u": u, "v": v, "capacidade": c, "nome": f"{u}→{v}", "bloqueada": b}
                    for i, (u, v, c, b) in enumerate(arestas)],
        "cenario": {"origens": ["Bairro"], "destinos": ["Abrigo"], "veiculos": 500},
    }


def salvar(nome_arquivo, inst):
    caminho = os.path.join(SAIDA, nome_arquivo)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(inst, f, ensure_ascii=False, separators=(",", ":"))
    c = inst["cenario"]
    print(f"{nome_arquivo:32s} V={len(inst['vertices']):5d} E={len(inst['arestas']):5d} "
          f"origens={len(c.get('origens', []))} destinos={len(c.get('destinos', []))}")


def main():
    os.makedirs(SAIDA, exist_ok=True)
    salvar("01_bairro_didatico.json", didatica())
    salvar("02_ilha_sem_caminho.json", sem_caminho())
    for chave, cfg in CIDADES.items():
        arq = os.path.join(RAW, f"{chave}.json")
        if not os.path.exists(arq):
            print(f"[aviso] {arq} não existe — rode scripts/baixar_osm.py {chave}")
            continue
        with open(arq, encoding="utf-8") as f:
            dados = json.load(f)
        inst = converter_osm(dados, cfg["bbox"], cfg["nome"], cfg["descricao"])
        lat, lon, raio = cfg["zona"]
        aplicar_zona_de_risco(inst, lat, lon, raio, cfg["veiculos"])
        salvar(f"{'03' if chave == 'brumadinho' else '04'}_{chave}.json", inst)
    salvar("05_cidade_sintetica_40x40.json", gerar_cidade(40, 40, semente=7, veiculos=12000))


if __name__ == "__main__":
    main()
