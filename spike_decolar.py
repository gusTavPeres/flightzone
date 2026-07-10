"""
Spike: testa se conseguimos renderizar resultados reais da Decolar
usando o Chrome instalado, passando (ou não) pelo antibot DataDome.
"""
import re
import sys
import traceback
from playwright.sync_api import sync_playwright

URL = "https://www.decolar.com/flights/GRU/GIG/2026-07-15/1"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",            # usa o Google Chrome do sistema
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = browser.new_context(
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            user_agent=UA,
            viewport={"width": 1366, "height": 900},
        )
        # esconde o sinal mais óbvio de automação
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = ctx.new_page()
        print(f"Abrindo: {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # espera o JS do site rodar / DataDome resolver
        page.wait_for_timeout(9000)

        html = page.content()
        title = page.title()
        final = page.url

        has_datadome = ("captcha-delivery" in html) or ("Please enable JS" in html) \
            or ("geo.captcha" in html)
        rs_hits = re.findall(r"R\$\s?\d[\d\.\,]*", html)

        print("---- RESULTADO ----")
        print("FINAL_URL  :", final)
        print("TITLE      :", title[:120])
        print("HTML_LEN   :", len(html))
        print("DATADOME?  :", has_datadome)
        print("PRECOS R$  :", len(rs_hits), "amostra:", rs_hits[:8])

        page.screenshot(path="/home/gustavo/flightzone/spike_decolar.png")
        with open("/home/gustavo/flightzone/spike_decolar.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Screenshot -> spike_decolar.png | HTML -> spike_decolar.html")
        browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
