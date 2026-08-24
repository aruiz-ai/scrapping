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
# Modal "Todos los filtros" (People search).
# Es un panel que se abre al pulsar "Todos los filtros". Se resuelve por
# rol/etiqueta accesible y placeholder (estable ante la rotación de clases).
# VERIFICADO EN VIVO (2026): el modal tiene, entre otros, los inputs de texto
# "Cargo" y "Empresa" (sección "Palabras clave"), botones "Añadir sector" que
# despliegan un buscador con opciones role="option", y el enlace de confirmar
# "Mostrar resultados".
# ---------------------------------------------------------------------------

# Botón que abre el modal.
ALL_FILTERS_TRIGGER_TEXT = re.compile(r"^(todos los filtros|all filters)$", re.IGNORECASE)
# Marcador de que el panel ya está abierto (botón Restablecer).
FILTERS_PANEL_MARKER = re.compile(r"^restablecer$|reset", re.IGNORECASE)
# Inputs de texto de la sección "Palabras clave".
TITLE_FIELD_LABELS = re.compile(r"^(cargo|title)$", re.IGNORECASE)
COMPANY_FIELD_LABELS = re.compile(r"^(empresa|company)$", re.IGNORECASE)
# Buscador de sectores: botón "Añadir sector" y su input de búsqueda.
ADD_SECTOR_BUTTON_TEXT = re.compile(r"^añadir sector$|add industry", re.IGNORECASE)
SECTOR_SEARCH_PLACEHOLDER = "Añadir sector"
# Enlace/botón que confirma y aplica los filtros.
APPLY_FILTERS_TEXT = re.compile(r"^(mostrar resultados|show results)$", re.IGNORECASE)
