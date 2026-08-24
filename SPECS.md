# SPECS — LinkedIn Employee Scraper

Documento de referencia técnica del sistema. Para dudas sobre *cómo funciona* el
código, consúltese este documento. El `README.md` sigue siendo la guía de uso,
instalación y estructura de archivos.

## Resumen del sistema

Scraper web local de LinkedIn: busca los empleados que trabajan en una empresa
indicada por el usuario, extrae de cada perfil **Nombre**, **Cargo** y **URL del
perfil**, y exporta los datos a un Excel `.xlsx`. Incluye una interfaz web que
muestra el progreso en vivo y permite descargar el archivo.

## Arquitectura y flujo de datos

```
Navegador (templates/index.html + static/app.js)
   │  POST /api/search
   ▼
Flask (app.py) ── crea un job ──▶ JobManager (jobs.py, en memoria)
   │                                │ (thread daemon)
   │                                ▼
   │                        LinkedInScraper (scraper/linkedin.py, Playwright)
   │                                │
   │                                ▼
   │                        export_to_excel (excel_writer.py) ──▶ data/exports/*.xlsx
   │
   └── poll GET /api/jobs/<id> ──▶ progreso en vivo en el navegador
```

- Todo el trabajo pesado (login o scraping) corre en un `threading.Thread` en
  segundo plano; Flask responde de inmediato con un `job_id`.
- El frontend consulta el estado del job por **polling** cada 1.5s
  (`POLL_INTERVAL` en `static/app.js`).
- El estado de los jobs vive **en memoria** (no hay base de datos): si se
  reinicia el servidor se pierden los jobs activos, pero los Excels generados se
  conservan en `data/exports/`.

## Parte por parte

### `app.py` — Servidor Flask y coordinación

| Endpoint | Función |
|---|---|
| `GET /` | Sirve la página web. |
| `GET /api/auth/status` | Dice si hay sesión guardada (`data/storage_state.json`) y si hay un login en curso. |
| `POST /api/login` | Lanza el login en un hilo (`_run_login`); no bloquea la petición. |
| `POST /api/search` | Valida empresa y opciones de paginación, verifica que exista sesión, crea un job y lo ejecuta en un hilo (`_run_job`). |
| `GET /api/jobs/<id>` | Devuelve el estado del job. |
| `GET /api/jobs/<id>/download` | Sirve el Excel generado (solo si el job está `done` y tiene archivo). |

Paginación en `/api/search`:
- Modo normal (`all_pages` ausente/falso): `max_pages` numérico, acotado a `[1, MAX_PAGES_LIMIT]` (por defecto `DEFAULT_MAX_PAGES`).
- Modo "todas las páginas" (`all_pages: true`): `max_pages` se guarda como `0` en el
  job; el scraper recorre páginas hasta agotar resultados, con tope de seguridad
  `ALL_PAGES_SAFETY_LIMIT`.

Filtros de LinkedIn en `/api/search`:
- Acepta un objeto opcional `filters` con claves `locations` (país/es) e
  `industries` (sector/es). Cada valor puede venir como lista (JSON) o como texto
  separado por coma/;/| (con comillas para valores que contengan coma); lo
  normaliza `_normalize_list`. Se ignoran claves desconocidas o vacías. Si no
  llega ningún filtro, ni siquiera se abre el panel de LinkedIn.
- La clave `current_company` NO la envía el cliente: si hay algún filtro,
  `app.py` inyecta SIEMPRE `filters["current_company"] = company`, para que el
  scraper aplique el filtro "Empresa actual" con la propia empresa buscada.
- El frontend separa varios valores con punto y coma (`;`) porque las industrias
  recomendadas contienen comas ("Technology, Information and Internet").

Detalles:
- `_run_job` es el corazón de la búsqueda: recorre páginas, va actualizando el
  job con el progreso y, al terminar, genera el Excel.
- Manejo de errores en `_run_job`:
  - `LoginRequiredError` → estado `needs_login` (sesión caducada).
  - `AuthWallError` / `CaptchaError` → estado `error` (LinkedIn bloqueó la automatización).
  - `ScraperError` → estado `error` con el mensaje.
  - Cualquier otra excepción → estado `error` con "Error inesperado".
- Usa un `threading.Lock` global para permitir **solo un login a la vez**
  (`LOGIN_STATE`).

### `config.py` — Constantes y rutas centralizadas

- Rutas: `BASE_DIR`, `DATA_DIR`, `EXPORTS_DIR`, `STORAGE_STATE_PATH`.
- URLs de LinkedIn: login, feed y búsqueda de personas.
- Parámetros: `DEFAULT_MAX_PAGES` (10), `MAX_PAGES_LIMIT` (100),
  `ALL_PAGES_SAFETY_LIMIT` (500), `LOGIN_TIMEOUT_SECONDS` (5 min).
- Ritmo de scraping: `PAGE_MIN_SECONDS` (60) y `PAGE_MAX_SECONDS` (180) delimitan
  el tiempo total por página; `PAUSE_CHUNK_MIN/MAX` (8–25 s) trocean las pausas
  de relleno; `SCROLL_STEP` (300 px) y `SCROLL_STEP_DELAY_MIN/MAX` (0.4–0.9 s)
  controlan la velocidad del scroll gradual.
- Panel de filtros (calibrado en vivo, ritmo tranquilo): `FILTER_ADD_DELAY` (3 s,
  tras abrir el buscador con "Add X"), `FILTER_TYPEAHEAD_DELAY` (4 s, espera de
  opciones), `FILTER_SELECT_DELAY` (4 s, tras confirmar el chip),
  `FILTER_RETRY_DELAY` (2 s, tras Escape sin coincidencia) y
  `FILTER_CLOSE_DELAY` (2 s, tras cerrar el panel).
- Verificación de perfiles: `PROFILE_LOOKUP_DELAY_MIN/MAX` (20–40 s por perfil
  visitado), `PROFILE_LOAD_TIMEOUT_SECONDS` (45) y
  `PROFILE_EXPERIENCE_WAIT_SECONDS` (15).
- Crea las carpetas `data/` y `data/exports/` al importarse.

### `jobs.py` — Gestor de jobs en memoria (thread-safe)

`JobManager` guarda los jobs en un dict y los protege con `threading.Lock`.

- `create(company, max_pages, all_pages=False, filters=None)`: genera un ID único
  (`uuid4` de 12 hex) y el job con estado inicial `pending`, contadores
  (`current_page`, `found`), `results`, la bandera `all_pages`, los `filters`
  (copia del dict) y metadatos temporales (`created_at`, `updated_at`).
- `get(job_id)`: devuelve una **copia** del job (clona la lista de `results`)
  para que quien lo lee no vea datos a medio escribir.
- `update(job_id, **kwargs)`: modifica campos arbitrarios y actualiza
  `updated_at`.
- `append_results(job_id, new_results)`: añade resultados **deduplicándolos**
  por URL (o por `nombre|cargo` cuando no hay URL) para evitar repetidos entre
  páginas, y actualiza el contador `found`.

### `scraper/linkedin.py` — Lógica Playwright (la parte más frágil)

Excepciones jerárquicas:
- `ScraperError` (base) → `LoginRequiredError`, `AuthWallError`, `CaptchaError`.

| Método | Rol |
|---|---|
| `scrape` / `login` | Wrappers que ejecutan la versión asíncrona con `asyncio.run`. |
| `_open` | Lanza Chromium **con ventana visible** (necesario para que el usuario haga login), con user-agent real, locale `es-ES` y timezone MX; oculta que es un navegador automatizado. Si existe `storage_state.json`, lo reutiliza como sesión. |
| `_scrape` | Recorre página por página de `/search/results/people/?keywords=...`. La página 1 se abre por URL; las siguientes SIEMPRE con clic en Next dentro de la SPA (`_go_to_next_page`): la URL no conserva los filtros del panel 2026 (estado puramente cliente) y `goto(...&page=N)` los pierde. Si `max_pages > 0`, recorre hasta esa página; si es `0` (modo "todas las páginas"), itera hasta agotar resultados o llegar a `ALL_PAGES_SAFETY_LIMIT`. En la página 1, si hay `filters`, llama a `_apply_filters` y extrae directamente de los resultados ya filtrados. Por página: verifica interrupciones (captcha/authwall), espera tarjetas de resultado, hace scroll gradual, extrae datos y llama a `progress()` para notificar al job. Dedup de resultados acumulado y **pacing por página**: mide el tiempo real de la página y lo completa hasta un objetivo sorteado de 1–3 min (`PAGE_MIN_SECONDS`/`PAGE_MAX_SECONDS`) con pausas en trozos (`_pace_page`). |
| `_go_to_next_page` | Clic en el botón de página siguiente DENTRO de la SPA, con estrategia dual: data-test-id legacy (`NEXT_PAGE_LEGACY`) + rol/nombre `^(next\|siguiente)$` (`NEXT_PAGE_FALLBACK`). Devuelve False (fin del recorrido) si no hay botón visible o está deshabilitado; tras el clic deja 5–9 s a que la SPA cargue. Verificado en vivo (2026): tras el clic la URL sí se actualiza (`...&page=N...`) y los resultados siguen filtrados. |
| `_apply_filters` | Abre el panel inline "All filters" y aplica `{locations: [], industries: [], current_company: ""}` como chips typeahead vía `_pick_combo`. El panel 2026 aplica cada selección AL INSTANTE (no hay botón Apply; el Submit interno está oculto y deshabilitado); al terminar se cierra con Escape y los resultados quedan filtrados detrás. Cada bloque tiene try/except independiente para que un fallo de un filtro no tumbe la búsqueda. |
| `_pick_combo` | Helper genérico de combo calibrado en vivo: pulsa el botón "Add X" si sigue visible (desaparece tras el primer chip de su sección), clic + fill del input typeahead, espera ~4 s y hace clic en la opción `[role=option]` cuya PRIMERA LÍNEA coincide exactamente en minúsculas (las opciones de empresa traen texto compuesto tipo "Google \|  \| Software Development"). Sin coincidencia, pulsa Escape para cerrar el desplegable sin contaminar la siguiente selección. Timings en config (`FILTER_*_DELAY`). |
| `_login` | Abre el feed; si ya existe la cookie `li_at`, guarda el estado y termina (`ya_autenticado`). Si no, abre la página de login y espera (hasta 5 min) a que el **usuario escriba sus credenciales a mano**; al detectar la cookie guarda `storage_state.json`. |
| `_extract_results` | Por tarjeta extrae nombre, URL (`/in/...`) y cargo usando los selectores centralizados. El cargo se decide así: si el snippet es del tipo **"Actual: \<puesto\> en \<empresa\>"** se limpia con `clean_position` (confianza total); si el snippet falta o tiene otro prefijo ("Anterior:", "Educación:", texto libre), se **verifica en el perfil** con `_lookup_current_role` (abre el perfil en una pestaña aparte, lee la experiencia actual y solo acepta el puesto si la empresa coincide con la buscada; añade una demora de 20–40 s por visita). Si la verificación no da resultado, se conserva el cargo del subtítulo. |
| `clean_position` | Convierte `"Actual: Desarrollador CLOUD en VCSOFT"` → `"Desarrollador CLOUD"` (quita lo previo a `:` y lo posterior a ` en ` / ` at `). Solo se aplica cuando `_snippet_is_current` confirma que el snippet empieza con "Actual:"/"Current:". |
| `_snippet_is_current` | True si el snippet es "Actual:/Current: \<texto\>". Prefijos como "Anterior:" o "Educación:" devuelven False y disparan la verificación en el perfil. |
| `_lookup_current_role(page, profile_url, company)` | Abre el perfil en una **pestaña nueva** del mismo contexto (la página de resultados nunca se recarga ni pierde el scroll). El perfil hidrata su contenido de forma diferida y la sección Experiencia solo se monta al hacer scroll del contenedor interno: espera ~2s, hace scroll (`_scroll_gradually`) y reintenta hasta 2 veces antes de rendirse. Lee el texto completo del card (no `li`: el DOM 2026 ya no usa listas), lo parsea con `_parse_experience_item` y devuelve el título solo si `_company_matches` confirma que la empresa coincide con la buscada. La pestaña se cierra siempre (`finally`). Detecta authwall/captcha también en el perfil. Verificado en vivo (2026): sin la espera de hidratación el lookup falla siempre. |
| `_parse_experience_item(text)` | Extrae `(titulo, empresa)` de la primera entrada de experiencia a partir de las líneas de texto (ignora el encabezado "Experiencia"/"Experience" inicial): la línea de empresa es la primera con `·` que no sea un rango de fechas (descarta líneas con dígitos o nombres de mes); si la entrada es un grupo de varios puestos en la misma empresa ("Empresa / duración / Puesto / fechas"), toma la empresa de la primera línea y el título de la tercera. |
| `_norm_company` / `_company_matches` | Normalizan nombres de empresa (minúsculas, sin acentos ni signos, sin sufijos societarios SA/SAC/SRL/INC/LLC...) y comparan por contención en cualquier dirección (mínimo 3 caracteres normalizados). |
| `_check_interruptions` | Detecta CAPTCHA/challenge, authwall (por URL o por el modal `GUEST_WALL_MODAL`). |
| `_scroll_gradually` | Scroll progresivo con pausa aleatoria (`SCROLL_STEP_DELAY_MIN`–`MAX` s) por paso de `SCROLL_STEP` px. **LinkedIn 2026 ya no scrollea la ventana**: el contenido vive en un contenedor interno con scroll propio (`#workspace`); la función lo detecta (o busca cualquier div alto con overflow) y desplaza ese contenedor hasta un fondo estable, con fallback al `window`. Aplica tanto a resultados como a perfiles. |
| `_pace_page(elapsed)` | Garantiza el ritmo de 1–3 min por página: sortea un objetivo (`PAGE_MIN_SECONDS`–`PAGE_MAX_SECONDS`) y duerme la diferencia contra el tiempo ya gastado, en trozos aleatorios de `PAUSE_CHUNK_MIN`–`PAUSE_CHUNK_MAX` s. Si la página ya consumió más que el objetivo (red lenta, filtros), no añade espera. |

### `scraper/selectors.py` — Selectores CSS centralizados

LinkedIn cambia su DOM con frecuencia (clases con hash que rotan). Los selectores
están anclados a atributos semánticos estables (`div[role='listitem']`, enlaces
con `/in/`). Si el scraping deja de funcionar, se ajusta aquí en un solo lugar.

El panel de filtros 2026 ya NO es un modal (`div[role=dialog]`/`.artdeco-modal`
desaparecieron): es un panel inline que se abre con el botón "All filters" y
aplica cada filtro AL INSTANTE como chip (sin botón Apply). Los selectores se
resuelven **por rol/etiqueta accesible y placeholder** (`get_by_role`,
`input[placeholder]`), bilingües EN/ES, no por clases CSS, porque LinkedIn rota
las clases: botones "Add a location"/"Añadir ubicación",
"Add an industry"/"Añadir sector" y "Add a company"/"Añadir empresa"; inputs
typeahead por placeholder (`ocation|ubicaci`, `ndustry|sector`, `ompany|empresa`);
opciones `[role=option]`; cierre del panel con Escape. La paginación usa
estrategia dual: `[data-test-id='pagination-next-page']` (legacy) + botón
Next/Siguiente por rol/nombre. Si LinkedIn los cambia, se ajustan aquí.

La sección Experiencia del perfil (para la verificación de puesto) usa
`EXPERIENCE_SECTION`: en el DOM 2026 el card se ancla a un id que contiene
`ExperienceTopLevelSection` (se conserva `#experience` clásico como fallback).
Las entradas ya NO son `<li>`: se separan con `<hr>` y se lee el texto completo
del card. Verificado en vivo (2026).

### `excel_writer.py` — Generación del Excel

- Cabeceras: `Nombre | Cargo | Correo | Número de teléfono | URL del perfil`.
  **Correo y Teléfono son columnas vacías** (marcos para rellenar a mano).
- Formato: cabecera azul, anchos de columna, `freeze_panes = "A2"`.
- Nombre de archivo con timestamp: `empleados_<empresa>_<YYYY-mm-dd_HH-MM-SS>.xlsx`
  guardado en `data/exports/`.

### `templates/index.html` + `static/app.js` — Frontend

- El HTML: formulario (empresa + máx. páginas con opción "todas las páginas" +
  sección desplegable **Filtros de LinkedIn opcional** con País/Ubicación y
  Sector/Industria), banner de estado de sesión, tarjeta de progreso (página
  actual, encontrados, barra), caja de errores, tabla de resultados y botón de
  descarga. Los sectores sugeridos van en un `<datalist>` con los dos valores
  recomendados ("IT Services and IT Consulting", "Technology, Information and
  Internet"); la "Empresa actual" no existe como campo: la inyecta el backend.
- El JS hace:
  - Polling del estado de login (`pollLogin`, cada 1.5s).
  - Polling del job (`startJob`, cada 1.5s) y renderizado en vivo.
  - Barra de progreso: `current_page / max_pages` en modo normal; en modo
    "todas las páginas" (`job.all_pages`) usa una animación **indeterminada**.
  - **Vista previa de máx. 60 resultados** (`PREVIEW_LIMIT`) en la tabla.
  - Enlaza el botón de descarga a `/api/jobs/<id>/download`.
  - Bloquea el formulario mientras hay una búsqueda en curso.
  - Deshabilita el input de páginas cuando el checkbox "todas las páginas" está activo.
  - Envía los filtros rellenos en el payload como `filters.locations` y
    `filters.industries`, ambas como **listas** (divide por `;`, `|` o salto de
    línea con `splitList`; NO divide por coma para no romper nombres que la
    contienen).

## Flujo detallado de una búsqueda

1. El usuario abre `http://127.0.0.1:5000` y, si no hay sesión, pulsa
   **Iniciar sesión en LinkedIn** → `POST /api/login` abre Chromium visible;
   el usuario entra con su cuenta y la sesión queda guardada en
   `data/storage_state.json`.
2. El usuario rellena empresa, elige el máximo de páginas o marca **Recorrer todas
   las páginas disponibles**, y opcionalmente rellena los **Filtros de LinkedIn**
   (país y sectores, separados por `;`). Pulsa **Buscar empleados** →
   `POST /api/search` valida, crea el job (con `current_company` inyectada si hay
   filtros) y devuelve `{ job_id }`.
3. `_run_job` ejecuta `scraper.scrape()`; en la página 1 aplica los filtros como
   chips en el panel "All filters" de LinkedIn, cierra el panel con Escape y
   extrae los resultados ya filtrados. Las páginas siguientes se recorren con
   clic en el botón Next dentro de la SPA (la URL no conserva los filtros).
   Cada página llama a `progress()`, que actualiza `current_page` y va
   acumulando resultados deduplicados. El cargo se toma del snippet
   "Actual: ..." cuando existe; si no, se verifica visitando el perfil
   (pestaña aparte, solo si la empresa coincide con la buscada, +20–40 s por
   visita) y la página regresa sola a los resultados para continuar.
4. Al terminar, `export_to_excel` genera el `.xlsx` y el job pasa a `done` con
   `filepath` y `filename`.
5. El botón **Descargar Excel** enlaza a `GET /api/jobs/<id>/download`.

## Notas técnicas

- Los jobs son volátiles (en memoria): reiniciar el servidor pierde jobs activos.
- `data/storage_state.json` contiene cookies de sesión y **no se versiona**
  (está en `.gitignore`).
- **Aviso legal**: el scraping automatizado de LinkedIn puede violar sus términos
  de servicio. Está pensado para uso personal y a bajo volumen; LinkedIn puede
  bloquear la cuenta si detecta automatización intensiva.
