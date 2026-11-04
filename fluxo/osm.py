"""
Conversão de dados brutos do OpenStreetMap (resposta JSON da Overpass API)
em uma instância de rede de evacuação.

Modelagem:
  * vértice  = interseção de vias (nó OSM compartilhado por 2+ vias),
               extremidade de via, ou ponto onde a via sai da área de estudo;
  * aresta   = trecho de via entre dois vértices, DIRECIONADO
               (mão dupla -> duas arestas; mão única -> uma aresta);
  * capacidade = veículos/hora naquele sentido
               = faixas_no_sentido x capacidade_por_faixa(tipo de via) x fator_pavimento.

Os valores de capacidade por faixa são uma simplificação inspirada no
Highway Capacity Manual (HCM) e em manuais do DNIT: vias arteriais
urbanas com semáforos/conversões operam bem abaixo das ~1900 veíc/h/faixa
de uma via expressa. São HIPÓTESES documentadas no relatório.
"""

import math

# capacidade por faixa (veículos/hora/faixa), por classe de via OSM
CAPACIDADE_POR_FAIXA = {
    "motorway": 2000, "trunk": 1800, "primary": 1500, "secondary": 1200,
    "tertiary": 1000, "unclassified": 700, "residential": 500, "living_street": 250,
}

# faixas TOTAIS padrão quando a tag "lanes" não existe
FAIXAS_PADRAO = {
    "motorway": 4, "trunk": 4, "primary": 2, "secondary": 2,
    "tertiary": 2, "unclassified": 2, "residential": 2, "living_street": 1,
}

# fator de redução por tipo de pavimento (vias de terra/cascalho são mais lentas)
FATOR_PAVIMENTO = {"unpaved": 0.6, "dirt": 0.5, "gravel": 0.6, "ground": 0.5,
                   "compacted": 0.7, "sett": 0.8, "cobblestone": 0.75, "paving_stones": 0.85}

CLASSES_SAIDA = {"motorway", "trunk", "primary", "secondary", "tertiary"}


def classe_base(highway):
    return highway[:-5] if highway.endswith("_link") else highway


def capacidade_por_sentido(tags):
    """Retorna (cap_ida, cap_volta) em veículos/h; cap_volta = 0 se mão única."""
    hw = tags.get("highway", "")
    base = classe_base(hw)
    cap_faixa = CAPACIDADE_POR_FAIXA.get(base, 500)
    if hw.endswith("_link"):
        cap_faixa = int(cap_faixa * 0.8)         # alças/acessos: capacidade reduzida
    oneway = tags.get("oneway", "no")
    mao_unica = oneway in ("yes", "1", "true", "-1") or tags.get("junction") == "roundabout"
    try:
        faixas = int(str(tags.get("lanes", "")).split(";")[0])
    except ValueError:
        faixas = FAIXAS_PADRAO.get(base, 2) if not mao_unica else max(1, FAIXAS_PADRAO.get(base, 2) // 2)
    faixas = max(1, faixas)
    fator = FATOR_PAVIMENTO.get(tags.get("surface", ""), 1.0)
    if mao_unica:
        cap = int(round(faixas * cap_faixa * fator))
        return (0, cap) if oneway == "-1" else (cap, 0)
    por_sentido = max(1, faixas // 2)
    cap = int(round(por_sentido * cap_faixa * fator))
    return cap, cap


def distancia_m(lat1, lon1, lat2, lon2):
    """Distância de Haversine em metros."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def converter_osm(dados, bbox, nome, descricao=""):
    """
    dados: JSON da Overpass (elements com 'node' e 'way').
    bbox:  (lat_min, lon_min, lat_max, lon_max) da área de estudo; trechos fora são cortados
           e o último nó dentro da área numa via principal vira candidato a SAÍDA.
    """
    lat_min, lon_min, lat_max, lon_max = bbox
    nos = {e["id"]: (e["lat"], e["lon"]) for e in dados["elements"] if e["type"] == "node"}
    vias = [e for e in dados["elements"] if e["type"] == "way" and "highway" in e.get("tags", {})]

    def dentro(nid):
        if nid not in nos:
            return False
        la, lo = nos[nid]
        return lat_min <= la <= lat_max and lon_min <= lo <= lon_max

    # 1) quantas vias usam cada nó -> interseções
    uso = {}
    for w in vias:
        for nid in set(w["nodes"]):
            uso[nid] = uso.get(nid, 0) + 1

    importantes = {nid for nid, c in uso.items() if c >= 2}
    saidas = set()
    pedacos_por_via = []
    for w in vias:
        ns = w["nodes"]
        # divide a via em pedaços contínuos dentro da área
        pedacos, atual = [], []
        for i, nid in enumerate(ns):
            if dentro(nid):
                atual.append(nid)
            else:
                if atual:
                    pedacos.append(atual)
                    if classe_base(w["tags"]["highway"]) in CLASSES_SAIDA:
                        saidas.add(atual[-1])            # via sai da área aqui
                atual = []
                # a via pode REENTRAR: o próximo nó dentro também é borda
                if i + 1 < len(ns) and dentro(ns[i + 1]) and classe_base(w["tags"]["highway"]) in CLASSES_SAIDA:
                    saidas.add(ns[i + 1])
        if atual:
            pedacos.append(atual)
        for p in pedacos:
            if len(p) >= 2:
                importantes.add(p[0])
                importantes.add(p[-1])
        pedacos_por_via.append((w, pedacos))
    importantes |= saidas

    # 2) cria arestas entre vértices importantes consecutivos de cada via
    arestas = []
    for w, pedacos in pedacos_por_via:
        tags = w["tags"]
        cap_ida, cap_volta = capacidade_por_sentido(tags)
        for p in pedacos:
            inicio, comp = p[0], 0.0
            for a, b in zip(p, p[1:]):
                comp += distancia_m(*nos[a], *nos[b])
                if b in importantes:
                    if inicio != b:
                        arestas.append((inicio, b, cap_ida, cap_volta, tags, comp))
                    inicio, comp = b, 0.0

    # 3) mantém só a maior componente conexa (ignorando direção)
    adj = {}
    for u, v, *_ in arestas:
        adj.setdefault(u, set()).add(v)
        adj.setdefault(v, set()).add(u)
    visto, maior = set(), set()
    for r in adj:
        if r in visto:
            continue
        comp, pilha = {r}, [r]
        visto.add(r)
        while pilha:
            x = pilha.pop()
            for y in adj[x]:
                if y not in visto:
                    visto.add(y); comp.add(y); pilha.append(y)
        if len(comp) > len(maior):
            maior = comp

    vertices = []
    for nid in sorted(maior):
        la, lo = nos[nid]
        v = {"id": str(nid), "x": round(lo, 7), "y": round(la, 7)}
        if nid in saidas:
            v["saida"] = True
        vertices.append(v)

    lista_arestas = []
    k = 0
    for u, v, ci, cv, tags, comp in arestas:
        if u not in maior:
            continue
        base = {"nome": tags.get("name", tags.get("ref", "")), "tipo": tags["highway"],
                "comprimento_m": round(comp, 1)}
        if ci > 0:
            lista_arestas.append(dict(base, id=f"e{k}", u=str(u), v=str(v), capacidade=ci)); k += 1
        if cv > 0:
            lista_arestas.append(dict(base, id=f"e{k}", u=str(v), v=str(u), capacidade=cv)); k += 1

    return {
        "nome": nome,
        "descricao": descricao,
        "fonte": "© OpenStreetMap contributors (ODbL) — via Overpass API",
        "geo": True,
        "unidade": "veículos/h",
        "vertices": vertices,
        "arestas": lista_arestas,
        "cenario": {},
    }


def aplicar_zona_de_risco(inst, lat, lon, raio_m, veiculos):
    """Origens = vértices dentro do círculo; destinos = saídas fora do círculo."""
    origens, destinos = [], []
    for v in inst["vertices"]:
        d = distancia_m(lat, lon, v["y"], v["x"])
        if d <= raio_m:
            origens.append(v["id"])
        elif v.get("saida"):
            destinos.append(v["id"])
    inst["cenario"] = {"origens": origens, "destinos": destinos, "veiculos": veiculos,
                       "zona": {"x": lon, "y": lat, "raio_m": raio_m}}
    return inst
