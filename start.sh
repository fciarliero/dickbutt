#!/usr/bin/env bash
# Levanta el juego en segundo plano.
#   ./start.sh                       → http://localhost:8765
#   PORT=9000 ./start.sh             → otro puerto
#   SIM_LAG_MS=150 ./start.sh        → con lag simulado para probar
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8765}"
PYTHON="${PYTHON:-python}"
LOG="game.log"

pid_on_port() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1
  else  # Windows (Git Bash)
    netstat -ano 2>/dev/null | awk -v p=":$PORT" '$1 == "TCP" && $2 ~ p"$" && $4 == "LISTENING" { print $5; exit }'
  fi
}

pid="$(pid_on_port)"
if [ -n "$pid" ]; then
  echo "Ya hay algo escuchando en el puerto $PORT (PID $pid). Bajalo con ./stop.sh"
  exit 1
fi

PORT="$PORT" nohup "$PYTHON" run.py >"$LOG" 2>&1 &
disown

for _ in $(seq 1 40); do
  if curl -s -o /dev/null "http://localhost:$PORT/"; then
    echo "Juego arriba en http://localhost:$PORT  (PID $(pid_on_port), log en $LOG)"
    echo "Para jugar online: ngrok http $PORT"
    exit 0
  fi
  sleep 0.25
done

echo "El juego no respondió en 10 s. Últimas líneas de $LOG:"
tail -n 20 "$LOG"
exit 1
