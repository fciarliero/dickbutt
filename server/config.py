"""Constantes tuneables del juego. Unidades: píxeles, segundos, radianes."""
import math

# --- Simulación / red ---
PHYSICS_HZ = 60
SUBSTEPS = 2
BROADCAST_EVERY = 2  # cada cuántos ticks se manda un snapshot (60/2 = 30 Hz)

# --- Arena ---
ARENA_W = 2400
ARENA_H = 1600
WALL_RADIUS = 10
# (x, y, radio) relativos a la esquina superior izquierda
OBSTACLES = [
    (ARENA_W / 2, ARENA_H / 2, 90),
    (ARENA_W / 2 - 520, ARENA_H / 2 - 300, 55),
    (ARENA_W / 2 + 520, ARENA_H / 2 - 300, 55),
    (ARENA_W / 2 - 520, ARENA_H / 2 + 300, 55),
    (ARENA_W / 2 + 520, ARENA_H / 2 + 300, 55),
]
SPAWN_RX = 900
SPAWN_RY = 560

# --- Anatomía ---
HEAD_R = 13
SEG_COUNT = 6
SEG_LEN = 20
SEG_R = 9
BALL_R = 16
BALL_GAP = 6  # separación entre las bolas (hueco de entrada)

HEAD_MASS = 1.0
SEG_MASS = 0.6
BALL_MASS = 0.35

# Tronco: resorte angular entre segmentos + límite de doblez
SHAFT_STIFFNESS = 1200  # más bajo = más flexible
SHAFT_DAMPING = 85
SHAFT_MAX_BEND = math.radians(55)  # doblez máximo por articulación

# Testículos: resorte hacia la posición de reposo
BALL_STIFFNESS = 50
BALL_DAMPING = 1.5
BALL_MAX_DIST = 12

# --- Movimiento ---
SPACE_DAMPING = 0.25  # fracción de velocidad que queda tras 1 s
THRUST = 2600
CHAIN_THRUST_BONUS = 0.55  # empuje extra por cada personaje en la cadena (no compensa del todo)
TURN_SPEED = 4.2  # rad/s
TURN_BLEND = 0.35
MAX_SPEED = 420
SAFETY_SPEED = 1400  # por encima de esto se recorta (evita explosiones)
SABOTAGE_FACTOR = 0.2

# --- Boost (barra espaciadora) ---
BOOST_DURATION = 0.3  # s de empuje extra
BOOST_COOLDOWN = 3.0  # s desde que se activa hasta poder usarlo de nuevo
BOOST_THRUST_MULT = 4.0
BOOST_SPEED_MULT = 1.7  # tope de velocidad mientras dura
BOOST_SABOTAGE_MULT = 4.0  # un conquistado con boost tironea más fuerte
OVERSPEED_DECAY = 0.85  # al terminar el boost la velocidad baja suave, no de golpe

# --- Penetración ---
ENTRY_RADIUS = HEAD_R + 21  # tolera ~25 px de desalineación lateral
ENTRY_ANGLE = math.radians(35)
ENTRY_MIN_SPEED = 90
COUPLE_MAX_BIAS = 260  # velocidad máx. con la que el acople "succiona" la cabeza
COUPLE_MAX_BEND = math.radians(45)

# --- Rondas ---
MIN_PLAYERS = 2
COUNTDOWN_S = 3.0
ROUND_OVER_S = 5.0
MAX_PLAYERS = 8
NAME_MAX = 16

COLORS = [
    "#ff6b9a", "#ffb347", "#6bd6ff", "#9b7bff",
    "#7cf08a", "#ff7a59", "#f5e663", "#e07bff",
]
