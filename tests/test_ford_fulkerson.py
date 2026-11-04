"""
Testes do algoritmo de Ford-Fulkerson e da camada de instâncias.

Rodar:  python3 -m unittest discover -s tests -v
"""

import itertools
import json
import os
import random
import sys
import threading
import unittest
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from fluxo.rede import RedeFluxo  # noqa: E402
from fluxo.ford_fulkerson import ford_fulkerson, verificar_fluxo  # noqa: E402
from fluxo.instancias import (ErroInstancia, carregar_instancia, executar,  # noqa: E402
                              instancia_de_texto, listar_instancias)
from fluxo.gerador import gerar_cidade  # noqa: E402
from fluxo.osm import capacidade_por_sentido  # noqa: E402

ESTRATEGIAS = ("dfs", "bfs")


def rede_de_lista(n, arestas):
    r = RedeFluxo(n)
    for u, v, c in arestas:
        r.adicionar_aresta(u, v, c)
    return r


def corte_minimo_forca_bruta(n, arestas, s, t):
    """Enumera todas as partições (S, T) com s em S e t em T: referência independente."""
    outros = [v for v in range(n) if v not in (s, t)]
    melhor = None
    for k in range(len(outros) + 1):
        for comb in itertools.combinations(outros, k):
            S = {s, *comb}
            cap = sum(c for u, v, c in arestas if u in S and v not in S)
            melhor = cap if melhor is None else min(melhor, cap)
    return melhor


def inst_simples(arestas, origens, destinos):
    vs = sorted({x for u, v, _ in arestas for x in (u, v)} | set(origens) | set(destinos))
    return {"vertices": [{"id": v} for v in vs],
            "arestas": [{"id": f"e{i}", "u": u, "v": v, "capacidade": c} for i, (u, v, c) in enumerate(arestas)],
            "cenario": {"origens": origens, "destinos": destinos}}


class TestCasosVerificaveis(unittest.TestCase):
    def test_exemplo_cormen_2300(self):
        inst = carregar_instancia("01_bairro_didatico.json")
        for est in ESTRATEGIAS:
            r = executar(inst, estrategia=est)
            self.assertEqual(r["valor"], 2300)
            self.assertEqual(r["capacidade_corte"], 2300)
            self.assertTrue(all(r["verificacao"][k] for k in ("capacidade", "conservacao", "valor_confere", "corte_igual_fluxo")))

    def test_aresta_unica(self):
        for est in ESTRATEGIAS:
            r = rede_de_lista(2, [(0, 1, 7)])
            self.assertEqual(ford_fulkerson(r, 0, 1, est).valor, 7)

    def test_caminho_em_serie_gargalo(self):
        for est in ESTRATEGIAS:
            r = rede_de_lista(4, [(0, 1, 10), (1, 2, 3), (2, 3, 10)])
            res = ford_fulkerson(r, 0, 3, est)
            self.assertEqual(res.valor, 3)
            self.assertEqual(res.iteracoes, 1)

    def test_arestas_paralelas_somam(self):
        for est in ESTRATEGIAS:
            r = rede_de_lista(2, [(0, 1, 4), (0, 1, 6)])
            self.assertEqual(ford_fulkerson(r, 0, 1, est).valor, 10)

    def test_cancelamento_de_fluxo(self):
        """
        Grafo em que o DFS primeiro usa s->a->b->t; o fluxo máximo (20) só é
        alcançado cancelando a->b pelo arco reverso b->a da rede residual.
        """
        arestas = [(0, 1, 10), (1, 2, 10), (2, 3, 10), (0, 2, 10), (1, 3, 10)]  # s=0 a=1 b=2 t=3
        r = rede_de_lista(4, arestas)
        res = ford_fulkerson(r, 0, 3, "dfs")
        self.assertEqual(res.valor, 20)
        usou_reverso = any(a % 2 == 1 for cam, g in res.caminhos for a in cam)
        self.assertTrue(usou_reverso, "esperava um caminho aumentante usando arco reverso")
        self.assertEqual(r.fluxo[2], 0)  # a->b termina sem fluxo


class TestSemSolucaoEFronteira(unittest.TestCase):
    def test_ilha_ponte_bloqueada(self):
        inst = carregar_instancia("02_ilha_sem_caminho.json")
        r = executar(inst)
        self.assertEqual(r["valor"], 0)
        self.assertEqual(r["iteracoes"], 0)
        self.assertIsNone(r["tempo_evacuacao_min"])

    def test_ilha_desbloqueada(self):
        inst = carregar_instancia("02_ilha_sem_caminho.json")
        for e in inst["arestas"]:
            e["bloqueada"] = False
        self.assertEqual(executar(inst)["valor"], 1200)   # R1->Cabeceira + R2->Cabeceira = 600 + 600

    def test_destino_inalcancavel_por_sentido(self):
        # só existe a rua t->s (mão única no sentido errado)
        for est in ESTRATEGIAS:
            r = rede_de_lista(2, [(1, 0, 100)])
            self.assertEqual(ford_fulkerson(r, 0, 1, est).valor, 0)

    def test_capacidade_zero(self):
        r = rede_de_lista(3, [(0, 1, 0), (1, 2, 5)])
        self.assertEqual(ford_fulkerson(r, 0, 2).valor, 0)

    def test_origem_igual_destino(self):
        with self.assertRaises(ValueError):
            ford_fulkerson(rede_de_lista(2, [(0, 1, 1)]), 0, 0)
        with self.assertRaises(ErroInstancia):
            executar(inst_simples([("a", "b", 1)], ["a"], ["a"]))

    def test_sem_origem(self):
        with self.assertRaises(ErroInstancia):
            executar(inst_simples([("a", "b", 1)], [], ["b"]))

    def test_capacidade_invalida(self):
        with self.assertRaises(ValueError):
            rede_de_lista(2, [(0, 1, 2.5)])
        with self.assertRaises(ErroInstancia):
            executar(inst_simples([("a", "b", -3)], ["a"], ["b"]))
        with self.assertRaises(ErroInstancia):
            executar(inst_simples([("a", "b", 1.5)], ["a"], ["b"]))

    def test_vertice_inexistente(self):
        inst = inst_simples([("a", "b", 1)], ["a"], ["b"])
        inst["arestas"].append({"id": "x", "u": "a", "v": "zzz", "capacidade": 1})
        with self.assertRaises(ErroInstancia):
            executar(inst)

    def test_aresta_entrando_na_origem_e_laco(self):
        r = rede_de_lista(3, [(1, 0, 50), (0, 1, 5), (1, 2, 9), (2, 2, 4)])
        self.assertEqual(ford_fulkerson(r, 0, 2).valor, 5)

    def test_capacidades_grandes(self):
        r = rede_de_lista(3, [(0, 1, 10 ** 12), (1, 2, 10 ** 12 - 1)])
        self.assertEqual(ford_fulkerson(r, 0, 2).valor, 10 ** 12 - 1)


class TestMultiplasOrigens(unittest.TestCase):
    def test_super_origem_e_super_destino(self):
        # duas origens e dois destinos independentes: fluxo = soma
        inst = inst_simples([("o1", "x", 5), ("o2", "x", 7), ("x", "d1", 4), ("x", "d2", 100)], ["o1", "o2"], ["d1", "d2"])
        r = executar(inst)
        self.assertEqual(r["valor"], 12)
        self.assertTrue(r["super_origem"] and r["super_destino"])
        self.assertTrue(r["verificacao"]["conservacao"])

    def test_equivale_a_super_origem_manual(self):
        inst = inst_simples([("o1", "x", 5), ("o2", "x", 7), ("x", "d", 9)], ["o1", "o2"], ["d"])
        manual = inst_simples([("S", "o1", 10 ** 6), ("S", "o2", 10 ** 6), ("o1", "x", 5), ("o2", "x", 7), ("x", "d", 9)], ["S"], ["d"])
        self.assertEqual(executar(inst)["valor"], executar(manual)["valor"])


class TestAleatorioContraForcaBruta(unittest.TestCase):
    def test_grafos_aleatorios(self):
        """200 grafos aleatórios pequenos: fluxo de FF == corte mínimo por força bruta."""
        rnd = random.Random(2024)
        for _ in range(200):
            n = rnd.randint(2, 8)
            arestas = [(u, v, rnd.randint(0, 20)) for u in range(n) for v in range(n)
                       if u != v and rnd.random() < 0.35]
            s, t = 0, n - 1
            esperado = corte_minimo_forca_bruta(n, arestas, s, t)
            for est in ESTRATEGIAS:
                r = rede_de_lista(n, arestas)
                res = ford_fulkerson(r, s, t, est)
                self.assertEqual(res.valor, esperado)
                self.assertEqual(res.capacidade_corte, esperado)
                v = verificar_fluxo(r, s, t, res.valor)
                self.assertTrue(v["capacidade"] and v["conservacao"] and v["valor_confere"])


class TestInstanciasReais(unittest.TestCase):
    def test_todas_as_instancias(self):
        for item in listar_instancias():
            inst = carregar_instancia(item["arquivo"])
            r_dfs = executar(inst, estrategia="dfs")
            r_bfs = executar(inst, estrategia="bfs")
            self.assertEqual(r_dfs["valor"], r_bfs["valor"], item["arquivo"])
            for r in (r_dfs, r_bfs):
                self.assertTrue(all(r["verificacao"][k] for k in ("capacidade", "conservacao", "valor_confere", "corte_igual_fluxo")), item["arquivo"])

    def test_interditar_corte_reduz_fluxo(self):
        inst = carregar_instancia("03_brumadinho.json")
        r = executar(inst)
        corte = set(r["corte"])
        alvo = max((e for e in inst["arestas"] if e["id"] in corte), key=lambda e: e["capacidade"])
        alvo["bloqueada"] = True
        r2 = executar(inst)
        self.assertLess(r2["valor"], r["valor"])
        self.assertGreaterEqual(r2["valor"], r["valor"] - alvo["capacidade"])


class TestEntradas(unittest.TestCase):
    def test_csv_mao_dupla(self):
        inst = instancia_de_texto("u,v,capacidade,nome,mao_dupla\na,b,10,R1,sim\nb,c,4,R2,nao\n", "csv")
        self.assertEqual(len(inst["arestas"]), 3)
        self.assertEqual(executar(inst, ["a"], ["c"])["valor"], 4)
        self.assertEqual(executar(inst, ["c"], ["a"])["valor"], 0)

    def test_csv_sem_colunas(self):
        with self.assertRaises(ErroInstancia):
            instancia_de_texto("x,y\n1,2\n", "csv")

    def test_json_invalido(self):
        with self.assertRaises(ErroInstancia):
            instancia_de_texto("{nao é json", "json")

    def test_gerador_reprodutivel(self):
        a, b = gerar_cidade(12, 9, semente=3), gerar_cidade(12, 9, semente=3)
        self.assertEqual(json.dumps(a), json.dumps(b))
        self.assertNotEqual(json.dumps(a), json.dumps(gerar_cidade(12, 9, semente=4)))
        self.assertGreater(executar(a)["valor"], 0)

    def test_capacidade_osm(self):
        self.assertEqual(capacidade_por_sentido({"highway": "primary"}), (1500, 1500))
        self.assertEqual(capacidade_por_sentido({"highway": "primary", "oneway": "yes", "lanes": "2"}), (3000, 0))
        self.assertEqual(capacidade_por_sentido({"highway": "residential", "oneway": "-1"}), (0, 500))
        self.assertEqual(capacidade_por_sentido({"highway": "secondary", "surface": "unpaved"}), (720, 720))


class TestServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fluxo.servidor import iniciar
        cls.srv = iniciar(0)
        cls.porta = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _post(self, rota, corpo):
        req = urllib.request.Request(f"http://127.0.0.1:{self.porta}{rota}", data=json.dumps(corpo).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_api_executar(self):
        inst = carregar_instancia("01_bairro_didatico.json")
        st, r = self._post("/api/executar", {"instancia": inst, "estrategia": "bfs"})
        self.assertEqual(st, 200)
        self.assertEqual(r["valor"], 2300)

    def test_api_erro(self):
        st, r = self._post("/api/executar", {"instancia": {"vertices": []}})
        self.assertEqual(st, 400)
        self.assertIn("erro", r)

    def test_api_nao_sai_da_pasta(self):
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/api/instancias/..%2F..%2Fapp.py")


if __name__ == "__main__":
    unittest.main()
