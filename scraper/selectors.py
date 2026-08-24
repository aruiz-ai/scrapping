"""Selectores CSS de LinkedIn.

LinkedIn cambia su DOM con frecuencia (usa clases con hash que rotan).
Centralizamos aquí selectores anclados en atributos semánticos estables
(role="listitem", enlaces /in/) para ajustarlos en un solo lugar.

Estructura observada (2026):
  div[role="listitem"]                       -> tarjeta de resultado
    > div[data-display-contents]
      > a[href*="/in/"]                      -> enlace exterior que envuelve la tarjeta
        > p > a[href*="/in/"]                -> enlace del nombre (texto = nombre)
        > div > p                            -> cargo (subtítulo)
"""

import re

RESULT_CARD = "div[role='listitem']:has(a[href*='/in/'])"
RESULTS_CONTAINER = RESULT_CARD

NAME_LINK = "p > a[href*='/in/']"

HEADLINE = "xpath=../following-sibling::div[1]//p[1]"

# Texto del cargo actual en la empresa buscada, p.ej. "Actual: Desarrollador CLOUD en VCSOFT"
SNIPPET = "div[id^='SearchResultssnippet_']"

# Sección "Experiencia" del perfil (se usa al verificar el puesto actual en el
# perfil cuando el snippet del resultado no empieza con "Actual:").
# LinkedIn 2026 la marca con un id que contiene "ExperienceTopLevelSection";
# se conserva el id clásico (#experience) como fallback por si rota de nuevo.
EXPERIENCE_SECTION = (
    "[id*='ExperienceTopLevelSection'], section[id='experience'], div[id='experience']"
)

GUEST_WALL_MODAL = "div.cta-modal"

AUTHWALL_URL_MARKS = ("/authwall", "/login", "/signup", "/checkpoint", "captcha", "challenge")

# ---------------------------------------------------------------------------
# Panel "Todos los filtros" (People search) — versión 2026.
# Ya NO es un modal: es un panel inline que se abre con el botón
# "All filters"/"Todos los filtros". Cada filtro se aplica AL INSTANTE como
# chip al seleccionar la opción (no hay botón Apply; el Submit interno está
# oculto y deshabilitado). El panel se cierra con Escape. Todo se resuelve
# por rol/etiqueta accesible y placeholder (estable ante la rotación de
# clases). VERIFICADO EN VIVO (2026, UI en inglés).
# ---------------------------------------------------------------------------

# Botón que abre el panel.
ALL_FILTERS_TRIGGER_TEXT = re.compile(r"^(todos los filtros|all filters)$", re.IGNORECASE)
# Marcador de que el panel ya está abierto (botón Restablecer/Reset).
FILTERS_PANEL_MARKER = re.compile(r"^restablecer$|reset", re.IGNORECASE)

# Botones "Add X" que despliegan el buscador de cada chip (bilingües).
# Una vez añadido el primer chip de una sección, su botón DESAPARECE.
ADD_LOCATION_BUTTON_TEXT = re.compile(r"^(añadir ubicaci[oó]n|add a location)$", re.IGNORECASE)
ADD_INDUSTRY_BUTTON_TEXT = re.compile(r"^(añadir sector|add an industry)$", re.IGNORECASE)
ADD_COMPANY_BUTTON_TEXT = re.compile(r"^(añadir empresa|add a company)$", re.IGNORECASE)

# Inputs typeahead del panel (bilingüe, insensible a mayúsculas).
LOCATION_INPUT = "input[placeholder*='ocation' i], input[placeholder*='ubicaci' i]"
INDUSTRY_INPUT = "input[placeholder*='ndustry' i], input[placeholder*='sector' i]"
COMPANY_INPUT = "input[placeholder*='ompany' i], input[placeholder*='empresa' i]"

# Botón de página siguiente: estrategia dual. El legacy usa data-test-id;
# el nuevo panel SPA se pagina con el botón Next/Siguiente por rol y nombre.
NEXT_PAGE_LEGACY = "[data-test-id='pagination-next-page']"
NEXT_PAGE_FALLBACK = re.compile(r"^(next|siguiente)$", re.IGNORECASE)
