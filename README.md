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

## Despliegue con Docker

La aplicación se conteneriza con un display virtual (Xvfb): Chromium corre con
ventana "visible" dentro del contenedor (mismo comportamiento anti-detección que
en local) y puedes verlo/controlarlo desde tu navegador vía noVNC para completar
el login de LinkedIn en el servidor.

### Archivos

- `Dockerfile` — imagen oficial Playwright + Xvfb/noVNC
- `entrypoint.sh` — arranca display virtual, VNC y gunicorn
- `docker-compose.yml` — puerto 5000 (app), 6080 (noVNC), volumen `./data`

### Desplegar en el servidor

1. Instala Docker Engine + plugin compose en el servidor (Linux):

   ```bash
   curl -fsSL https://get.docker.com | sh
   ```

2. Clona el repo y levanta el servicio:

   ```bash
   git clone <url-del-repo>
   cd scrapping
   docker compose up -d --build
   ```

3. Abre los puertos en el firewall: `5000` (app web) y `6080` (noVNC).

4. **Primer login**: entra a `http://<servidor>:6080/vnc.html` (escritorio del
   contenedor), y en otra pestaña abre `http://<servidor>:5000`, pulsa
   **Iniciar sesión** y escribe tus credenciales/captcha dentro del canvas de
   noVNC. Tienes 5 minutos. La sesión queda guardada en `data/storage_state.json`
   (volumen persistente) y los siguientes inicios serán automáticos.

### Notas de operación

- `data/` se monta como volumen: la sesión y los Excel sobreviven a reinicios y
  recreaciones del contenedor.
- Los jobs en curso viven en memoria: al reiniciar el contenedor se pierden
  (los Excel ya descargados no).
- noVNC queda expuesto **sin contraseña** por defecto. Protégelo descomentando
  `VNC_PASSWORD` en `docker-compose.yml` o restringiendo el puerto 6080 en el
  firewall (ábrenlo solo durante el login).
- Actualizar a una nueva versión:

  ```bash
  git pull
  docker compose up -d --build
  ```

## Límites anti-detección

La aplicación se auto-limita para imitar uso personal a bajo volumen. Todos los
valores son configurables en `config.py` (bloque "Límites anti-detección").

- **Páginas por búsqueda**: máximo 25 en la UI; el modo "todas las páginas"
  comparte ese mismo techo de emergencia.
- **Ritmo**: cada página tarda 3–5 min (carga, scroll y pausas de lectura).
- **Sesión continua**: máximo 60 min de actividad por job; al llegar al límite
  corta tras terminar la página en curso y exporta lo acumulado. Las pausas
  largas entre bloques de perfiles NO consumen este tiempo.
- **Perfiles visitados**: en bloques de 15, con pausa aleatoria de 5–15 min
  entre bloques; tope duro de 70 visitas/día. Si el tope se agota a mitad de
  búsqueda, los perfiles restantes quedan con el cargo sin verificar y el job
  termina igual (el mensaje final lo indica).
- **Cooldown**: hay que esperar 2 h desde el fin de una búsqueda para lanzar
  otra; fuera de eso la API responde cuándo estará disponible.
- **Horario**: solo se pueden INICIAR búsquedas entre las 8:00 y las 21:00
  (hora del servidor). Varía tú la hora exacta dentro de la franja: el timing
  fijo diario es tan detectable como el volumen.

El contador diario vive en `data/usage_state.json` y sobrevive a reinicios del
contenedor. El uso manual de LinkedIn no es rastreable por la app: si navegas
LinkedIn a mano el mismo día, suma esas visitas editando la entrada de la fecha
en ese archivo. Con Premium tienes más margen oficial, pero el límite real lo
pone el patrón de comportamiento, no la cuota.

Además, cada ejecución rota fingerprint (user-agent Windows/macOS + tamaño de
ventana aleatorios, stealth completo vía playwright-stealth) y un circuit
breaker corta el job al detectar mensajes de restricción de uso comercial,
límites alcanzados o cuenta restringida, igual que ya hacía con captcha/authwall.

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