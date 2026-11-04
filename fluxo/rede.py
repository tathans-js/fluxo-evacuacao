"""
Estrutura de dados da rede de fluxo (grafo direcionado com capacidades).

Representação escolhida: lista de adjacência com arcos armazenados em vetores
paralelos. Cada aresta original u->v com capacidade c gera DOIS arcos:

    arco 2k   : u -> v   capacidade c   (arco "direto")
    arco 2k+1 : v -> u   capacidade 0   (arco "reverso", existe só na rede residual)

Assim, o arco reverso de qualquer arco `a` é simplesmente `a ^ 1` (xor 1),
o que deixa a atualização da rede residual em O(1) por arco.

Capacidade residual de um arco a:  cf(a) = capacidade[a] - fluxo[a]
Antissimetria mantida pelo algoritmo:  fluxo[a ^ 1] == -fluxo[a]

Nenhuma biblioteca de grafos é utilizada.
"""


class RedeFluxo:
    def __init__(self, n_vertices):
        self.n = n_vertices
        # adjacencia[v] = lista de índices de arcos que saem de v (diretos e reversos)
        self.adjacencia = [[] for _ in range(n_vertices)]
        self.origem_arco = []      # origem_arco[a]  = vértice de onde o arco sai
        self.destino_arco = []     # destino_arco[a] = vértice onde o arco chega
        self.capacidade = []       # capacidade[a]   (0 nos arcos reversos)
        self.fluxo = []            # fluxo[a]        (pode ser negativo nos reversos)
        self.rotulo_arco = []      # informação externa associada (ex.: id da aresta da instância)

    def adicionar_vertice(self):
        self.adjacencia.append([])
        self.n += 1
        return self.n - 1

    def adicionar_aresta(self, u, v, capacidade, rotulo=None):
        """Adiciona a aresta u->v. Retorna o índice do arco direto (sempre par)."""
        if capacidade < 0:
            raise ValueError("capacidade negativa não é permitida")
        if int(capacidade) != capacidade:
            raise ValueError("capacidades devem ser inteiras (garante a terminação do Ford-Fulkerson)")
        a = len(self.capacidade)
        # arco direto
        self.origem_arco.append(u)
        self.destino_arco.append(v)
        self.capacidade.append(int(capacidade))
        self.fluxo.append(0)
        self.rotulo_arco.append(rotulo)
        self.adjacencia[u].append(a)
        # arco reverso (residual)
        self.origem_arco.append(v)
        self.destino_arco.append(u)
        self.capacidade.append(0)
        self.fluxo.append(0)
        self.rotulo_arco.append(rotulo)
        self.adjacencia[v].append(a + 1)
        return a

    @property
    def n_arestas(self):
        return len(self.capacidade) // 2

    def residual(self, a):
        return self.capacidade[a] - self.fluxo[a]

    def eh_direto(self, a):
        return a % 2 == 0

    def zerar_fluxo(self):
        self.fluxo = [0] * len(self.fluxo)

    def arestas_diretas(self):
        """Itera sobre (indice_arco, u, v, capacidade, fluxo) apenas dos arcos diretos."""
        for a in range(0, len(self.capacidade), 2):
            yield a, self.origem_arco[a], self.destino_arco[a], self.capacidade[a], self.fluxo[a]
