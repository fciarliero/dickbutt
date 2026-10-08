#!/usr/bin/env bash
# Baja el juego (lo que esté escuchando en el puerto, aunque no lo haya levantado start.sh).
#   ./stop.sh               → puerto 8765
#   PORT=9000 ./stop.sh     → otro puerto
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8765}"

pid_on_port() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1
  else  # Windows (Git Bash)
    netstat -ano 2>/dev/null | awk -v p=":$PORT" '$1 == "TCP" && $2 ~ p"$" && $4 == "LISTENING" { print $5; exit }'
  fi
}

pid="$(pid_on_port)"
if [ -z "$pid" ]; then
  echo "No hay nada corriendo en el puerto $PORT."
  exit 0
fi

if command -v taskkill >/dev/null 2>&1; then
  taskkill //PID "$pid" //F >/dev/null
else
  kill "$pid"
fi

for _ in $(seq 1 20); do
  if [ -z "$(pid_on_port)" ]; then
    echo "Juego bajado (PID $pid)."
    exit 0
  fi
  sleep 0.25
done

echo "El proceso $pid sigue escuchando en el puerto $PORT."
exit 1
