/*
 * Interface do Planejador de Evacuação.
 * Responsabilidades: desenhar a rede, editar o cenário, chamar a API e
 * visualizar o resultado (fluxo, caminhos aumentantes, rede residual, corte mínimo).
 * O algoritmo de Ford-Fulkerson NÃO roda aqui: ele está em fluxo/ford_fulkerson.py.
 */
"use strict";

// ------------------------------------------------------------------ estado
const E = {
  inst: null,            // instância atual (objeto do formato JSON)
  vert: new Map(),       // id -> vértice (com wx, wy = coordenadas de mundo)
  arestas: [],           // lista de arestas da instância
  arestaPorId: new Map(),
  temReversa: new Set(), // ids de arestas que possuem aresta no sentido oposto
  origens: new Set(), destinos: new Set(),
  zona: null,            // {x, y, raio_m} em coordenadas da instância
  res: null,             // resultado do servidor
  passo: 0,              // quantos caminhos aumentantes aplicados na visualização
  fluxo: new Map(),      // fluxo por aresta no passo atual
  visao: "fluxo", modo: "selecionar",
  sel: null,             // {tipo: "v"|"e", id}
  inicioAresta: null,    // vértice inicial no modo "Nova via"
  cam: { s: 1, ox: 0, oy: 0 },
  maxCap: 1, play: null, modificada: false,
};

const $ = (id) => document.getElementById(id);
const cv = $("mapa"), ctx = cv.getContext("2d");
const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString("pt-BR"));

function status(msg, erro = false) {
  $("status").textContent = msg;
  $("status").className = erro ? "erro" : "";
}

async function api(rota, corpo) {
  const op = corpo ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) } : {};
  const r = await fetch(rota, op);
  const j = await r.json();
  if (!r.ok) throw new Error(j.erro || r.statusText);
  return j;
}

// ------------------------------------------------------------------ instância
function usarInstancia(inst) {
  E.inst = inst;
  E.vert.clear(); E.arestaPorId.clear(); E.temReversa.clear();
  // projeção: geo -> metros (equiretangular local); plano -> coordenadas como estão
  let kx = 1, ky = 1;
  if (inst.geo) {
    const lat0 = inst.vertices.reduce((s, v) => s + v.y, 0) / inst.vertices.length;
    ky = 110540; kx = 111320 * Math.cos(lat0 * Math.PI / 180);
  }
  E.kx = kx; E.ky = ky;
  for (const v of inst.vertices) { v.wx = v.x * kx; v.wy = v.y * ky; E.vert.set(String(v.id), v); }
  E.arestas = inst.arestas;
  const pares = new Set(E.arestas.map((a) => a.u + "→" + a.v));
  for (const a of E.arestas) {
    E.arestaPorId.set(a.id, a);
    if (pares.has(a.v + "→" + a.u)) E.temReversa.add(a.id);
  }
  E.maxCap = Math.max(1, ...E.arestas.map((a) => a.capacidade));
  const c = inst.cenario || {};
  E.origens = new Set((c.origens || []).map(String));
  E.destinos = new Set((c.destinos || []).map(String));
  E.zona = c.zona || null;
  if (c.veiculos != null) $("veiculos").value = c.veiculos;
  if (E.zona) $("raioZona").value = Math.round(E.zona.raio_m);
  else $("raioZona").value = inst.geo ? 800 : 1;
  E.sel = null; E.inicioAresta = null;
  limparResultado();
  $("infoInstancia").innerHTML = `<b>${esc(inst.nome)}</b><br>${esc(inst.descricao || "")}<br>
    ${fmt(inst.vertices.length)} vértices · ${fmt(inst.arestas.length)} arestas direcionadas<br>
    <i>Fonte: ${esc(inst.fonte || "—")}</i>`;
  enquadrar();
  atualizarContadores();
  renderDetalhes();
  desenhar();
  status(`Instância carregada: ${inst.nome}`);
}

function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

function instanciaAtual() {
  // devolve a instância com o cenário atualizado pela interface
  const inst = E.inst;
  inst.cenario = Object.assign({}, inst.cenario, {
    origens: [...E.origens], destinos: [...E.destinos],
    veiculos: Number($("veiculos").value) || 0, zona: E.zona,
  });
  const limpa = Object.assign({}, inst, {
    vertices: inst.vertices.map(({ wx, wy, ...r }) => r),
  });
  return limpa;
}

function marcarModificada() {
  if (E.res) { limparResultado(); status("Rede/cenário alterados — execute novamente."); }
  atualizarContadores();
  desenhar();
}

function limparResultado() {
  E.res = null; E.passo = 0; E.fluxo = new Map();
  pararPlay();
  $("resultado").innerHTML = '<p class="pequeno">Execute o algoritmo para ver o fluxo máximo.</p>';
  $("caminhos").innerHTML = "";
  $("comparacao").innerHTML = "";
  $("pSlider").max = 0; $("pSlider").value = 0; $("pRotulo").textContent = "—";
}

function atualizarContadores() {
  $("nOrigens").textContent = fmt(E.origens.size);
  $("nDestinos").textContent = fmt(E.destinos.size);
  $("nBloq").textContent = fmt(E.arestas.filter((a) => a.bloqueada).length);
}

// ------------------------------------------------------------------ execução
function estrategia() { return document.querySelector("input[name=estrategia]:checked").value; }

async function executar() {
  if (!E.inst) return;
  status("Executando Ford-Fulkerson…");
  try {
    const inst = instanciaAtual();
    const r = await api("/api/executar", { instancia: inst, origens: inst.cenario.origens, destinos: inst.cenario.destinos, estrategia: estrategia() });
    E.res = r;
    $("pSlider").max = r.caminhos.length;
    irPara(r.caminhos.length);
    renderResultado();
    renderCaminhos();
    status(`Fluxo máximo = ${fmt(r.valor)} ${E.inst.unidade} (${r.iteracoes} caminhos aumentantes, ${r.tempo_ms} ms)`);
  } catch (ex) { status("Erro: " + ex.message, true); }
}

async function comparar() {
  if (!E.inst) return;
  status("Comparando DFS e BFS…");
  try {
    const inst = instanciaAtual();
    const r = await api("/api/comparar", { instancia: inst, origens: inst.cenario.origens, destinos: inst.cenario.destinos });
    const l = (k, f) => `<tr><td>${k}</td><td>${f(r.dfs)}</td><td>${f(r.bfs)}</td></tr>`;
    $("comparacao").innerHTML = `<table><tr><th></th><th>DFS</th><th>BFS</th></tr>
      ${l("Fluxo máximo", (x) => fmt(x.valor))}
      ${l("Caminhos aumentantes", (x) => fmt(x.iteracoes))}
      ${l("Tempo (ms)", (x) => x.tempo_ms.toFixed(2))}
      ${l("Arcos/caminho (média)", (x) => x.comprimento_medio)}
      ${l("Maior gargalo", (x) => fmt(x.maior_gargalo))}
      ${l("Menor gargalo", (x) => fmt(x.menor_gargalo))}</table>
      <p class="pequeno">O valor do fluxo máximo é sempre o mesmo; muda o número de iterações e o tempo.</p>`;
    status("Comparação concluída.");
  } catch (ex) { status("Erro: " + ex.message, true); }
}

// Recalcula o fluxo após aplicar os k primeiros caminhos aumentantes
function irPara(k) {
  if (!E.res) return;
  const cams = E.res.caminhos;
  k = Math.max(0, Math.min(k, cams.length));
  E.passo = k;
  E.fluxo = new Map();
  if (k === cams.length) {
    // passo final: usa o fluxo calculado pelo servidor
    for (const [id, f] of Object.entries(E.res.fluxo_arestas)) E.fluxo.set(id, f);
  } else {
    for (let i = 0; i < k; i++) {
      const c = cams[i];
      for (const [id, sentido] of c.arcos) {
        if (id == null) continue; // arcos da super-origem/super-destino
        E.fluxo.set(id, (E.fluxo.get(id) || 0) + sentido * c.gargalo);
      }
    }
  }
  const valor = cams.slice(0, k).reduce((s, c) => s + c.gargalo, 0);
  $("pSlider").value = k;
  $("pRotulo").textContent = k === 0 ? "Fluxo inicial = 0" :
    `Após ${k}/${cams.length} caminho(s): fluxo = ${fmt(k === cams.length ? E.res.valor : valor)}`;
  document.querySelectorAll("#caminhos .cam").forEach((d) => d.classList.toggle("atual", Number(d.dataset.k) === k));
  const atual = document.querySelector(`#caminhos .cam[data-k="${k}"]`);
  if (atual) atual.scrollIntoView({ block: "nearest" });
  renderDetalhes();
  desenhar();
}

function pararPlay() { if (E.play) { clearInterval(E.play); E.play = null; $("pPlay").textContent = "⏵"; } }
function alternarPlay() {
  if (!E.res) return;
  if (E.play) return pararPlay();
  if (E.passo >= E.res.caminhos.length) irPara(0);
  const intervalo = E.res.caminhos.length > 60 ? 80 : 600;
  E.play = setInterval(() => { if (E.passo >= E.res.caminhos.length) pararPlay(); else irPara(E.passo + 1); }, intervalo);
  $("pPlay").textContent = "⏸";
}

// ------------------------------------------------------------------ painéis
function renderResultado() {
  const r = E.res, v = r.verificacao, u = E.inst.unidade;
  const chk = (b) => (b ? '<span class="ok">✔</span>' : '<span class="falha">✘</span>');
  const sat = E.arestas.filter((a) => (E.fluxo.get(a.id) || 0) >= a.capacidade && a.capacidade > 0 && !a.bloqueada).length;
  let evac = "";
  if (r.tempo_evacuacao_min != null) {
    evac = `<div><b>${fmt(r.tempo_evacuacao_min)} min</b><span>tempo mínimo p/ ${fmt(r.veiculos)} veículos</span></div>`;
  } else if (r.valor === 0) {
    evac = `<div><b class="falha">∞</b><span>sem rota de fuga</span></div>`;
  }
  $("resultado").innerHTML = `<div class="kpi">
      <div class="grande"><b>${fmt(r.valor)}</b><span>fluxo máximo (${esc(u)})</span></div>
      <div><b>${fmt(r.iteracoes)}</b><span>caminhos aumentantes</span></div>
      <div><b>${r.tempo_ms.toFixed(2)} ms</b><span>tempo do algoritmo</span></div>
      <div><b>${fmt(r.corte.length)}</b><span>vias no corte mínimo</span></div>
      <div><b>${fmt(sat)}</b><span>vias saturadas</span></div>
      ${evac}
    </div>
    <p class="pequeno">Estratégia: <b>${r.estrategia === "dfs" ? "DFS (Ford-Fulkerson clássico)" : "BFS (Edmonds-Karp)"}</b>
      · ${fmt(r.n_vertices)} vértices, ${fmt(r.n_arcos)} arcos na rede
      ${r.super_origem ? "· super-origem S*" : ""} ${r.super_destino ? "· super-destino T*" : ""}</p>
    <table>
      <tr><td>Capacidade respeitada (0 ≤ f ≤ c)</td><td>${chk(v.capacidade)}</td></tr>
      <tr><td>Conservação de fluxo nos cruzamentos</td><td>${chk(v.conservacao)}</td></tr>
      <tr><td>Saída da origem = chegada no destino</td><td>${chk(v.valor_confere)}</td></tr>
      <tr><td>Capacidade do corte (${fmt(r.capacidade_corte)}) = fluxo</td><td>${chk(v.corte_igual_fluxo)}</td></tr>
    </table>
    ${r.valor === 0 ? '<div class="aviso">Não existe caminho da zona de risco até nenhum destino. Verifique vias interditadas ou mãos de direção.</div>' : ""}
    ${r.corte.length ? `<p class="pequeno"><b>Gargalos (corte mínimo)</b> — aumentar a capacidade destas vias é o que pode aumentar o fluxo:</p>
      <table>${r.corte.slice(0, 15).map((id) => { const a = E.arestaPorId.get(id);
        return `<tr data-e="${esc(id)}" class="lnk"><td>${esc(a.nome || id)}</td><td>${fmt(a.capacidade)}</td></tr>`; }).join("")}</table>` : ""}`;
  $("resultado").querySelectorAll("tr.lnk").forEach((tr) => tr.onclick = () => { E.sel = { tipo: "e", id: tr.dataset.e }; centralizarEm(E.sel); renderDetalhes(); desenhar(); });
}

function renderCaminhos() {
  const cams = E.res.caminhos;
  const pequeno = E.arestas.length <= 120;
  const lim = Math.min(cams.length, 400);
  let html = `<div class="cam" data-k="0">Fluxo inicial (0)</div>`;
  for (let i = 0; i < lim; i++) {
    const c = cams[i];
    const canc = c.arcos.filter(([id, s]) => s < 0).length;
    html += `<div class="cam" data-k="${i + 1}"><b>#${i + 1}</b> gargalo <b>${fmt(c.gargalo)}</b> · ${c.arcos.length} arcos
      ${canc ? `<span class="tag">${canc} cancelamento(s)</span>` : ""}
      ${pequeno ? `<small>${c.vertices.map(rotuloV).join(" → ")}</small>` : ""}</div>`;
  }
  if (cams.length > lim) html += `<p class="pequeno">… mais ${cams.length - lim} caminhos (use o controle deslizante).</p>`;
  if (E.res.caminhos_omitidos) html += `<p class="pequeno">${E.res.caminhos_omitidos} caminhos não foram enviados pelo servidor.</p>`;
  if (!cams.length) html += `<p class="pequeno">Nenhum caminho aumentante encontrado.</p>`;
  $("caminhos").innerHTML = html;
  $("caminhos").querySelectorAll(".cam").forEach((d) => d.onclick = () => { pararPlay(); irPara(Number(d.dataset.k)); });
}

function rotuloV(id) { const v = E.vert.get(String(id)); return esc(v && v.rotulo ? v.rotulo : id); }

function renderDetalhes() {
  const d = $("detalhes");
  if (!E.sel) { d.innerHTML = '<p class="pequeno">Clique em uma via ou cruzamento.</p>'; return; }
  if (E.sel.tipo === "e") {
    const a = E.arestaPorId.get(E.sel.id);
    if (!a) { E.sel = null; return renderDetalhes(); }
    const f = E.fluxo.get(a.id) || 0;
    const noCorte = E.res && E.res.corte.includes(a.id);
    d.innerHTML = `<p><b>${esc(a.nome || "(sem nome)")}</b> <span class="tag">${esc(a.tipo || "via")}</span>
        ${noCorte ? '<span class="tag corte">corte mínimo</span>' : ""} ${a.bloqueada ? '<span class="tag bloq">interditada</span>' : ""}</p>
      <table>
        <tr><td>Aresta</td><td>${esc(a.id)}: ${rotuloV(a.u)} → ${rotuloV(a.v)}</td></tr>
        ${a.comprimento_m ? `<tr><td>Comprimento</td><td>${fmt(Math.round(a.comprimento_m))} m</td></tr>` : ""}
        <tr><td>Capacidade c</td><td>${fmt(a.capacidade)}</td></tr>
        <tr><td>Fluxo f</td><td>${fmt(f)} ${a.capacidade ? `(${Math.round(100 * f / a.capacidade)}%)` : ""}</td></tr>
        <tr><td>Residual direto c−f</td><td>${fmt(a.capacidade - f)}</td></tr>
        <tr><td>Residual reverso f</td><td>${fmt(f)}</td></tr>
      </table>
      <div class="linha"><input type="number" id="novaCap" value="${a.capacidade}" min="0" style="width:90px">
        <button id="btnCap">Alterar capacidade</button></div>
      <div class="linha"><button id="btnBloq">${a.bloqueada ? "Liberar via" : "Interditar via"}</button>
        <button id="btnRem">Remover aresta</button></div>`;
    $("btnCap").onclick = () => {
      const c = Math.round(Number($("novaCap").value));
      if (!(c >= 0)) return status("Capacidade inválida", true);
      a.capacidade = c; E.maxCap = Math.max(1, ...E.arestas.map((x) => x.capacidade)); marcarModificada(); renderDetalhes();
    };
    $("btnBloq").onclick = () => { alternarBloqueio(a); renderDetalhes(); };
    $("btnRem").onclick = () => { removerAresta(a); };
  } else {
    const v = E.vert.get(E.sel.id);
    if (!v) { E.sel = null; return renderDetalhes(); }
    let ent = 0, sai = 0, grauE = 0, grauS = 0;
    for (const a of E.arestas) {
      if (a.v === v.id) { ent += E.fluxo.get(a.id) || 0; grauE++; }
      if (a.u === v.id) { sai += E.fluxo.get(a.id) || 0; grauS++; }
    }
    const ladoS = E.res && E.res.lado_s.includes(v.id);
    d.innerHTML = `<p><b>${rotuloV(v.id)}</b> ${E.origens.has(v.id) ? '<span class="tag">origem</span>' : ""}
        ${E.destinos.has(v.id) ? '<span class="tag">destino</span>' : ""} ${v.saida ? '<span class="tag">saída da área</span>' : ""}</p>
      <table><tr><td>Id</td><td>${esc(v.id)}</td></tr>
        <tr><td>Grau entrada/saída</td><td>${grauE} / ${grauS}</td></tr>
        <tr><td>Fluxo que entra</td><td>${fmt(ent)}</td></tr><tr><td>Fluxo que sai</td><td>${fmt(sai)}</td></tr>
        ${E.res ? `<tr><td>Lado do corte</td><td>${ladoS ? "S (alcançável da origem)" : "T"}</td></tr>` : ""}</table>
      <div class="linha"><button id="btnVO">${E.origens.has(v.id) ? "Remover origem" : "Tornar origem"}</button>
        <button id="btnVD">${E.destinos.has(v.id) ? "Remover destino" : "Tornar destino"}</button></div>`;
    $("btnVO").onclick = () => { alternar(E.origens, E.destinos, v.id); renderDetalhes(); };
    $("btnVD").onclick = () => { alternar(E.destinos, E.origens, v.id); renderDetalhes(); };
  }
}

// ------------------------------------------------------------------ edição
function alternar(conj, outro, id) { if (conj.has(id)) conj.delete(id); else { conj.add(id); outro.delete(id); } marcarModificada(); }

function alternarBloqueio(a) {
  const novo = !a.bloqueada;
  for (const b of E.arestas) if ((b.u === a.u && b.v === a.v) || (b.u === a.v && b.v === a.u)) b.bloqueada = novo;
  status(`${a.nome || a.id}: ${novo ? "interditada" : "liberada"} (os dois sentidos)`);
  marcarModificada();
}

function removerAresta(a) {
  E.arestas.splice(E.arestas.indexOf(a), 1);
  E.arestaPorId.delete(a.id);
  E.temReversa.delete(a.id);
  for (const b of E.arestas) if (b.u === a.v && b.v === a.u) E.temReversa.delete(b.id);
  E.sel = null; renderDetalhes(); marcarModificada();
}

function novaAresta(u, v) {
  const cap = Math.max(1, Math.round(Number($("capNova").value) || 1));
  let n = E.arestas.length;
  const novoId = () => { while (E.arestaPorId.has("n" + n)) n++; return "n" + n; };
  const add = (x, y) => { const a = { id: novoId(), u: x, v: y, capacidade: cap, nome: "Nova via", tipo: "nova" }; E.arestas.push(a); E.arestaPorId.set(a.id, a); return a; };
  const a = add(u, v);
  if ($("maoDupla").checked) { const b = add(v, u); E.temReversa.add(a.id); E.temReversa.add(b.id); }
  E.maxCap = Math.max(E.maxCap, cap);
  status(`Via criada: ${rotuloV(u)} → ${rotuloV(v)} (${cap})`);
  marcarModificada();
}

function definirZona(wx, wy) {
  const raio = Number($("raioZona").value) || 1;
  E.zona = { x: wx / E.kx, y: wy / E.ky, raio_m: raio };
  E.origens = new Set();
  for (const v of E.inst.vertices) if (Math.hypot(v.wx - wx, v.wy - wy) <= raio) { E.origens.add(v.id); E.destinos.delete(v.id); }
  status(`Zona de risco: ${E.origens.size} cruzamentos marcados como origem`);
  marcarModificada();
}

// ------------------------------------------------------------------ desenho
function aTela(v) { return [v.wx * E.cam.s + E.cam.ox, -v.wy * E.cam.s + E.cam.oy]; }
function doMundo(px, py) { return [(px - E.cam.ox) / E.cam.s, -(py - E.cam.oy) / E.cam.s]; }

function enquadrar() {
  if (!E.inst) return;
  redimensionar();
  const xs = E.inst.vertices.map((v) => v.wx), ys = E.inst.vertices.map((v) => v.wy);
  const minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys);
  const W = cv.clientWidth, H = cv.clientHeight, m = 60;
  const s = Math.min((W - 2 * m) / Math.max(maxx - minx, 1e-9), (H - 2 * m) / Math.max(maxy - miny, 1e-9));
  E.cam.s = s;
  E.cam.ox = W / 2 - s * (minx + maxx) / 2;
  E.cam.oy = H / 2 + s * (miny + maxy) / 2;
  desenhar();
}

function centralizarEm(sel) {
  let x, y;
  if (sel.tipo === "v") { const v = E.vert.get(sel.id); x = v.wx; y = v.wy; }
  else { const a = E.arestaPorId.get(sel.id); const p = E.vert.get(a.u), q = E.vert.get(a.v); x = (p.wx + q.wx) / 2; y = (p.wy + q.wy) / 2; }
  E.cam.ox = cv.clientWidth / 2 - x * E.cam.s;
  E.cam.oy = cv.clientHeight / 2 + y * E.cam.s;
}

function redimensionar() {
  const dpr = window.devicePixelRatio || 1;
  cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function corUtilizacao(r) {
  // 0 -> azul-esverdeado; 1 -> vermelho (saturado)
  if (r >= 0.999) return "#d7191c";
  const pts = [[0, [44, 162, 95]], [0.5, [254, 196, 79]], [1, [230, 85, 13]]];
  let i = r < 0.5 ? 0 : 1;
  const [r0, c0] = pts[i], [r1, c1] = pts[i + 1], t = (r - r0) / (r1 - r0);
  return `rgb(${c0.map((c, k) => Math.round(c + (c1[k] - c) * t)).join(",")})`;
}

function caminhoDestacado() {
  if (!E.res || E.passo === 0 || E.passo > E.res.caminhos.length) return null;
  if (E.passo === E.res.caminhos.length && E.res.caminhos.length > 1 && !E.mostrarUltimo) return null;
  return E.res.caminhos[E.passo - 1];
}

function desenhar() {
  const W = cv.clientWidth, H = cv.clientHeight;
  ctx.clearRect(0, 0, W, H);
  if (!E.inst) return;
  const pequeno = E.arestas.length <= 60;
  const rotulos = $("chkRotulos").checked || pequeno;
  const final = E.res && E.passo === E.res.caminhos.length; // o corte mínimo só vale para o fluxo final
  const corte = new Set(final && $("chkCorte").checked ? E.res.corte : []);
  const cam = caminhoDestacado();
  const noCaminho = new Map();
  if (cam) for (const [id, s] of cam.arcos) if (id != null) noCaminho.set(id, s);
  const s = E.cam.s;
  const desloc = pequeno ? 6 : Math.min(3, Math.max(0.6, s * 3));

  // zona de risco
  if (E.zona) {
    const c = aTela({ wx: E.zona.x * E.kx, wy: E.zona.y * E.ky });
    ctx.beginPath(); ctx.arc(c[0], c[1], E.zona.raio_m * s, 0, 2 * Math.PI);
    ctx.fillStyle = "rgba(215,25,28,0.07)"; ctx.fill();
    ctx.strokeStyle = "rgba(215,25,28,0.5)"; ctx.setLineDash([6, 4]); ctx.lineWidth = 1.5; ctx.stroke(); ctx.setLineDash([]);
  }

  const maxFluxo = Math.max(1, ...E.fluxo.values());
  const desenhos = [];
  for (const a of E.arestas) {
    const p = E.vert.get(a.u), q = E.vert.get(a.v);
    let [x1, y1] = aTela(p), [x2, y2] = aTela(q);
    if (Math.max(x1, x2) < -20 || Math.min(x1, x2) > W + 20 || Math.max(y1, y2) < -20 || Math.min(y1, y2) > H + 20) continue;
    const dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1;
    const nx = -dy / L, ny = dx / L; // normal à direita do sentido
    const off = E.temReversa.has(a.id) ? desloc : 0;
    x1 += nx * off; y1 += ny * off; x2 += nx * off; y2 += ny * off;
    const f = E.fluxo.get(a.id) || 0;
    const base = { a, x1, y1, x2, y2, L, nx, ny, f };
    if (a.bloqueada) { desenhos.push(Object.assign(base, { cor: "#b42318", w: 2, tracejado: [3, 3], z: 1 })); continue; }

    if (E.visao === "capacidade") {
      desenhos.push(Object.assign(base, { cor: "#5b7083", w: 0.6 + 4 * a.capacidade / E.maxCap, z: 0, rot: fmt(a.capacidade) }));
    } else if (E.visao === "fluxo") {
      if (f > 0) desenhos.push(Object.assign(base, { cor: corUtilizacao(f / a.capacidade), w: 1.2 + 4.5 * f / maxFluxo, z: 2, rot: `${fmt(f)}/${fmt(a.capacidade)}` }));
      else desenhos.push(Object.assign(base, { cor: "#c9d0d8", w: 0.8, z: 0, rot: `0/${fmt(a.capacidade)}` }));
    } else { // residual: arco direto c-f (azul) e arco reverso f (laranja, sentido oposto)
      const rf = a.capacidade - f;
      if (rf > 0) desenhos.push(Object.assign(base, { cor: "#2b83ba", w: 0.8 + 3 * rf / E.maxCap, z: 1, rot: fmt(rf) }));
      else desenhos.push(Object.assign(base, { cor: "#e3e7ec", w: 0.6, z: 0 }));
      if (f > 0) {
        const o = off + desloc + 1.5;
        const [ax, ay] = aTela(p), [bx, by] = aTela(q);
        desenhos.push({ a, x1: bx - nx * o, y1: by - ny * o, x2: ax - nx * o, y2: ay - ny * o, L, nx: -nx, ny: -ny, f,
          cor: "#f28e2b", w: 0.8 + 3 * f / E.maxCap, z: 2, tracejado: [5, 3], rot: fmt(f) });
      }
    }
  }
  desenhos.sort((p, q) => p.z - q.z);
  for (const d of desenhos) linha(d, d.cor, d.w, d.tracejado);
  // corte mínimo
  for (const d of desenhos) if (corte.has(d.a.id) && d.cor !== "#f28e2b") { linha(d, "rgba(197,27,138,0.35)", d.w + 7); linha(d, "#c51b8a", Math.max(2.5, d.w)); }
  // caminho aumentante destacado
  for (const d of desenhos) if (noCaminho.has(d.a.id) && (noCaminho.get(d.a.id) > 0) === (d.cor !== "#f28e2b") ) {
    linha(d, "rgba(0,168,107,0.3)", 10); linha(d, "#00a86b", 3.5, noCaminho.get(d.a.id) < 0 ? [6, 4] : null);
  }
  // seleção
  if (E.sel && E.sel.tipo === "e") for (const d of desenhos) if (d.a.id === E.sel.id) linha(d, "#111", d.w + 3);
  // setas e rótulos
  for (const d of desenhos) {
    if (d.L > 28 && (pequeno || s > 0.5 || d.L > 60)) seta(d, d.cor === "#e3e7ec" ? "#c9d0d8" : d.cor, pequeno ? 9 : 6);
    if (rotulos && d.rot && d.L > 50) rotulo(d);
  }

  // vértices
  const raio = pequeno ? 21 : Math.max(1.6, Math.min(5, s * 4));
  const ladoS = new Set(final && $("chkCorte").checked ? E.res.lado_s : []);
  for (const v of E.inst.vertices) {
    const [x, y] = aTela(v);
    if (x < -20 || x > W + 20 || y < -20 || y > H + 20) continue;
    const ehO = E.origens.has(v.id), ehD = E.destinos.has(v.id);
    let r = raio, cor = ladoS.has(v.id) && !ehO ? "#cfe8d6" : "#8794a3";
    if (pequeno) cor = ladoS.has(v.id) ? "#dff3e5" : "#fff";
    if (ehO) { cor = "#1a9850"; r = raio * (pequeno ? 1 : 1.3); }
    if (ehD) { cor = "#2166ac"; r = raio * (pequeno ? 1 : 1.9); }
    ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fillStyle = cor; ctx.fill();
    if (pequeno || ehD || v.saida) { ctx.lineWidth = v.saida && !ehD ? 2 : 1.2; ctx.strokeStyle = v.saida && !ehD ? "#2166ac" : "#33414f"; ctx.stroke(); }
    if (E.sel && E.sel.tipo === "v" && E.sel.id === v.id) { ctx.lineWidth = 3; ctx.strokeStyle = "#111"; ctx.stroke(); }
    if (E.inicioAresta === v.id) { ctx.lineWidth = 3; ctx.strokeStyle = "#ff7f00"; ctx.stroke(); }
    if (pequeno) {
      ctx.fillStyle = ehO || ehD ? "#fff" : "#1d2430"; ctx.font = "600 10px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const t = String(v.rotulo || v.id); ctx.fillText(t.length > 7 ? t.slice(0, 6) + "…" : t, x, y);
    }
  }
  if (pequeno) for (const v of E.inst.vertices) { // nome completo abaixo
    const t = String(v.rotulo || v.id); if (t.length <= 7) continue;
    const [x, y] = aTela(v); ctx.fillStyle = "#1d2430"; ctx.font = "11px sans-serif"; ctx.fillText(t, x, y + raio + 9);
  }
  renderLegenda();
}

function linha(d, cor, w, tracejado) {
  ctx.beginPath(); ctx.moveTo(d.x1, d.y1); ctx.lineTo(d.x2, d.y2);
  ctx.strokeStyle = cor; ctx.lineWidth = w; ctx.setLineDash(tracejado || []); ctx.stroke(); ctx.setLineDash([]);
}

function seta(d, cor, tam) {
  const t = d.L > 80 ? 0.6 : 0.72;
  const x = d.x1 + (d.x2 - d.x1) * t, y = d.y1 + (d.y2 - d.y1) * t;
  const ux = (d.x2 - d.x1) / d.L, uy = (d.y2 - d.y1) / d.L;
  ctx.beginPath(); ctx.moveTo(x + ux * tam, y + uy * tam);
  ctx.lineTo(x - ux * tam * 0.6 + uy * tam * 0.6, y - uy * tam * 0.6 - ux * tam * 0.6);
  ctx.lineTo(x - ux * tam * 0.6 - uy * tam * 0.6, y - uy * tam * 0.6 + ux * tam * 0.6);
  ctx.closePath(); ctx.fillStyle = cor; ctx.fill();
}

function rotulo(d) {
  const x = (d.x1 + d.x2) / 2 + d.nx * 9, y = (d.y1 + d.y2) / 2 + d.ny * 9;
  ctx.font = "11px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  const w = ctx.measureText(d.rot).width + 6;
  ctx.fillStyle = "rgba(255,255,255,0.88)"; ctx.fillRect(x - w / 2, y - 7, w, 14);
  ctx.fillStyle = "#1d2430"; ctx.fillText(d.rot, x, y);
}

function renderLegenda() {
  const v = E.visao;
  let h = "";
  if (v === "capacidade") h += `<div><i style="background:#5b7083"></i>espessura ∝ capacidade (veíc/h)</div>`;
  if (v === "fluxo") h += `<div><i style="background:#c9d0d8"></i>sem fluxo</div><div><i style="background:linear-gradient(90deg,#2ca25f,#fec44f,#e6550d)"></i>utilização f/c</div><div><i style="background:#d7191c"></i>saturada (f = c)</div>`;
  if (v === "residual") h += `<div><i style="background:#2b83ba"></i>residual direto c − f</div><div><i style="background:#f28e2b"></i>residual reverso f (sentido oposto)</div>`;
  if (E.res && E.passo === E.res.caminhos.length && $("chkCorte").checked) h += `<div><i style="background:#c51b8a"></i>corte mínimo (gargalo)</div>`;
  if (caminhoDestacado()) h += `<div><i style="background:#00a86b"></i>caminho aumentante atual (tracejado = cancela fluxo)</div>`;
  h += `<div><i style="background:#b42318"></i>via interditada</div>`;
  h += `<div><b class="p" style="background:#1a9850"></b>origem (zona de risco) <b class="p" style="background:#2166ac;margin-left:6px"></b>destino</div>`;
  $("legenda").innerHTML = h;
}

// ------------------------------------------------------------------ interação no mapa
function maisProximo(px, py) {
  let melhorV = null, dv = 9;
  for (const v of E.inst.vertices) {
    const [x, y] = aTela(v); const d = Math.hypot(x - px, y - py);
    if (d < dv) { dv = d; melhorV = v; }
  }
  if (melhorV) return { tipo: "v", id: melhorV.id };
  let melhorE = null, de = 6;
  for (const a of E.arestas) {
    const p = E.vert.get(a.u), q = E.vert.get(a.v);
    let [x1, y1] = aTela(p), [x2, y2] = aTela(q);
    const dx = x2 - x1, dy = y2 - y1, L2 = dx * dx + dy * dy || 1;
    if (E.temReversa.has(a.id)) { // considera o deslocamento lateral
      const L = Math.sqrt(L2), off = E.arestas.length <= 60 ? 6 : Math.min(3, Math.max(0.6, E.cam.s * 3));
      x1 += -dy / L * off; y1 += dx / L * off; x2 += -dy / L * off; y2 += dx / L * off;
    }
    const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / L2));
    const d = Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
    if (d < de) { de = d; melhorE = a; }
  }
  return melhorE ? { tipo: "e", id: melhorE.id } : null;
}

function clique(px, py) {
  if (!E.inst) return;
  const alvo = maisProximo(px, py);
  switch (E.modo) {
    case "selecionar": E.sel = alvo; renderDetalhes(); break;
    case "origem": if (alvo && alvo.tipo === "v") alternar(E.origens, E.destinos, alvo.id); break;
    case "destino": if (alvo && alvo.tipo === "v") alternar(E.destinos, E.origens, alvo.id); break;
    case "zona": { const [wx, wy] = doMundo(px, py); definirZona(wx, wy); break; }
    case "bloquear": if (alvo && alvo.tipo === "e") alternarBloqueio(E.arestaPorId.get(alvo.id)); break;
    case "aresta":
      if (!alvo || alvo.tipo !== "v") break;
      if (!E.inicioAresta) { E.inicioAresta = alvo.id; status("Agora clique no cruzamento final da nova via"); }
      else if (E.inicioAresta !== alvo.id) { novaAresta(E.inicioAresta, alvo.id); E.inicioAresta = null; }
      break;
  }
  desenhar();
}

let arrasto = null;
cv.addEventListener("mousedown", (ev) => { arrasto = { x: ev.offsetX, y: ev.offsetY, ox: E.cam.ox, oy: E.cam.oy, moveu: false }; });
cv.addEventListener("mousemove", (ev) => {
  if (arrasto) {
    const dx = ev.offsetX - arrasto.x, dy = ev.offsetY - arrasto.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) arrasto.moveu = true;
    if (arrasto.moveu) { E.cam.ox = arrasto.ox + dx; E.cam.oy = arrasto.oy + dy; cv.style.cursor = "grabbing"; desenhar(); }
    return;
  }
  if (!E.inst) return;
  const alvo = maisProximo(ev.offsetX, ev.offsetY);
  const dica = $("dica");
  if (!alvo) { dica.style.display = "none"; return; }
  let t;
  if (alvo.tipo === "v") { const v = E.vert.get(alvo.id); t = `${v.rotulo || v.id}${E.origens.has(v.id) ? " · origem" : ""}${E.destinos.has(v.id) ? " · destino" : ""}${v.saida ? " · saída" : ""}`; }
  else { const a = E.arestaPorId.get(alvo.id); const f = E.fluxo.get(a.id) || 0; t = `${a.nome || a.id} · f/c = ${fmt(f)}/${fmt(a.capacidade)}${a.bloqueada ? " · interditada" : ""}`; }
  dica.textContent = t; dica.style.display = "block";
  dica.style.left = ev.offsetX + 14 + "px"; dica.style.top = ev.offsetY + 10 + "px";
});
window.addEventListener("mouseup", (ev) => {
  if (arrasto && !arrasto.moveu && ev.target === cv) clique(ev.offsetX, ev.offsetY);
  arrasto = null; cv.style.cursor = "grab";
});
cv.addEventListener("mouseleave", () => { $("dica").style.display = "none"; });
cv.addEventListener("wheel", (ev) => {
  ev.preventDefault();
  const k = Math.exp(-ev.deltaY * 0.0015);
  E.cam.ox = ev.offsetX - (ev.offsetX - E.cam.ox) * k;
  E.cam.oy = ev.offsetY - (ev.offsetY - E.cam.oy) * k;
  E.cam.s *= k; desenhar();
}, { passive: false });
window.addEventListener("resize", () => { redimensionar(); desenhar(); });

// ------------------------------------------------------------------ botões
document.querySelectorAll("#modos button").forEach((b) => b.onclick = () => {
  document.querySelectorAll("#modos button").forEach((x) => x.classList.remove("ativo"));
  b.classList.add("ativo"); E.modo = b.dataset.modo; E.inicioAresta = null;
  const dicas = { selecionar: "Clique para ver detalhes.", origem: "Clique em cruzamentos para marcar origens.", destino: "Clique em cruzamentos para marcar destinos.",
    zona: "Clique no centro da zona de risco (raio no campo ao lado).", bloquear: "Clique em uma via para interditar/liberar.", aresta: "Clique no cruzamento inicial da nova via." };
  status(dicas[E.modo]); desenhar();
});
document.querySelectorAll("#abasVisao button").forEach((b) => b.onclick = () => {
  document.querySelectorAll("#abasVisao button").forEach((x) => x.classList.remove("ativo"));
  b.classList.add("ativo"); E.visao = b.dataset.visao; desenhar();
});
$("chkCorte").onchange = desenhar; $("chkRotulos").onchange = desenhar;
$("btnEnquadrar").onclick = enquadrar;
$("btnExecutar").onclick = executar;
$("btnComparar").onclick = comparar;
$("pInicio").onclick = () => { pararPlay(); irPara(0); };
$("pAnt").onclick = () => { pararPlay(); E.mostrarUltimo = true; irPara(E.passo - 1); };
$("pProx").onclick = () => { pararPlay(); E.mostrarUltimo = true; irPara(E.passo + 1); };
$("pFim").onclick = () => { pararPlay(); E.mostrarUltimo = false; irPara(E.res ? E.res.caminhos.length : 0); };
$("pPlay").onclick = () => { E.mostrarUltimo = true; alternarPlay(); };
$("pSlider").oninput = (ev) => { pararPlay(); E.mostrarUltimo = true; irPara(Number(ev.target.value)); };
$("btnSaidas").onclick = () => {
  if (!E.inst) return;
  E.destinos = new Set(E.inst.vertices.filter((v) => v.saida && !E.origens.has(v.id)).map((v) => v.id));
  status(`${E.destinos.size} pontos de saída marcados como destino`); marcarModificada();
};
$("btnLimpar").onclick = () => { E.origens.clear(); E.destinos.clear(); E.zona = null; marcarModificada(); };
$("veiculos").onchange = () => { if (E.res) marcarModificada(); };

$("btnCarregar").onclick = async () => {
  try { usarInstancia(await api("/api/instancias/" + encodeURIComponent($("selInstancia").value))); }
  catch (ex) { status("Erro: " + ex.message, true); }
};
$("selInstancia").onchange = () => $("btnCarregar").click();
$("btnGerar").onclick = async () => {
  status("Gerando cidade sintética…");
  try {
    usarInstancia(await api("/api/gerar", {
      linhas: +$("gLinhas").value, colunas: +$("gColunas").value, semente: +$("gSemente").value,
      prob_mao_unica: $("gMaoUnica").value / 100, prob_remocao: $("gRemocao").value / 100, raio_zona: +$("gRaio").value,
      veiculos: +$("veiculos").value || 5000,
    }));
  } catch (ex) { status("Erro: " + ex.message, true); }
};
$("arqImportar").onchange = async (ev) => {
  const arq = ev.target.files[0]; if (!arq) return;
  const texto = await arq.text();
  const formato = arq.name.toLowerCase().endsWith(".csv") ? "csv" : "json";
  try { usarInstancia(await api("/api/importar", { formato, texto })); }
  catch (ex) { status("Erro ao importar: " + ex.message, true); }
  ev.target.value = "";
};
$("btnExportar").onclick = () => {
  if (!E.inst) return;
  const blob = new Blob([JSON.stringify(instanciaAtual(), null, 1)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = (E.inst.nome || "instancia").normalize("NFD").replace(/[^\w]+/g, "_").toLowerCase() + ".json";
  a.click(); URL.revokeObjectURL(a.href);
};
document.addEventListener("keydown", (ev) => {
  if (ev.target.tagName === "INPUT" || ev.target.tagName === "SELECT") return;
  if (ev.key === "ArrowRight") $("pProx").click();
  if (ev.key === "ArrowLeft") $("pAnt").click();
  if (ev.key === " ") { ev.preventDefault(); $("pPlay").click(); }
  if (ev.key === "Enter") executar();
});

// ------------------------------------------------------------------ início
(async function iniciar() {
  redimensionar();
  try {
    const lista = await api("/api/instancias");
    $("selInstancia").innerHTML = lista.map((i) => `<option value="${esc(i.arquivo)}">${esc(i.nome)} (${i.n_vertices} V, ${i.n_arestas} E)</option>`).join("");
    // parâmetros opcionais de URL: ?instancia=03_brumadinho.json&estrategia=bfs&visao=residual&executar=1&passo=2
    const q = new URLSearchParams(location.search);
    if (q.get("instancia")) $("selInstancia").value = q.get("instancia");
    if (q.get("estrategia")) document.querySelector(`input[name=estrategia][value=${q.get("estrategia") === "bfs" ? "bfs" : "dfs"}]`).checked = true;
    if (q.get("visao")) { const b = document.querySelector(`#abasVisao button[data-visao="${q.get("visao")}"]`); if (b) b.click(); }
    if (lista.length) usarInstancia(await api("/api/instancias/" + encodeURIComponent($("selInstancia").value)));
    if (q.get("executar")) {
      await executar();
      if (q.get("passo")) { E.mostrarUltimo = true; irPara(Number(q.get("passo"))); }
    }
  } catch (ex) { status("Erro ao conectar ao servidor: " + ex.message, true); }
})();
