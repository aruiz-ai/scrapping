import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXPORTS_DIR = os.path.join(DATA_DIR, "exports")
STORAGE_STATE_PATH = os.path.join(DATA_DIR, "storage_state.json")

LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"
LINKEDIN_SEARCH_URL = "https://www.linkedin.com/search/results/people/"

DEFAULT_MAX_PAGES = 10
MAX_PAGES_LIMIT = 25
ALL_PAGES_SAFETY_LIMIT = 25
LOGIN_TIMEOUT_SECONDS = 5 * 60

# Ritmo de scraping: cada página debe tardar entre PAGE_MIN_SECONDS y
# PAGE_MAX_SECONDS en total (suma de carga, scroll, extracción y pausas).
# El scraper mide el tiempo real gastado en la página y reparte el resto
# como pausas "de lectura" en trozos, para imitar a una persona.
PAGE_MIN_SECONDS = 180
PAGE_MAX_SECONDS = 300
PAUSE_CHUNK_MIN = 8        # tamaño mínimo de cada trozo de pausa (segundos)
PAUSE_CHUNK_MAX = 25       # tamaño máximo de cada trozo de pausa (segundos)

# ---------------------------------------------------------------------------
# Límites anti-detección (uso personal a bajo volumen)
# ---------------------------------------------------------------------------

# Sesión continua máxima medida en TIEMPO ACTIVO: las pausas largas entre
# bloques de perfiles no cuentan (el reloj se congela durante ellas); el
# pacing normal de página sí. Al llegar al límite el job corta tras terminar
# la página en curso y exporta lo acumulado.
SESSION_MAX_ACTIVE_SECONDS = 120 * 60

# Visitas a perfil: se hacen en bloques; al completar un bloque se inserta
# UNA pausa larga aleatoria antes del siguiente.
PROFILE_LOOKUP_SESSION_MAX = 15
PROFILE_LOOKUP_BLOCK_PAUSE_MIN = 5 * 60
PROFILE_LOOKUP_BLOCK_PAUSE_MAX = 15 * 60

# Tope diario duro de visitas de perfil hechas por el scraper (persistente
# en data/usage_state.json). Si se agota a mitad de job, las restantes se
# saltan y el cargo queda sin verificar. El uso MANUAL de LinkedIn no es
# rastreable: súmalo a mano editando ese JSON.
DAILY_PROFILE_LOOKUP_LIMIT = 70

# Fingerprint: viewport con jitter por ejecución (tamaños realistas de
# escritorio; nunca exactamente iguales entre corridas).
VIEWPORT_WIDTH_RANGE = (1320, 1400)
VIEWPORT_HEIGHT_RANGE = (840, 940)

# Operativa entre ejecuciones: mínimo de horas desde el fin del último job
# y ventana horaria (hora local del servidor) para INICIAR búsquedas.
COOLDOWN_HOURS = 2
ALLOWED_START_HOUR = 8
ALLOWED_END_HOUR = 21

USAGE_STATE_PATH = os.path.join(DATA_DIR, "usage_state.json")

# Scroll gradual: pasos de SCROLL_STEP píxeles con una pausa aleatoria entre
# pasos (lento a propósito: fuerza la carga diferida y suma tiempo de página).
SCROLL_STEP = 150
SCROLL_STEP_DELAY_MIN = 0.6   # segundos entre pasos de scroll
SCROLL_STEP_DELAY_MAX = 1.2

# Verificación del puesto en el perfil: cuando el snippet del resultado no es
# "Actual: ..." se abre el perfil en una pestaña aparte, se lee la experiencia
# actual y solo se usa si la empresa coincide con la buscada. Cada visita
# añade una demora humana entre PROFILE_LOOKUP_DELAY_MIN y MAX segundos.
PROFILE_LOOKUP_DELAY_MIN = 30
PROFILE_LOOKUP_DELAY_MAX = 60
PROFILE_LOAD_TIMEOUT_SECONDS = 68
PROFILE_EXPERIENCE_WAIT_SECONDS = 23

# Panel de filtros (calibrado en vivo, ritmo tranquilo): cada selección
# escribe en el typeahead, espera a que aparezcan las opciones (~4 s) y
# confirma el chip. Tras cada paso se deja asentar la UI.
FILTER_ADD_DELAY = 3.0        # tras pulsar el botón "Add X" (abre el buscador)
FILTER_TYPEAHEAD_DELAY = 4.0  # tras escribir: tiempo en aparecer las opciones
FILTER_SELECT_DELAY = 4.0     # tras hacer clic en la opción (chip aplicado)
FILTER_RETRY_DELAY = 2.0      # tras Escape cuando no hubo coincidencia
FILTER_CLOSE_DELAY = 2.0      # tras cerrar el panel con Escape

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)