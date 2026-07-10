"""
Monitor de PREÇO REAL via navegador — TODAS as rotas, continuamente.

Usa 1 Chrome persistente (sob xvfb = invisível), lê o "a partir de R$ X" de cada
rota, grava no banco e alerta quedas (Telegram). Ritmo configurável + backoff
automático se o Google começar a bloquear (busca vazia repetida -> desacelera).

Uso:
    ./.venv/bin/python realprice_monitor.py --routes-file routes.json --gap 16
"""
import argparse
import os
import random
import sys
import time
from datetime import datetime, timezone

from app import routes_store
from app.browser_scraper import new_browser, read_cheapest_on_page, looks_blocked, extract_top_details
from app.scrapers.google_flights import GoogleFlightsScraper
from app.normalizers.flight_normalizer import FlightNormalizer
from app.links import gflights_url
from app.notify import telegram_send, telegram_configured
from app.database.sqlite_client import SQLiteClient
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def money(v):
    return f"R$ {v:.0f}" if v is not None else "—"


def _fmt_det(d):
    if not d:
        return ""
    parts = []
    if d.get("airline"):
        parts.append(d["airline"])
    st = d.get("stops")
    if st is not None:
        parts.append("direto" if st == 0 else f"{st} parada(s)")
    du = d.get("duration")
    if du:
        parts.append(f"{du // 60}h{du % 60:02d}")
    if d.get("dep_time"):
        parts.append(f"saída {d['dep_time']}")
    return ("\n✈️ " + " · ".join(parts)) if parts else ""


def _ff_details(r):
    """Detalhes via fast-flights (fallback confiável quando o navegador não casa)."""
    try:
        raw = GoogleFlightsScraper().scrape(r.origin, r.dest, r.date, r.trip, r.rdate)
        fl = FlightNormalizer.normalize_items(raw)
        if fl:
            f = min(fl, key=lambda x: x["price"])
            return {"airline": f.get("airline"), "stops": f.get("stops"),
                    "duration": f.get("duration_minutes"), "dep_time": f.get("departure_time")}
    except Exception:
        pass
    return {}


class Route:
    def __init__(self, spec):
        o = spec.get("from") or spec.get("origin")
        d = spec.get("to") or spec.get("destination")
        self.origin, self.dest = str(o).upper(), str(d).upper()
        self.date = str(spec["date"])
        self.trip = spec.get("trip", "oneway")
        self.rdate = spec.get("return_date") or spec.get("return")
        self.threshold = spec.get("threshold")
        self.best = None
        self.next_due = 0.0
        self.error_alerted = False
        self.threshold_alerted = False
        self.iv = 0.0
        self.last_price = None

    @property
    def label(self):
        return f"{self.origin}->{self.dest} {self.date}" + (f"->{self.rdate}" if self.rdate else "")


def main():
    ap = argparse.ArgumentParser(description="Monitor de preço REAL (navegador), todas as rotas")
    ap.add_argument("--routes-file", required=True)
    ap.add_argument("--gap", type=float, default=16.0, help="segundos de pausa entre buscas")
    ap.add_argument("--jitter", type=float, default=0.3)
    ap.add_argument("--settle", type=float, default=6.0)
    ap.add_argument("--max-read", type=float, default=28.0)
    ap.add_argument("--max-checks", type=int, default=0, help="0 = roda pra sempre (teste usa >0)")
    ap.add_argument("--block-threshold", type=int, default=5,
                    help="buscas vazias seguidas p/ considerar bloqueio")
    ap.add_argument("--block-pause", type=float, default=45.0,
                    help="minutos de pausa ao detectar bloqueio")
    ap.add_argument("--sim-block", type=int, default=0, help="TESTE: força N buscas 'bloqueadas'")
    ap.add_argument("--browser-restart", type=int, default=150,
                    help="reinicia o navegador a cada N buscas (evita vazamento de memória)")
    ap.add_argument("--error-pct", type=float, default=0.30,
                    help="fração abaixo da média p/ alertar tarifa-erro (0.30 = 30%%)")
    ap.add_argument("--base-interval", type=float, default=16.0,
                    help="minutos-alvo entre buscas da MESMA rota")
    ap.add_argument("--max-interval", type=float, default=45.0,
                    help="intervalo máx. por rota quando o preço está estável (cache)")
    ap.add_argument("--night-factor", type=float, default=3.0,
                    help="multiplica o intervalo de madrugada (00-06h)")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        logger.error(f"playwright indisponível: {e}")
        sys.exit(1)

    db = SQLiteClient()
    mtime, routes = None, []
    backoff, gfails, checks, block_alerted = 1.0, 0, 0, False
    since_restart, last_req = 0, 0.0
    base_iv, max_iv = args.base_interval * 60, args.max_interval * 60

    with sync_playwright() as p:
        b, ctx = new_browser(p)
        pg = ctx.new_page()
        logger.info(f"monitor de PREÇO REAL iniciado (gap~{args.gap:.0f}s, 1 navegador)")
        if telegram_configured():
            telegram_send("🤖 Monitor de <b>preço real</b> iniciado no gustavopc.")
        try:
            while True:
                if since_restart >= args.browser_restart:      # watchdog anti-vazamento de memória
                    logger.info(f"watchdog: reiniciando o navegador ({since_restart} buscas)")
                    try:
                        b.close()
                    except Exception:
                        pass
                    b, ctx = new_browser(p)
                    pg = ctx.new_page()
                    since_restart = 0
                if os.path.exists(args.routes_file):           # hot-reload
                    m = os.path.getmtime(args.routes_file)
                    if m != mtime:
                        mtime = m
                        routes = [Route(s) for s in routes_store.load(args.routes_file)]
                        random.shuffle(routes)      # ordem aleatória (menos previsível)
                        for r in routes:
                            r.best = db.price_history_min(r.origin, r.dest, r.date, r.trip, r.rdate)
                            r.next_due = 0.0
                            r.iv = base_iv
                        logger.info(f"routes.json carregado: {len(routes)} rotas")
                if not routes:
                    time.sleep(10)
                    continue

                r = min(routes, key=lambda x: x.next_due)
                now = time.time()
                wake = max(r.next_due, last_req + args.gap * backoff * (1 + random.uniform(0, args.jitter)))
                if wake > now:                                 # cache: espera a rota ficar due (ocioso)
                    time.sleep(min(wake - now, 30))
                    continue
                url = gflights_url(r.origin, r.dest, r.date, r.trip, r.rdate)
                checked_at = datetime.now(timezone.utc).isoformat()
                sim = checks < args.sim_block                  # TESTE: força "bloqueio"
                try:
                    price = None if sim else read_cheapest_on_page(pg, url, args.settle, args.max_read)
                except Exception as e:
                    price = None
                    logger.warning(f"erro {r.label}: {e}")
                    if any(k in str(e).lower() for k in ("closed", "crashed", "disconnected", "target page")):
                        try:                                   # navegador caiu -> reinicia na hora
                            b.close()
                        except Exception:
                            pass
                        b, ctx = new_browser(p)
                        pg = ctx.new_page()
                        since_restart = 0
                        logger.warning("navegador caiu -> reiniciado automaticamente")
                blocked = sim or (price is None and looks_blocked(pg))
                last_req = time.time()

                if price is not None:
                    db.record_price_point(r.origin, r.dest, r.date, r.trip, price,
                                          "", 1, checked_at, return_date=r.rdate)
                    drop = (r.best - price) if (r.best is not None and price < r.best) else 0
                    if r.best is None or price < r.best:
                        r.best = price
                    avg, nreads = db.recent_stats(r.origin, r.dest, r.date, r.trip, r.rdate)
                    is_error = bool(avg and nreads >= 15 and price <= avg * (1 - args.error_pct))
                    det_str = ""
                    if drop > 0 or (is_error and not r.error_alerted):     # busca detalhes 1x
                        det_str = _fmt_det(extract_top_details(pg, price) or _ff_details(r))
                    below = r.threshold is not None and price <= r.threshold
                    if drop > 0:
                        hit = f"\n🎯 abaixo do alvo {money(r.threshold)}!" if below else ""
                        telegram_send(f"✈️ <b>{r.label}</b>\nCaiu para <b>{money(price)}</b> "
                                      f"(real) — economia {money(drop)}.{det_str}{hit}")
                    elif below and not r.threshold_alerted:
                        # cruzou o alvo sem ser mínima histórica nova (antes ficava mudo)
                        telegram_send(f"🎯 <b>{r.label}</b>\n<b>{money(price)}</b> — abaixo do "
                                      f"alvo {money(r.threshold)}.{det_str}")
                    r.threshold_alerted = below
                    if is_error and not r.error_alerted:
                        pct = 100 * (1 - price / avg)
                        telegram_send(f"🚨 <b>POSSÍVEL TARIFA-ERRO</b>\n{r.label}\n"
                                      f"<b>{money(price)}</b> — {pct:.0f}% abaixo da média "
                                      f"({money(avg)})!{det_str}")
                        r.error_alerted = True
                    elif not is_error:
                        r.error_alerted = False
                    logger.info(f"{r.label}: {money(price)}" + (f"  🔻 -{money(drop)}" if drop else "")
                                + ("  🚨ERRO?" if is_error else ""))
                    gfails = 0
                    block_alerted = False
                    backoff = max(1.0, backoff * 0.6)
                    night = args.night_factor if datetime.now().hour < 6 else 1.0
                    if r.last_price is not None and price == r.last_price:
                        r.iv = min(r.iv * 1.5, max_iv)          # estável -> raspa menos (cache)
                    else:
                        r.iv = base_iv
                    r.last_price = price
                    r.next_due = time.time() + r.iv * night * (1 + random.uniform(-args.jitter, args.jitter))
                else:
                    gfails += 1
                    if blocked or gfails >= args.block_threshold:
                        reason = ("captcha/bloqueio detectado" if (blocked and not sim)
                                  else f"{gfails} buscas vazias seguidas")
                        if not block_alerted:
                            telegram_send(f"⚠️ <b>FlightZone</b>: possível bloqueio do scraper "
                                          f"({reason}). Pausando ~{args.block_pause:.0f} min."
                                          + (" (TESTE)" if sim else ""))
                            block_alerted = True
                        logger.warning(f"possível bloqueio (sinal={blocked}, gfails={gfails}) "
                                       f"— pausando {args.block_pause:.0f}min")
                        time.sleep(args.block_pause * 60)
                        gfails = 0
                    else:
                        backoff = min(backoff * 2, 12)
                        logger.warning(f"{r.label}: sem preço ({gfails}) backoff x{backoff:.0f}")
                    r.next_due = time.time() + r.iv * (1 + random.uniform(0, args.jitter))

                checks += 1
                since_restart += 1
                if args.max_checks and checks >= args.max_checks:
                    logger.info(f"{checks} checagens concluídas (modo teste).")
                    break
        finally:
            b.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
