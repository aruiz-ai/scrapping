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
        print("URL con panel abierto:", page.url[:130])

        await elegir(page, re.compile(r"^add a location$", re.I), "input[placeholder*='ocation' i]", ["Mexico"])
        print("URL tras ubicacion:", page.url[:130])

        await elegir(
            page,
            re.compile(r"^add an industry$", re.I),
            "input[placeholder*='ndustry' i]",
            ["IT Services and IT Consulting", "Technology, Information and Internet"],
        )
        print("URL tras industrias:", page.url[:150])

        await elegir(page, re.compile(r"^add a company$", re.I), "input[placeholder*='ompany' i]", ["Google"])
        print("URL tras empresa:", page.url[:170])

        # Cerrar el panel y ver si los resultados ya estan filtrados
        await page.keyboard.press("Escape")
        await asyncio.sleep(6)
        print("\nURL final tras Escape:", page.url[:180])
        print("tarjetas de resultado:", await page.locator(selectors.RESULT_CARD).count())
    finally:
        await browser.close()
        await s._pw.stop()


asyncio.run(main())
