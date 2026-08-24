# LinkedIn Employee Scraper

Aplicación web local que busca en LinkedIn los empleados que trabajan en una empresa
indicada por el usuario y exporta sus datos a un archivo Excel.

## Qué hace

- Búsqueda en LinkedIn People por nombre de empresa.
- Filtros opcionales de país y sector; el filtro "Empresa actual" se aplica
  siempre automáticamente con la empresa buscada.
- Extrae de cada perfil: **Nombre**, **Cargo** y **URL del perfil**.
- Genera un excel `.xlsx` con las columnas:
  `Nombre | Cargo | Correo | Número de teléfono | URL del perfil`

  `Correo` y `Número de teléfono` se crean como encabezados vacíos (no se rellenan).
  El cargo se toma del texto *"Actual: <puesto> en <empresa>"* de los resultados,
  dejando únicamente el puesto. Si el resultado no trae ese texto (p. ej. dice
  "Anterior: ..." o "Educación: ..."), se visita el perfil en una pestaña aparte
  para leer el puesto de su experiencia actual, y solo se usa si la empresa
  coincide con la buscada; luego se regresa a los resultados y se continúa
  (cada verificación añade una demora de 20–40 s).

## Requisitos

- Python 3.12+
- Windows (desarrollado y probado en Windows)

## Instalación

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

## Uso

1. Inicia el servidor:

   ```powershell
   python app.py
   ```

2. Abre http://127.0.0.1:5000 en tu navegador.
3. Si es la primera vez, haz clic en **Iniciar sesión en LinkedIn**. Se abrirá una
   ventana del navegador automatizado: entra con tu cuenta y la sesión quedará
   guardada en `data/storage_state.json` para futuros usos.
4. Escribe el nombre de la empresa y el número máximo de páginas (10 resultados por
   página), o marca **Recorrer todas las páginas disponibles** para revisarlas todas.
   Opcionalmente despliega **Filtros de LinkedIn** y rellena País/Ubicación y/o
   Sector/Industria (varios valores separados por punto y coma; el campo de sector
   trae sugerencias con los dos valores recomendados). La "Empresa actual" se aplica
   siempre automáticamente con la empresa buscada; todo se gestiona en el panel
   "All filters" de LinkedIn, que aplica cada chip al instante. Pulsa
   **Buscar empleados**.
5. Mientras corre verás el progreso en vivo; al terminar usa **Descargar Excel (.xlsx)**.

Los archivos generados quedan en `data/exports/`.

## Estructura

```
├── app.py               # Flask: rutas y coordinación de jobs
├── config.py            # Rutas y parámetros configurables
├── jobs.py              # Gestor de jobs en memoria (thread-safe)
├── excel_writer.py      # Generación del Excel
├── scraper/
│   ├── linkedin.py      # Lógica Playwright (login, búsqueda, extracción)
│   └── selectors.py     # Selectores CSS centralizados
├── templates/index.html # Página web
├── static/app.js        # Lógica del frontend
└── data/
    ├── storage_state.json   # Sesión guardada de LinkedIn (no versionar)
    └── exports/             # Excels generados
```

## Notas

- Si se caduca la sesión de LinkedIn, el proceso lo detecta y pide re-iniciar sesión.
- LinkedIn cambia su DOM con frecuencia; los selectores están centralizados en
  `scraper/selectors.py`. Si dejan de funcionar, ajusta ahí. El panel de filtros
  se resuelve por rol/etiqueta accesible y placeholder (verificados en vivo en
  2026: botones "Add a location"/"Add an industry"/"Add a company", inputs
  typeahead y opciones por primera línea); la paginación se hace con clic en el
  botón Next dentro de la SPA, porque la URL no conserva los filtros.
- **Aviso legal**: el scraping automatizado de LinkedIn puede violar sus términos de
  servicio. Esta herramienta está pensada para uso personal y a bajo volumen;
  LinkedIn puede bloquear la cuenta si detecta automatización intensiva.