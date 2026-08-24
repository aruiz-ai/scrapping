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
- Acepta un objeto opcional `filters` con claves `title`, `industry`, `company`
  (Cargo/Título, Sector/Industria, Empresa actual). Se ignoran claves desconocidas
  o valores vacíos. Se guardan en el job y se pasan al scraper, que los aplica en
  el modal "Todos los filtros" de LinkedIn (ver `_apply_filters`).
- El campo `title` acepta un único cargo (LinkedIn no soporta varios términos con
  OR en ese campo; hay estrategias posibles a futuro, pero por ahora se usa uno solo).
- El campo `industry` acepta **varios sectores**: el valor puede venir como lista
  (JSON) o como texto separado por comas, punto y coma o `|`. `app.py` lo normaliza
  y `_pick_industries` los aplica uno a uno, ya que LinkedIn sí permite varios
  chips de sector (verificado en vivo: `industry=%5B%224%22%2C%2296%22%5D` para
  "Desarrollo de software" + "Servicios y consultoría de TI").

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
| `_scrape` | Recorre página por página de `/search/results/people/?keywords=...`. Si `max_pages > 0`, recorre hasta esa página; si es `0` (modo "todas las páginas"), itera hasta agotar resultados o llegar a `ALL_PAGES_SAFETY_LIMIT`. En la página 1, si hay `filters`, llama a `_apply_filters` y reutiliza la URL resultante (`_strip_page_param`) como base de paginación para que las páginas siguientes conserven los filtros. Por página: verifica interrupciones (captcha/authwall), espera tarjetas de resultado, hace scroll gradual, extrae datos y llama a `progress()` para notificar al job. Dedup de resultados acumulado y **pacing por página**: mide el tiempo real de la página y lo completa hasta un objetivo sorteado de 1–3 min (`PAGE_MIN_SECONDS`/`PAGE_MAX_SECONDS`) con pausas en trozos (`_pace_page`), así cada página tarda entre 1 y 3 minutos sumando todas sus actividades. |
| `_apply_filters` | Abre el modal "Todos los filtros" y aplica los filtros dados (cargo, empresa, sector). Cada filtro se aplica con `try/except`: si un selector falla se continúa con el resto (o sin filtros), para no tumbar la búsqueda. |
| `_fill_text_field` | Rellena un campo de texto de la sección "Palabras clave" del modal (Cargo, Empresa). |
| `_pick_industries` | Divide el valor de sector (con `_split_sectors`) en varios y llama a `_pick_industry` por cada uno. |
| `_pick_industry` | Asegura el buscador "Añadir sector" abierto (lo abre si la búsqueda anterior lo cerró), escribe y selecciona la opción (`role="option"`) que coincide con el texto; si no hay coincidencia, se omite ese sector. |
| `_strip_page_param` | Quita el parámetro `page=N` de una URL (para usarla como base de paginación con filtros ya aplicados). |
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

Para el modal "Todos los filtros" los selectores se resuelven **por rol/etiqueta
accesible y placeholder** (`get_by_role`, `input[placeholder]`), no por clases
CSS, porque LinkedIn rota las clases. Verificado en vivo (2026): el modal usa
inputs de texto "Cargo" y "Empresa" (sección "Palabras clave"), un botón
"Añadir sector" con buscador de opciones, y un enlace "Mostrar resultados" para
confirmar. Si LinkedIn los cambia, se ajustan aquí.

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
  sección desplegable **Filtros de LinkedIn opcional** con Cargo/Título, Sector y
  Empresa actual), banner de estado de sesión, tarjeta de progreso (página
  actual, encontrados, barra), caja de errores, tabla de resultados y botón de
  descarga. El sector se elige con un `<select multiple>` que incluye la **taxonomía
  completa de sectores de LinkedIn en español** (~188, barridos del typeahead en vivo)
  más un campo libre para otros separados por coma.
- El JS hace:
  - Polling del estado de login (`pollLogin`, cada 1.5s).
  - Polling del job (`startJob`, cada 1.5s) y renderizado en vivo.
  - Barra de progreso: `current_page / max_pages` en modo normal; en modo
    "todas las páginas" (`job.all_pages`) usa una animación **indeterminada**.
  - **Vista previa de máx. 60 resultados** (`PREVIEW_LIMIT`) en la tabla.
  - Enlaza el botón de descarga a `/api/jobs/<id>/download`.
  - Bloquea el formulario mientras hay una búsqueda en curso.
  - Deshabilita el input de páginas cuando el checkbox "todas las páginas" está activo.
  - Envía los filtros rellenos en el payload como `filters`. `industry` se envía
    como **lista** (sectores del `<select multiple>` + los del campo libre).

## Flujo detallado de una búsqueda

1. El usuario abre `http://127.0.0.1:5000` y, si no hay sesión, pulsa
   **Iniciar sesión en LinkedIn** → `POST /api/login` abre Chromium visible;
   el usuario entra con su cuenta y la sesión queda guardada en
   `data/storage_state.json`.
2. El usuario rellena empresa, elige el máximo de páginas o marca **Recorrer todas
   las páginas disponibles**, y opcionalmente rellena los **Filtros de LinkedIn**
   (título, sectores —uno o varios—, empresa actual). Pulsa **Buscar empleados** →
   `POST /api/search` valida, crea el job y devuelve `{ job_id }`.
3. `_run_job` ejecuta `scraper.scrape()`; en la página 1 aplica los filtros en el
   modal "Todos los filtros" de LinkedIn y usa la URL filtrada como base de
   paginación. Cada página llama a `progress()`, que actualiza `current_page` y va
   acumulando resultados deduplicados. El cargo se toma del snippet "Actual: ..."
   cuando existe; si no, se verifica visitando el perfil (pestaña aparte, solo si
   la empresa coincide con la buscada, +20–40 s por visita) y la página regresa
   sola a los resultados para continuar.
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
