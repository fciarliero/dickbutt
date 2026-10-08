"use strict";

const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
const $ = (id) => document.getElementById(id);

let ws = null;
let myId = null;
let arena = null;
let cfg = null;
let snaps = []; // [{time, state}]
let latest = null;
let cam = { x: 1200, y: 800, zoom: 0.5 };
const input = { l: 0, r: 0, u: 0, b: 0 };
let latestTime = 0;

// ------------------------------------------------------------------ conexión
$("joinForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const name = $("name").value.trim();
  store("name", name);
  connect(name, e.submitter && e.submitter.dataset.mode);
});

// Con servidor Python es un WebSocket; en GitHub Pages (p2p.js) es una conexión P2P
// con la misma interfaz. mode solo importa en P2P: "host", "join" o "code".
function openTransport(mode) {
  if (window.P2P) return P2P.open(mode || P2P.defaultMode);
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return new WebSocket(`${proto}://${location.host}/ws`);
}

function connect(name, mode) {
  if (ws && ws.readyState === 0) return; // ya se está conectando
  $("err").textContent = "";
  ws = openTransport(mode);
  ws.onopen = () => ws.send(JSON.stringify({ t: "join", name }));
  ws.onmessage = (ev) => onMessage(JSON.parse(ev.data));
  ws.onclose = (ev) => {
    $("join").style.display = "grid";
    $("net").style.display = "none";
    if (ev && ev.reason) $("err").textContent = ev.reason;
    else if (myId) $("err").textContent = "Se cortó la conexión.";
    myId = null;
    snaps = [];
    pred = null;
    ownSmooth = null;
    net.rtt = null;
  };
}

function onMessage(msg) {
  if (msg.t === "welcome") {
    if (CLIENT_VERSION && msg.version !== CLIENT_VERSION) return reloadForUpdate();
    myId = msg.id;
    try { sessionStorage.removeItem("updateTries"); } catch { /* sin storage */ }
    arena = msg.arena;
    cfg = msg.config;
    $("join").style.display = "none";
    $("net").style.display = "block";
    cam = { x: arena.w / 2, y: arena.h / 2, zoom: 0.5 };
  } else if (msg.t === "error") {
    if (myId) showEvent({ kind: "error", msg: msg.msg });
    else $("err").textContent = msg.msg;
  } else if (msg.t === "pong") {
    onPong(msg.c);
  } else if (msg.t === "state") {
    onSnapshotTiming(performance.now());
    snaps.push({ time: performance.now(), state: msg });
    if (snaps.length > 30) snaps.shift();
    latest = msg;
    latestTime = performance.now();
    if (msg.events) msg.events.forEach(showEvent);
    updateHud(msg);
  }
}

// -------------------------------------------------------------------- input
const KEYS = { ArrowLeft: "l", KeyA: "l", ArrowRight: "r", KeyD: "r", ArrowUp: "u", KeyW: "u", Space: "b" };

function setKey(code, down) {
  const k = KEYS[code];
  if (!k || input[k] === down) return false;
  input[k] = down;
  if (k === "b" && down) predictBoost();
  if (ws && ws.readyState === 1 && myId) ws.send(JSON.stringify({ t: "input", ...input }));
  return true;
}
addEventListener("keydown", (e) => { if (KEYS[e.code] && myId) { e.preventDefault(); setKey(e.code, 1); } });
addEventListener("keyup", (e) => setKey(e.code, 0));
addEventListener("blur", () => Object.keys(KEYS).forEach((c) => setKey(c, 0)));

// --------------------------------------------------------------------- bots
function sendCmd(t) {
  if (ws && ws.readyState === 1 && myId) ws.send(JSON.stringify({ t }));
}
for (const [id, cmd] of [["botPlus", "add_bot"], ["botMinus", "remove_bot"]]) {
  $(id).addEventListener("click", (e) => { sendCmd(cmd); e.currentTarget.blur(); });
}

// ------------------------------------------------------------ nombre guardado
function store(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* sin storage: no se recuerda */ }
}
function recall(key) {
  try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
}
const savedName = recall("name");
if (typeof savedName === "string" && !$("name").value) $("name").value = savedName;

// ----------------------------------------------------------------- versión
// Si el servidor tiene otra versión del cliente (se reinició con cambios), recargar y
// volver a entrar solo. El guardia evita un bucle si la recarga no trae la versión nueva.
const CLIENT_VERSION = (document.querySelector('meta[name="client-version"]') || {}).content;

function reloadForUpdate() {
  ws.onclose = null;
  ws.close();
  let tries = 0;
  try { tries = Number(sessionStorage.getItem("updateTries")) || 0; } catch { /* sin storage */ }
  if (tries >= 2) {
    $("err").textContent = window.P2P ? "Tu versión del juego no es la del host: recarguen los dos con Ctrl+F5."
      : "Hay una versión nueva del juego: recargá con Ctrl+F5.";
    return;
  }
  try {
    sessionStorage.setItem("updateTries", String(tries + 1));
    sessionStorage.setItem("autojoin", "join");
  } catch { /* sin storage: el jugador vuelve a tocar Entrar */ }
  location.reload();
}

try {
  const mode = sessionStorage.getItem("autojoin");
  if (mode) {
    sessionStorage.removeItem("autojoin");
    connect($("name").value.trim(), mode);
  }
} catch { /* sin storage */ }

// ------------------------------------------------------------ red y latencia
const net = { rtt: null, gap: 1000 / 30, jitter: 4, lastRecv: 0, delay: 60 };

setInterval(() => {
  if (ws && ws.readyState === 1 && myId) ws.send(JSON.stringify({ t: "ping", c: performance.now() }));
}, 1000);

function onPong(sent) {
  const sample = performance.now() - sent;
  net.rtt = net.rtt === null ? sample : net.rtt + (sample - net.rtt) * 0.25;
  const ms = Math.round(net.rtt);
  const el = $("ping");
  el.textContent = `${ms} ms`;
  el.style.color = ms < 80 ? "#7cf08a" : ms < 150 ? "#f5e663" : "#ff7a59";
}

// El buffer de interpolación se adapta: cubre el intervalo entre snapshots más su variación.
function onSnapshotTiming(now) {
  if (net.lastRecv) {
    const gap = now - net.lastRecv;
    net.gap += (gap - net.gap) * 0.05;
    net.jitter += (Math.abs(gap - net.gap) - net.jitter) * 0.05;
  }
  net.lastRecv = now;
  const target = Math.min(150, Math.max(35, net.gap + 3 * net.jitter));
  net.delay += (target - net.delay) * 0.05; // de a poco, para que la interpolación no pegue saltos
}

// --------------------------------------------------------------- utilidades
const lerp = (a, b, t) => a + (b - a) * t;
function lerpAngle(a, b, t) {
  let d = (b - a) % (2 * Math.PI);
  if (d > Math.PI) d -= 2 * Math.PI;
  if (d < -Math.PI) d += 2 * Math.PI;
  return a + d * t;
}
function angleDelta(a, b) {
  return lerpAngle(a, b, 1) - a;
}
const lerpPt = (p, q, t) => [lerp(p[0], q[0], t), lerp(p[1], q[1], t), p.length > 2 ? lerpAngle(p[2], q[2], t) : 0];

function shade(hex, f) {
  const n = parseInt(hex.slice(1), 16);
  const ch = (s) => {
    const v = (n >> s) & 255;
    return Math.round(f >= 0 ? v + (255 - v) * f : v * (1 + f));
  };
  return `rgb(${ch(16)},${ch(8)},${ch(0)})`;
}

function interpolatedChars() {
  if (!snaps.length) return {};
  const rt = performance.now() - net.delay;
  let i = snaps.length - 1;
  while (i > 0 && snaps[i - 1].time > rt) i--;
  const s1 = snaps[i];
  const s0 = snaps[i - 1];
  if (!s0 || rt >= s1.time) return { ...s1.state.chars };
  const t = Math.max(0, Math.min(1, (rt - s0.time) / (s1.time - s0.time)));
  const out = {};
  for (const [pid, c1] of Object.entries(s1.state.chars)) {
    const c0 = s0.state.chars[pid];
    if (!c0) { out[pid] = c1; continue; }
    out[pid] = {
      h: lerpPt(c0.h, c1.h, t),
      s: c1.s.map((p, k) => lerpPt(c0.s[k], p, t)),
      b: c1.b.map((p, k) => lerpPt(c0.b[k], p, t)),
      t: c1.t && c0.t ? lerpPt(c0.t, c1.t, t) : c1.t,
    };
  }
  return out;
}

// --------------------------------------------------------------- predicción
// La cadena que manejo se dibuja "en el presente": la cabeza sigue mis teclas al
// instante con un modelo simple de la física del servidor, el resto del cuerpo se
// extrapola, y todo se corrige suave hacia lo que dice el servidor.
let pred = null; // estado local de la cabeza que manejo
let ownSmooth = null; // puntos ya dibujados de mi cadena (para suavizar correcciones)
const PRED_CORRECTION_S = 0.2; // qué tan rápido la predicción vuelve a lo que dice el servidor
const PRED_SNAP_PX = 150; // si la predicción se aleja más que esto, se descarta
const PRED_MAX_AHEAD_S = 0.25;
const SMOOTH_S = 0.03;

function boostCooldownLeft(now) {
  const me = latest && latest.players.find((p) => p.id === myId);
  return me ? Math.max(0, me.boost - (now - latestTime) / 1000) : Infinity;
}

function predictBoost() {
  const now = performance.now();
  if (pred && boostCooldownLeft(now) === 0) pred.boostUntil = now + cfg.boostDuration * 1000;
}

function extrapolate(c0, c1, dt, ahead) {
  const ex = (p0, p1) => [
    p1[0] + (p1[0] - p0[0]) / dt * ahead,
    p1[1] + (p1[1] - p0[1]) / dt * ahead,
    p1.length > 2 ? p1[2] + angleDelta(p0[2], p1[2]) / dt * ahead : 0,
  ];
  return {
    h: ex(c0.h, c1.h),
    s: c1.s.map((p, k) => ex(c0.s[k], p)),
    b: c1.b.map((p, k) => ex(c0.b[k], p)),
    t: c1.t && c0.t ? ex(c0.t, c1.t) : c1.t,
  };
}

// Mismo modelo de control que server/game.py (_apply_controls), simplificado.
function stepModel(p, dt, chainLen, now) {
  const substeps = dt * cfg.physicsHz * cfg.substeps;
  const turn = input.r - input.l;
  if (turn) p.w += (turn * cfg.turnSpeed - p.w) * (1 - Math.pow(1 - cfg.turnBlend, substeps));
  else p.w *= Math.pow(0.9, substeps);
  p.a += p.w * dt;

  let acc = 0;
  let max = cfg.maxSpeed;
  const thrust = cfg.thrust * (1 + cfg.chainThrustBonus * (chainLen - 1)) / (cfg.charMass * chainLen);
  if (now < (p.boostUntil || 0)) {
    acc = thrust * cfg.boostThrustMult;
    max *= cfg.boostSpeedMult;
  } else if (input.u) acc = thrust;
  p.vx += Math.cos(p.a) * acc * dt;
  p.vy += Math.sin(p.a) * acc * dt;
  const damp = Math.pow(cfg.damping, dt);
  p.vx *= damp;
  p.vy *= damp;
  const speed = Math.hypot(p.vx, p.vy);
  if (speed > max) { p.vx *= max / speed; p.vy *= max / speed; }
  p.x += p.vx * dt;
  p.y += p.vy * dt;
}

function smoothChars(prev, target, k) {
  const out = {};
  const mix = (a, b) => (a && a.length === b.length
    ? [lerp(a[0], b[0], k), lerp(a[1], b[1], k), b.length > 2 ? lerpAngle(a[2], b[2], k) : 0]
    : b);
  for (const [pid, c] of Object.entries(target)) {
    const p = prev && prev[pid];
    out[pid] = !p || p.s.length !== c.s.length ? c : {
      h: mix(p.h, c.h),
      s: c.s.map((q, i) => mix(p.s[i], q)),
      b: c.b.map((q, i) => mix(p.b[i], q)),
      t: c.t && p.t ? mix(p.t, c.t) : c.t,
    };
  }
  return out;
}

function predictOwnChain(chars, now, dt) {
  const chain = latest && chainOf(latest, myId);
  const playing = latest && (latest.phase === "playing" || latest.phase === "round_over");
  if (!chain || chain.pilot !== myId || !playing || snaps.length < 2) {
    pred = null;
    ownSmooth = null;
    return;
  }
  const s1 = snaps[snaps.length - 1];
  const s0 = snaps[snaps.length - 2];
  const tickDt = (s1.state.tick - s0.state.tick) / cfg.physicsHz;
  if (tickDt <= 0) return;
  // mis teclas de ahora le llegan al servidor en rtt/2 y el resultado vuelve en otro rtt/2
  const ahead = Math.min(PRED_MAX_AHEAD_S, (now - s1.time) / 1000 + (net.rtt || 0) / 1000);

  const targets = {};
  for (const pid of chain.members) {
    const c0 = s0.state.chars[pid];
    const c1 = s1.state.chars[pid];
    if (c0 && c1) targets[pid] = extrapolate(c0, c1, tickDt, ahead);
  }
  const front = chain.members[0];
  const server = targets[front];
  if (!server) return;

  const h0 = s0.state.chars[front].h;
  const h1 = s1.state.chars[front].h;
  const sv = [(h1[0] - h0[0]) / tickDt, (h1[1] - h0[1]) / tickDt];
  const sw = angleDelta(h0[2], h1[2]) / tickDt;
  if (!pred || pred.front !== front || Math.hypot(pred.x - server.h[0], pred.y - server.h[1]) > PRED_SNAP_PX) {
    pred = { front, x: server.h[0], y: server.h[1], a: server.h[2], vx: sv[0], vy: sv[1], w: sw,
             boostUntil: pred ? pred.boostUntil : 0 };
  }
  stepModel(pred, dt, chain.members.length, now);

  const k = 1 - Math.exp(-dt / PRED_CORRECTION_S);
  pred.x += (server.h[0] - pred.x) * k;
  pred.y += (server.h[1] - pred.y) * k;
  pred.a = lerpAngle(pred.a, server.h[2], k);
  pred.vx += (sv[0] - pred.vx) * k;
  pred.vy += (sv[1] - pred.vy) * k;
  pred.w += (sw - pred.w) * k;

  // la cabeza va donde dice la predicción; el tronco la acompaña cada vez menos hacia la base
  const dx = pred.x - server.h[0];
  const dy = pred.y - server.h[1];
  const n = server.s.length;
  server.h = [pred.x, pred.y, pred.a];
  server.s = server.s.map((p, i) => {
    const w = 1 - (i + 1) / (n + 1);
    return [p[0] + dx * w, p[1] + dy * w, p[2]];
  });

  ownSmooth = smoothChars(ownSmooth, targets, 1 - Math.exp(-dt / SMOOTH_S));
  Object.assign(chars, ownSmooth);
}

// -------------------------------------------------------------------- estado
function playersById(state) {
  const m = {};
  for (const p of state.players) m[p.id] = p;
  return m;
}
function chainOf(state, pid) {
  return state.chains.find((c) => c.members.includes(pid));
}

function cameraTarget(state, chars) {
  const chain = chainOf(state, myId);
  if (!chain || !chars[myId]) return null;
  const pid = chain.pilot === myId ? chain.members[0] : myId;
  return chars[pid] && chars[pid].h;
}

// ---------------------------------------------------------------------- HUD
function updateHud(state) {
  const players = playersById(state);
  const me = players[myId];
  const banner = $("banner");
  let html = "";
  if (state.phase === "lobby") {
    const n = state.players.filter((p) => p.connected).length;
    html = `Esperando jugadores… (${n}/2)<small>Compartí el link para que entren</small>`;
  } else if (state.phase === "countdown") {
    html = `${Math.ceil(state.timer)}<small>¡Preparate!</small>`;
  } else if (state.phase === "round_over") {
    const w = players[state.winner];
    const chain = chainOf(state, state.winner);
    html = `🏆 ${w ? esc(w.name) : "?"} se quedó con todo${chain ? ` (cadena de ${chain.members.length})` : ""}` +
      `<small>Nueva ronda en ${Math.ceil(state.timer)}…</small>`;
  } else if (me && me.spectator) {
    html = `Mirando<small>Entrás en la próxima ronda</small>`;
  } else if (me) {
    const chain = chainOf(state, myId);
    if (chain && chain.pilot !== myId && chain.members.length > 1) {
      const pilot = players[chain.pilot];
      html = `Te conquistó ${pilot ? esc(pilot.name) : "nadie"}<small>Sabotealo con tus teclas</small>`;
    }
  }
  banner.innerHTML = html;
  banner.style.display = html ? "block" : "none";

  const rows = state.chains.map((c) => {
    const items = c.members.map((pid) => {
      const p = players[pid];
      if (!p) return "";
      const cls = ["who", p.connected ? "" : "off", pid === myId ? "me" : ""].join(" ");
      const crown = pid === c.pilot && c.members.length > 1 ? "👑" : "";
      return `<span class="${cls}"><span class="dot" style="background:${p.color}"></span>${crown}${esc(p.name)}</span>`;
    });
    return `<div class="chain">${items.join('<span class="arrow">→</span>')}</div>`;
  });
  if (state.phase === "lobby") {
    const waiting = state.players.filter((p) => p.connected);
    rows.push(`<div class="chain">${waiting.map((p) => `<span class="who"><span class="dot" style="background:${p.color}"></span>${esc(p.name)}</span>`).join(" ")}</div>`);
  }
  const specs = state.players.filter((p) => p.spectator && p.connected);
  if (specs.length) rows.push(`<div class="chain" style="color:var(--muted)">👀 ${specs.map((p) => esc(p.name)).join(", ")}</div>`);
  $("botCount").textContent = state.players.filter((p) => p.bot && p.connected).length;
  $("chains").innerHTML = rows.join("") || '<div class="chain" style="color:var(--muted)">—</div>';
}

function showEvent(ev) {
  const players = latest ? playersById(latest) : {};
  const n = (pid) => {
    const p = players[pid];
    return p ? `<b style="color:${p.color}">${esc(p.name)}</b>` : "alguien";
  };
  let text;
  if (ev.kind === "conquest") {
    text = ev.entered === ev.controls
      ? `${n(ev.by)} se metió entre las bolas de ${n(ev.entered)} 🍆`
      : `${n(ev.by)} se metió en ${n(ev.entered)} y ahora maneja a ${n(ev.controls)} 🍆`;
  } else if (ev.kind === "win") {
    text = `🏆 ${n(ev.who)} ganó la ronda`;
  } else if (ev.kind === "join") {
    text = `${n(ev.who)} entró`;
  } else if (ev.kind === "leave") {
    text = `${n(ev.who)} se fue`;
  } else if (ev.kind === "error") {
    text = `⚠️ ${esc(ev.msg)}`;
  } else return;
  const div = document.createElement("div");
  div.innerHTML = text;
  const feed = $("feed");
  feed.appendChild(div);
  while (feed.children.length > 5) feed.firstChild.remove();
  setTimeout(() => { div.style.opacity = 0; }, 5000);
  setTimeout(() => div.remove(), 6000);
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// ------------------------------------------------------------------- render
function resize() {
  const dpr = devicePixelRatio || 1;
  canvas.width = innerWidth * dpr;
  canvas.height = innerHeight * dpr;
}
addEventListener("resize", resize);
resize();

function drawArena() {
  ctx.fillStyle = "#1d1626";
  ctx.fillRect(0, 0, arena.w, arena.h);
  ctx.strokeStyle = "rgba(255,255,255,0.045)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (let x = 0; x <= arena.w; x += 80) { ctx.moveTo(x, 0); ctx.lineTo(x, arena.h); }
  for (let y = 0; y <= arena.h; y += 80) { ctx.moveTo(0, y); ctx.lineTo(arena.w, y); }
  ctx.stroke();

  ctx.strokeStyle = "#5b4670";
  ctx.lineWidth = 20;
  ctx.lineCap = "round";
  for (const [x1, y1, x2, y2] of arena.walls) {
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  }
  for (const [x, y, r] of arena.obstacles) {
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = "#3a2c4a"; ctx.fill();
    ctx.lineWidth = 6; ctx.strokeStyle = "#5b4670"; ctx.stroke();
  }
}

function shaftPoints(c) {
  const pts = [[c.h[0], c.h[1]]];
  for (const s of c.s) pts.push([s[0], s[1]]);
  const base = c.s[c.s.length - 1];
  pts.push([base[0] - Math.cos(base[2]) * cfg.segLen / 2, base[1] - Math.sin(base[2]) * cfg.segLen / 2]);
  return pts;
}

function strokePath(pts, width, color) {
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length - 1; i++) {
    const mx = (pts[i][0] + pts[i + 1][0]) / 2, my = (pts[i][1] + pts[i + 1][1]) / 2;
    ctx.quadraticCurveTo(pts[i][0], pts[i][1], mx, my);
  }
  const last = pts[pts.length - 1];
  ctx.lineTo(last[0], last[1]);
  ctx.lineWidth = width;
  ctx.strokeStyle = color;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.stroke();
}

const OUTLINE = "#1a0f17";

function drawHead([hx, hy, ha], color) {
  const R = cfg.headR;
  ctx.save();
  ctx.translate(hx, hy);
  ctx.rotate(ha);
  ctx.beginPath(); ctx.arc(0, 0, R + 2.5, 0, Math.PI * 2); ctx.fillStyle = OUTLINE; ctx.fill();
  ctx.beginPath(); ctx.arc(0, 0, R, 0, Math.PI * 2); ctx.fillStyle = shade(color, 0.3); ctx.fill();
  // corona del glande
  ctx.beginPath(); ctx.arc(0, 0, R - 1, Math.PI * 0.6, Math.PI * 1.4);
  ctx.lineWidth = 3; ctx.strokeStyle = shade(color, -0.25); ctx.stroke();
  // meato
  ctx.beginPath(); ctx.moveTo(R * 0.35, 0); ctx.lineTo(R * 0.9, 0);
  ctx.lineWidth = 2; ctx.strokeStyle = OUTLINE; ctx.stroke();
  ctx.restore();
}

function drawBody(c, color) {
  const pts = shaftPoints(c);
  const r = cfg.segR;
  strokePath(pts, r * 2 + 5, OUTLINE);
  strokePath(pts, r * 2, color);
  strokePath(pts.map(([x, y]) => [x - r * 0.22, y - r * 0.22]), r * 0.6, shade(color, 0.35)); // brillo
  drawHead(c.h, color);
}

function drawBalls(c, color) {
  const r = cfg.ballR;
  for (const [x, y] of c.b) {
    ctx.beginPath(); ctx.arc(x, y, r + 2.5, 0, Math.PI * 2); ctx.fillStyle = OUTLINE; ctx.fill();
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = shade(color, -0.15); ctx.fill();
    ctx.beginPath(); ctx.arc(x - r * 0.25, y - r * 0.25, r * 0.35, 0, Math.PI * 2); ctx.fillStyle = shade(color, 0.3); ctx.fill();
  }
}

function drawTarget(pt, mine, now) {
  const pulse = 1 + 0.25 * Math.sin(now / 160);
  ctx.beginPath(); ctx.arc(pt[0], pt[1], 9 * pulse, 0, Math.PI * 2);
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = mine ? "rgba(255,90,90,0.75)" : "rgba(255,255,255,0.6)";
  ctx.setLineDash([4, 4]); ctx.stroke(); ctx.setLineDash([]);
}

function drawLabels(state, chars, players) {
  ctx.textAlign = "center";
  ctx.font = `bold ${Math.round(14 / cam.zoom)}px system-ui, sans-serif`;
  for (const chain of state.chains) {
    chain.members.forEach((pid, idx) => {
      const c = chars[pid], p = players[pid];
      if (!c || !p) return;
      const pilot = players[chain.pilot];
      // anillo del piloto alrededor de la cabeza que maneja
      if (idx === 0 && pilot && chain.pilot !== pid) {
        ctx.beginPath(); ctx.arc(c.h[0], c.h[1], cfg.headR + 8, 0, Math.PI * 2);
        ctx.lineWidth = 3; ctx.strokeStyle = pilot.color; ctx.stroke();
      }
      let label = p.name;
      if (pid === chain.pilot && chain.members.length > 1) label = `👑 ${label} ×${chain.members.length}`;
      const y = c.h[1] - cfg.headR - 12 / cam.zoom;
      ctx.lineWidth = 4 / cam.zoom;
      ctx.strokeStyle = "rgba(0,0,0,0.7)";
      ctx.strokeText(label, c.h[0], y);
      ctx.fillStyle = p.connected ? (pid === myId ? "#fff" : p.color) : "#777";
      ctx.fillText(label, c.h[0], y);
    });
  }
}

function drawMinimap(state, chars, players) {
  const W = 180, H = W * arena.h / arena.w, pad = 16;
  const dpr = devicePixelRatio || 1;
  const x0 = innerWidth - W - pad, y0 = innerHeight - H - pad;
  const s = W / arena.w;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "rgba(20,14,28,0.82)";
  ctx.fillRect(x0, y0, W, H);
  ctx.strokeStyle = "#5b4670"; ctx.lineWidth = 1; ctx.strokeRect(x0, y0, W, H);
  ctx.fillStyle = "#3a2c4a";
  for (const [x, y, r] of arena.obstacles) { ctx.beginPath(); ctx.arc(x0 + x * s, y0 + y * s, r * s, 0, Math.PI * 2); ctx.fill(); }
  for (const [pid, c] of Object.entries(chars)) {
    const p = players[pid];
    if (!p) continue;
    ctx.fillStyle = p.color;
    ctx.beginPath(); ctx.arc(x0 + c.h[0] * s, y0 + c.h[1] * s, pid === myId ? 4 : 2.5, 0, Math.PI * 2); ctx.fill();
    if (c.t) {
      ctx.strokeStyle = "rgba(255,255,255,0.6)";
      ctx.beginPath(); ctx.arc(x0 + c.t[0] * s, y0 + c.t[1] * s, 3, 0, Math.PI * 2); ctx.stroke();
    }
  }
}

function updateBoostMeter(players, now) {
  const me = players[myId];
  const show = me && !me.spectator && (latest.phase === "playing" || latest.phase === "round_over");
  const el = $("boost");
  el.style.display = show ? "block" : "none";
  if (!show) return;
  const left = Math.max(0, me.boost - (now - latestTime) / 1000);
  el.classList.toggle("ready", left === 0);
  $("boostFill").style.width = `${100 * (1 - left / cfg.boostCooldown)}%`;
  $("boostText").textContent = left === 0 ? "LISTO" : `${left.toFixed(1)}s`;
}

const TRAIL_S = 0.6; // las estelas duran un poco más que el boost y se desvanecen

// estelas detrás de la cabeza que empuja cada jugador con boost
function drawBoostTrails(state, chars, players, now) {
  for (const p of state.players) {
    const elapsed = cfg.boostCooldown - (p.boost - (now - latestTime) / 1000);
    if (p.boost <= 0 || elapsed > TRAIL_S) continue;
    ctx.globalAlpha = Math.max(0, 1 - elapsed / TRAIL_S);
    const chain = chainOf(state, p.id);
    const pushed = chain && chain.pilot === p.id ? chain.members[0] : p.id;
    const c = chars[pushed];
    if (!c) continue;
    const [hx, hy, ha] = c.h;
    const bx = -Math.cos(ha), by = -Math.sin(ha), px = -by, py = bx;
    ctx.lineCap = "round";
    for (const k of [-1.6, -1, 1, 1.6]) {
      const off = k * (cfg.segR + 6);
      const len = 45 + 25 * Math.sin(now / 40 + k * 3);
      const sx = hx + px * off + bx * cfg.headR, sy = hy + py * off + by * cfg.headR;
      const grad = ctx.createLinearGradient(sx, sy, sx + bx * len, sy + by * len);
      grad.addColorStop(0, "rgba(255,255,255,0.95)");
      grad.addColorStop(1, "rgba(255,255,255,0)");
      ctx.strokeStyle = grad;
      ctx.lineWidth = Math.abs(k) === 1 ? 4 : 2.5;
      ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(sx + bx * len, sy + by * len); ctx.stroke();
    }
    ctx.beginPath(); ctx.arc(hx, hy, cfg.headR + 6, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255,255,255,0.18)"; ctx.fill();
  }
  ctx.globalAlpha = 1;
}

let lastFrame = performance.now();

function frame() {
  requestAnimationFrame(frame);
  const frameNow = performance.now();
  const dt = Math.min(0.1, (frameNow - lastFrame) / 1000);
  lastFrame = frameNow;
  const dpr = devicePixelRatio || 1;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = "#0e0a12";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!arena || !latest) return;

  const now = performance.now();
  const chars = interpolatedChars();
  predictOwnChain(chars, now, dt);
  const players = playersById(latest);

  // cámara: sigue a lo que manejo; si no juego, muestra toda la arena
  const target = cameraTarget(latest, chars);
  const fitZoom = Math.min(innerWidth / (arena.w + 100), innerHeight / (arena.h + 100));
  const goal = target
    ? { x: target[0], y: target[1], zoom: Math.max(fitZoom, Math.max(innerWidth, innerHeight) / 1500) }
    : { x: arena.w / 2, y: arena.h / 2, zoom: fitZoom };
  cam.x = lerp(cam.x, goal.x, 0.12);
  cam.y = lerp(cam.y, goal.y, 0.12);
  cam.zoom = lerp(cam.zoom, goal.zoom, 0.05);

  ctx.setTransform(dpr * cam.zoom, 0, 0, dpr * cam.zoom,
    dpr * (innerWidth / 2 - cam.x * cam.zoom), dpr * (innerHeight / 2 - cam.y * cam.zoom));
  drawArena();

  const myChain = chainOf(latest, myId);
  for (const [pid, c] of Object.entries(chars)) {
    if (c.t) drawTarget(c.t, myChain && myChain.members.includes(pid), now);
  }
  // cuerpos primero y bolas después: así la cabeza acoplada queda "adentro"
  for (const [pid, c] of Object.entries(chars)) if (players[pid]) drawBody(c, players[pid].color);
  for (const [pid, c] of Object.entries(chars)) if (players[pid]) drawBalls(c, players[pid].color);
  drawBoostTrails(latest, chars, players, now);
  drawLabels(latest, chars, players);
  drawMinimap(latest, chars, players);
  updateBoostMeter(players, now);
}
requestAnimationFrame(frame);
