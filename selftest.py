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
    ok &= _ok("a partir de: prefere o de 'Menores preços'",
              _apartir("Bagagem a partir de R$ 65 ... Menores preços · a partir de R$ 957") == 957)
    return ok


def deal_tests():
    """Regra de aviso: só preço realmente bom vs. o histórico."""
    from realprice_monitor import good_deal
    g = lambda score, n, drop: good_deal(score, n, drop, 15, 0.85)
    ok = True
    ok &= _ok("histórico ok + percentil alto -> avisa", g(0.92, 40, 0))
    ok &= _ok("histórico ok + percentil médio -> cala", not g(0.60, 40, 0))
    ok &= _ok("histórico ok: mínima histórica sozinha não basta", not g(0.50, 40, 100))
    ok &= _ok("histórico curto -> volta p/ mínima histórica", g(1.0, 3, 100))
    ok &= _ok("histórico curto e sem queda -> cala", not g(1.0, 3, 0))
    ok &= _ok("rota nova (sem leituras) -> cala", not g(None, 0, 0))
    return ok


def notify_tests():
    """Alerta do Telegram tem que virar markdown no Discord — e calar se não configurado."""
    import os
    from app.notify import _md, discord_send
    ok = _ok("<b> vira ** no Discord",
             _md("✈️ <b>GYN->JPA</b>\n<b>R$ 802</b> — bom") == "✈️ **GYN->JPA**\n**R$ 802** — bom")
    if not os.getenv("DISCORD_WEBHOOK") and not os.path.exists("discord.json"):
        ok &= _ok("sem webhook -> no-op silencioso", discord_send("teste") is False)
    return ok


def db_tests():
    """Testa as queries do banco num SQLite temporário (offline)."""
    import tempfile
    from datetime import datetime, timedelta, timezone
    from app.database.sqlite_client import SQLiteClient
    ok = True
    with tempfile.TemporaryDirectory() as td:
        db = SQLiteClient(db_path=td + "/t.db")
        now = datetime.now(timezone.utc)
        # 3 leituras: 900, 800, depois SOBE p/ 850 (a atual)
        for i, p in enumerate((900, 800, 850)):
            db.record_price_point("GYN", "JPA", "2026-11-20", "oneway", p, "", 1,
                                  (now - timedelta(hours=3 - i)).isoformat())
        ok &= _ok("price_history_min = menor já visto",
                  db.price_history_min("GYN", "JPA", "2026-11-20", "oneway") == 800)
        rows = db.price_by_date("GYN", "JPA")
        ok &= _ok("price_by_date: atual é a ÚLTIMA leitura (não o mínimo)",
                  rows and rows[0]["price"] == 850 and rows[0]["min_price"] == 800)
        avg, n = db.recent_stats("GYN", "JPA", "2026-11-20", "oneway")
        ok &= _ok("recent_stats média/contagem", n == 3 and abs(avg - 850) < 0.01)
        frac, n = db.deal_score("GYN", "JPA", "2026-11-20", "oneway", 810)
        ok &= _ok("deal_score: 2 de 3 leituras mais caras que 810",
                  n == 3 and abs(frac - 2 / 3) < 0.01)
        # roundtrip não contamina oneway (e vice-versa)
        db.record_price_point("GYN", "JPA", "2026-11-20", "roundtrip", 1300, "", 1,
                              now.isoformat(), return_date="2026-11-29")
        ok &= _ok("oneway não vê preço do roundtrip",
                  db.price_history_min("GYN", "JPA", "2026-11-20", "oneway") == 800)
        ok &= _ok("roundtrip_matrix acha o combo",
                  db.roundtrip_matrix("GYN", "JPA")[0]["price"] == 1300)
        ok &= _ok("WAL ativo",
                  db._conn().execute("PRAGMA journal_mode").fetchone()[0] == "wal")
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
    print("=== banco ===")
    ok = db_tests() and ok
    print("=== regra de aviso ===")
    ok = deal_tests() and ok
    print("=== notificação ===")
    ok = notify_tests() and ok
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
