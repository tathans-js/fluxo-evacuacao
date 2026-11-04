# Planejador de Evacuação por Fluxo Máximo (Ford-Fulkerson)

Trabalho de Teoria dos Grafos, **Tema 7: Fluxo em Grafos**. O algoritmo obrigatório é o Ford-Fulkerson.

A aplicação calcula **quantos veículos por hora conseguem sair de uma zona de risco** (área sujeita a
enchente, deslizamento ou rompimento de barragem) até os pontos seguros, usando a **malha viária real**
da cidade, tirada do OpenStreetMap. Além do valor do fluxo máximo, ela mostra:

- o fluxo em cada rua, com cor de acordo com a utilização;
- os **caminhos aumentantes**, um por um (dá pra andar passo a passo ou animar);
- a **rede residual** (arcos diretos `c − f` e reversos `f`);
- o **corte mínimo**, ou seja, as ruas que formam o gargalo da evacuação;
- uma estimativa do **tempo mínimo de evacuação** (veículos ÷ fluxo máximo);
- a verificação automática da solução (capacidade, conservação e corte = fluxo).

Também dá pra simular cenários: **interditar vias** (ex.: ponte alagada), mudar capacidades, criar vias,
mover a zona de risco e comparar **DFS (Ford-Fulkerson clássico)** com **BFS (Edmonds-Karp)**.

## Integrantes

Centro Universitário Sagrado Coração (UNISAGRADO), Bauru/SP. Curso de Ciência da Computação, disciplina de Teoria dos Grafos.
Professor: Patrick Pedreira.

| Nome | RA |
|------|----------------|
| Pedro Henrique Teixeira Moroni | 23110956 |
| Jonathans David da Silva P Jr | 23110246 |
| Guilherme de Oliveira Lazari | 23110982 |
| Lucas Soares de Almeida | 23210133 |

## Instalação e execução

Só precisa de **Python 3.8 ou mais novo**. O projeto não usa nenhuma biblioteca externa (só a biblioteca
padrão), então não tem `pip install`. Também funciona sem internet, porque os dados já estão no repositório.

```bash
git clone https://github.com/tathans-js/fluxo-evacuacao.git
cd fluxo-evacuacao
python3 app.py
```

O navegador abre em `http://127.0.0.1:8000`. Outras opções:

```bash
python3 app.py --porta 8080 --sem-navegador
```

No Windows, use `python` no lugar de `python3`.

### Testes e experimentos

```bash
python3 -m unittest discover -s tests -v     # 28 testes automatizados
python3 scripts/benchmark.py                 # gera docs/resultados/*.csv e *.svg
python3 scripts/construir_instancias.py      # regenera data/instancias/ a partir de data/raw/
python3 scripts/baixar_osm.py mariana        # baixa outra cidade da Overpass API (precisa de internet)
```

## Como usar

1. **Instância:** escolha uma das instâncias prontas, importe um `.json` ou `.csv`, ou gere uma cidade sintética.
2. **Cenário:** as origens (cruzamentos dentro da zona de risco) e os destinos (saídas) já vêm definidos.
   Dá pra alterar com os modos *Origem*, *Destino* e *Zona de risco* (clique no mapa usando o raio informado).
   Com *Interditar via* você bloqueia uma rua nos dois sentidos.
3. **Execução:** escolha DFS ou BFS e clique em **Executar** (ou aperte Enter).
4. **Resultado:** use as abas *Capacidades / Fluxo / Rede residual* e os controles ⏮ ◀ ⏵ ▶ ⏭ (ou as setas do
   teclado) para acompanhar os caminhos aumentantes. Clique numa rua ou num cruzamento para ver os detalhes.

Parâmetros de URL, úteis na apresentação:
`http://127.0.0.1:8000/?instancia=03_brumadinho.json&estrategia=bfs&visao=residual&executar=1`

## Instâncias incluídas

| Arquivo | V | E | Característica |
|---|---:|---:|---|
| `01_bairro_didatico.json` | 6 | 10 | Resultado conhecido (Cormen, Fig. 26.1, ×100): fluxo = **2300**. Dá pra conferir à mão. |
| `02_ilha_sem_caminho.json` | 6 | 7 | **Sem solução**: a única ponte está interditada, fluxo = 0. |
| `03_brumadinho.json` | 842 | 2108 | Malha real de Brumadinho/MG, 244 origens e 7 saídas. |
| `04_petropolis.json` | 1174 | 2341 | Malha real do centro de Petrópolis/RJ, 182 origens e 6 saídas. |
| `05_cidade_sintetica_40x40.json` | 1600 | 5182 | Cidade sintética para teste de escala. |

O gerador cria cidades de até 200×200 cruzamentos. No benchmark rodamos até 10 000 vértices e 32 768 arestas.

## Formato dos dados

**JSON** (formato completo, ver `fluxo/instancias.py`):

```json
{
  "nome": "...", "geo": true, "unidade": "veículos/h",
  "vertices": [{"id": "n1", "x": -44.20, "y": -20.14, "saida": true}],
  "arestas":  [{"id": "e1", "u": "n1", "v": "n2", "capacidade": 1500, "nome": "Av. X", "bloqueada": false}],
  "cenario":  {"origens": ["n1"], "destinos": ["n9"], "veiculos": 4000}
}
```

**CSV** (importação rápida; o layout é calculado automaticamente):

```csv
u,v,capacidade,nome,mao_dupla
A,B,1200,Rua 1,sim
B,C,800,Rua 2,nao
```

## Origem dos dados

- **Malha viária:** © colaboradores do OpenStreetMap, licença ODbL, baixada pela Overpass API em 04/11/2026.
  Os arquivos brutos estão em `data/raw/` e podem ser baixados de novo com `scripts/baixar_osm.py`.
- **Capacidades:** estimadas pelo tipo de via, número de faixas e pavimento (tabela em `fluxo/osm.py`),
  com valores simplificados inspirados no *Highway Capacity Manual*.
- **Zona de risco e número de veículos:** são **hipóteses de planejamento** inspiradas em desastres reais
  (Brumadinho 2019 e Petrópolis 2022). Não são dados oficiais da Defesa Civil e podem ser alterados na interface.

## Estrutura do código

```
app.py                     ponto de entrada (sobe o servidor e abre o navegador)
fluxo/
  rede.py                  estrutura da rede de fluxo (lista de adjacência + arcos reversos)
  ford_fulkerson.py        ALGORITMO: Ford-Fulkerson (DFS/BFS), corte mínimo e verificação
  instancias.py            leitura/validação de JSON/CSV, super-origem/destino, execução
  osm.py                   conversão OpenStreetMap -> rede (capacidades por tipo de via)
  gerador.py               gerador de cidades sintéticas
  servidor.py              API HTTP + arquivos da interface
web/                       interface (HTML + CSS + JavaScript puro, desenho em <canvas>)
data/raw/                  dados brutos do OSM
data/instancias/           instâncias prontas para uso
scripts/                   download do OSM, construção das instâncias e benchmark
tests/                     testes automatizados (unittest)
docs/                      proposta, relatório (PDF), figuras e resultados
```

**Bibliotecas de grafos:** nenhuma. O Ford-Fulkerson, as buscas, o corte mínimo e a verificação foram
implementados pelo grupo em `fluxo/ford_fulkerson.py`.

## Uso de IA

Usamos ferramentas de IA generativa (Claude, da Anthropic) como apoio na escrita de partes do código e do texto.
Todos os integrantes revisaram, testaram e conseguem explicar o código e as decisões. Mais detalhes na seção
de transparência do relatório.
