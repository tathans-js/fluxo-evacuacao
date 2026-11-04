# Proposta de Projeto — Tema 7: Fluxo em Grafos (Ford-Fulkerson)

**Título:** Planejador de evacuação urbana por fluxo máximo

**Grupo:** Pedro Henrique Teixeira Moroni (23110956), Jonathans David da Silva P Jr (23110246), Guilherme de Oliveira Lazari (23110982), Lucas Soares de Almeida (23210133)

**Curso:** Ciência da Computação, UNISAGRADO, Bauru/SP. **Professor:** Patrick Pedreira

## Problema

Em desastres como o rompimento da barragem de Brumadinho (2019) e as chuvas de Petrópolis (2022), a
Defesa Civil precisa tirar muita gente de uma área de risco em pouco tempo. Uma pergunta básica nesse
planejamento é: **quantos veículos por hora a malha viária consegue escoar da zona de risco até um local
seguro, e quais ruas limitam esse escoamento?** A resposta dá uma cota inferior para o tempo de evacuação
e mostra onde vale a pena colocar agentes de trânsito, liberar faixas ou evitar interdições.

## Modelagem como grafo

- **Vértices:** cruzamentos da malha viária (e os pontos onde as vias saem da área de estudo).
- **Arestas:** trechos de rua entre cruzamentos. O grafo é **direcionado**: rua de mão dupla vira duas
  arestas, uma em cada sentido, e rua de mão única vira uma.
- **Peso / capacidade:** veículos por hora naquele sentido = faixas × capacidade por faixa (depende do tipo
  da via) × fator do pavimento.
- **Origem e destino:** todos os cruzamentos dentro da zona de risco são origens, ligadas a uma super-origem
  S\*. As saídas da cidade (ou abrigos) são destinos, ligados a um super-destino T\*.
- **Hipóteses:** fluxo em regime permanente (veículos/h), sem considerar o tempo de percurso nem a
  formação de filas. As capacidades são estimativas.

## Algoritmo

Ford-Fulkerson implementado pelo grupo, sem biblioteca de grafos, com duas estratégias de busca do caminho
aumentante: DFS (versão clássica) e BFS (Edmonds-Karp), para comparação. O corte mínimo é tirado da rede
residual final e serve como certificado de que o fluxo é máximo.

## Funcionalidades previstas

- Interface web com o mapa da rede: capacidades, fluxo por rua, rede residual e corte mínimo.
- Execução passo a passo dos caminhos aumentantes.
- Seleção e edição de instâncias: carregar, importar JSON/CSV, gerar cidades sintéticas, interditar vias,
  mudar capacidades, definir a zona de risco.
- Estimativa do tempo mínimo de evacuação.
- Testes automatizados e análise do tempo de execução.

## Origem dos dados

Malha viária real do **OpenStreetMap** (Overpass API) para Brumadinho/MG e Petrópolis/RJ, com cerca de 800 a
1200 cruzamentos e mais de 2000 arestas cada. Também usaremos instâncias pequenas com resultado conhecido
(para validação), um caso sem solução e cidades sintéticas de até 10 000 cruzamentos (para teste de escala).
