# ESTADO DE LA TAREA — Cambio de filtros del scraper de LinkedIn

> Documento para retomar el trabajo donde se quedó (última actualización:
> calibración en vivo terminada, implementación pendiente).

## Objetivo

Reemplazar los filtros actuales del scraper (`title`, `industry`, `company`
del modal viejo) por:

1. **locations** — campo de país (uno o varios).
2. **Empresa actual** — SIEMPRE la misma empresa que se busca (automático,
   no se pide al usuario).
3. **industries** — varias separadas por coma. Sugerencias recomendadas:
   - `IT Services and IT Consulting`
   - `Technology, Information and Internet`

También adaptar la interfaz web (formulario) y probar con ritmo **tranquilo**
(el usuario pidió explícitamente NO acelerar las pruebas).

## Estado actual

- Sesión cambiada: se borró `data/storage_state.json` y se inició sesión con
  la cuenta nueva (**la UI de LinkedIn quedó en INGLÉS**: "All filters",
  "Add a location", "Next", etc.). Login verificado: `login_completado`.
- Calibración en vivo del nuevo panel de filtros: **COMPLETA**.
- Implementación en código producción: **PENDIENTE** (no se ha tocado nada
  todavía de app/jobs/scraper/frontend para esta tarea).

## Hallazgos de la calibración (verificados en vivo, cuenta EN inglés)

### Panel de filtros nuevo
- Ya NO existe un modal `div[role=dialog]` ni `.artdeco-modal`: es un panel
  inline que se abre con el botón `All filters` (rol button). Los textos
  antiguos en español hay que hacerlos bilingües.
- Botones "Add X" (get_by_role button):
  - `^add a location$` (+ español previsto `^añadir ubicación$`)
  - `^add an industry$` (+ `^añadir sector$`)
  - `^add a company$` (+ `^añadir empresa$`)  ← empresa ACTUAL del filtro
  - Al añadir un chip, el botón "Add X" correspondiente DESAPARECE.
- Inputs typeahead (CSS, case-insensitive):
  - ubicación: `input[placeholder*='ocation' i]`
  - industria: `input[placeholder*='ndustry' i]`
  - empresa:   `input[placeholder*='ompany' i]`
- Selección de opciones: escribir en el input → aparecen `[role=option]`
  (~4s de espera) → clic en la opción.
  **IMPORTANTE**: comparar solo la PRIMERA LÍNEA del texto de la opción en
  minúsculas, porque las de empresa traen texto compuesto:
  `Google |  | Software Development`.
  Con coincidencia exacta de primera línea funcionaron: `Mexico`,
  `IT Services and IT Consulting`, `Technology, Information and Internet`,
  `Google`.

### Aplicación instantánea (sin botón Apply)
- Los filtros se aplican como chips AL INSTANTE de seleccionar cada opción.
- El botón `Submit` existe pero está OCULTO y DESHABILADO (rect 0x0,
  disabled=true): no se usa. Tampoco cambia la URL al aplicar.
- Para cerrar el panel: `Escape`. Los resultados ya quedan filtrados detrás
  (10 tarjetas con enlace vs 3 sin filtros).

### Paginación (CRÍTICO — cambio de estrategia)
- La URL NO refleja los filtros (estado puramente cliente/SPA).
- Hacer `goto(...&page=N)` pierde los filtros; además en pruebas previas
  (test_final con la cuenta nueva) la página 2 por URL devolvió el mismo
  contenido y el dedup la descartó.
- **Forma correcta**: clic en el botón `Next` DENTRO de la SPA
  (`get_by_role("button", name="^next$")`; el selector viejo
  `[data-test-id="pagination-next-page"]` ya no aplica). Tras el clic la URL
  sí se actualiza a `...&page=2&spellCorrectionEnabled=true...` y los
  resultados siguen filtrados (verificado página 2 = 10 filas @Google).
- El botón `NEXT_PAGE` viejo debe volverse estrategia dual: data-test-id
  (legacy) + rol/nombre `^(next|siguiente)$`.

### Otros datos útiles
- Con filtros activos se extraen 10 filas/página con URL (antes 3): muchos
  resultados eran "Miembro de LinkedIn" sin enlace público.
- `_extract_results`, perfil-lookup y pacing de la tarea anterior funcionan
  bien (ya probados en vivo); esta tarea NO los toca.

## Pendiente (orden sugerido)

1. `scraper/selectors.py`
   - Constantes bilingües nuevas: add-buttons (location/industry/company),
     placeholders de inputs, `NEXT_PAGE_FALLBACK` (rol/nombre next|siguiente).
   - Eliminar lo obsoleto: `TITLE_FIELD_LABELS`, `COMPANY_FIELD_LABELS`,
     `SECTOR_SEARCH_PLACEHOLDER`, `APPLY_FILTERS_TEXT` (no hay botón aplicar).
2. `scraper/linkedin.py`
   - Helper genérico de combo (calibrado): si Add-btn visible → clic;
     clic+fill input; espera 3–4s; match de opción por primera línea
     ci-exact; clic; Escape si no hubo match.
   - Reescribir `_apply_filters(page, filters)` con
     `{locations:[], current_company:"", industries:[]}` (cada bloque con
     try/except independiente). Borrar `_fill_text_field`,
     `_pick_industries`, `_pick_industry`.
   - `_scrape`: paginar SIEMPRE con clic en Next dentro de la SPA (no
     `goto&page=N`); mantener condiciones de parada (sin filas nuevas /
     sin next / max_pages). `base_url/_strip_page_param` queda solo para la
     URL inicial.
3. `app.py` `/api/search`
   - Normalizar `filters.locations` e `filters.industries` (lista o texto
     con comas, reutilizar `_normalize_list`).
   - Inyectar siempre `filters["current_company"] = company`.
4. Frontend
   - `templates/index.html`: quitar Cargo, el `<select>` gigante de sectores
     y "Empresa actual"; dejar inputs `filterLocations` (país/es por coma) y
     `filterIndustries` con `datalist` sugerencias: las dos industrias
     recomendadas.
   - `static/app.js`: payload con `filters.locations` / `filters.industries`
     como listas; borrar lógica del select múltiple.
5. Docs: actualizar `SPECS.md` (filtros, paginación por clic, hallazgos 2026)
   y `README.md`.
6. Prueba final TRANQUILA (timings por defecto, sin overrides): búsqueda con
   país + 2 industrias + empresa automática, 1–2 páginas, verificar Excel.
7. Borrar scripts auxiliares: `_calibrate_*.py` (filtros, submit, autoapply,
   paginacion).

## Scripts auxiliares presentes (referencia, borrar al final)

- `_calibrate_filters.py` — flujo completo de selección (versión con bug de
  Submit al final, pero útil para el helper de opciones por primera línea).
- `_calibrate_submit.py` — demuestra que Submit está oculto/deshabilitado.
- `_calibrate_autoapply.py` — demuestra aplicación instantánea sin cambiar URL.
- `_calibrate_paginacion.py` — DEMUESTRA la estrategia ganadora: filtros +
  Next por clic conservan el filtrado (página 2 = 10 filas @Google). Es la
  mejor referencia para reescribir `_apply_filters` + `_scrape`.
