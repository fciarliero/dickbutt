# Dicknbutt

Juego multijugador en el navegador. Cada jugador maneja la cabeza de un pene con dos testículos atrás. Si te metés entre las bolas de otro (por detrás, alineado y con velocidad), pasás a manejar su cuerpo y el tuyo queda enganchado atrás. Gana quien maneja la cadena cuando están todos adentro.

## Correr

```
pip install -r requirements.txt
./start.sh               # levanta en segundo plano: http://localhost:8765 (log en game.log)
./stop.sh                # lo baja
python run.py            # o en primer plano  (otro puerto: PORT=9000 ./start.sh)
ngrok http 8765          # compartí la URL https con tus amigos
```

## Jugar sin servidor (GitHub Pages)

La rama principal se publica sola en GitHub Pages (`.github/workflows/pages.yml`; una vez: *Settings → Pages → Source: GitHub Actions*). Ahí no hay servidor: quien toca **Crear sala** corre la física en su navegador y comparte el link (`?sala=CÓDIGO`); los demás se conectan directo a él por WebRTC. Si el host cierra la pestaña, se termina la partida.

```
python tools/build_pages.py              # arma _site/
python -m http.server 8080 -d _site      # probalo en http://localhost:8080
```

Detalle en [ARCHITECTURE.md](ARCHITECTURE.md#15-modo-p2p-github-pages).

## Controles

- `←` `→` / `A` `D`: girar
- `↑` / `W`: empujar
- `Espacio`: boost para adelante (0,3 s de empuje fuerte, 3 s de cooldown). Si te conquistaron, el boost es un tirón de sabotaje.
- Si te conquistaron, las mismas teclas **sabotean**: tironean tu segmento, pero no te sueltan.

En el celu (se activa solo en pantallas táctiles):

- **Joystick** en la mitad izquierda: apoyá el dedo en cualquier lado y arrastrá hacia donde querés ir. Poco arrastre gira; arrastre largo, además empuja.
- **⚡** abajo a la derecha: boost. El aro muestra el cooldown.
- Se juega mejor con el celu horizontal. En Android, ⛶ (al lado del ping) pone pantalla completa.
- Si creás la sala desde el celu, no cambies de app ni bloquees la pantalla: el navegador frena la página y la sala se cae para todos.

## Chat

En la PC apretá **Enter**, escribí y otra vez **Enter** para mandar (**Esc** cierra). En el celu, el botón **💬** al lado del ping; tiene un punto cuando hay mensajes sin leer. Los bots también hablan cuando los conquistan, conquistan o ganan.

## Bots

Con los botones `−` / `+` del panel de cadenas cualquiera puede sacar o agregar bots (`server/bots.py`). Cuentan como jugadores: pueden conquistar, ser conquistados (y sabotear) y ganar. Un bot agregado a mitad de ronda entra en la siguiente. Sin humanos conectados, los bots esperan en el lobby.

## Latencia

- Arriba a la izquierda se ve el ping.
- La cadena que manejás se dibuja con predicción: la cabeza responde a tus teclas al instante y se corrige suave hacia el servidor. El resto se interpola con un buffer que se adapta solo (~35–50 ms en una conexión estable).
- Para probar cómo se siente con lag sin salir de tu PC: `SIM_LAG_MS=150 python run.py` (en Windows el lag real queda un poco por debajo, ~120 ms).

## Estructura

Detalle completo en [ARCHITECTURE.md](ARCHITECTURE.md).

- `server/config.py`: todos los valores tuneables (velocidades, rigidez, hitbox, tiempos).
- `server/game.py`: física (pymunk), fases de ronda, controles y penetración.
- `server/character.py`: construcción del personaje (glande, tronco de 6 segmentos, bolas).
- `server/chains.py`: reglas de cadenas, sin física.
- `server/main.py`: FastAPI, WebSocket `/ws` y el loop a 60 Hz (snapshots a 30 Hz).
- `server/room.py`: el mismo protocolo sin red, para correrlo en el navegador.
- `client/`: HTML + canvas, sin build. `p2p.js` y `host-worker.js` solo se usan en GitHub Pages.

## Tests

```
pytest
```
