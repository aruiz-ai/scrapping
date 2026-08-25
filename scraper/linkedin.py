import asyncio
import os
import random
import re
import time
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

try:  # playwright-stealth v2: refuerzo del fingerprint (plugins, WebGL, etc.)
    from playwright_stealth import Stealth
except Exception:  # pragma: no cover - si no está instalado, siguen los parches propios
    Stealth = None

import config
from scraper import selectors

# Personas de fingerprint: se elige una al azar por ejecución. El major de
# Chrome coincide SIEMPRE con el motor real (Chromium 151); solo rota el SO.
_PERSONAS = [
    {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "platform": "Win32",
        "platform_version": "15.1.0",
    },
    {
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "platform": "MacIntel",
        "platform_version": "14.6.0",
    },
]


class ScraperError(Exception):
    pass


class LoginRequiredError(ScraperError):
    pass


class AuthWallError(ScraperError):
    pass


class CaptchaError(ScraperError):
    pass


class RestrictionError(ScraperError):
    """LinkedIn señalizó restricción de uso comercial o fricción nueva."""


class LinkedInScraper:

    @staticmethod
    def clean_position(snippet):
        """Convierte 'Actual: Desarrollador CLOUD en VCSOFT' -> 'Desarrollador CLOUD'.

        Quita la etiqueta previa a los dos puntos y todo lo que sigue a ' en ' / ' at '.
        """
        text = (snippet or "").strip()
        if not text:
            return ""
        if ":" in text:
            text = text.split(":", 1)[1].strip()
        best = None
        for marker in (" en ", " at "):
            idx = text.rfind(marker)
            if idx != -1 and (best is None or idx > best[0]):
                best = (idx, marker)
        if best:
            text = text[: best[0]]
        return text.strip()

    def scrape(
        self,
        company,
        progress,
        max_pages,
        filters=None,
    ):
        return asyncio.run(
            self._scrape(
                company,
                progress,
                max_pages,
                filters,
            )
        )

    def login(self, timeout_seconds=None):
        return asyncio.run(self._login(timeout_seconds or config.LOGIN_TIMEOUT_SECONDS))

    async def _scrape(
        self,
        company,
        progress,
        max_pages,
        filters=None,
    ):
        browser, context, page = await self._open()
        try:
            first_url = (
                f"{config.LINKEDIN_SEARCH_URL}?keywords={quote_plus(company)}"
                "&origin=GLOBAL_SEARCH_HEADER"
            )
            all_results = []
            page_no = 0
            while True:
                page_no += 1
                if max_pages > 0 and page_no > max_pages:
                    break
                if max_pages <= 0 and page_no > config.ALL_PAGES_SAFETY_LIMIT:
                    break
                page_started = time.monotonic()
                if page_no == 1:
                    await page.goto(
                        first_url, wait_until="domcontentloaded", timeout=60000
                    )
                else:
                    # Paginación SIEMPRE con clic en Next dentro de la SPA:
                    # la URL no conserva los filtros del nuevo panel (estado
                    # cliente), y goto(&page=N) los pierde.
                    if not await self._go_to_next_page(page):
                        break
                await self._check_interruptions(page)
                try:
                    await page.wait_for_selector(
                        selectors.RESULTS_CONTAINER, timeout=12000
                    )
                except Exception:
                    await asyncio.sleep(3)
                await self._scroll_gradually(page)
                await self._check_interruptions(page)

                if page_no == 1 and filters:
                    await self._apply_filters(page, filters)
                    await self._check_interruptions(page)
                    try:
                        await page.wait_for_selector(
                            selectors.RESULTS_CONTAINER, timeout=12000
                        )
                    except Exception:
                        await asyncio.sleep(3)
                    await self._scroll_gradually(page)
                    await self._check_interruptions(page)

                page_results = await self._extract_results(page)
                new_on_page = self._new_items(page_results, all_results)
                all_results.extend(new_on_page)

                progress(page_no, len(all_results), all_results)

                if not page_results or not new_on_page:
                    break
                # Ritmo humano: completa la página hasta el objetivo de
                # 3-5 min (config) con pausas repartidas en trozos.
                await self._pace_page(time.monotonic() - page_started)
            return all_results
        finally:
            await browser.close()
            await self._pw.stop()

    async def _go_to_next_page(self, page):
        """Avanza a la siguiente página de resultados DENTRO de la SPA.

        Estrategia dual: data-test-id legacy y, si no existe, botón
        Next/Siguiente por rol y nombre (el panel 2026 ya no usa aquel
        atributo). Devuelve False cuando no hay página siguiente (sin botón
        o deshabilitado), lo que corta el recorrido.
        """
        candidates = []
        legacy = page.locator(selectors.NEXT_PAGE_LEGACY)
        if await legacy.count() > 0:
            candidates.append(legacy.first)
        rol = page.get_by_role("button", name=selectors.NEXT_PAGE_FALLBACK).first
        if await rol.count() > 0:
            candidates.append(rol)
        for candidate in candidates:
            try:
                if not await candidate.is_visible():
                    continue
                if await candidate.is_disabled():
                    return False
                await candidate.click(timeout=8000)
            except Exception:
                continue
            await self._human_delay(5, 9)
            return True
        return False

    async def _apply_filters(self, page, filters):
        """Abre el panel 'All filters' y aplica los filtros como chips.

        Formato: {locations: [...], industries: [...], current_company: str}.
        El panel 2026 aplica cada selección AL INSTANTE (no hay botón Apply);
        al terminar se cierra con Escape y los resultados quedan filtrados
        detrás. Cada bloque tiene try/except propio para que un fallo de un
        filtro no tumbe la búsqueda entera.
        """
        try:
            trigger = page.get_by_role("button", name=selectors.ALL_FILTERS_TRIGGER_TEXT)
            await trigger.first.click(timeout=8000)
        except Exception:
            return
        try:
            marker = page.get_by_role("button", name=selectors.FILTERS_PANEL_MARKER)
            await marker.first.wait_for(state="visible", timeout=8000)
        except Exception:
            return

        for location in filters.get("locations") or []:
            try:
                await self._pick_combo(
                    page,
                    selectors.ADD_LOCATION_BUTTON_TEXT,
                    selectors.LOCATION_INPUT,
                    location,
                )
            except Exception:
                pass
        for industry in filters.get("industries") or []:
            try:
                await self._pick_combo(
                    page,
                    selectors.ADD_INDUSTRY_BUTTON_TEXT,
                    selectors.INDUSTRY_INPUT,
                    industry,
                )
            except Exception:
                pass
        if filters.get("current_company"):
            try:
                await self._pick_combo(
                    page,
                    selectors.ADD_COMPANY_BUTTON_TEXT,
                    selectors.COMPANY_INPUT,
                    filters["current_company"],
                )
            except Exception:
                pass

        # Sin botón Apply: los chips ya están activos; solo cerrar el panel.
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await asyncio.sleep(config.FILTER_CLOSE_DELAY)

    async def _pick_combo(self, page, add_button_regex, input_selector, value):
        """Selecciona un valor en un combo typeahead del panel de filtros.

        Flujo calibrado en vivo (2026): si el botón 'Add X' sigue visible se
        pulsa para desplegar el buscador (desaparece tras el primer chip de
        su sección); se escribe el valor, se esperan las opciones (~4 s) y se
        hace clic en aquella cuya PRIMERA LÍNEA coincida exactamente en
        minúsculas (las opciones de empresa traen texto compuesto tipo
        'Google |  | Software Development'). Si no hay coincidencia se pulsa
        Escape para cerrar el desplegable y no contaminar la siguiente
        selección.
        """
        add_btn = page.get_by_role("button", name=add_button_regex).first
        try:
            if await add_btn.count() > 0 and await add_btn.is_visible():
                await add_btn.click(timeout=5000)
                await asyncio.sleep(config.FILTER_ADD_DELAY)
        except Exception:
            pass
        box = page.locator(input_selector).first
        await box.click(timeout=5000)
        await asyncio.sleep(1)
        await box.fill(value, timeout=5000)
        await asyncio.sleep(config.FILTER_TYPEAHEAD_DELAY)
        options = page.locator("[role=option]")
        for index in range(await options.count()):
            try:
                first_line = (
                    (await options.nth(index).inner_text()).strip().splitlines()[0].strip()
                )
            except Exception:
                continue
            if first_line.lower() == value.strip().lower():
                await options.nth(index).click(timeout=6000)
                await asyncio.sleep(config.FILTER_SELECT_DELAY)
                return
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await asyncio.sleep(config.FILTER_RETRY_DELAY)

    async def _login(self, timeout_seconds):
        browser, context, page = await self._open()
        try:
            await page.goto(
                config.LINKEDIN_FEED_URL, wait_until="domcontentloaded", timeout=60000
            )
            if await self._is_logged_in(context):
                await self._save_state(context)
                return "ya_autenticado"

            await page.goto(
                config.LINKEDIN_LOGIN_URL, wait_until="domcontentloaded", timeout=60000
            )
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                if await self._is_logged_in(context):
                    await self._save_state(context)
                    return "login_completado"
                await asyncio.sleep(2)
            raise ScraperError(
                "Tiempo agotado para completar el inicio de sesión."
            )
        finally:
            await browser.close()
            await self._pw.stop()

    async def _open(self):
        self._pw = await async_playwright().start()
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--start-maximized",
        ]
        if os.getenv("CHROMIUM_NO_SANDBOX") == "1":
            launch_args.append("--no-sandbox")
        browser = await self._pw.chromium.launch(
            headless=False,
            args=launch_args,
            ignore_default_args=["--enable-automation"],
        )
        # Fingerprint rotativo: persona (UA+plataforma) y viewport con jitter,
        # distintos en cada ejecución. Locale/timezone se mantienen fijos:
        # son la identidad estable de la cuenta.
        persona = random.choice(_PERSONAS)
        context = await browser.new_context(
            storage_state=config.STORAGE_STATE_PATH
            if os.path.exists(config.STORAGE_STATE_PATH)
            else None,
            user_agent=persona["user_agent"],
            viewport={
                "width": random.randint(*config.VIEWPORT_WIDTH_RANGE),
                "height": random.randint(*config.VIEWPORT_HEIGHT_RANGE),
            },
            locale="es-ES",
            timezone_id="America/Mexico_City",
        )
        if Stealth is not None:
            try:
                await Stealth().apply_stealth_async(context)
            except Exception:
                pass
        # Alinea las superficies JS que el contenedor/Linux deja incoherentes
        # con el UA elegido (en Docker navigator.platform diría Linux).
        init_script = """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'platform', {get: () => '__PLATFORM__'});
            try {
                const uad = navigator.userAgentData;
                if (uad) {
                    Object.defineProperty(uad, 'platform', {get: () => '__PLATFORM__'});
                    const origHighEntropy = uad.getHighEntropyValues.bind(uad);
                    uad.getHighEntropyValues = async (hints) => {
                        const values = await origHighEntropy(hints);
                        if ('platform' in values) values.platform = '__PLATFORM__';
                        if ('platformVersion' in values) values.platformVersion = '__PLATFORM_VERSION__';
                        return values;
                    };
                }
            } catch (error) {}
        """.replace("__PLATFORM_VERSION__", persona["platform_version"]).replace(
            "__PLATFORM__", persona["platform"]
        )
        await context.add_init_script(init_script)
        page = await context.new_page()
        return browser, context, page

    @staticmethod
    async def _is_logged_in(context):
        cookies = await context.cookies("https://www.linkedin.com")
        return any(cookie["name"] == "li_at" for cookie in cookies)

    @staticmethod
    async def _save_state(context):
        await context.storage_state(path=config.STORAGE_STATE_PATH)

    async def _extract_results(self, page):
        results = []
        cards = page.locator(selectors.RESULT_CARD)
        count = await cards.count()

        for index in range(count):
            card = cards.nth(index)
            name_link = card.locator(selectors.NAME_LINK).first
            try:
                name = (await name_link.inner_text(timeout=3000)).strip()
            except Exception:
                name = ""
            try:
                url = await name_link.get_attribute("href", timeout=3000)
                url = url.split("?")[0] if url else ""
            except Exception:
                url = ""
            try:
                role = (
                    await name_link.locator(selectors.HEADLINE)
                    .inner_text(timeout=3000)
                ).strip()
            except Exception:
                role = ""
            if not name and not url:
                continue
            if "linkedin.com/in/" not in url:
                url = ""
            results.append({"name": name, "role": role, "url": url})
        return results

    @staticmethod
    def _new_items(page_results, accumulated):
        keys = {
            row.get("url") or (row.get("name") + "|" + row.get("role"))
            for row in accumulated
        }
        return [
            row
            for row in page_results
            if (row.get("url") or (row.get("name") + "|" + row.get("role"))) not in keys
        ]

    async def _check_interruptions(self, page):
        current_url = page.url
        lowered = current_url.lower()
        if "captcha" in lowered or "challenge" in lowered:
            raise CaptchaError("LinkedIn mostró un CAPTCHA o challenge.")
        if any(mark in current_url for mark in selectors.AUTHWALL_URL_MARKS):
            raise AuthWallError("LinkedIn redirigió a una pared de autenticación.")
        if await page.locator(selectors.GUEST_WALL_MODAL).count() > 0:
            raise AuthWallError("LinkedIn muestra una ventana de inicio de sesión.")
        await self._check_restriction_text(page)

    @staticmethod
    async def _check_restriction_text(page):
        """Detecta mensajes de restricción de uso / límite alcanzado en el
        texto visible de la página y aborta el job (circuit breaker)."""
        try:
            text = await page.locator("body").inner_text(timeout=2500)
        except Exception:
            return
        sample = re.sub(r"\s+", " ", (text or "")[:8000])
        if not sample:
            return
        for pattern in selectors.RESTRICTION_TEXT_PATTERNS:
            if pattern.search(sample):
                raise RestrictionError(
                    "LinkedIn muestra un mensaje de restricción o límite alcanzado."
                )

    async def _scroll_gradually(self, page):
        delay_min = int(config.SCROLL_STEP_DELAY_MIN * 1000)
        delay_max = int(config.SCROLL_STEP_DELAY_MAX * 1000)
        await page.evaluate(
            """async ([step, delayMin, delayMax]) => {
                const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
                const rand = () => delayMin + Math.random() * (delayMax - delayMin);
                // LinkedIn (2026) mete el contenido en un contenedor interno
                // con scroll propio (#workspace); hacer scroll de la ventana
                // ya no carga nada. Se prefiere ese contenedor y, si no
                // existe, cualquier div alto con overflow; ultimo recurso,
                // la ventana.
                let el = document.getElementById('workspace');
                if (!el || !(el.scrollHeight > el.clientHeight + 50)) {
                    el = null;
                    for (const node of document.querySelectorAll('div,section,main')) {
                        if (node.scrollHeight > node.clientHeight + 100 && node.clientHeight > 300) {
                            el = node;
                            break;
                        }
                    }
                }
                const pos = () => (el ? el.scrollTop : window.scrollY);
                const bottom = () =>
                    el
                        ? el.scrollHeight - el.clientHeight
                        : document.body.scrollHeight - window.innerHeight;
                let stable = 0;
                for (let guard = 0; guard < 120 && stable < 3; guard++) {
                    if (el) el.scrollTop = pos() + step;
                    else window.scrollBy(0, step);
                    await sleep(rand());
                    if (pos() >= bottom() - 5) stable += 1;
                    else stable = 0;
                }
            }""",
            [config.SCROLL_STEP, delay_min, delay_max],
        )
        await self._human_delay(1, 2)

    async def _pace_page(self, elapsed_seconds):
        """Rellena el tiempo de la página hasta un objetivo de 1-3 min.

        El objetivo se sortea por página (uniforme entre PAGE_MIN_SECONDS y
        PAGE_MAX_SECONDS); si las actividades reales ya consumieron ese tiempo,
        no se espera nada extra. El resto se duerme en trozos aleatorios para
        que el ritmo no sea un bloque único predecible.
        """
        target = random.uniform(config.PAGE_MIN_SECONDS, config.PAGE_MAX_SECONDS)
        remaining = target - elapsed_seconds
        while remaining > 0:
            chunk = min(
                remaining,
                random.uniform(config.PAUSE_CHUNK_MIN, config.PAUSE_CHUNK_MAX),
            )
            await asyncio.sleep(chunk)
            remaining -= chunk

    async def _human_delay(self, lo=1.5, hi=3.5):
        await asyncio.sleep(random.uniform(lo, hi))