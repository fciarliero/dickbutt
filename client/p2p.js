"use strict";
// Modo P2P (GitHub Pages): no hay servidor. Quien crea la sala corre la simulación en su
// navegador (host-worker.js) y los demás se conectan a él por WebRTC con PeerJS.
// game.js no se entera: P2P.open() devuelve un objeto con la misma forma que un WebSocket.

window.P2P = (() => {
  const PEERJS = "https://cdnjs.cloudflare.com/ajax/libs/peerjs/1.5.5/peerjs.min.js";
  const PREFIX = "culocaca-v1-"; // id en el broker público de PeerJS: PREFIX + código de sala
  const CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // sin 0/O ni 1/I
  const CONNECT_TIMEOUT = 15000;
  const VERSION = (document.querySelector('meta[name="client-version"]') || {}).content || "dev";
  const el = (id) => document.getElementById(id);

  document.body.classList.add("p2p");

  // -------------------------------------------------------------- utilidades
  let peerjs = null;
  function loadPeerJS() {
    peerjs ||= new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = PEERJS;
      s.onload = resolve;
      s.onerror = () => { peerjs = null; reject(new Error("no se pudo cargar PeerJS")); };
      document.head.appendChild(s);
    });
    return peerjs;
  }

  // WebRTC tarda ~30 s en dar por muerta una conexión que se cortó sin avisar (pestaña
  // colgada, se fue el wifi). Si ICE queda "disconnected" más de ICE_GRACE, la cerramos.
  const ICE_GRACE = 5000;
  function watchIce(c) {
    const pc = c.peerConnection;
    if (!pc) return;
    let timer = null;
    pc.addEventListener("iceconnectionstatechange", () => {
      const st = pc.iceConnectionState;
      clearTimeout(timer);
      if (st === "failed" || st === "closed") c.close();
      else if (st === "disconnected") timer = setTimeout(() => c.close(), ICE_GRACE);
    });
  }

  const cleanCode = (s) => (s || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
  const newCode = () => Array.from({ length: 5 }, () => CODE_CHARS[Math.floor(Math.random() * CODE_CHARS.length)]).join("");
  const roomLink = (code) => `${location.origin}${location.pathname}?sala=${code}`;
  const status = (text) => { el("status").textContent = text || ""; };

  // Un objeto con la interfaz de WebSocket que usa game.js.
  function makeTransport(sendImpl, closeImpl) {
    const t = {
      readyState: 0,
      onopen: null, onmessage: null, onclose: null,
      send(data) { if (t.readyState === 1) sendImpl(data); },
      close() { if (t.readyState < 2) { closeImpl(); t._closed(""); } },
      _open() { if (t.readyState !== 0) return; t.readyState = 1; status(""); t.onopen && t.onopen(); },
      _message(data) { if (t.readyState === 1) t.onmessage && t.onmessage({ data }); },
      _closed(reason) {
        if (t.readyState === 3) return;
        t.readyState = 3;
        status("");
        showRoom(null);
        t.onclose && t.onclose({ reason });
      },
    };
    return t;
  }

  // -------------------------------------------------------------------- host
  let host = null; // {worker, peer, code, conns: Map, local, ready}

  function startHost() {
    const worker = new Worker(`host-worker.js?v=${VERSION}`, { type: "module" });
    const h = host = { worker, peer: null, code: null, conns: new Map(), local: null, online: false, ready: null };
    const toConn = (conn, data) => {
      if (conn === "local") h.local && h.local._message(data);
      else { const c = h.conns.get(conn); if (c && c.open) c.send(data); }
    };
    let started = false;
    h.ready = new Promise((resolve, reject) => {
      const fail = (error) => {
        if (started) shutdown(h, `El juego se colgó: ${error}`); // falló Python en plena partida
        else reject(new Error(error));
      };
      worker.onmessage = (e) => {
        const m = e.data;
        if (m.op === "broadcast") {
          h.local && h.local._message(m.data);
          for (const c of h.conns.values()) if (c.open) c.send(m.data);
        } else if (m.op === "send") toConn(m.conn, m.data);
        else if (m.op === "kick") {
          if (m.conn === "local") h.local && h.local._closed("");
          else { const c = h.conns.get(m.conn); if (c) setTimeout(() => c.close(), 200); } // que llegue el error
        } else if (m.op === "status") status(m.text);
        else if (m.op === "ready") { started = true; resolve(); }
        else if (m.op === "fail") fail(m.error);
      };
      worker.onerror = (e) => fail(e.message || "falló el worker");
    });
    worker.postMessage({ op: "init", version: VERSION });
    h.online = openRoom(h).catch((err) => { console.warn("[p2p]", err); return false; });
    return h;
  }

  // Registra la sala en el broker de PeerJS. Si falla, se juega igual (solo, contra bots).
  async function openRoom(h, tries = 3) {
    await loadPeerJS();
    const code = newCode();
    const peer = new Peer(PREFIX + code);
    const ok = await new Promise((resolve, reject) => {
      setTimeout(() => reject(new Error("el broker de PeerJS no contestó")), CONNECT_TIMEOUT);
      peer.on("open", () => resolve(true));
      peer.on("error", (err) => {
        if (err.type === "unavailable-id") resolve(false); // código ocupado: probar otro
        else reject(err);
      });
    }).catch((err) => { peer.destroy(); throw err; });
    if (!ok) {
      peer.destroy();
      if (tries > 1) return openRoom(h, tries - 1);
      throw new Error("no se encontró un código libre");
    }
    if (host !== h) { peer.destroy(); return false; } // el host falló mientras tanto
    h.peer = peer;
    h.code = code;
    let next = 1;
    peer.on("connection", (c) => {
      const conn = `c${next++}`;
      h.conns.set(conn, c);
      c.on("data", (data) => h.worker.postMessage({ op: "msg", conn, data: String(data) }));
      c.on("close", () => {
        h.conns.delete(conn);
        h.worker.postMessage({ op: "close", conn });
      });
      c.on("open", () => watchIce(c));
      c.on("error", () => c.close());
    });
    // si se corta el broker las conexiones abiertas siguen; reconectar para que entren nuevos
    peer.on("disconnected", () => setTimeout(() => !peer.destroyed && peer.reconnect(), 1000));
    peer.on("error", (err) => console.warn("[p2p] host:", err.type, err));
    addEventListener("pagehide", () => peer.destroy()); // avisa a los demás enseguida
    return true;
  }

  // Apaga la sala: corta a los invitados, frena el worker y cierra el transporte local.
  function shutdown(h, reason) {
    if (host === h) host = null;
    h.worker.terminate();
    if (h.peer) h.peer.destroy();
    if (h.local) h.local._closed(reason);
  }

  function openAsHost() {
    if (!host) startHost();
    const h = host;
    const t = makeTransport(
      (data) => h.worker.postMessage({ op: "msg", conn: "local", data }),
      () => h.worker.postMessage({ op: "close", conn: "local" }));
    h.local = t;
    Promise.all([h.ready, h.online]).then(([, online]) => {
      showRoom(online ? h.code : null, true);
      t._open();
    }, (err) => shutdown(h, `No se pudo arrancar el juego: ${err.message}`));
    return t;
  }

  // ------------------------------------------------------------------ unirse
  function openAsGuest(code) {
    let peer = null;
    let conn = null;
    const t = makeTransport((data) => conn.send(data), () => peer && peer.destroy());
    const fail = (reason) => { if (peer) peer.destroy(); t._closed(reason); };
    if (!code) {
      setTimeout(() => fail("Escribí el código de la sala."));
      return t;
    }
    status("Conectando…");
    loadPeerJS().then(() => {
      peer = new Peer();
      addEventListener("pagehide", () => peer.destroy(), { once: true }); // que el host se entere enseguida
      const timer = setTimeout(() => fail("No se pudo conectar con la sala (tardó demasiado)."), CONNECT_TIMEOUT);
      peer.on("open", () => {
        conn = peer.connect(PREFIX + code, { reliable: true, serialization: "raw" });
        conn.on("open", () => {
          clearTimeout(timer);
          watchIce(conn);
          history.replaceState(null, "", `?sala=${code}`); // el link sirve para invitar y para recargar
          showRoom(code, false);
          t._open();
        });
        conn.on("data", (data) => t._message(String(data)));
        conn.on("close", () => fail(t.readyState === 1 ? "El host cerró la sala." : "No se pudo conectar con la sala."));
      });
      peer.on("error", (err) => {
        clearTimeout(timer);
        fail(err.type === "peer-unavailable" ? `No existe la sala ${code} (¿el host cerró la pestaña?).`
          : `Error de conexión (${err.type}).`);
      });
    }, (err) => fail(`No se pudo conectar: ${err.message}.`));
    return t;
  }

  // ---------------------------------------------------------------- pantalla
  const urlCode = cleanCode(new URLSearchParams(location.search).get("sala"));
  if (urlCode) {
    el("p2pJoinLink").hidden = false;
    el("roomLabel").textContent = urlCode;
    el("p2pHost").classList.add("secondary");
    el("p2pCodeRow").hidden = true;
  }
  el("code").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); el("p2pJoinCode").click(); }
  });

  function showRoom(code, isHost) {
    const panel = el("room");
    if (code === null && isHost === undefined) { panel.style.display = "none"; return; }
    panel.style.display = "block";
    el("roomCode").textContent = code || "—";
    el("roomCopy").hidden = !code;
    el("roomCopy").textContent = copyLabel();
    // en el celu el navegador congela la página si cambiás de app o se apaga la pantalla
    const touch = document.body.classList.contains("touch");
    el("roomNote").textContent = !code ? "sin conexión: solo vos y los bots"
      : !isHost ? ""
      : touch ? "sos el host: no cambies de app ni bloquees el celu"
      : "sos el host: si cerrás la pestaña se termina";
  }
  // En el celu abre el menú de compartir del sistema (WhatsApp, etc.); en la PC copia el link
  // (Chrome en Windows también tiene navigator.share, pero ahí copiar es más cómodo).
  const canShare = () => Boolean(navigator.share) && document.body.classList.contains("touch");
  const copyLabel = () => (canShare() ? "Compartir" : "Copiar link");
  el("roomCopy").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const url = roomLink(el("roomCode").textContent);
    btn.blur();
    if (canShare()) {
      try {
        await navigator.share({ title: "Culo Caca", text: "Entrá a mi sala de Culo Caca", url });
        return;
      } catch (err) {
        if (err.name === "AbortError") return; // lo cerró sin compartir
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      btn.textContent = "¡Copiado!";
    } catch {
      btn.textContent = url;
    }
    setTimeout(() => { btn.textContent = copyLabel(); }, 2500);
  });

  return {
    // mode: "host" crea la sala; "join" entra a la del link; "code" a la del código escrito
    open(mode) {
      if (mode === "host") return openAsHost();
      return openAsGuest(mode === "code" ? cleanCode(el("code").value) : urlCode);
    },
    defaultMode: urlCode ? "join" : "host",
  };
})();
