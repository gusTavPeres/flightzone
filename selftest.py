"""
Auto-teste do FlightZone.
  - sem argumentos: testa os PARSERS (rápido, offline) — pega regressões.
  - com --live: canário — confere se o scraper ainda pega preço/detalhes de
    verdade; se falhar (Google mudou o layout), avisa no Telegram.

Uso:  ./.venv/bin/python selftest.py [--live]
"""
import sys

from app.browser_scraper import looks_blocked, _parse_flight_label, _apartir


class FakePg:
    def __init__(self, t):
        self.t = t

    def inner_text(self, _):
        return self.t


def _ok(name, cond):
    print(("  OK   " if cond else "  FALHOU  ") + name)
    return bool(cond)


def parser_tests():
    ok = True
    ok &= _ok("looks_blocked capta captcha", looks_blocked(FakePg("Please complete the reCAPTCHA")))
    ok &= _ok("looks_blocked capta DataDome", looks_blocked(FakePg("...não com um robô. Deslize para")))
    ok &= _ok("looks_blocked ignora normal", not looks_blocked(FakePg("Menores preços a partir de R$ 802")))
    d = _parse_flight_label("802 Reais brasileiros. Voo da Gol com 1 parada. Sai às 19:25. Duração 6 h 5 min")
    ok &= _ok("parse preço", d["price"] == 802)
    ok &= _ok("parse companhia", d["airline"] == "Gol")
    ok &= _ok("parse escalas", d["stops"] == 1)
    ok &= _ok("parse duração", d["duration"] == 365)
    ok &= _ok("parse a partir de", _apartir("Menores preços a partir de R$ 957 · voos") == 957)
    return ok


def live_test():
    from datetime import datetime, timedelta
    from playwright.sync_api import sync_playwright
    from app.browser_scraper import new_browser, read_cheapest_on_page, extract_top_details
    from app.links import gflights_url
    d = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
    url = gflights_url("GRU", "GIG", d, "oneway")
    with sync_playwright() as p:
        b, ctx = new_browser(p)
        pg = ctx.new_page()
        price = read_cheapest_on_page(pg, url)
        det = extract_top_details(pg, price) if price else {}
        b.close()
    print(f"  canário GRU→GIG {d}: preço={price} | detalhes={det}")
    return bool(price)


def main():
    print("=== parsers ===")
    ok = parser_tests()
    if "--live" in sys.argv:
        print("=== canário ao vivo ===")
        live_ok = live_test()
        ok = _ok("scraper ainda pega preço (canário)", live_ok) and ok
        if not live_ok:
            try:
                from app.notify import telegram_send
                telegram_send("🧪 <b>FlightZone selftest</b>: o canário FALHOU — o scraper não "
                              "pegou preço. O Google pode ter mudado o layout, verifique!")
            except Exception:
                pass
    print("=> TUDO OK ✅" if ok else "=> HÁ FALHAS ❌")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
