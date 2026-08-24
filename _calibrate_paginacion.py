import asyncio
import re

import config
from scraper import selectors
from scraper.linkedin import LinkedInScraper


async def elegir(page, add_regex, input_selector, valores):
    for valor in valores:
        add_btn = page.get_by_role("button", name=add_regex).first
        try:
            if await add_btn.count() > 0 and await add_btn.is_visible():
                await add_btn.click()
                await asyncio.sleep(3)
        except Exception:
            pass
        box = page.locator(input_selector).first
        await box.click()
        await asyncio.sleep(1)
        await box.fill(valor)
        await asyncio.sleep(4)
        ops = page.locator("[role=option]")
        n = await ops.count()
        for i in range(n):
            try:
                primera = (await ops.nth(i).inner_text()).strip().splitlines()[0].strip()
            except Exception:
                continue
            if primera.lower() == valor.lower():
                await ops.nth(i).click()
                await asyncio.sleep(4)
                return


async def main():
    s = LinkedInScraper()
    browser, context, page = await s._open()
    try:
        url = f"{config.LINKEDIN_SEARCH_URL}?keywords=Google&origin=GLOBAL_SEARCH_HEADER"
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        await page.get_by_role("button", name="All filters").first.click()
        await asyncio.sleep(5)
        await elegir(page, re.compile(r"^add a location$", re.I), "input[placeholder*='ocation' i]", ["Mexico"])
        await elegir(
            page,
            re.compile(r"^add an industry$", re.I),
            "input[placeholder*='ndustry' i]",
            ["IT Services and IT Consulting", "Technology, Information and Internet"],
        )
        await elegir(page, re.compile(r"^add a company$", re.I), "input[placeholder*='ompany' i]", ["Google"])
        await page.keyboard.press("Escape")
        await asyncio.sleep(6)

        # Extraer nombres de la pagina 1 filtrada
        rows = await s._extract_results(page, "Google")
        print(f"\npagina 1 filtrada: {len(rows)} filas")
        for r in rows[:5]:
            print("   ", r["name"][:30], "|", r["role"][:40])
        print("URL pagina 1:", page.url[:140])

        # Paginar DENTRO de la SPA: boton siguiente
        nxt = page.get_by_role("button", name=re.compile(r"^next$|^siguiente$", re.I)).first
        alt = page.locator("[aria-label*='ext'], [aria-label*='iguiente']").first
        print("\nboton Next por rol:", await nxt.count(), "| por aria:", await alt.count())
        target = nxt if await nxt.count() > 0 else alt
        await target.click()
        await asyncio.sleep(8)
        print("URL tras Next:", page.url[:160])
        rows2 = await s._extract_results(page, "Google")
        print(f"pagina 2 filtrada: {len(rows2)} filas")
        for r in rows2[:5]:
            print("   ", r["name"][:30], "|", r["role"][:40])
    finally:
        await browser.close()
        await s._pw.stop()


asyncio.run(main())
