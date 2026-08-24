import asyncio
import json

import config
from scraper.linkedin import LinkedInScraper


async def main():
    s = LinkedInScraper()
    browser, context, page = await s._open()
    try:
        url = f"{config.LINKEDIN_SEARCH_URL}?keywords=Google&origin=GLOBAL_SEARCH_HEADER"
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        await page.get_by_role("button", name="All filters").first.click()
        await asyncio.sleep(5)

        info = await page.evaluate(
            """() => {
                const out = [];
                for (const el of document.querySelectorAll('button, input[type=submit], [role=button]')) {
                    const t = (el.innerText || el.value || '').trim();
                    if (/submit|show results|mostrar resultados|aplicar/i.test(t)) {
                        const r = el.getBoundingClientRect();
                        out.push({
                            tag: el.tagName,
                            tipo: el.getAttribute('type') || '',
                            texto: t.slice(0, 40),
                            aria: el.getAttribute('aria-label') || '',
                            disabled: el.disabled === true || el.getAttribute('aria-disabled') || '',
                            visible: r.width > 0 && r.height > 0,
                            rect: `${Math.round(r.x)},${Math.round(r.y)} ${Math.round(r.width)}x${Math.round(r.height)}`,
                            cls: (el.className || '').toString().slice(0, 60),
                        });
                    }
                }
                return out;
            }"""
        )
        print(json.dumps(info, ensure_ascii=False, indent=2))
        await page.keyboard.press("Escape")
        await asyncio.sleep(2)
    finally:
        await browser.close()
        await s._pw.stop()


asyncio.run(main())
