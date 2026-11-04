"""
Algoritmo de Ford-Fulkerson para fluxo máximo (implementação própria).

Método de Ford-Fulkerson (1956):
    1. Comece com fluxo f = 0 em todas as arestas.
    2. Enquanto existir um caminho aumentante p de s até t na rede residual G_f:
         a. gargalo = min{ cf(a) : a em p }
         b. para cada arco a de p:  f(a) += gargalo  e  f(reverso(a)) -= gargalo
    3. Quando não existir caminho aumentante, f é máximo
       (teorema do fluxo máximo / corte mínimo).

A forma de ENCONTRAR o caminho aumentante não é fixada pelo método. Aqui
oferecemos duas estratégias, para comparação:

    "dfs" -> busca em profundidade: Ford-Fulkerson "clássico".
             Complexidade O(E * |f*|), onde |f*| é o valor do fluxo máximo
             (depende das capacidades, não só do tamanho do grafo).

    "bfs" -> busca em largura: caminho aumentante com o MENOR número de arcos.
             Essa escolha é conhecida como Edmonds-Karp (1972) e garante
             O(V * E^2), independente das capacidades.

Com capacidades inteiras, cada aumento soma pelo menos 1 ao fluxo, então o
algoritmo sempre termina e o fluxo final é inteiro.
"""

import time
from collections import deque

from .rede import RedeFluxo

ESTRATEGIAS = ("dfs", "bfs")


# ---------------------------------------------------------------------------
# Busca de caminho aumentante na rede residual
# ---------------------------------------------------------------------------

def _reconstruir_caminho(arco_pai, rede, s, t):
    """Volta de t até s seguindo o arco usado para chegar em cada vértice."""
    caminho = []
    v = t
    while v != s:
        a = arco_pai[v]
        caminho.append(a)
        v = rede.origem_arco[a]
    caminho.reverse()
    return caminho


def caminho_aumentante_dfs(rede: RedeFluxo, s, t):
    """
    Busca em profundidade (iterativa, para não estourar o limite de recursão
    do Python em grafos grandes) que só atravessa arcos com residual > 0.
    Retorna a lista de arcos do caminho s->t, ou None se t é inalcançável.
    """
    arco_pai = [-1] * rede.n
    visitado = [False] * rede.n
    visitado[s] = True
    # pilha de (vértice, posição do próximo arco a examinar na adjacência)
    pilha = [(s, 0)]
    while pilha:
        v, i = pilha[-1]
        adj = rede.adjacencia[v]
        avancou = False
        while i < len(adj):
            a = adj[i]
            i += 1
            w = rede.destino_arco[a]
            if not visitado[w] and rede.capacidade[a] - rede.fluxo[a] > 0:
                pilha[-1] = (v, i)          # guarda onde parou em v
                visitado[w] = True
                arco_pai[w] = a
                if w == t:
                    return _reconstruir_caminho(arco_pai, rede, s, t)
                pilha.append((w, 0))
                avancou = True
                break
        if not avancou:
            pilha.pop()                     # todos os vizinhos de v esgotados: retrocede
    return None


def caminho_aumentante_bfs(rede: RedeFluxo, s, t):
    """Busca em largura na rede residual: menor caminho (em número de arcos)."""
    arco_pai = [-1] * rede.n
    visitado = [False] * rede.n
    visitado[s] = True
    fila = deque([s])
    while fila:
        v = fila.popleft()
        for a in rede.adjacencia[v]:
            w = rede.destino_arco[a]
            if not visitado[w] and rede.capacidade[a] - rede.fluxo[a] > 0:
                visitado[w] = True
                arco_pai[w] = a
                if w == t:
                    return _reconstruir_caminho(arco_pai, rede, s, t)
                fila.append(w)
    return None


# ---------------------------------------------------------------------------
# Ford-Fulkerson
# ---------------------------------------------------------------------------

class ResultadoFluxo:
    def __init__(self):
        self.valor = 0                 # valor do fluxo máximo
        self.caminhos = []             # [(lista_de_arcos, gargalo), ...] na ordem em que foram aumentados
        self.iteracoes = 0             # número de caminhos aumentantes
        self.tempo_ms = 0.0
        self.estrategia = None
        self.lado_s = set()            # vértices alcançáveis de s na residual final (lado S do corte mínimo)
        self.arcos_corte = []          # arcos diretos do corte mínimo (S -> T)
        self.capacidade_corte = 0


def ford_fulkerson(rede: RedeFluxo, s, t, estrategia="dfs", registrar_caminhos=True,
                   limite_iteracoes=None):
    """
    Calcula o fluxo máximo de s para t, ALTERANDO rede.fluxo.
    Retorna um ResultadoFluxo com valor, caminhos aumentantes e corte mínimo.
    """
    if estrategia not in ESTRATEGIAS:
        raise ValueError(f"estratégia inválida: {estrategia}")
    if s == t:
        raise ValueError("origem e destino devem ser vértices diferentes")

    buscar = caminho_aumentante_dfs if estrategia == "dfs" else caminho_aumentante_bfs
    res = ResultadoFluxo()
    res.estrategia = estrategia
    inicio = time.perf_counter()

    while True:
        if limite_iteracoes is not None and res.iteracoes >= limite_iteracoes:
            break
        caminho = buscar(rede, s, t)
        if caminho is None:
            break                                       # não há caminho aumentante: fluxo é máximo

        gargalo = min(rede.capacidade[a] - rede.fluxo[a] for a in caminho)

        for a in caminho:                               # aumenta o fluxo ao longo do caminho
            rede.fluxo[a] += gargalo
            rede.fluxo[a ^ 1] -= gargalo                # mantém a antissimetria (arco reverso)

        res.valor += gargalo
        res.iteracoes += 1
        if registrar_caminhos:
            res.caminhos.append((caminho, gargalo))

    res.tempo_ms = (time.perf_counter() - inicio) * 1000.0
    calcular_corte_minimo(rede, s, res)
    return res


# ---------------------------------------------------------------------------
# Corte mínimo (certificado de otimalidade)
# ---------------------------------------------------------------------------

def calcular_corte_minimo(rede: RedeFluxo, s, res: ResultadoFluxo):
    """
    Após o término, S = vértices alcançáveis a partir de s na rede residual.
    As arestas originais (u em S, v fora de S) formam um corte mínimo e
    estão todas saturadas. Pelo teorema fluxo-máximo/corte-mínimo,
    capacidade(corte) == valor do fluxo.
    """
    alcancavel = [False] * rede.n
    alcancavel[s] = True
    fila = deque([s])
    while fila:
        v = fila.popleft()
        for a in rede.adjacencia[v]:
            w = rede.destino_arco[a]
            if not alcancavel[w] and rede.capacidade[a] - rede.fluxo[a] > 0:
                alcancavel[w] = True
                fila.append(w)
    res.lado_s = {v for v in range(rede.n) if alcancavel[v]}
    res.arcos_corte = [a for a, u, v, c, f in rede.arestas_diretas()
                       if alcancavel[u] and not alcancavel[v] and c > 0]
    res.capacidade_corte = sum(rede.capacidade[a] for a in res.arcos_corte)
    return res


# ---------------------------------------------------------------------------
# Verificação independente da solução
# ---------------------------------------------------------------------------

def verificar_fluxo(rede: RedeFluxo, s, t, valor):
    """
    Confere as propriedades de um fluxo válido:
      - restrição de capacidade: 0 <= f(e) <= c(e) para toda aresta original
      - conservação: entrada == saída em todo vértice diferente de s e t
      - valor: saída líquida de s == entrada líquida de t == valor informado
    Retorna dicionário com o resultado de cada verificação.
    """
    saldo = [0] * rede.n
    capacidade_ok = True
    for a, u, v, c, f in rede.arestas_diretas():
        if f < 0 or f > c:
            capacidade_ok = False
        saldo[u] -= f
        saldo[v] += f
    conservacao_ok = all(saldo[v] == 0 for v in range(rede.n) if v not in (s, t))
    return {
        "capacidade": capacidade_ok,
        "conservacao": conservacao_ok,
        "valor_saida_origem": -saldo[s],
        "valor_entrada_destino": saldo[t],
        "valor_confere": (-saldo[s] == valor == saldo[t]),
    }
