// Host P2P: corre el servidor Python (server/room.py) en el navegador con Pyodide.
// Vive en un Web Worker para que la física no trabe el render y para que el loop siga
// andando con la pestaña en segundo plano (los timers de la página se frenan, los del worker no).
//
// página → worker: {op: "init", version} · {op: "msg", conn, data} · {op: "close", conn}
// worker → página: {op: "status", text} · {op: "ready"} · {op: "fail", error}
//                  {op: "send", conn, data} · {op: "broadcast", data} · {op: "kick", conn}

// Es un worker de tipo módulo: Chrome ya no deja usar importScripts con scripts de otro dominio.
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const PYMUNK = "pymunk==7.3.0"; // tiene wheel para Pyodide 314 en PyPI

let room = null;
const pending = []; // mensajes que llegan mientras carga Pyodide

const post = (msg) => postMessage(msg);

onmessage = (e) => {
  const m = e.data;
  if (m.op === "init") start(m.version).catch((err) => post({ op: "fail", error: String(err) }));
  else if (!room) pending.push(m);
  else handle(m);
};

function handle(m) {
  try {
    if (m.op === "msg") room.receive(m.conn, m.data);
    else if (m.op === "close") room.leave(m.conn);
  } catch (err) {
    console.error(err); // un mensaje raro de un invitado no tiene que tirar la sala
  }
}

async function start(version) {
  post({ op: "status", text: "Cargando Python…" });
  const pyodide = await loadPyodide({ indexURL: PYODIDE });
  post({ op: "status", text: "Cargando la física…" });
  await pyodide.loadPackage("micropip");
  await pyodide.pyimport("micropip").install(PYMUNK);

  post({ op: "status", text: "Cargando el juego…" });
  const base = new URL("server/", location.href);
  const files = await (await fetch(new URL(`manifest.json?v=${version}`, base))).json();
  pyodide.FS.mkdirTree("/game/server");
  await Promise.all(files.map(async (f) => {
    const res = await fetch(new URL(`${f}?v=${version}`, base));
    if (!res.ok) throw new Error(`no se pudo bajar server/${f} (${res.status})`);
    pyodide.FS.writeFile(`/game/server/${f}`, await res.text());
  }));
  pyodide.runPython("import sys; sys.path.insert(0, '/game')");

  const { Room } = pyodide.pyimport("server.room");
  room = Room(version,
    (conn, data) => post({ op: "send", conn, data }),
    (conn) => post({ op: "kick", conn }));
  pending.splice(0).forEach(handle);
  post({ op: "ready" });
  loop();
}

// Paso fijo a 60 Hz: room.tick corre los ticks que se deben y devuelve el snapshot cuando toca.
function loop() {
  try {
    const state = room.tick(performance.now() / 1000);
    if (state) post({ op: "broadcast", data: state });
  } catch (err) {
    console.error(err);
    post({ op: "fail", error: String(err).trim().split("\n").pop() }); // última línea del traceback
    return;
  }
  setTimeout(loop, Math.max(0, room.next_t * 1000 - performance.now()));
}
